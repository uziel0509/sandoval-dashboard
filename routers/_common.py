"""
Shared admin router setup — all domain sub-routers import from here.
"""
import os
import uuid, json
from datetime import datetime, timedelta
from pathlib import Path

import bcrypt
import jwt as pyjwt
from fastapi import APIRouter, Request, HTTPException, UploadFile, File
from typing import List
from fastapi.responses import HTMLResponse
from sqlalchemy import text

router = APIRouter(prefix="/admin", tags=["admin"])

def _img_to_url(path: str) -> str:
    """Normaliza cualquier imagen_path almacenada a una URL web válida."""
    if not path:
        return path
    # Ya es URL web
    if path.startswith('/facturas/') or path.startswith('/evidencia/') or path.startswith('/static/'):
        return path
    # Quitar prefijo absoluto del VPS
    p = path.replace('/var/www/sandoval/', '').replace('/var/www/sandoval', '')
    # static/facturas/x.jpg → /facturas/x.jpg
    if p.startswith('static/facturas/'):
        return '/facturas/' + p[len('static/facturas/'):]
    # static/evidencia/temp/x.jpg → /evidencia/temp/x.jpg
    if p.startswith('static/evidencia/'):
        return '/evidencia/' + p[len('static/evidencia/'):]
    # facturas/x.jpg → /facturas/x.jpg
    if p.startswith('facturas/'):
        return '/' + p
    # evidencia/x.jpg → /evidencia/x.jpg
    if p.startswith('evidencia/'):
        return '/' + p
    # Fallback: usar basename bajo /facturas/
    return '/facturas/' + os.path.basename(p)



ADMIN_HTML = Path(__file__).parent / "static" / "admin" / "index.html"
TALLER_ID = 1  # taller por defecto hasta implementar multi-tenant en frontend

# ── Auth ─────────────────────────────────────────────────────────────────────
def _secret():
    key = os.environ.get("SECRET_KEY")
    if not key or len(key) < 32:
        raise RuntimeError(
            "SECRET_KEY no configurado o demasiado corto (<32 chars). "
            "Definir en /var/www/sandoval/.env antes de arrancar el servicio."
        )
    return key + "_admin_v2"

def _make_token(user: dict) -> str:
    tid = user.get("taller_id")
    if not isinstance(tid, int) or tid < 1:
        raise HTTPException(500, "taller_id del usuario no es válido")
    payload = {
        "sub": str(user["id"]),
        "nombre": user["nombre"],
        "rol": user["rol"],
        "taller_id": tid,
        "jti": uuid.uuid4().hex,
        "exp": datetime.utcnow() + timedelta(hours=10),
    }
    return pyjwt.encode(payload, _secret(), algorithm="HS256")


def _is_jwt_revoked(jti: str) -> bool:
    """Comprueba si jti esta en jwt_revoked."""
    if not jti:
        return False
    try:
        from sqlalchemy import text as _t
        from utils.models import get_db
        db = get_db()
        try:
            row = db.execute(_t("SELECT 1 FROM jwt_revoked WHERE jti=:j AND exp > NOW()"),
                             {"j": jti}).fetchone()
            return row is not None
        finally:
            db.close()
    except Exception:
        return False

def _auth(request: Request) -> dict:
    # 2026-04-29 audit P1-EtA: dual-auth (cookie HttpOnly OR Authorization header)
    from utils.auth_cookies import get_token_from_request, COOKIE_ADMIN_NAME
    token = get_token_from_request(request, cookie_name=COOKIE_ADMIN_NAME)
    if not token:
        raise HTTPException(401, "Token requerido")
    try:
        data = pyjwt.decode(token, _secret(), algorithms=["HS256"])
        # 2026-04-30 sec-audit: bloquear temp_token de 2FA pending (defensa en profundidad)
        if data.get("typ") == "2fa_pending":
            raise HTTPException(401, "Token incompleto: completar 2FA")
        if _is_jwt_revoked(data.get("jti", "")):
            try:
                from utils.security_events import track_revoked_token_use as _trrt
                _trrt(data.get("jti", ""), request.client.host if request.client else "")
            except Exception: pass
            raise HTTPException(401, "Token revocado")
        return data
    except pyjwt.ExpiredSignatureError:
        raise HTTPException(401, "Sesión expirada")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(401, "Token inválido")

def _db():
    import sys; sys.path.insert(0, "/var/www/sandoval")
    from utils.models import get_db
    db = get_db()
    try:
        yield db
    finally:
        db.close()

def _get_db():
    import sys; sys.path.insert(0, "/var/www/sandoval")
    from utils.models import get_db
    return get_db()

def _safe_date(v):
    """Convierte fecha a string seguro sea datetime, date o str."""
    if v is None: return None
    if isinstance(v, str): return v[:19]
    try: return v.strftime("%Y-%m-%d %H:%M")
    except Exception: return str(v)[:19]

def _parse_json_field(v):
    if v is None: return []
    if isinstance(v, (list, dict)): return v
    try: return json.loads(v)
    except Exception: return []

def _require_admin(tok: dict):
    if tok.get("rol") not in ("admin",):
        raise HTTPException(403, "Solo administradores")


def _require_staff(tok: dict):
    """Permite admin, recepcionista, tecnico. Rechaza cliente y cualquier otro rol."""
    if tok.get("rol") not in ("admin", "recepcionista", "tecnico"):
        raise HTTPException(403, "Acceso restringido a personal del taller")




def _client_ip(request: "Request") -> str:
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        return xff.split(",")[0].strip()[:45]
    return (request.client.host if request.client else "unknown")[:45]


def _check_login_rate_limit(db, ip: str, max_fails: int = 5, window_minutes: int = 15):
    """Raise 429 if IP has max_fails+ failed /api/login attempts in window."""
    db.execute(text(
        "DELETE FROM rate_limit_log WHERE ts < NOW() - INTERVAL \'24 hours\'"
    ))
    fails = db.execute(text(
        "SELECT COUNT(*) FROM rate_limit_log "
        "WHERE ip=:ip AND endpoint=\'/api/login\' AND ok=FALSE "
        "AND ts > NOW() - (:mins * INTERVAL \'1 minute\')"
    ), {"ip": ip, "mins": window_minutes}).fetchone()[0] or 0
    if fails >= max_fails:
        raise HTTPException(429, f"Demasiados intentos. Espera {window_minutes} minutos.")


def _log_login_attempt(db, ip: str, username: str, ok: bool):
    try:
        db.execute(text(
            "INSERT INTO rate_limit_log (ip, endpoint, username, ok) "
            "VALUES (:ip, \'/api/login\', :u, :ok)"
        ), {"ip": ip, "u": username[:100], "ok": ok})
        db.commit()
    except Exception:
        pass


# ── Multi-tenant helpers ─────────────────────────────────────────────────────
def _tenant_id(tok: dict | None = None) -> int:
    """Resuelve el taller del request leyendo del JWT.

    Retorna el taller_id del token, o lanza 401 si el token no es válido.
    No hay fallback silencioso — si un endpoint llega sin taller en el JWT,
    es bug de autenticación y debe fallar explícitamente para evitar cruce
    de datos entre talleres.
    """
    if isinstance(tok, dict):
        tid = tok.get("taller_id")
        if isinstance(tid, int) and tid > 0:
            return tid
    raise HTTPException(401, "Sesión sin taller válido — reautenticar")


def tenant_sql(sql: str, params: dict | None = None, tok: dict | None = None):
    """Prepara (stmt, params) con :taller_id inyectado.

    Uso:
        stmt, p = tenant_sql("SELECT * FROM clientes WHERE taller_id=:taller_id", tok=tok)
        rows = db.execute(stmt, p).fetchall()

    Si la query no contiene la palabra 'taller_id', lanza AssertionError — así
    el desarrollador no puede olvidarse del filtro multi-tenant.
    """
    assert "taller_id" in sql, "tenant_sql: la consulta debe referenciar taller_id explícitamente"
    merged = dict(params or {})
    merged.setdefault("taller_id", _tenant_id(tok))
    return text(sql), merged


def tenant_filter(query, model, tok: dict | None = None):
    """Aplica .filter(Model.taller_id == <taller>) a una Query ORM.

    Uso:
        q = tenant_filter(db.query(Cliente), Cliente, tok=tok)
        rows = q.order_by(Cliente.nombre).all()
    """
    if not hasattr(model, "taller_id"):
        raise AssertionError(
            f"tenant_filter: el modelo {getattr(model, '__name__', model)} no tiene columna taller_id"
        )
    return query.filter(model.taller_id == _tenant_id(tok))


# Re-export private helpers so domain modules can import them with 'from routers._common import *'
__all__ = [
    # FastAPI router
    'router', 'TALLER_ID', 'ADMIN_HTML',
    # Helpers
    '_auth', '_get_db', '_db', '_require_admin', '_require_staff', '_safe_date',
    '_client_ip', '_check_login_rate_limit', '_log_login_attempt',
    '_img_to_url', '_parse_json_field', '_make_token', '_secret', '_is_jwt_revoked',
    '_tenant_id', 'tenant_sql', 'tenant_filter',
    # stdlib
    'os', 'json', 'datetime', 'timedelta', 'Path',
    # FastAPI
    'APIRouter', 'Request', 'HTTPException', 'UploadFile', 'File', 'List', 'HTMLResponse',
    # SQLAlchemy
    'text',
    # Auth libs
    'bcrypt',
]

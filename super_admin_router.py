"""
Super Admin Router — Sandoval SaaS
Portal exclusivo para Sandoval (la empresa) para gestionar todos los talleres.
URL: /superadmin
"""
import os, json, uuid
from utils.password_policy import validate_password_strength
from datetime import datetime, timedelta
from typing import Optional
from pathlib import Path

import bcrypt
import jwt as pyjwt
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import text


# SECRET_KEY estricto (sin fallback) - 2026-04-29 audit fix V1
SECRET_KEY = os.environ.get("SECRET_KEY", "")
if not SECRET_KEY or len(SECRET_KEY) < 32:
    raise RuntimeError(
        "SECRET_KEY ausente o demasiado corto (<32 chars). "
        "Definir en /var/www/sandoval/.env antes de arrancar el servicio."
    )

router = APIRouter(prefix="/superadmin", tags=["superadmin"])

# ── Configuración ────────────────────────────────────────────────────────────
def _get_secret():
    # 2026-05-04 P1-A3: namespace propio "_sa_v2" (antes "_superadmin_2026"
    # se mantiene compat para tokens viejos via fallback).
    base = SECRET_KEY  # ya validado al import
    return base + "_sa_v2"

def _get_secret_legacy():
    """Compat: tokens emitidos antes del 2026-05-04 usaban este namespace."""
    return SECRET_KEY + "_superadmin_2026"

# 2026-05-04 P1-A3 HARDENING:
#   - Sesiones cortas: 30 min (antes 4h, mucho riesgo si el token se filtra).
#   - jti UUID + revocación en logout via tabla jwt_revoked.
#   - Rate limit 3 fails / 15 min (más estricto que admin normal: 5/15).
#   - Hash compatible con verify_password (Argon2id+rehash automático).
SA_TOKEN_EXP_MINUTES = 30
SA_IMPERSONATE_EXP_MINUTES = 15
SA_RATE_LIMIT_MAX_FAILS = 3
SA_RATE_LIMIT_WINDOW_MIN = 15
SA_HTML_PATH = Path(__file__).parent / "static" / "super_admin.html"

# ── DB ───────────────────────────────────────────────────────────────────────
def _db():
    """Generador de sesión DB — mismo patrón que el resto de la app."""
    import sys
    sys.path.insert(0, '/var/www/sandoval')
    from utils.models import get_db
    db = get_db()
    try:
        yield db
    finally:
        db.close()

# ── Auth helpers ─────────────────────────────────────────────────────────────
# 2026-05-04 P1-A3 HARDENING:
#   - jti UUID en cada token (revocable individual)
#   - Sesiones cortas (30 min vs 4h previo)
#   - verify_password centralizado (Argon2id + rehash compat)
#   - Revocación check via tabla jwt_revoked (compartida con admin)
def _create_sa_token(user_id: int, email: str, *, exp_minutes: int = SA_TOKEN_EXP_MINUTES,
                     extra: dict = None) -> str:
    """Genera JWT super-admin con jti UUID + exp corto.
    extra: dict opcional (e.g. {'impersonate_taller': N} para impersonación)."""
    payload = {
        "sub":   str(user_id),
        "email": email,
        "rol":   "super_admin",
        "jti":   uuid.uuid4().hex,
        "iat":   int(datetime.utcnow().timestamp()),
        "exp":   datetime.utcnow() + timedelta(minutes=exp_minutes),
    }
    if extra:
        payload.update(extra)
    return pyjwt.encode(payload, _get_secret(), algorithm="HS256")


def _is_jti_revoked(db, jti: str) -> bool:
    """Verifica si el jti está en la blacklist (logout / revocación manual).
    Schema real (verificado VPS): jwt_revoked(jti, exp, revoked_at, user_id, reason)."""
    if not jti:
        return False
    try:
        row = db.execute(
            text("SELECT 1 FROM jwt_revoked WHERE jti = :j AND exp > NOW() LIMIT 1"),
            {"j": jti}
        ).fetchone()
        return bool(row)
    except Exception:
        return False  # tabla aún no existe: fail-open compat


SA_COOKIE_NAME = "sandoval_sa_token"


def _verify_sa_token(request: Request) -> dict:
    """2026-05-05 P1-1: dual-auth (cookie HttpOnly OR Bearer header).

    Lee el token en cascada:
      1. Cookie HttpOnly `sandoval_sa_token` (post-migración localStorage→cookie).
      2. Header `Authorization: Bearer ...` (compat legacy).
    """
    token = None
    # Intento 1: Cookie HttpOnly
    try:
        token = request.cookies.get(SA_COOKIE_NAME)
    except Exception:
        token = None
    # Intento 2: Authorization Bearer (legacy)
    if not token:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
    if not token:
        raise HTTPException(status_code=401, detail="Token requerido")
    # Intento 1: secret nuevo (_sa_v2). Intento 2: legacy (_superadmin_2026).
    data = None
    for _sec in (_get_secret(), _get_secret_legacy()):
        try:
            data = pyjwt.decode(token, _sec, algorithms=["HS256"])
            break
        except pyjwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Sesión expirada")
        except pyjwt.InvalidTokenError:
            continue
    if not data:
        raise HTTPException(status_code=401, detail="Token inválido")
    if data.get("rol") != "super_admin":
        raise HTTPException(status_code=403, detail="Acceso denegado")
    # 2026-05-04 P1-A3: chequear revocación
    jti = data.get("jti")
    if jti:
        db_gen = _db()
        db_chk = next(db_gen)
        try:
            if _is_jti_revoked(db_chk, jti):
                raise HTTPException(status_code=401, detail="Sesión revocada")
        finally:
            try: next(db_gen)
            except StopIteration: pass
    return data


def _require_sa(request: Request) -> dict:
    return _verify_sa_token(request)


def _sa_check_rate_limit(db, ip: str):
    """Bloquea si ip excedió SA_RATE_LIMIT_MAX_FAILS fails en SA_RATE_LIMIT_WINDOW_MIN.
    Schema real (verificado VPS): rate_limit_log(ip, endpoint, username, ok, ts)."""
    try:
        row = db.execute(text("""
            SELECT COUNT(*) FROM rate_limit_log
             WHERE ip = :ip AND endpoint = :ep
               AND ts > NOW() - (:w || ' minutes')::interval
               AND ok = FALSE
        """), {"ip": ip, "ep": "/superadmin/api/login",
               "w": str(SA_RATE_LIMIT_WINDOW_MIN)}).fetchone()
        if row and row[0] >= SA_RATE_LIMIT_MAX_FAILS:
            raise HTTPException(status_code=429,
                detail=f"Demasiados intentos fallidos. Espera {SA_RATE_LIMIT_WINDOW_MIN} min.")
    except HTTPException:
        raise
    except Exception:
        pass  # si la tabla no existe aún, no bloqueamos


def _sa_log_rate_attempt(db, ip: str, success: bool, email: str = None):
    """Registra intento de login en rate_limit_log."""
    try:
        db.execute(text("""
            INSERT INTO rate_limit_log (ip, endpoint, username, ok, ts)
            VALUES (:ip, :ep, :u, :ok, NOW())
        """), {"ip": ip, "ep": "/superadmin/api/login",
               "u": (email or "")[:100], "ok": success})
        db.commit()
    except Exception:
        try: db.rollback()
        except Exception: pass


def _log_event(db, tipo: str, severidad: str, descripcion: str,
               ip: str = None, taller_id: int = None, endpoint: str = None):
    """Registra un evento de seguridad."""
    try:
        db.execute(text("""
            INSERT INTO eventos_seguridad
                (taller_id, tipo, severidad, ip, endpoint, descripcion)
            VALUES (:tid, :tipo, :sev, :ip, :ep, :desc)
        """), {
            'tid': taller_id, 'tipo': tipo, 'sev': severidad,
            'ip': ip, 'ep': endpoint, 'desc': descripcion
        })
        db.commit()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass


# ── Servir HTML ───────────────────────────────────────────────────────────────
@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def super_admin_ui():
    """Sirve el SPA del Super Admin."""
    if SA_HTML_PATH.exists():
        return HTMLResponse(SA_HTML_PATH.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>super_admin.html no encontrado</h1>", status_code=500)


# ── Auth ──────────────────────────────────────────────────────────────────────
@router.post("/api/login")
async def sa_login(request: Request):
    """2026-05-04 P1-A3 HARDENING:
        - Rate limit 3 fails / 15 min ANTES de revisar credenciales
        - verify_password centralizado (Argon2id+bcrypt+PBKDF2 compat)
        - Rehash automático a Argon2id en cada login exitoso (legacy → moderno)
        - Token corto (30 min) con jti UUID revocable
        - Rate log en cada intento (success o fail)"""
    body = await request.json()
    email = body.get("email", "").strip().lower()
    password = body.get("password", "")
    ip = request.client.host if request.client else "unknown"

    db_gen = _db()
    db = next(db_gen)
    try:
        # 1) Rate limit ANTES de tocar la DB de usuarios
        _sa_check_rate_limit(db, ip)

        row = db.execute(
            text("SELECT id, nombre, password_hash, activo FROM super_admin_users WHERE email = :e"),
            {"e": email}
        ).fetchone()

        if not row or not row[3]:
            _sa_log_rate_attempt(db, ip, success=False)
            _log_event(db, "LOGIN_FALLIDO", "WARN",
                       f"Login fallido super admin: {email}", ip=ip, endpoint="/superadmin/api/login")
            raise HTTPException(status_code=401, detail="Credenciales incorrectas")

        # 2) verify_password centralizado (Argon2id+bcrypt+PBKDF2 compat)
        try:
            from utils.models import verify_password as _vp, _new_needs_rehash, _new_hash_pwd
            ok = _vp(password, row[2])
        except Exception:
            # Fallback bcrypt directo (compat extrema)
            try:
                ok = bcrypt.checkpw(password.encode(), row[2].encode())
            except Exception:
                ok = False
        if not ok:
            _sa_log_rate_attempt(db, ip, success=False)
            _log_event(db, "LOGIN_FALLIDO", "WARN",
                       f"Contraseña incorrecta super admin: {email}", ip=ip, endpoint="/superadmin/api/login")
            raise HTTPException(status_code=401, detail="Credenciales incorrectas")

        # 3) Rehash a Argon2id si el hash actual es legacy
        try:
            if _new_needs_rehash(row[2]):
                new_h = _new_hash_pwd(password)
                db.execute(text("UPDATE super_admin_users SET password_hash=:h WHERE id=:id"),
                           {"h": new_h, "id": row[0]})
        except Exception:
            pass

        db.execute(
            text("UPDATE super_admin_users SET ultimo_acceso = NOW() WHERE id = :id"),
            {"id": row[0]}
        )
        db.commit()
        _sa_log_rate_attempt(db, ip, success=True)
        _log_event(db, "LOGIN_EXITOSO", "INFO",
                   f"Login super admin: {email}", ip=ip, endpoint="/superadmin/api/login")

        token = _create_sa_token(row[0], email)
        # 2026-05-05 P1-1: setear cookie HttpOnly + Secure + SameSite=Lax.
        # El frontend deja de almacenar el token en localStorage.
        from starlette.responses import JSONResponse as _JR
        _resp = _JR({"token": token, "nombre": row[1], "email": email,
                     "exp_minutes": SA_TOKEN_EXP_MINUTES})
        _resp.set_cookie(
            key=SA_COOKIE_NAME,
            value=token,
            max_age=SA_TOKEN_EXP_MINUTES * 60,
            httponly=True,
            secure=True,
            samesite="lax",
            path="/superadmin",
        )
        return _resp
    finally:
        try:
            next(db_gen)
        except StopIteration:
            pass


# ── Hidratación sesión (HttpOnly migration) ─────────────────────────────────
@router.get("/api/me")
async def sa_me(request: Request):
    """2026-05-05 P1-1: endpoint de hidratación post-migración localStorage.
    Frontend lo llama al cargar para validar la cookie HttpOnly y obtener el
    user dict (la cookie es HttpOnly, JS no la puede leer)."""
    sa_user = _require_sa(request)
    return {"email": sa_user.get("email"),
            "nombre": sa_user.get("nombre", sa_user.get("email")),
            "rol": "super_admin"}


# ── Logout (revocación jti) ──────────────────────────────────────────────────
@router.post("/api/logout")
async def sa_logout(request: Request):
    """2026-05-04 P1-A3: revoca el jti del token actual hasta su exp natural.
    2026-05-05 P1-1: lee también cookie HttpOnly sandoval_sa_token y la limpia."""
    token = None
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        token = auth[7:]
    if not token:
        try: token = request.cookies.get(SA_COOKIE_NAME)
        except Exception: token = None
    if not token:
        # Idempotente: nada que revocar pero igual borramos cookie por si quedó residual
        from starlette.responses import JSONResponse as _JR_e
        _r = _JR_e({"ok": True})
        _r.delete_cookie(key=SA_COOKIE_NAME, path="/superadmin")
        return _r
    payload = None
    for _sec in (_get_secret(), _get_secret_legacy()):
        try:
            payload = pyjwt.decode(token, _sec, algorithms=["HS256"], options={"verify_exp": False})
            break
        except Exception:
            continue
    if not payload or not payload.get("jti"):
        from starlette.responses import JSONResponse as _JR_n
        _r = _JR_n({"ok": True})
        _r.delete_cookie(key=SA_COOKIE_NAME, path="/superadmin")
        return _r
    db_gen = _db()
    db = next(db_gen)
    try:
        exp_ts = payload.get("exp", int(datetime.utcnow().timestamp()) + 3600)
        db.execute(text("""
            INSERT INTO jwt_revoked (jti, exp, revoked_at, user_id, reason)
            VALUES (:j, to_timestamp(:e), NOW(), :uid, 'logout_sa')
            ON CONFLICT (jti) DO NOTHING
        """), {"j": payload["jti"], "e": exp_ts,
               "uid": int(payload.get("sub")) if str(payload.get("sub","")).isdigit() else None})
        db.commit()
        _log_event(db, "LOGOUT_SA", "INFO",
                   f"Logout super admin (jti={payload['jti'][:8]}...)",
                   ip=(request.client.host if request.client else "unknown"),
                   endpoint="/superadmin/api/logout")
    except Exception:
        try: db.rollback()
        except Exception: pass
    finally:
        try: next(db_gen)
        except StopIteration: pass
    # 2026-05-05 P1-1: limpiar cookie HttpOnly tras logout exitoso
    from starlette.responses import JSONResponse as _JR_ok
    _r_ok = _JR_ok({"ok": True})
    _r_ok.delete_cookie(key=SA_COOKIE_NAME, path="/superadmin")
    return _r_ok


# ── Dashboard ─────────────────────────────────────────────────────────────────
@router.get("/api/dashboard")
async def sa_dashboard(request: Request):
    _require_sa(request)
    db_gen = _db()
    db = next(db_gen)
    try:
        # KPIs de talleres
        t = db.execute(text("""
            SELECT
                COUNT(*) FILTER (WHERE estado = 'activo') as activos,
                COUNT(*) FILTER (WHERE estado = 'suspendido') as suspendidos,
                COUNT(*) FILTER (WHERE estado = 'prueba') as prueba,
                COUNT(*) FILTER (WHERE estado = 'cancelado') as cancelados,
                COUNT(*) as total,
                COALESCE(SUM(precio_mensual) FILTER (WHERE estado='activo'), 0) as mrr,
                COUNT(*) FILTER (
                    WHERE fecha_registro >= date_trunc('month', NOW())
                    AND estado != 'cancelado'
                ) as nuevos_mes
            FROM talleres
        """)).fetchone()

        # Órdenes globales
        o = db.execute(text("""
            SELECT
                COUNT(*) FILTER (WHERE (CASE WHEN fecha ~ '^[0-9]{2}/' THEN TO_DATE(fecha,'DD/MM/YYYY') ELSE fecha::date END) = CURRENT_DATE) as hoy,
                COUNT(*) FILTER (
                    WHERE (CASE WHEN fecha ~ '^[0-9]{2}/' THEN TO_DATE(fecha,'DD/MM/YYYY') ELSE fecha::date END) >= date_trunc('month', NOW())::date
                ) as mes,
                COUNT(*) FILTER (WHERE estado != 'ARCHIVADO') as activas
            FROM ordenes
        """)).fetchone()

        # Cobros del mes
        cobros = db.execute(text("""
            SELECT
                COALESCE(SUM(monto) FILTER (WHERE estado='PAGADO'), 0) as cobrado,
                COALESCE(SUM(monto), 0) as total_esperado
            FROM talleres_pagos
            WHERE periodo = TO_CHAR(NOW(), 'YYYY-MM')
        """)).fetchone()

        # Alertas recientes (últimas 10 CRITICAL/WARN)
        alertas_rows = db.execute(text("""
            SELECT es.id, es.tipo, es.severidad, es.descripcion,
                   es.ip, t.nombre as taller_nombre, es.fecha, es.resuelto
            FROM eventos_seguridad es
            LEFT JOIN talleres t ON t.id = es.taller_id
            WHERE es.severidad IN ('CRITICAL','WARN')
            ORDER BY es.fecha DESC
            LIMIT 10
        """)).fetchall()

        alertas = [{
            'id': r[0], 'tipo': r[1], 'severidad': r[2],
            'descripcion': r[3], 'ip': r[4], 'taller': r[5],
            'fecha': str(r[6])[:16] if r[6] else '',
            'resuelto': r[7]
        } for r in alertas_rows]

        # Talleres más activos hoy
        activos_rows = db.execute(text("""
            SELECT t.id, t.nombre, COUNT(o.consecutivo) as ordenes_hoy
            FROM talleres t
            LEFT JOIN ordenes o ON o.taller_id = t.id
                AND (CASE WHEN o.fecha ~ '^[0-9]{2}/' THEN TO_DATE(o.fecha,'DD/MM/YYYY') ELSE o.fecha::date END) = CURRENT_DATE
            WHERE t.estado = 'activo'
            GROUP BY t.id, t.nombre
            ORDER BY ordenes_hoy DESC
            LIMIT 5
        """)).fetchall()

        top_talleres = [{'id': r[0], 'nombre': r[1], 'ordenes_hoy': r[2]}
                        for r in activos_rows]

        # MRR histórico últimos 6 meses
        mrr_hist = db.execute(text("""
            SELECT TO_CHAR(fecha_registro, 'YYYY-MM') as mes,
                   COALESCE(SUM(monto) FILTER (WHERE estado='PAGADO'), 0) as cobrado
            FROM talleres_pagos
            WHERE fecha_registro >= NOW() - INTERVAL '6 months'
            GROUP BY mes
            ORDER BY mes
        """)).fetchall()

        # Distribución por plan
        planes = db.execute(text("""
            SELECT COALESCE(plan,'basico') as plan, COUNT(*) as cantidad
            FROM talleres
            WHERE estado = 'activo'
            GROUP BY plan
        """)).fetchall()

        return {
            'talleres': {
                'activos': t[0] or 0, 'suspendidos': t[1] or 0,
                'prueba': t[2] or 0, 'cancelados': t[3] or 0,
                'total': t[4] or 0, 'nuevos_mes': t[6] or 0,
            },
            'mrr': float(t[5] or 0),
            'ordenes': {'hoy': o[0] or 0, 'mes': o[1] or 0, 'activas': o[2] or 0},
            'cobros': {
                'cobrado': float(cobros[0] or 0),
                'esperado': float(cobros[1] or 0),
            },
            'alertas': alertas,
            'top_talleres': top_talleres,
            'mrr_historico': [{'mes': r[0], 'cobrado': float(r[1])} for r in mrr_hist],
            'planes': [{'plan': r[0], 'cantidad': r[1]} for r in planes],
        }
    finally:
        try:
            next(db_gen)
        except StopIteration:
            pass


# ── Talleres ──────────────────────────────────────────────────────────────────
@router.get("/api/talleres")
async def sa_list_talleres(request: Request, estado: str = None, plan: str = None, q: str = None):
    _require_sa(request)
    db_gen = _db()
    db = next(db_gen)
    try:
        filters = []
        params = {}
        if estado:
            filters.append("t.estado = :estado")
            params['estado'] = estado
        if plan:
            filters.append("t.plan = :plan")
            params['plan'] = plan
        if q:
            filters.append("(t.nombre ILIKE :q OR t.email ILIKE :q OR t.ruc ILIKE :q)")
            params['q'] = f'%{q}%'

        where = ("WHERE " + " AND ".join(filters)) if filters else ""

        rows = db.execute(text(f"""
            SELECT
                t.id, t.nombre, COALESCE(t.plan,'basico') as plan,
                COALESCE(t.estado,'activo') as estado,
                t.email, t.telefono, t.ruc, t.subdominio,
                t.precio_mensual, t.super_admin_notes,
                t.fecha_registro,
                (SELECT COUNT(*) FROM ordenes WHERE taller_id = t.id) as ordenes_total,
                (SELECT COUNT(*) FROM usuarios WHERE taller_id = t.id AND activo = TRUE) as usuarios,
                (SELECT MAX(fecha) FROM ordenes WHERE taller_id = t.id) as ultima_actividad
            FROM talleres t
            {where}
            ORDER BY t.id
        """), params).fetchall()

        return [
            {
                'id': r[0], 'nombre': r[1], 'plan': r[2], 'estado': r[3],
                'email': r[4], 'telefono': r[5], 'ruc': r[6], 'subdominio': r[7],
                'precio_mensual': float(r[8] or 0), 'notas': r[9],
                'fecha_registro': str(r[10])[:10] if r[10] else '',
                'ordenes_total': r[11], 'usuarios': r[12],
                'ultima_actividad': str(r[13])[:16] if r[13] else 'Sin actividad',
            }
            for r in rows
        ]
    finally:
        try:
            next(db_gen)
        except StopIteration:
            pass


@router.get("/api/talleres/{taller_id}")
async def sa_taller_detail(taller_id: int, request: Request):
    _require_sa(request)
    db_gen = _db()
    db = next(db_gen)
    try:
        t = db.execute(text("""
            SELECT id, nombre, plan, estado, email, telefono, ruc, subdominio,
                   precio_mensual, super_admin_notes, fecha_registro, fecha_suspension
            FROM talleres WHERE id = :id
        """), {'id': taller_id}).fetchone()
        if not t:
            raise HTTPException(status_code=404, detail="Taller no encontrado")

        stats = db.execute(text("""
            SELECT
                (SELECT COUNT(*) FROM ordenes WHERE taller_id = :tid) as ordenes_total,
                (SELECT COUNT(*) FROM ordenes WHERE taller_id = :tid
                    AND (CASE WHEN fecha ~ '^[0-9]{2}/' THEN TO_DATE(fecha,'DD/MM/YYYY') ELSE fecha::date END) >= date_trunc('month', NOW())::date) as ordenes_mes,
                (SELECT COUNT(*) FROM clientes WHERE taller_id = :tid) as clientes,
                (SELECT COUNT(*) FROM inventario WHERE taller_id = :tid) as inventario,
                (SELECT COUNT(*) FROM usuarios WHERE taller_id = :tid AND activo=TRUE) as usuarios
        """), {'tid': taller_id}).fetchone()

        pagos = db.execute(text("""
            SELECT id, monto, plan, periodo, estado, fecha_pago, metodo_pago, notas, fecha_registro
            FROM talleres_pagos WHERE taller_id = :tid
            ORDER BY fecha_registro DESC LIMIT 24
        """), {'tid': taller_id}).fetchall()

        eventos = db.execute(text("""
            SELECT id, tipo, severidad, descripcion, ip, fecha, resuelto
            FROM eventos_seguridad
            WHERE taller_id = :tid
            ORDER BY fecha DESC LIMIT 20
        """), {'tid': taller_id}).fetchall()

        return {
            'taller': {
                'id': t[0], 'nombre': t[1], 'plan': t[2] or 'basico',
                'estado': t[3] or 'activo', 'email': t[4], 'telefono': t[5],
                'ruc': t[6], 'subdominio': t[7],
                'precio_mensual': float(t[8] or 0), 'notas': t[9],
                'fecha_registro': (str(t[10])[:10] if isinstance(t[10], str) else t[10].strftime('%Y-%m-%d')) if t[10] else '',
                'fecha_suspension': (str(t[11])[:10] if isinstance(t[11], str) else t[11].strftime('%Y-%m-%d')) if t[11] else None,
            },
            'stats': {
                'ordenes_total': stats[0], 'ordenes_mes': stats[1],
                'clientes': stats[2], 'inventario': stats[3], 'usuarios': stats[4],
            },
            'pagos': [{
                'id': p[0], 'monto': float(p[1]), 'plan': p[2], 'periodo': p[3],
                'estado': p[4],
                'fecha_pago': (str(p[5])[:10] if isinstance(p[5], str) else p[5].strftime('%Y-%m-%d')) if p[5] else None,
                'metodo_pago': p[6], 'notas': p[7],
                'fecha_registro': (str(p[8])[:10] if isinstance(p[8], str) else p[8].strftime('%Y-%m-%d')) if p[8] else '',
            } for p in pagos],
            'eventos': [{
                'id': e[0], 'tipo': e[1], 'severidad': e[2],
                'descripcion': e[3], 'ip': e[4],
                'fecha': (str(e[5])[:16] if isinstance(e[5], str) else e[5].strftime('%Y-%m-%d %H:%M')) if e[5] else '',
                'resuelto': e[6],
            } for e in eventos],
        }
    finally:
        try:
            next(db_gen)
        except StopIteration:
            pass


@router.post("/api/talleres")
async def sa_create_taller(request: Request):
    sa_user = _require_sa(request)
    body = await request.json()
    nombre = body.get('nombre', '').strip()
    email = body.get('email', '').strip().lower()
    password = body.get('password', '').strip()
    plan = body.get('plan', 'basico')
    precio = float(body.get('precio_mensual', 0))
    telefono = body.get('telefono', '')
    ruc = body.get('ruc', '')
    subdominio = body.get('subdominio', '')
    notas = body.get('notas', '')

    if not nombre or not email or not password:
        raise HTTPException(status_code=400, detail="nombre, email y password son obligatorios")

    db_gen = _db()
    db = next(db_gen)
    try:
        # Verificar email único
        existe = db.execute(
            text("SELECT id FROM usuarios WHERE email = :e"), {'e': email}
        ).fetchone()
        if existe:
            raise HTTPException(status_code=400, detail="Ya existe un usuario con este email")

        # Crear taller
        res = db.execute(text("""
            INSERT INTO talleres (nombre, plan, estado, email, telefono, ruc,
                                  subdominio, precio_mensual, super_admin_notes, fecha_registro)
            VALUES (:n, :p, 'activo', :e, :tel, :ruc, :sub, :precio, :notas, NOW())
            RETURNING id
        """), {
            'n': nombre, 'p': plan, 'e': email, 'tel': telefono,
            'ruc': ruc, 'sub': subdominio, 'precio': precio, 'notas': notas
        })
        db.commit()
        taller_id = res.fetchone()[0]

        # Crear usuario admin del taller
        _ok, _why = validate_password_strength(password, role='admin')
        if not _ok:
            raise HTTPException(status_code=400, detail=f"Contraseña debil: {_why}")
        pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        db.execute(text("""
            INSERT INTO usuarios (taller_id, nombre, email, password_hash, rol, activo)
            VALUES (:tid, :n, :e, :h, 'admin', TRUE)
        """), {'tid': taller_id, 'n': nombre, 'e': email, 'h': pw_hash})

        # Config sistema por defecto
        for clave, valor in [
            ('nombre_taller', nombre), ('igv_porcentaje', '18'),
            ('moneda', 'S/'), ('timezone', 'America/Lima')
        ]:
            try:
                db.execute(text("""
                    INSERT INTO config_sistema (taller_id, clave, valor)
                    VALUES (:tid, :c, :v)
                    ON CONFLICT (taller_id, clave) DO NOTHING
                """), {'tid': taller_id, 'c': clave, 'v': valor})
            except Exception:
                pass

        db.commit()

        _log_event(db, 'ACCION_CRITICA', 'INFO',
                   f"Super admin {sa_user['email']} creó taller '{nombre}' (id={taller_id})")

        return {
            'success': True,
            'taller_id': taller_id,
            'mensaje': f"Taller '{nombre}' creado. Admin: {email}"
        }
    finally:
        try:
            next(db_gen)
        except StopIteration:
            pass


@router.put("/api/talleres/{taller_id}")
async def sa_update_taller(taller_id: int, request: Request):
    sa_user = _require_sa(request)
    body = await request.json()
    db_gen = _db()
    db = next(db_gen)
    try:
        fields = []
        params = {'id': taller_id}
        for campo in ['nombre', 'plan', 'email', 'telefono', 'ruc',
                      'subdominio', 'super_admin_notes']:
            if campo in body:
                fields.append(f"{campo} = :{campo}")
                params[campo] = body[campo]
        if 'precio_mensual' in body:
            fields.append("precio_mensual = :precio_mensual")
            params['precio_mensual'] = float(body['precio_mensual'])

        if not fields:
            return {'success': True, 'mensaje': 'Sin cambios'}

        db.execute(text(f"UPDATE talleres SET {', '.join(fields)} WHERE id = :id"), params)
        db.commit()
        _log_event(db, 'ACCION_CRITICA', 'INFO',
                   f"Super admin {sa_user['email']} editó taller id={taller_id}")
        return {'success': True}
    finally:
        try:
            next(db_gen)
        except StopIteration:
            pass


@router.post("/api/talleres/{taller_id}/suspender")
async def sa_suspender(taller_id: int, request: Request):
    sa_user = _require_sa(request)
    body = await request.json()
    motivo = body.get('motivo', 'Sin motivo especificado')
    db_gen = _db()
    db = next(db_gen)
    try:
        db.execute(text("""
            UPDATE talleres SET estado='suspendido', fecha_suspension=NOW(),
            super_admin_notes = COALESCE(super_admin_notes,'') || '\n[SUSPENDIDO ' ||
            TO_CHAR(NOW(),'YYYY-MM-DD') || '] ' || :motivo
            WHERE id = :id
        """), {'id': taller_id, 'motivo': motivo})
        db.commit()
        _log_event(db, 'ACCION_CRITICA', 'WARN',
                   f"SA {sa_user['email']} suspendió taller {taller_id}. Motivo: {motivo}",
                   taller_id=taller_id)
        return {'success': True}
    finally:
        try:
            next(db_gen)
        except StopIteration:
            pass


@router.post("/api/talleres/{taller_id}/activar")
async def sa_activar(taller_id: int, request: Request):
    sa_user = _require_sa(request)
    db_gen = _db()
    db = next(db_gen)
    try:
        db.execute(text("""
            UPDATE talleres SET estado='activo', fecha_suspension=NULL WHERE id = :id
        """), {'id': taller_id})
        db.commit()
        _log_event(db, 'ACCION_CRITICA', 'INFO',
                   f"SA {sa_user['email']} activó taller {taller_id}", taller_id=taller_id)
        return {'success': True}
    finally:
        try:
            next(db_gen)
        except StopIteration:
            pass


@router.get("/api/talleres/{taller_id}/impersonar")
async def sa_impersonar(taller_id: int, request: Request):
    """Genera un JWT temporal de admin para ese taller (soporte)."""
    sa_user = _require_sa(request)
    db_gen = _db()
    db = next(db_gen)
    try:
        admin_row = db.execute(text("""
            SELECT id, email, nombre FROM usuarios
            WHERE taller_id = :tid AND rol = 'admin' AND activo = TRUE
            ORDER BY id LIMIT 1
        """), {'tid': taller_id}).fetchone()

        if not admin_row:
            raise HTTPException(status_code=404, detail="No hay admin activo en este taller")

        taller_row = db.execute(
            text("SELECT nombre FROM talleres WHERE id = :id"), {'id': taller_id}
        ).fetchone()

        # 2026-05-04 SECURITY-REVIEWER FIX: token de impersonación con jti
        # revocable + namespace _admin_v2 (mismo que admin SPA, así verifica
        # con _auth() del flujo normal) + TTL reducido a SA_IMPERSONATE_EXP_MINUTES
        # (15 min vs 2h previo). El jti permite revocar en logout SA o
        # manualmente vía tabla jwt_revoked.
        secret = SECRET_KEY + "_admin_v2"
        payload = {
            'sub': str(admin_row[0]),
            'taller_id': taller_id,
            'rol': 'admin',
            'email': admin_row[1],
            'nombre': admin_row[2],
            'impersonado_por': sa_user['email'],
            'jti': uuid.uuid4().hex,
            'iat': int(datetime.utcnow().timestamp()),
            'exp': datetime.utcnow() + timedelta(minutes=SA_IMPERSONATE_EXP_MINUTES),
        }
        token = pyjwt.encode(payload, secret, algorithm='HS256')

        _log_event(db, 'ACCION_CRITICA', 'INFO',
                   f"SA {sa_user['email']} impersonó taller {taller_id} ({taller_row[0] if taller_row else ''})",
                   taller_id=taller_id)

        # 2026-05-05 P0-4/P2-3 FIX: setear cookie HttpOnly en lugar de
        # forzar token en URL del nuevo tab (sa_impersonate=...). El JWT
        # ya no aparece en logs nginx/Referer/historial.
        from utils.auth_cookies import set_token_cookie, COOKIE_ADMIN_NAME
        from starlette.responses import JSONResponse as _JR_imp
        _resp = _JR_imp({
            'token': token,  # mantenido para compat con clientes legacy
            'taller_nombre': taller_row[0] if taller_row else f'Taller #{taller_id}',
            'admin_email': admin_row[1],
            'admin_nombre': admin_row[2],
            'expira_en': f'{SA_IMPERSONATE_EXP_MINUTES} minutos',
        })
        set_token_cookie(_resp, token, cookie_name=COOKIE_ADMIN_NAME)
        return _resp
    finally:
        try:
            next(db_gen)
        except StopIteration:
            pass


# ── Seguridad ─────────────────────────────────────────────────────────────────
@router.get("/api/seguridad/eventos")
async def sa_eventos(request: Request, tipo: str = None, severidad: str = None,
                     taller_id: int = None, limit: int = 100):
    _require_sa(request)
    db_gen = _db()
    db = next(db_gen)
    try:
        filters, params = [], {}
        if tipo:
            filters.append("es.tipo = :tipo")
            params['tipo'] = tipo
        if severidad:
            filters.append("es.severidad = :sev")
            params['sev'] = severidad
        if taller_id:
            filters.append("es.taller_id = :tid")
            params['tid'] = taller_id
        where = ("WHERE " + " AND ".join(filters)) if filters else ""
        params['limit'] = min(limit, 500)

        rows = db.execute(text(f"""
            SELECT es.id, es.tipo, es.severidad, es.descripcion,
                   es.ip, es.endpoint, t.nombre, es.fecha, es.resuelto, es.bloqueado
            FROM eventos_seguridad es
            LEFT JOIN talleres t ON t.id = es.taller_id
            {where}
            ORDER BY es.fecha DESC
            LIMIT :limit
        """), params).fetchall()

        return [{
            'id': r[0], 'tipo': r[1], 'severidad': r[2], 'descripcion': r[3],
            'ip': r[4], 'endpoint': r[5], 'taller': r[6],
            'fecha': str(r[7])[:16] if r[7] else '',
            'resuelto': r[8], 'bloqueado': r[9],
        } for r in rows]
    finally:
        try:
            next(db_gen)
        except StopIteration:
            pass


@router.get("/api/seguridad/ips_bloqueadas")
async def sa_ips_bloqueadas(request: Request):
    _require_sa(request)
    db_gen = _db()
    db = next(db_gen)
    try:
        rows = db.execute(text("""
            SELECT id, ip, motivo, bloqueada_hasta, bloqueada_por, fecha_registro
            FROM ips_bloqueadas
            ORDER BY fecha_registro DESC
        """)).fetchall()
        return [{
            'id': r[0], 'ip': r[1], 'motivo': r[2],
            'bloqueada_hasta': str(r[3])[:16] if r[3] else 'Permanente',
            'bloqueada_por': r[4],
            'fecha_registro': str(r[5])[:16] if r[5] else '',
        } for r in rows]
    finally:
        try:
            next(db_gen)
        except StopIteration:
            pass


@router.post("/api/seguridad/bloquear_ip")
async def sa_bloquear_ip(request: Request):
    sa_user = _require_sa(request)
    body = await request.json()
    ip = body.get('ip', '').strip()
    motivo = body.get('motivo', 'Bloqueado por Super Admin')
    permanente = body.get('permanente', False)

    if not ip:
        raise HTTPException(status_code=400, detail="IP requerida")

    db_gen = _db()
    db = next(db_gen)
    try:
        hasta = None if permanente else (datetime.utcnow() + timedelta(days=7))
        db.execute(text("""
            INSERT INTO ips_bloqueadas (ip, motivo, bloqueada_hasta, bloqueada_por)
            VALUES (:ip, :m, :hasta, :por)
            ON CONFLICT (ip) DO UPDATE
            SET motivo=:m, bloqueada_hasta=:hasta, bloqueada_por=:por,
                fecha_registro=NOW()
        """), {'ip': ip, 'm': motivo, 'hasta': hasta, 'por': sa_user['email']})
        db.commit()
        _log_event(db, 'IP_BLOQUEADA', 'WARN',
                   f"SA {sa_user['email']} bloqueó IP {ip}: {motivo}", ip=ip)
        return {'success': True}
    finally:
        try:
            next(db_gen)
        except StopIteration:
            pass


@router.delete("/api/seguridad/ips_bloqueadas/{ip_id}")
async def sa_desbloquear_ip(ip_id: int, request: Request):
    sa_user = _require_sa(request)
    db_gen = _db()
    db = next(db_gen)
    try:
        row = db.execute(
            text("SELECT ip FROM ips_bloqueadas WHERE id = :id"), {'id': ip_id}
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="IP no encontrada")
        db.execute(text("DELETE FROM ips_bloqueadas WHERE id = :id"), {'id': ip_id})
        db.commit()
        _log_event(db, 'ACCION_CRITICA', 'INFO',
                   f"SA {sa_user['email']} desbloqueó IP {row[0]}", ip=row[0])
        return {'success': True}
    finally:
        try:
            next(db_gen)
        except StopIteration:
            pass


@router.post("/api/seguridad/eventos/{evento_id}/resolver")
async def sa_resolver_evento(evento_id: int, request: Request):
    _require_sa(request)
    db_gen = _db()
    db = next(db_gen)
    try:
        db.execute(text("UPDATE eventos_seguridad SET resuelto=TRUE WHERE id=:id"), {'id': evento_id})
        db.commit()
        return {'success': True}
    finally:
        try:
            next(db_gen)
        except StopIteration:
            pass


# ── Facturación ───────────────────────────────────────────────────────────────
@router.get("/api/facturacion")
async def sa_facturacion(request: Request, periodo: str = None):
    _require_sa(request)
    db_gen = _db()
    db = next(db_gen)
    try:
        periodo_actual = periodo or datetime.now().strftime('%Y-%m')

        # Resumen del período
        resumen = db.execute(text("""
            SELECT
                COUNT(*) FILTER (WHERE estado='PAGADO') as pagados,
                COUNT(*) FILTER (WHERE estado='PENDIENTE') as pendientes,
                COUNT(*) FILTER (WHERE estado='VENCIDO') as vencidos,
                COALESCE(SUM(monto) FILTER (WHERE estado='PAGADO'), 0) as total_cobrado,
                COALESCE(SUM(monto), 0) as total_esperado,
                COUNT(*) as total
            FROM talleres_pagos
            WHERE periodo = :p
        """), {'p': periodo_actual}).fetchone()

        # Pagos del período con detalle de taller
        pagos_rows = db.execute(text("""
            SELECT tp.id, tp.taller_id, t.nombre, tp.monto, tp.plan,
                   tp.estado, tp.fecha_pago, tp.metodo_pago, tp.notas, tp.fecha_registro
            FROM talleres_pagos tp
            JOIN talleres t ON t.id = tp.taller_id
            WHERE tp.periodo = :p
            ORDER BY tp.estado, t.nombre
        """), {'p': periodo_actual}).fetchall()

        # MRR histórico
        hist = db.execute(text("""
            SELECT periodo,
                   COALESCE(SUM(monto) FILTER (WHERE estado='PAGADO'), 0) as cobrado,
                   COALESCE(SUM(monto), 0) as esperado
            FROM talleres_pagos
            GROUP BY periodo
            ORDER BY periodo DESC
            LIMIT 12
        """)).fetchall()

        return {
            'periodo': periodo_actual,
            'resumen': {
                'pagados': resumen[0], 'pendientes': resumen[1], 'vencidos': resumen[2],
                'total_cobrado': float(resumen[3]), 'total_esperado': float(resumen[4]),
                'total': resumen[5],
                'tasa_cobro': round(float(resumen[3]) / float(resumen[4]) * 100, 1)
                if resumen[4] else 0,
            },
            'pagos': [{
                'id': p[0], 'taller_id': p[1], 'taller_nombre': p[2],
                'monto': float(p[3]), 'plan': p[4], 'estado': p[5],
                'fecha_pago': (str(p[6])[:10] if isinstance(p[6], str) else p[6].strftime('%Y-%m-%d')) if p[6] else None,
                'metodo_pago': p[7], 'notas': p[8],
                'fecha_registro': (str(p[9])[:10] if isinstance(p[9], str) else p[9].strftime('%Y-%m-%d')) if p[9] else '',
            } for p in pagos_rows],
            'historico': [{
                'periodo': h[0], 'cobrado': float(h[1]), 'esperado': float(h[2])
            } for h in hist],
        }
    finally:
        try:
            next(db_gen)
        except StopIteration:
            pass


@router.post("/api/facturacion/generar_cobros")
async def sa_generar_cobros(request: Request):
    """Genera registros PENDIENTE para todos los talleres activos del mes actual."""
    sa_user = _require_sa(request)
    db_gen = _db()
    db = next(db_gen)
    try:
        periodo = datetime.now().strftime('%Y-%m')
        talleres = db.execute(text("""
            SELECT id, nombre, plan, precio_mensual
            FROM talleres WHERE estado='activo' AND precio_mensual > 0
        """)).fetchall()

        creados = 0
        for t in talleres:
            existe = db.execute(text("""
                SELECT id FROM talleres_pagos
                WHERE taller_id=:tid AND periodo=:p
            """), {'tid': t[0], 'p': periodo}).fetchone()
            if not existe:
                db.execute(text("""
                    INSERT INTO talleres_pagos (taller_id, monto, plan, periodo, estado)
                    VALUES (:tid, :m, :p, :per, 'PENDIENTE')
                """), {'tid': t[0], 'm': t[3], 'p': t[2], 'per': periodo})
                creados += 1

        db.commit()
        _log_event(db, 'ACCION_CRITICA', 'INFO',
                   f"SA {sa_user['email']} generó {creados} cobros para {periodo}")
        return {'success': True, 'creados': creados, 'periodo': periodo}
    finally:
        try:
            next(db_gen)
        except StopIteration:
            pass


@router.put("/api/facturacion/pagos/{pago_id}")
async def sa_update_pago(pago_id: int, request: Request):
    _require_sa(request)
    body = await request.json()
    db_gen = _db()
    db = next(db_gen)
    try:
        fields, params = [], {'id': pago_id}
        if 'estado' in body:
            fields.append("estado=:estado")
            params['estado'] = body['estado']
            if body['estado'] == 'PAGADO':
                fields.append("fecha_pago=NOW()")
        if 'metodo_pago' in body:
            fields.append("metodo_pago=:metodo")
            params['metodo'] = body['metodo_pago']
        if 'notas' in body:
            fields.append("notas=:notas")
            params['notas'] = body['notas']
        if fields:
            db.execute(text(f"UPDATE talleres_pagos SET {', '.join(fields)} WHERE id=:id"), params)
            db.commit()
        return {'success': True}
    finally:
        try:
            next(db_gen)
        except StopIteration:
            pass


# ── Actividad global ──────────────────────────────────────────────────────────
@router.get("/api/actividad")
async def sa_actividad(request: Request, taller_id: int = None, limit: int = 100):
    _require_sa(request)
    db_gen = _db()
    db = next(db_gen)
    try:
        params = {'limit': min(limit, 500)}
        where = "WHERE a.taller_id = :tid" if taller_id else ""
        if taller_id:
            params['tid'] = taller_id

        rows = db.execute(text(f"""
            SELECT a.id, a.accion, a.modulo, a.fecha,
                   a.usuario_id, t.nombre as taller_nombre,
                   a.taller_id
            FROM actividades a
            LEFT JOIN talleres t ON t.id = a.taller_id
            {where}
            ORDER BY a.fecha DESC
            LIMIT :limit
        """), params).fetchall()

        return [{
            'id': r[0], 'accion': r[1], 'modulo': r[2],
            'fecha': str(r[3])[:16] if r[3] else '',
            'usuario_id': r[4], 'taller': r[5], 'taller_id': r[6],
        } for r in rows]
    finally:
        try:
            next(db_gen)
        except StopIteration:
            pass


# ── Métricas ──────────────────────────────────────────────────────────────────
@router.get("/api/metricas")
async def sa_metricas(request: Request):
    _require_sa(request)
    db_gen = _db()
    db = next(db_gen)
    try:
        # Uso por taller (últimos 30 días)
        uso = db.execute(text("""
            SELECT t.id, t.nombre, t.plan,
                   COUNT(o.consecutivo) as ordenes_30d,
                   COUNT(DISTINCT u.id) as usuarios_activos
            FROM talleres t
            LEFT JOIN ordenes o ON o.taller_id = t.id
                AND (CASE WHEN o.fecha ~ '^[0-9]{2}/' THEN TO_DATE(o.fecha,'DD/MM/YYYY') ELSE o.fecha::date END) >= (NOW() - INTERVAL '30 days')::date
            LEFT JOIN usuarios u ON u.taller_id = t.id AND u.activo=TRUE
            WHERE t.estado = 'activo'
            GROUP BY t.id, t.nombre, t.plan
            ORDER BY ordenes_30d DESC
        """)).fetchall()

        # Órdenes por día últimas 2 semanas (todos los talleres)
        daily = db.execute(text("""
            SELECT DATE(fecha) as dia, COUNT(*) as ordenes
            FROM ordenes
            WHERE fecha >= NOW() - INTERVAL '14 days'
            GROUP BY dia
            ORDER BY dia
        """)).fetchall()

        # Total usuarios en la plataforma
        tot_users = db.execute(text(
            "SELECT COUNT(*) FROM usuarios WHERE activo=TRUE"
        )).fetchone()[0]

        # Total clientes en la plataforma
        tot_clientes = db.execute(text(
            "SELECT COUNT(*) FROM clientes"
        )).fetchone()[0]

        return {
            'uso_por_taller': [{
                'id': r[0], 'nombre': r[1], 'plan': r[2],
                'ordenes_30d': r[3], 'usuarios_activos': r[4],
            } for r in uso],
            'ordenes_diarias': [{
                'dia': str(r[0]), 'ordenes': r[1]
            } for r in daily],
            'totales': {
                'usuarios_plataforma': tot_users,
                'clientes_plataforma': tot_clientes,
            }
        }
    finally:
        try:
            next(db_gen)
        except StopIteration:
            pass


# ── Configuración ─────────────────────────────────────────────────────────────
@router.get("/api/config")
async def sa_get_config(request: Request):
    sa_user = _require_sa(request)
    db_gen = _db()
    db = next(db_gen)
    try:
        users = db.execute(text("""
            SELECT id, nombre, email, activo, ultimo_acceso, fecha_registro
            FROM super_admin_users ORDER BY id
        """)).fetchall()
        return {
            'usuarios': [{
                'id': u[0], 'nombre': u[1], 'email': u[2], 'activo': u[3],
                'ultimo_acceso': (str(u[4])[:16] if isinstance(u[4], str) else u[4].strftime('%Y-%m-%d %H:%M')) if u[4] else 'Nunca',
                'fecha_registro': (str(u[5])[:10] if isinstance(u[5], str) else u[5].strftime('%Y-%m-%d')) if u[5] else '',
            } for u in users]
        }
    finally:
        try:
            next(db_gen)
        except StopIteration:
            pass


@router.post("/api/config/cambiar_password")
async def sa_cambiar_password(request: Request):
    sa_user = _require_sa(request)
    body = await request.json()
    password_actual = body.get('password_actual', '')
    password_nuevo = body.get('password_nuevo', '')

    if len(password_nuevo) < 8:
        raise HTTPException(status_code=400, detail="La nueva contraseña debe tener al menos 8 caracteres")

    db_gen = _db()
    db = next(db_gen)
    try:
        row = db.execute(
            text("SELECT password_hash FROM super_admin_users WHERE email=:e"),
            {'e': sa_user['email']}
        ).fetchone()
        # 2026-05-04 SECURITY-REVIEWER #3 FIX: usar verify_password centralizado
        # (compat Argon2id+bcrypt+PBKDF2) en lugar de bcrypt directo. Esto:
        #   1. Mantiene compat con hashes bcrypt existentes
        #   2. Permite que un usuario con hash bcrypt viejo siga validando
        #   3. Genera el hash NUEVO en Argon2id (más resistente a GPU)
        try:
            from utils.models import verify_password as _vp, hash_password as _new_hash_pwd
        except Exception:
            _vp = None
            _new_hash_pwd = None
        if not row:
            raise HTTPException(status_code=401, detail="Contraseña actual incorrecta")
        try:
            ok = _vp(password_actual, row[0]) if _vp else bcrypt.checkpw(password_actual.encode(), row[0].encode())
        except Exception:
            ok = False
        if not ok:
            raise HTTPException(status_code=401, detail="Contraseña actual incorrecta")

        _ok, _why = validate_password_strength(password_nuevo, role='admin')
        if not _ok:
            raise HTTPException(status_code=400, detail=f"Contraseña debil: {_why}")
        # Hash nuevo SIEMPRE en Argon2id (centralizado)
        if _new_hash_pwd:
            nuevo_hash = _new_hash_pwd(password_nuevo)
        else:
            nuevo_hash = bcrypt.hashpw(password_nuevo.encode(), bcrypt.gensalt()).decode()
        db.execute(
            text("UPDATE super_admin_users SET password_hash=:h WHERE email=:e"),
            {'h': nuevo_hash, 'e': sa_user['email']}
        )
        db.commit()
        return {'success': True, 'mensaje': 'Contraseña cambiada exitosamente'}
    finally:
        try:
            next(db_gen)
        except StopIteration:
            pass

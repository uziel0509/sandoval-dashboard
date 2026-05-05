"""utils.api.common — helpers compartidos por TODOS los dominios."""
from __future__ import annotations
import os as _os
import sqlite3 as _sqlite3
import json as _json
import secrets
import hashlib
from datetime import datetime, timedelta
from typing import Optional
from starlette.requests import Request
from starlette.responses import JSONResponse

TOKEN_TTL_MINUTES = 60 * 8
_SESSIONS_DB = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))), 'data', 'sessions.db')


# === IMPORTS_LEGACY ===
import secrets
import hashlib
import hmac
import os
import json
import sqlite3
import threading as _threading
from collections import defaultdict as _defaultdict
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from starlette.requests import Request
from starlette.responses import JSONResponse, FileResponse, RedirectResponse
from sqlalchemy import text, text as _sa_text
from utils.models import (
    get_db, Usuario, Cliente, Vehiculo, ItemInventario,
    Orden, Cita, NotaVenta, Proveedor, log_actividad,
    verify_password, hash_password,
)
from utils.security_events import track_login_failure as _track_login_fail
from utils.auth_cookies import (
    get_token_from_request, set_token_cookie, clear_token_cookie,
    COOKIE_CLIENT_NAME, COOKIE_ADMIN_NAME,
)
from utils.upload_validator import validate_upload_bytes, safe_extension
# === FIN IMPORTS_LEGACY ===

def _get_sessions_db():
    conn = _sqlite3.connect(_SESSIONS_DB)
    conn.execute('''CREATE TABLE IF NOT EXISTS sessions (
        token TEXT PRIMARY KEY,
        user_json TEXT NOT NULL,
        expires TEXT NOT NULL
    )''')
    conn.commit()
    return conn


def _new_token(user_dict: dict) -> str:
    token = secrets.token_hex(32)
    expires = (datetime.now() + timedelta(minutes=TOKEN_TTL_MINUTES)).isoformat()
    conn = _get_sessions_db()
    try:
        conn.execute('INSERT OR REPLACE INTO sessions (token, user_json, expires) VALUES (?,?,?)',
                     (token, _json.dumps(user_dict), expires))
        conn.commit()
    finally:
        conn.close()
    return token


def _get_user_from_token(token: str) -> Optional[dict]:
    # 1) Intentar como sesión SQLite (PWA / portal cliente)
    conn = _get_sessions_db()
    try:
        row = conn.execute('SELECT user_json, expires FROM sessions WHERE token=?', (token,)).fetchone()
        if row:
            if datetime.now() > datetime.fromisoformat(row[1]):
                conn.execute('DELETE FROM sessions WHERE token=?', (token,))
                conn.commit()
                return None
            new_exp = (datetime.now() + timedelta(minutes=TOKEN_TTL_MINUTES)).isoformat()
            conn.execute('UPDATE sessions SET expires=? WHERE token=?', (new_exp, token))
            conn.commit()
            return _json.loads(row[0])
    finally:
        conn.close()
    # 2) Intentar como JWT del admin SPA (routers/_common.py)
    try:
        from routers._common import _secret
        import jwt as _pyjwt
        payload = _pyjwt.decode(token, _secret(), algorithms=['HS256'])
        # El JWT del admin SPA usa 'sub' o 'id' para el usuario; normalizamos.
        if 'id' not in payload and 'sub' in payload:
            payload['id'] = payload['sub']
        if 'rol' not in payload:
            payload['rol'] = 'admin'
        return payload
    except Exception:
        return None


def _extract_token(request: Request) -> Optional[str]:
    """2026-04-29 P1-EtA: dual-auth. Lee token desde:
    1) Cookie HttpOnly sandoval_token (admin)
    2) Cookie HttpOnly sandoval_client_token (cliente/conductor)
    3) Cookie sandoval_api_token (legacy, compat)
    4) Header Authorization: Bearer (legacy localStorage)
    """
    # Header Authorization (legacy)
    auth = request.headers.get('Authorization', '') or request.headers.get('authorization', '')
    if auth.startswith('Bearer '):
        return auth[7:]
    # Cookies (preferido post-migracion)
    return (request.cookies.get('sandoval_token') or
            request.cookies.get('sandoval_client_token') or
            request.cookies.get('sandoval_api_token'))


def _require_auth(request: Request) -> dict | JSONResponse:
    token = _extract_token(request)
    if not token:
        return JSONResponse({'error': 'No autorizado'}, status_code=401)
    user = _get_user_from_token(token)
    if not user:
        return JSONResponse({'error': 'Token inválido o expirado'}, status_code=401)
    return user


def _require_admin(request: Request) -> dict | JSONResponse:
    result = _require_auth(request)
    if isinstance(result, JSONResponse):
        return result
    if result.get('rol') not in ('admin', 'recepcionista', 'tecnico'):
        return JSONResponse({'error': 'Acceso denegado'}, status_code=403)
    return result


def _require_staff(request: Request) -> dict | JSONResponse:
    """Alias semantico de _require_admin (acepta admin/recepcionista/tecnico).

    El nombre _require_admin es legacy y engañoso: en realidad valida que
    el usuario sea staff (cualquier rol con acceso al portal). Para forzar
    admin estricto, usar _require_admin_strict.
    """
    return _require_admin(request)


def _require_admin_strict(request: Request) -> dict | JSONResponse:
    """Solo permite rol='admin' duro (no recepcionista, no tecnico).

    2026-04-29 audit V6: nuevo helper para endpoints donde la verificacion
    laxa de _require_admin no era apropiada (ej. crear/eliminar usuarios,
    cambiar configuracion sensible).
    """
    user = _require_auth(request)
    if isinstance(user, JSONResponse):
        return user
    if user.get("rol") != "admin":
        return JSONResponse(
            {"error": "Solo administradores pueden acceder a este recurso"},
            status_code=403
        )
    return user


# 2026-05-04 P1-A4 FIX: Eliminado _cors() manual con Access-Control-Allow-Origin=*.
# El CORSMiddleware estricto en main.py (con allow_origins explícito + allow_credentials)
# ya maneja TODOS los headers CORS automáticamente. El wildcard '*' era incompatible
# con Cookies HttpOnly (los navegadores rechazan credentials cuando origin=*).
#
# STUB no-op: utils/api/auth.py todavía hace `from utils.api.common import _cors`
# por compat. Devuelve la response sin tocarla — el CORSMiddleware ya hizo su trabajo.
def _cors(response: JSONResponse) -> JSONResponse:
    return response


def json_ok(data, status=200) -> JSONResponse:
    return JSONResponse(data, status_code=status)


def json_err(msg, status=400) -> JSONResponse:
    return JSONResponse({'error': msg}, status_code=status)


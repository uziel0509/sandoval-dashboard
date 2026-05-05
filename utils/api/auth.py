"""utils.api.auth — endpoints login/me/logout."""
from __future__ import annotations
import secrets
from datetime import datetime, timedelta
from starlette.requests import Request
from starlette.responses import JSONResponse
from sqlalchemy import text as _sa_text
from utils.models import get_db, verify_password, hash_password
from utils.security_events import track_login_failure as _track_login_fail
from utils.auth_cookies import (
    get_token_from_request, set_token_cookie, clear_token_cookie,
    COOKIE_CLIENT_NAME, COOKIE_ADMIN_NAME
)
from utils.api.common import (
    _require_auth, _extract_token, _new_token, _get_user_from_token,
    _get_sessions_db, json_ok, json_err, _cors,
)
from utils.api.ratelimit import (
    _check_rate_limit, _record_failed_attempt, _clear_attempts,
)


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

async def api_login(request: Request) -> JSONResponse:
    """POST /api/auth/login  {username, password, tipo: 'staff'|'cliente', placa?}"""
    # Rate limiting por IP
    client_ip = request.headers.get('X-Forwarded-For', request.client.host if request.client else 'unknown').split(',')[0].strip()
    if _check_rate_limit(client_ip):
        return json_err('Demasiados intentos fallidos. Espere 15 minutos.', 429)
    try:
        body = await request.json()
    except Exception:
        return json_err('Body JSON inválido')

    tipo = body.get('tipo', 'staff')
    # IMPORTANTE: con RLS STRICT, las queries directas sobre `usuarios`,
    # `vehiculos` y `clientes` SIN `app.taller_id` seteado devuelven 0 filas.
    # El usuario aún no está autenticado → no hay contexto. Por eso usamos
    # las funciones SECURITY DEFINER (`lookup_usuario_by_username`,
    # `lookup_cliente_by_placa`) que bypasean RLS solo para lookups de auth.
    from sqlalchemy import text as _sa_text
    db = get_db()
    try:
        if tipo == 'staff':
            username = (body.get('username') or '').strip()
            password = body.get('password') or ''
            row = db.execute(_sa_text(
                "SELECT id, username, nombre, rol, taller_id, activo, password_hash, email "
                "FROM lookup_usuario_by_username(:u)"
            ), {"u": username}).fetchone()
            if not row or not row[5]:  # row[5] = activo
                _record_failed_attempt(client_ip)
                return json_err('Usuario o contraseña incorrectos', 401)
            if not verify_password(password, row[6]):
                _record_failed_attempt(client_ip)
                return json_err('Usuario o contraseña incorrectos', 401)
            taller_id = int(row[4])
            # Setear contexto RLS para la sesión actual (UPDATE ultimo_login)
            try:
                from utils.rls_session import set_current_taller_id
                set_current_taller_id(taller_id)
                db.execute(_sa_text(
                    "SELECT set_config('app.taller_id', :tid, false)"
                ), {"tid": str(taller_id)})
            except Exception:
                pass
            db.execute(_sa_text(
                "UPDATE usuarios SET ultimo_login=NOW() WHERE id=:id AND taller_id=:t"
            ), {"id": row[0], "t": taller_id})
            db.commit()
            user_dict = {
                'id': row[0], 'username': row[1],
                'nombre': row[2], 'rol': row[3],
                'taller_id': taller_id,
                'email': row[7] or '', 'tipo': 'empleado',
            }
            token = _new_token(user_dict)
            _clear_attempts(client_ip)
            # 2026-04-29 P1-EtA: cookie HttpOnly + body (dual-auth, compat localStorage)
            _resp = json_ok({'token': token, 'user': user_dict})
            set_token_cookie(_resp, token, cookie_name=COOKIE_ADMIN_NAME)
            return _resp

        else:  # cliente o conductor (detección automática)
            placa_raw = (body.get('placa') or '').strip().upper()
            password = (body.get('password') or '').strip()
            from utils.flota import detect_login_role
            info = detect_login_role(
                db, placa_raw=placa_raw, password=password,
                bcrypt_verify=verify_password, bcrypt_hash=hash_password,
            )
            if info is None:
                _record_failed_attempt(client_ip)
                return json_err('Placa o contraseña incorrectos', 401)
            if info.get('kind') == 'blocked':
                return json_err('Tu acceso fue desactivado por la empresa.', 403)

            taller_id = int(info['taller_id'])
            try:
                from utils.rls_session import set_current_taller_id
                set_current_taller_id(taller_id)
                db.execute(_sa_text("SELECT set_config('app.taller_id', :tid, false)"), {"tid": str(taller_id)})
            except Exception:
                pass

            if info['kind'] == 'cliente':
                # Detectar si está usando el documento (RUC/DNI) como contraseña.
                # Esto significa que es la primera vez que entra → forzar cambio de PIN.
                row_pin = db.execute(_sa_text(
                    "SELECT pin_acceso, COALESCE(documento,'') FROM clientes WHERE id=:c AND taller_id=:t"
                ), {"c": info['cliente_id'], "t": taller_id}).fetchone()
                must_change_jefe = False
                if row_pin:
                    pin_actual_hash = row_pin[0] or ''
                    doc_real = (row_pin[1] or '').strip()
                    if not pin_actual_hash:
                        # Nunca cambió → obligar cambio
                        must_change_jefe = True
                        try:
                            db.execute(_sa_text(
                                "UPDATE clientes SET pin_acceso=:p WHERE id=:c AND taller_id=:t"
                            ), {"p": hash_password(password), "c": info['cliente_id'], "t": taller_id})
                            db.commit()
                        except Exception:
                            db.rollback()
                    elif doc_real and password.strip() == doc_real:
                        # Tiene PIN custom PERO usó el documento (raro: bcrypt_verify aceptó documento como pass)
                        # Solo forzar cambio si efectivamente la pass es el documento crudo
                        try:
                            if verify_password(doc_real, pin_actual_hash):
                                must_change_jefe = True
                        except Exception:
                            pass
                user_dict = {
                    'id': info['cliente_id'], 'nombre': info['nombre'],
                    'rol': 'cliente', 'placa': info['placa'],
                    'must_change_pin': must_change_jefe,
                    'taller_id': taller_id, 'tipo': 'cliente',
                    'tipo_cliente': info.get('tipo_cliente', 'individual'),
                }
            else:  # conductor
                user_dict = {
                    'id': info['placa'],
                    'nombre': info['nombre'],
                    'rol': 'conductor',
                    'placa': info['placa'],
                    'cliente_id': info['cliente_id'],
                    'taller_id': taller_id, 'tipo': 'conductor',
                    'must_change_pin': info.get('must_change', False),
                }

            token = _new_token(user_dict)
            _clear_attempts(client_ip)
            _resp = json_ok({'token': token, 'user': user_dict})
            set_token_cookie(_resp, token, cookie_name=COOKIE_CLIENT_NAME)
            return _resp
    finally:
        db.close()


async def api_me(request: Request) -> JSONResponse:
    """GET /api/auth/me"""
    result = _require_auth(request)
    if isinstance(result, JSONResponse):
        return result
    return json_ok(result)


async def api_logout(request: Request) -> JSONResponse:
    """POST /api/auth/logout"""
    token = _extract_token(request)
    if token:
        try:
            conn = _get_sessions_db()
            conn.execute('DELETE FROM sessions WHERE token=?', (token,))
            conn.commit()
            conn.close()
        except Exception:
            pass
    # 2026-04-29 P1-EtA: limpiar TODAS las cookies posibles (admin + cliente + legacy)
    _resp = json_ok({'ok': True, 'message': 'Sesion cerrada'})
    clear_token_cookie(_resp, cookie_name=COOKIE_ADMIN_NAME)
    clear_token_cookie(_resp, cookie_name=COOKIE_CLIENT_NAME)
    return _resp


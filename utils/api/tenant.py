"""utils.api.tenant — multi-tenant / RLS helpers."""
from __future__ import annotations
import json
from sqlalchemy import text as _sa_text
from utils.api.common import _require_auth, _require_admin, json_err


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

def _flota_actor_meta(request: Request):
    """Devuelve (actor_tipo, actor_id, ip, user) para auditoría."""
    user = _require_auth(request)
    if isinstance(user, JSONResponse):
        return None, None, '', user
    rol = user.get('rol', '')
    if rol in ('admin', 'staff', 'recepcionista', 'tecnico'):
        actor_tipo = 'admin_taller'
        actor_id = str(user.get('username') or user.get('id') or '')
    elif rol == 'cliente':
        actor_tipo = 'jefe_empresa'
        actor_id = str(user.get('id') or '')
    else:
        actor_tipo = 'conductor'
        actor_id = str(user.get('placa') or user.get('id') or '')
    ip = (request.headers.get('X-Forwarded-For') or
          (request.client.host if request.client else '') or '').split(',')[0].strip()
    return actor_tipo, actor_id, ip, user


def _ensure_admin(user):
    if user.get('rol') not in ('admin', 'staff', 'recepcionista', 'tecnico'):
        return json_err('Solo staff', 403)
    return None


def _ensure_jefe_empresa(user, db=None):
    """Verifica que el usuario sea jefe de empresa.
    Si JWT no trae tipo_cliente='empresa' (token viejo), consulta BD para validar."""
    if user.get('rol') != 'cliente':
        return json_err('Solo el jefe puede gestionar flota', 403)
    if user.get('tipo_cliente') == 'empresa':
        return None
    # JWT no tiene la marca — verificar BD por si activaron empresa después del login
    if db is None:
        return json_err('Tu cuenta no está marcada como empresa. Cerrá sesión y volvé a entrar.', 403)
    try:
        cid = user.get('id', '')
        taller_id = int(user.get('taller_id') or 1)
        row = db.execute(_sa_text(
            "SELECT COALESCE(tipo_cliente,'individual') FROM clientes WHERE id=:c AND taller_id=:t"
        ), {'c': cid, 't': taller_id}).fetchone()
        if row and row[0] == 'empresa':
            user['tipo_cliente'] = 'empresa'  # actualizar in-memory
            return None
    except Exception:
        pass
    return json_err('Tu cuenta no está marcada como empresa', 403)


def _setup_flota_ctx(db, taller_id):
    from utils.rls_session import set_current_taller_id
    set_current_taller_id(taller_id)
    db.execute(_sa_text("SELECT set_config('app.taller_id', :t, false)"), {'t': str(taller_id)})


def _cliente_id_pertenece_taller(db, cliente_id: str, taller_id: int) -> bool:
    """Verificar que el cliente pertenece a este taller (RLS-safe)."""
    r = db.execute(_sa_text("SELECT 1 FROM clientes WHERE id=:c AND taller_id=:t"),
                   {'c': cliente_id, 't': taller_id}).fetchone()
    return r is not None


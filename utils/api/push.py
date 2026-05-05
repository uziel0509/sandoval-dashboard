"""utils.api.push — endpoints VAPID Web Push."""
from __future__ import annotations
from starlette.requests import Request
from starlette.responses import JSONResponse
from utils.api.common import _require_auth, _require_admin, json_ok, json_err


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

async def api_push_vapid_key(request: Request) -> JSONResponse:
    db = get_db()
    try:
        from utils.flota import get_vapid_public
        return json_ok({'public_key': get_vapid_public(db)})
    finally:
        db.close()


async def api_push_subscribe(request: Request) -> JSONResponse:
    user = _require_auth(request)
    if isinstance(user, JSONResponse): return user
    try: body = await request.json()
    except: return json_err('Body inválido', 400)
    sub = body.get('subscription') or body
    user_agent = request.headers.get('User-Agent', '')[:500]
    rol = user.get('rol')
    user_kind = 'staff' if rol in ('admin','staff','recepcionista','tecnico') else rol
    user_id_str = str(user.get('placa') if rol == 'conductor' else user.get('id'))
    taller_id = int(user.get('taller_id') or 1)
    db = get_db()
    try:
        from utils.flota import save_push_subscription
        save_push_subscription(db, taller_id=taller_id, user_kind=user_kind,
                               user_id_str=user_id_str, sub=sub, user_agent=user_agent)
        return json_ok({'ok': True})
    except ValueError as e:
        return json_err(str(e), 400)
    finally:
        db.close()


async def api_push_unsubscribe(request: Request) -> JSONResponse:
    user = _require_auth(request)
    if isinstance(user, JSONResponse): return user
    try: body = await request.json()
    except: body = {}
    endpoint = body.get('endpoint', '')
    if not endpoint: return json_err('endpoint requerido', 400)
    db = get_db()
    try:
        from utils.flota import delete_push_subscription
        delete_push_subscription(db, endpoint=endpoint)
        return json_ok({'ok': True})
    finally:
        db.close()


async def admin_notificar_orden(request: Request) -> JSONResponse:
    """Envía push a jefe + conductor de una orden y devuelve wa.me links."""
    user = _require_auth(request)
    if isinstance(user, JSONResponse): return user
    if user.get('rol') not in ('admin','staff','recepcionista','tecnico'):
        return json_err('Solo staff', 403)
    cons = request.path_params.get('cons', '')
    try: body = await request.json()
    except: body = {}
    evento = str(body.get('evento') or 'diagnostico_listo')
    taller_id = int(user.get('taller_id') or 1)
    db = get_db()
    try:
        _setup_flota_ctx(db, taller_id)
        from utils.flota import notify_orden_event
        return json_ok(notify_orden_event(db, taller_id=taller_id, consecutivo=cons, evento=evento))
    finally:
        db.close()


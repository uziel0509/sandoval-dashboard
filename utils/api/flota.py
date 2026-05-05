"""utils.api.flota — handlers admin + cliente flota empresarial."""
from __future__ import annotations
import json
from starlette.requests import Request
from starlette.responses import JSONResponse
from sqlalchemy import text as _sa_text
from utils.models import get_db
from utils.api.common import _require_auth, _require_admin, json_ok, json_err
from utils.api.tenant import _setup_flota_ctx, _flota_actor_meta, _ensure_admin, _ensure_jefe_empresa, _cliente_id_pertenece_taller


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

async def admin_listar_flota(request: Request) -> JSONResponse:
    actor_tipo, actor_id, ip, user = _flota_actor_meta(request)
    if isinstance(user, JSONResponse): return user
    err = _ensure_admin(user)
    if err: return err
    cid = request.path_params.get('cid', '')
    taller_id = int(user.get('taller_id') or 1)
    db = get_db()
    try:
        _setup_flota_ctx(db, taller_id)
        from utils.flota import listar_flota
        return json_ok({'flota': listar_flota(db, taller_id=taller_id, cliente_id=cid)})
    finally:
        db.close()


async def admin_asignar_conductor(request: Request) -> JSONResponse:
    actor_tipo, actor_id, ip, user = _flota_actor_meta(request)
    if isinstance(user, JSONResponse): return user
    err = _ensure_admin(user)
    if err: return err
    cid = request.path_params.get('cid', '')
    placa = request.path_params.get('placa', '')
    try: body = await request.json()
    except: return json_err('Body inválido', 400)
    taller_id = int(user.get('taller_id') or 1)
    db = get_db()
    try:
        _setup_flota_ctx(db, taller_id)
        from utils.flota import asignar_conductor
        res = asignar_conductor(
            db, taller_id=taller_id, cliente_id=cid, placa=placa,
            nombre=str(body.get('nombre') or ''),
            dni=str(body.get('dni') or ''),
            telefono=str(body.get('telefono') or ''),
            email=str(body.get('email') or ''),
            pin_inicial=(str(body.get('pin_inicial')) if body.get('pin_inicial') else None),
            bcrypt_hash=hash_password,
            actor_tipo=actor_tipo, actor_id=actor_id, ip=ip,
        )
        return json_ok(res)
    except ValueError as e:
        return json_err(str(e), 400)
    except Exception as e:
        db.rollback()
        return json_err(str(e), 500)
    finally:
        db.close()


async def admin_quitar_conductor(request: Request) -> JSONResponse:
    actor_tipo, actor_id, ip, user = _flota_actor_meta(request)
    if isinstance(user, JSONResponse): return user
    err = _ensure_admin(user)
    if err: return err
    cid = request.path_params.get('cid', '')
    placa = request.path_params.get('placa', '')
    taller_id = int(user.get('taller_id') or 1)
    db = get_db()
    try:
        _setup_flota_ctx(db, taller_id)
        from utils.flota import quitar_conductor
        quitar_conductor(db, taller_id=taller_id, cliente_id=cid, placa=placa,
                         actor_tipo=actor_tipo, actor_id=actor_id, ip=ip)
        return json_ok({'ok': True})
    finally:
        db.close()


async def admin_reset_pin_conductor(request: Request) -> JSONResponse:
    actor_tipo, actor_id, ip, user = _flota_actor_meta(request)
    if isinstance(user, JSONResponse): return user
    err = _ensure_admin(user)
    if err: return err
    cid = request.path_params.get('cid', '')
    placa = request.path_params.get('placa', '')
    taller_id = int(user.get('taller_id') or 1)
    db = get_db()
    try:
        _setup_flota_ctx(db, taller_id)
        from utils.flota import reset_pin_conductor
        nuevo_pin = reset_pin_conductor(
            db, taller_id=taller_id, cliente_id=cid, placa=placa,
            bcrypt_hash=hash_password,
            actor_tipo=actor_tipo, actor_id=actor_id, ip=ip,
        )
        return json_ok({'pin': nuevo_pin})
    finally:
        db.close()


async def admin_toggle_conductor_activo(request: Request) -> JSONResponse:
    actor_tipo, actor_id, ip, user = _flota_actor_meta(request)
    if isinstance(user, JSONResponse): return user
    err = _ensure_admin(user)
    if err: return err
    cid = request.path_params.get('cid', '')
    placa = request.path_params.get('placa', '')
    try: body = await request.json()
    except: body = {}
    activar = bool(body.get('activo', True))
    taller_id = int(user.get('taller_id') or 1)
    db = get_db()
    try:
        _setup_flota_ctx(db, taller_id)
        from utils.flota import activar_conductor, desactivar_conductor
        if activar:
            activar_conductor(db, taller_id=taller_id, cliente_id=cid, placa=placa,
                              actor_tipo=actor_tipo, actor_id=actor_id, ip=ip)
        else:
            desactivar_conductor(db, taller_id=taller_id, cliente_id=cid, placa=placa,
                                 actor_tipo=actor_tipo, actor_id=actor_id, ip=ip)
        return json_ok({'ok': True, 'activo': activar})
    finally:
        db.close()


async def admin_get_audit(request: Request) -> JSONResponse:
    actor_tipo, actor_id, ip, user = _flota_actor_meta(request)
    if isinstance(user, JSONResponse): return user
    err = _ensure_admin(user)
    if err: return err
    cid = request.path_params.get('cid', '')
    taller_id = int(user.get('taller_id') or 1)
    db = get_db()
    try:
        _setup_flota_ctx(db, taller_id)
        from utils.flota import get_audit
        return json_ok({'audit': get_audit(db, taller_id=taller_id, cliente_id=cid, limit=100)})
    finally:
        db.close()


async def admin_reset_pin_jefe(request: Request) -> JSONResponse:
    """Genera un PIN nuevo de 6 dígitos para el JEFE / cliente. Lo retorna UNA SOLA VEZ."""
    actor_tipo, actor_id, ip, user = _flota_actor_meta(request)
    if isinstance(user, JSONResponse): return user
    err = _ensure_admin(user)
    if err: return err
    cid = request.path_params.get('cid', '')
    taller_id = int(user.get('taller_id') or 1)
    db = get_db()
    try:
        _setup_flota_ctx(db, taller_id)
        # Verificar que el cliente existe
        if not _cliente_id_pertenece_taller(db, cid, taller_id):
            return json_err('Cliente no encontrado', 404)
        import secrets, string
        pin = ''.join(secrets.choice(string.digits) for _ in range(6))
        new_hash = hash_password(pin)
        db.execute(_sa_text("UPDATE clientes SET pin_acceso=:p WHERE id=:c AND taller_id=:t"),
                   {'p': new_hash, 'c': cid, 't': taller_id})
        db.commit()
        from utils.flota import audit
        audit(db, taller_id=taller_id, cliente_id=cid, placa=None,
              accion='jefe_pin_reset', actor_tipo=actor_tipo, actor_id=actor_id, ip=ip)
        return json_ok({'pin': pin})
    finally:
        db.close()


async def admin_set_tipo_cliente(request: Request) -> JSONResponse:
    actor_tipo, actor_id, ip, user = _flota_actor_meta(request)
    if isinstance(user, JSONResponse): return user
    err = _ensure_admin(user)
    if err: return err
    cid = request.path_params.get('cid', '')
    try: body = await request.json()
    except: return json_err('Body inválido', 400)
    tipo = str(body.get('tipo') or '').lower()
    if tipo not in ('individual', 'empresa'):
        return json_err('tipo debe ser individual o empresa', 400)
    taller_id = int(user.get('taller_id') or 1)
    db = get_db()
    try:
        _setup_flota_ctx(db, taller_id)
        db.execute(_sa_text("UPDATE clientes SET tipo_cliente=:tp WHERE id=:c AND taller_id=:t"),
                   {'tp': tipo, 'c': cid, 't': taller_id})
        db.commit()
        from utils.flota import audit
        audit(db, taller_id=taller_id, cliente_id=cid, placa=None,
              accion=f'tipo_cliente_set_{tipo}', actor_tipo=actor_tipo, actor_id=actor_id, ip=ip)
        return json_ok({'tipo': tipo})
    finally:
        db.close()


async def cliente_mi_flota(request: Request) -> JSONResponse:
    actor_tipo, actor_id, ip, user = _flota_actor_meta(request)
    if isinstance(user, JSONResponse): return user
    taller_id = int(user.get('taller_id') or 1)
    db = get_db()
    try:
        _setup_flota_ctx(db, taller_id)
        err = _ensure_jefe_empresa(user, db)
        if err: return err
        from utils.flota import listar_flota
        return json_ok({'flota': listar_flota(db, taller_id=taller_id, cliente_id=user['id'])})
    finally:
        db.close()


async def cliente_asignar_conductor(request: Request) -> JSONResponse:
    actor_tipo, actor_id, ip, user = _flota_actor_meta(request)
    if isinstance(user, JSONResponse): return user
    placa = request.path_params.get('placa', '')
    try: body = await request.json()
    except: return json_err('Body inválido', 400)
    taller_id = int(user.get('taller_id') or 1)
    db = get_db()
    try:
        _setup_flota_ctx(db, taller_id)
        err = _ensure_jefe_empresa(user, db)
        if err: return err
        from utils.flota import asignar_conductor
        res = asignar_conductor(
            db, taller_id=taller_id, cliente_id=user['id'], placa=placa,
            nombre=str(body.get('nombre') or ''),
            dni=str(body.get('dni') or ''),
            telefono=str(body.get('telefono') or ''),
            email=str(body.get('email') or ''),
            pin_inicial=(str(body.get('pin_inicial')) if body.get('pin_inicial') else None),
            bcrypt_hash=hash_password,
            actor_tipo=actor_tipo, actor_id=actor_id, ip=ip,
        )
        return json_ok(res)
    except ValueError as e:
        return json_err(str(e), 400)
    finally:
        db.close()


async def cliente_quitar_conductor(request: Request) -> JSONResponse:
    actor_tipo, actor_id, ip, user = _flota_actor_meta(request)
    if isinstance(user, JSONResponse): return user
    placa = request.path_params.get('placa', '')
    taller_id = int(user.get('taller_id') or 1)
    db = get_db()
    try:
        _setup_flota_ctx(db, taller_id)
        err = _ensure_jefe_empresa(user, db)
        if err: return err
        from utils.flota import quitar_conductor
        quitar_conductor(db, taller_id=taller_id, cliente_id=user['id'], placa=placa,
                         actor_tipo=actor_tipo, actor_id=actor_id, ip=ip)
        return json_ok({'ok': True})
    finally:
        db.close()


async def cliente_reset_pin_conductor(request: Request) -> JSONResponse:
    actor_tipo, actor_id, ip, user = _flota_actor_meta(request)
    if isinstance(user, JSONResponse): return user
    placa = request.path_params.get('placa', '')
    taller_id = int(user.get('taller_id') or 1)
    db = get_db()
    try:
        _setup_flota_ctx(db, taller_id)
        err = _ensure_jefe_empresa(user, db)
        if err: return err
        from utils.flota import reset_pin_conductor
        nuevo_pin = reset_pin_conductor(
            db, taller_id=taller_id, cliente_id=user['id'], placa=placa,
            bcrypt_hash=hash_password,
            actor_tipo=actor_tipo, actor_id=actor_id, ip=ip,
        )
        return json_ok({'pin': nuevo_pin})
    finally:
        db.close()


async def cliente_toggle_conductor_activo(request: Request) -> JSONResponse:
    actor_tipo, actor_id, ip, user = _flota_actor_meta(request)
    if isinstance(user, JSONResponse): return user
    placa = request.path_params.get('placa', '')
    try: body = await request.json()
    except: body = {}
    activar = bool(body.get('activo', True))
    taller_id = int(user.get('taller_id') or 1)
    db = get_db()
    try:
        _setup_flota_ctx(db, taller_id)
        err = _ensure_jefe_empresa(user, db)
        if err: return err
        from utils.flota import activar_conductor, desactivar_conductor
        if activar:
            activar_conductor(db, taller_id=taller_id, cliente_id=user['id'], placa=placa,
                              actor_tipo=actor_tipo, actor_id=actor_id, ip=ip)
        else:
            desactivar_conductor(db, taller_id=taller_id, cliente_id=user['id'], placa=placa,
                                 actor_tipo=actor_tipo, actor_id=actor_id, ip=ip)
        return json_ok({'ok': True, 'activo': activar})
    finally:
        db.close()


async def cliente_get_audit(request: Request) -> JSONResponse:
    actor_tipo, actor_id, ip, user = _flota_actor_meta(request)
    if isinstance(user, JSONResponse): return user
    taller_id = int(user.get('taller_id') or 1)
    db = get_db()
    try:
        _setup_flota_ctx(db, taller_id)
        err = _ensure_jefe_empresa(user, db)
        if err: return err
        from utils.flota import get_audit
        return json_ok({'audit': get_audit(db, taller_id=taller_id, cliente_id=user['id'], limit=100)})
    finally:
        db.close()


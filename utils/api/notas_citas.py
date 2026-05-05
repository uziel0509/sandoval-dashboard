"""utils.api.notas_citas — notas-venta + citas."""
from __future__ import annotations
import json
from datetime import datetime
from starlette.requests import Request
from starlette.responses import JSONResponse
from sqlalchemy import text as _sa_text
from utils.models import get_db, NotaVenta, Cita
from utils.api.common import _require_auth, _require_admin, json_ok, json_err
from utils.api.tenant import _setup_flota_ctx


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

async def api_notas_list(request: Request) -> JSONResponse:
    user = _require_admin(request)
    if isinstance(user, JSONResponse):
        return user
    # 2026-05-05 P0 IDOR FIX (sync-guardian audit): filtro taller_id +
    # limite 200 (era 50, divergente del admin SPA).
    taller_id = user.get('taller_id')
    if not taller_id:
        return json_err('taller_id ausente en sesión', 401)
    db = get_db()
    try:
        notas = (db.query(NotaVenta)
                 .filter(NotaVenta.taller_id == taller_id)
                 .order_by(NotaVenta.fecha.desc())
                 .limit(200).all())
        return json_ok([{
            'id': n.id, 'numero': n.numero,
            'fecha': str(n.fecha or ''),
            'cliente_nombre': n.cliente_nombre or '',
            'total': n.total, 'estado': n.estado,
        } for n in notas])
    finally:
        db.close()


async def api_nota_create(request: Request) -> JSONResponse:
    user = _require_admin(request)
    if isinstance(user, JSONResponse):
        return user
    # 2026-05-05 P1 FIX (sync-guardian audit): setear taller_id + estado
    # 'PAGADO' (mayúscula) coherente con admin SPA. Antes estado='pagada'
    # rompía filtros del admin.
    taller_id = user.get('taller_id')
    if not taller_id:
        return json_err('taller_id ausente en sesión', 401)
    try:
        body = await request.json()
    except Exception:
        return json_err('Body inválido')
    items = body.get('items', [])
    if not items:
        return json_err('Sin ítems')
    db = get_db()
    try:
        last = (db.query(NotaVenta)
                .filter(NotaVenta.taller_id == taller_id)
                .order_by(NotaVenta.id.desc()).first())
        seq = (last.id + 1) if last else 1
        numero = f"NV-{datetime.now().year}-{seq:04d}"
        sub = sum(it.get('subtotal', 0) for it in items)
        igv = round(sub * 0.18, 2)
        tot = round(sub + igv, 2)
        # Descontar stock — filtrado por taller_id
        for it in items:
            p = (db.query(ItemInventario)
                 .filter(ItemInventario.codigo == it.get('codigo'),
                         ItemInventario.taller_id == taller_id)
                 .first())
            if p:
                p.stock = max(0, p.stock - it.get('cantidad', 0))
        nv = NotaVenta(
            taller_id=taller_id,
            numero=numero, fecha=datetime.now(),
            cliente_nombre=body.get('cliente_nombre', 'Mostrador'),
            subtotal=sub, igv=igv, total=tot,
            estado='PAGADO', items=items,
        )
        db.add(nv)
        db.commit()
        return json_ok({'ok': True, 'numero': numero, 'total': tot}, 201)
    except Exception as e:
        db.rollback()
        return json_err(str(e))
    finally:
        db.close()


async def api_citas_list(request: Request) -> JSONResponse:
    user = _require_admin(request)
    if isinstance(user, JSONResponse):
        return user
    # 2026-05-05 P0 IDOR FIX (sync-guardian audit): filtro taller_id
    taller_id = user.get('taller_id')
    if not taller_id:
        return json_err('taller_id ausente en sesión', 401)
    db = get_db()
    try:
        citas = (db.query(Cita)
                 .filter(Cita.taller_id == taller_id)
                 .order_by(Cita.id.desc())
                 .limit(200).all())
        return json_ok([{
            'id': c.id, 'fecha': c.fecha_cita,
            'descripcion': c.motivo or '',
            'estado': c.estado or '', 'placa': c.vehiculo_placa or '',
            'cliente_id': c.cliente_id or '',
        } for c in citas])
    finally:
        db.close()


async def api_cita_create(request: Request) -> JSONResponse:
    user = _require_auth(request)
    if isinstance(user, JSONResponse):
        return user
    try:
        body = await request.json()
    except Exception:
        return json_err('Body inválido')
    db = get_db()
    try:
        fecha_str = body.get('fecha', '')
        try:
            fecha = datetime.fromisoformat(fecha_str)
        except Exception:
            return json_err('Fecha inválida')
        c = Cita(
            cliente_id=body.get('cliente_id', user.get('id')),
            vehiculo_placa=body.get('placa', ''),
            fecha_cita=fecha_str,
            hora=fecha.strftime('%H:%M'),
            motivo=body.get('descripcion', ''),
            estado='programada',
        )
        db.add(c)
        db.commit()

        # Notificar al administrador
        try:
            cli = db.query(Cliente).get(c.cliente_id)
            nom = f"{cli.nombre} {cli.apellidos}".strip() if cli else "Cliente"
            log_actividad(f"Nueva cita agendada por {nom} para el {c.fecha_cita}. Confirmar.", 'citas')
        except Exception: pass
        # Push notification a admin/staff (2026-04-29)
        try:
            # 2026-05-04 FASE1.4: pool acotado en lugar de Thread(daemon=True)
            from utils._async_helpers import fire_and_forget as _faf
            from utils.notifications import notify_admin_nueva_cita
            taller_id = getattr(c, 'taller_id', None) or user.get('taller_id') or 1
            try:
                from utils.models import get_db as _get_db2
                _db2_cita = _get_db2()
                _faf(notify_admin_nueva_cita, _db2_cita, int(taller_id), c.id)
            except Exception: pass
        except Exception: pass
        return json_ok({'ok': True, 'id': c.id}, 201)
    except Exception as e:
        db.rollback()
        return json_err(str(e))
    finally:
        db.close()


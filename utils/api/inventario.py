"""utils.api.inventario — endpoints inventario."""
from __future__ import annotations
import json
from starlette.requests import Request
from starlette.responses import JSONResponse
from sqlalchemy import text as _sa_text
from utils.models import get_db, ItemInventario
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

async def api_inventario_list(request: Request) -> JSONResponse:
    user = _require_auth(request)
    if isinstance(user, JSONResponse):
        return user
    # 2026-05-05 P0 IDOR FIX (sync-guardian audit): filtro taller_id +
    # campos margen/estado_stock/codigo_barras/descripcion para sincronizar
    # con admin SPA PC.
    taller_id = user.get('taller_id')
    if not taller_id:
        return json_err('taller_id ausente en sesión', 401)
    db = get_db()
    try:
        items = (db.query(ItemInventario)
                 .filter(ItemInventario.taller_id == taller_id)
                 .order_by(ItemInventario.nombre)
                 .all())
        result = []
        for i in items:
            precio = float(i.precio or 0); costo = float(i.costo or 0)
            stock = int(i.stock or 0); smin = int(i.stock_minimo or 0)
            margen = round((precio - costo) / precio * 100, 1) if precio > 0 else 0
            estado = 'AGOTADO' if stock == 0 else ('BAJO' if (smin > 0 and stock <= smin) else 'OK')
            result.append({
                'codigo': i.codigo, 'nombre': i.nombre,
                'categoria': i.categoria, 'tipo': i.tipo,
                'costo': costo, 'precio': precio,
                'stock': stock, 'stock_minimo': smin,
                'margen': margen, 'estado_stock': estado,
                'codigo_barras': getattr(i, 'codigo_barras', '') or '',
                'descripcion': getattr(i, 'descripcion', '') or '',
            })
        return json_ok(result)
    finally:
        db.close()


async def api_inventario_buscar(request: Request) -> JSONResponse:
    """GET /api/inventario/buscar
       ?codigo=XXX  → scanner: busca por codigo_barras o codigo, devuelve objeto único (404 si no existe)
       ?q=texto     → búsqueda por nombre/codigo (ILIKE), devuelve lista de hasta 20 ítems
    Case-insensitive. Multi-tenant: filtra por taller_id del JWT."""
    user = _require_auth(request)
    if isinstance(user, JSONResponse):
        return user
    codigo = (request.query_params.get('codigo') or '').strip()
    q = (request.query_params.get('q') or '').strip()
    if not codigo and not q:
        return json_err('Parámetro codigo o q requerido', 400)
    taller_id = int(user.get('taller_id') or 1)
    from sqlalchemy import text as _sql_text
    db = get_db()
    try:
        if codigo:
            row = db.execute(_sql_text("""
                SELECT codigo, nombre, categoria, tipo, precio, costo,
                       stock, stock_minimo, descripcion, codigo_barras
                  FROM inventario
                 WHERE taller_id = :t
                   AND (codigo_barras = :c OR UPPER(codigo) = UPPER(:c))
                 LIMIT 1
            """), {'t': taller_id, 'c': codigo}).fetchone()
            if not row:
                return json_err('No encontrado', 404)
            precio = float(row[4] or 0); costo = float(row[5] or 0)
            margen = round((precio - costo) / precio * 100, 1) if precio > 0 else 0
            stock = int(row[6] or 0); smin = int(row[7] or 0)
            estado = 'AGOTADO' if stock == 0 else ('BAJO' if (smin > 0 and stock <= smin) else 'OK')
            return json_ok({
                'codigo': row[0], 'nombre': row[1], 'categoria': row[2], 'tipo': row[3],
                'precio': precio, 'costo': costo, 'margen': margen,
                'stock': stock, 'stock_minimo': smin, 'estado_stock': estado,
                'descripcion': row[8] or '', 'codigo_barras': row[9] or '',
            })
        pat = '%' + q.replace('%', '').replace('_', '') + '%'
        rows = db.execute(_sql_text("""
            SELECT codigo, nombre, categoria, tipo, precio, costo,
                   stock, stock_minimo, descripcion, codigo_barras
              FROM inventario
             WHERE taller_id = :t
               AND (UPPER(nombre) LIKE UPPER(:p)
                    OR UPPER(codigo) LIKE UPPER(:p)
                    OR UPPER(COALESCE(codigo_barras,'')) LIKE UPPER(:p)
                    OR UPPER(COALESCE(descripcion,'')) LIKE UPPER(:p))
             ORDER BY (CASE WHEN stock > 0 THEN 0 ELSE 1 END), nombre
             LIMIT 20
        """), {'t': taller_id, 'p': pat}).fetchall()
        items = []
        for r in rows:
            precio = float(r[4] or 0); costo = float(r[5] or 0)
            stock = int(r[6] or 0); smin = int(r[7] or 0)
            estado = 'AGOTADO' if stock == 0 else ('BAJO' if (smin > 0 and stock <= smin) else 'OK')
            items.append({
                'codigo': r[0], 'nombre': r[1], 'categoria': r[2], 'tipo': r[3],
                'precio': precio, 'costo': costo,
                'stock': stock, 'stock_minimo': smin, 'estado_stock': estado,
                'descripcion': r[8] or '', 'codigo_barras': r[9] or '',
            })
        return json_ok(items)
    finally:
        db.close()


async def api_inventario_usar(request: Request) -> JSONResponse:
    """POST /api/inventario/{codigo}/usar — decrementa stock"""
    user = _require_auth(request)
    if isinstance(user, JSONResponse): return user
    if user.get('rol') == 'cliente':
        return json_err('Acceso denegado', 403)
    codigo = request.path_params.get('codigo','')
    try: body = await request.json()
    except: body = {}
    try: cantidad = float(body.get('cantidad', 1))
    except: cantidad = 1.0
    if cantidad <= 0:
        return json_err('cantidad debe ser > 0')
    # 2026-05-04 MULTI-TENANT FIX: extraer taller_id de la sesion en lugar de hardcodear 1
    taller_id = int(user.get('taller_id') or 0)
    if taller_id <= 0:
        return json_err('taller invalido en sesion', 401)
    from sqlalchemy import text as _sqltxt
    db = get_db()
    try:
        db.execute(_sqltxt(
            "UPDATE inventario SET stock = GREATEST(stock - :q, 0) WHERE codigo=:c AND taller_id=:t"
        ), {"q": cantidad, "c": codigo, "t": taller_id})
        db.commit()
        row = db.execute(_sqltxt(
            "SELECT stock FROM inventario WHERE codigo=:c AND taller_id=:t"
        ), {"c": codigo, "t": taller_id}).fetchone()
        return json_ok({'ok': True, 'stock_actual': row[0] if row else 0})
    except Exception as e:
        db.rollback(); return json_err(str(e))
    finally: db.close()


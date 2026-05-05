"""utils.api.reportes — dashboard + reportes ganancia."""
from __future__ import annotations
from datetime import datetime, timedelta
from starlette.requests import Request
from starlette.responses import JSONResponse
from sqlalchemy import text as _sa_text
from utils.models import get_db
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

async def api_dashboard(request: Request) -> JSONResponse:
    user = _require_admin(request)
    if isinstance(user, JSONResponse):
        return user
    db = get_db()
    try:
        from sqlalchemy import func
        ordenes = db.query(Orden).all()
        n_clientes = db.query(Cliente).count()
        COMPLETADOS = {'ARCHIVADO','ENTREGADO','ENTREGA','Entrega'}
        activas = [o for o in ordenes if (o.estado or '') not in COMPLETADOS]
        completadas = [o for o in ordenes if (o.estado or '') in COMPLETADOS]
        total_ingresos = 0
        for o in ordenes:
            items = o.items_cotizacion or []
            if isinstance(items, str):
                try:
                    import json as _json
                    items = _json.loads(items)
                except Exception:
                    items = []
            if isinstance(items, list):
                for it in items:
                    try:
                        total_ingresos += float(it.get('total', 0) or 0)
                    except Exception:
                        pass
        stock_bajo = db.query(ItemInventario).filter(
            ItemInventario.stock <= ItemInventario.stock_minimo).count()
        # ventas notas del mes
        now = datetime.now()
        notas_mes = [
            n for n in db.query(NotaVenta).filter_by(estado='pagada').all()
            if n.fecha and n.fecha.month == now.month and n.fecha.year == now.year
        ]
        ventas_mes = sum(n.total for n in notas_mes)

        return json_ok({
            'n_ordenes_activas': len(activas),
            'n_completadas': len(completadas),
            'n_clientes': n_clientes,
            'total_ingresos': total_ingresos,
            'stock_bajo': stock_bajo,
            'ventas_mes': ventas_mes,
            'estados': {
                est: len([o for o in ordenes if o.estado == est])
                for est in ['RECEPCIÓN', 'DIAGNÓSTICO', 'REPUESTOS',
                            'APROBACIÓN', 'REPARACIÓN', 'CONTROL CALIDAD', 'ARCHIVADO']
            },
        })
    finally:
        db.close()


async def api_reportes_ganancia(request: Request) -> JSONResponse:
    """GET /api/reportes/ganancia?periodo=semana|mes|año — rentabilidad por periodo"""
    user = _require_admin(request)
    if isinstance(user, JSONResponse):
        return user

    periodo = request.query_params.get('periodo', 'mes')
    now = datetime.now()

    if periodo == 'semana':
        inicio = now - timedelta(days=7)
    elif periodo == 'año':
        inicio = now - timedelta(days=365)
    else:  # mes (default) = últimos 30 días
        inicio = now - timedelta(days=30)

    inicio_dt = inicio.replace(hour=0, minute=0, second=0, microsecond=0)

    def _parse_fecha(f):
        """Normaliza fecha a datetime independiente del formato."""
        f = (f or '').strip()[:10]
        for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%Y/%m/%d'):
            try:
                return datetime.strptime(f, fmt)
            except Exception:
                pass
        return None

    db = get_db()
    try:
        # Construir mapa de costos del inventario: codigo -> costo
        inv_items = db.query(ItemInventario).all()
        costos_map = {it.codigo: (it.costo or 0) for it in inv_items}

        # ── Procesar Órdenes de Servicio ──────────────────────────────────
        ordenes = db.query(Orden).all()

        ing_repuestos = 0.0
        costo_repuestos = 0.0
        ing_mano_obra = 0.0
        productos_agg = {}  # nombre -> {ingresos, costo, ganancia, unidades}

        for o in ordenes:
            fecha_dt = _parse_fecha(o.fecha)
            if not fecha_dt or fecha_dt < inicio_dt:
                continue

            items = o.items_cotizacion or []
            if isinstance(items, str):
                try:
                    import json as _j
                    items = _j.loads(items)
                except Exception:
                    items = []
            if not isinstance(items, list):
                continue

            for it in items:
                precio_u = float(it.get('precio_unitario', 0) or 0)
                cant = float(it.get('cantidad', 1) or 1)
                total = precio_u * cant
                cat = (it.get('categoria') or '').strip().lower()
                ref = (it.get('referencia') or it.get('ref') or '').strip()
                nombre = (it.get('nombre') or 'Sin nombre').strip()

                es_mo = cat in ('servicio', 'mano de obra') or ref == 'MANO-DE-OBRA' or 'mano' in nombre.lower()

                if es_mo:
                    ing_mano_obra += total
                    key = 'mano_obra'
                    if key not in productos_agg:
                        productos_agg[key] = {'nombre': 'Mano de obra / Servicios', 'ingresos': 0, 'costo': 0, 'ganancia': 0, 'unidades': 0, 'es_mo': True}
                    productos_agg[key]['ingresos'] += total
                    productos_agg[key]['ganancia'] += total
                    productos_agg[key]['unidades'] += cant
                else:
                    costo_u = costos_map.get(ref, 0) if ref else 0
                    costo_total = costo_u * cant
                    ganancia = total - costo_total
                    ing_repuestos += total
                    costo_repuestos += costo_total
                    key = ref or nombre
                    if key not in productos_agg:
                        productos_agg[key] = {'nombre': nombre, 'ingresos': 0, 'costo': 0, 'ganancia': 0, 'unidades': 0, 'es_mo': False}
                    productos_agg[key]['ingresos'] += total
                    productos_agg[key]['costo'] += costo_total
                    productos_agg[key]['ganancia'] += ganancia
                    productos_agg[key]['unidades'] += cant

        # ── Procesar Notas de Venta ───────────────────────────────────────
        notas = db.query(NotaVenta).filter_by(estado='pagada').all()
        for n in notas:
            if not n.fecha or n.fecha < inicio_dt:
                continue
            items_n = n.items or []
            if isinstance(items_n, str):
                try:
                    import json as _j
                    items_n = _j.loads(items_n)
                except Exception:
                    items_n = []
            for it in items_n:
                precio_u = float(it.get('precio', 0) or 0)
                cant = float(it.get('cantidad', 1) or 1)
                total = precio_u * cant
                ref = (it.get('codigo') or '').strip()
                nombre = (it.get('nombre') or 'Sin nombre').strip()
                costo_u = costos_map.get(ref, 0) if ref else 0
                costo_total = costo_u * cant
                ganancia = total - costo_total
                ing_repuestos += total
                costo_repuestos += costo_total
                key = ref or nombre
                if key not in productos_agg:
                    productos_agg[key] = {'nombre': nombre, 'ingresos': 0, 'costo': 0, 'ganancia': 0, 'unidades': 0, 'es_mo': False}
                productos_agg[key]['ingresos'] += total
                productos_agg[key]['costo'] += costo_total
                productos_agg[key]['ganancia'] += ganancia
                productos_agg[key]['unidades'] += cant

        # Top productos por ganancia (sin mano de obra mezclada)
        top_productos = sorted(
            [v for v in productos_agg.values() if not v.get('es_mo')],
            key=lambda x: x['ganancia'], reverse=True
        )[:10]

        total_ingresos = ing_repuestos + ing_mano_obra
        total_costo = costo_repuestos
        total_ganancia = (ing_repuestos - costo_repuestos) + ing_mano_obra
        margen = round((total_ganancia / total_ingresos * 100) if total_ingresos > 0 else 0, 1)

        return json_ok({
            'periodo': periodo,
            'desde': inicio_dt.strftime('%Y-%m-%d'),
            'resumen': {
                'total_ingresos': round(total_ingresos, 2),
                'total_costo': round(total_costo, 2),
                'total_ganancia': round(total_ganancia, 2),
                'margen_pct': margen,
                'ingresos_repuestos': round(ing_repuestos, 2),
                'costo_repuestos': round(costo_repuestos, 2),
                'ganancia_repuestos': round(ing_repuestos - costo_repuestos, 2),
                'ingresos_mano_obra': round(ing_mano_obra, 2),
                'ganancia_mano_obra': round(ing_mano_obra, 2),
            },
            'top_productos': [
                {
                    'nombre': p['nombre'],
                    'ingresos': round(p['ingresos'], 2),
                    'costo': round(p['costo'], 2),
                    'ganancia': round(p['ganancia'], 2),
                    'unidades': round(p['unidades'], 1),
                }
                for p in top_productos
            ],
        })
    except Exception as e:
        return json_err(str(e))
    finally:
        db.close()


async def api_reportes_ganancia_diaria(request: Request) -> JSONResponse:
    """GET /api/reportes/ganancia-diaria?dias=30 — historial de ganancias día a día"""
    user = _require_admin(request)
    if isinstance(user, JSONResponse):
        return user

    try:
        dias = int(request.query_params.get('dias', 30))
    except Exception:
        dias = 30
    dias = min(max(dias, 1), 365)

    now = datetime.now()
    inicio_dt = (now - timedelta(days=dias)).replace(hour=0, minute=0, second=0, microsecond=0)

    def _parse_fecha_d(f):
        f = (f or '').strip()[:10]
        for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%Y/%m/%d'):
            try:
                return datetime.strptime(f, fmt)
            except Exception:
                pass
        return None

    db = get_db()
    try:
        inv_items = db.query(ItemInventario).all()
        costos_map = {it.codigo: float(it.costo or 0) for it in inv_items}

        dias_data = {}

        def _get_dia(key):
            if key not in dias_data:
                dias_data[key] = {'fecha': key, 'gan_rep': 0.0, 'gan_mo': 0.0, 'gan_total': 0.0, 'num_ordenes': 0}
            return dias_data[key]

        # ── Órdenes de servicio ──
        for o in db.query(Orden).all():
            fecha_dt = _parse_fecha_d(o.fecha)
            if not fecha_dt or fecha_dt < inicio_dt:
                continue
            key = fecha_dt.strftime('%Y-%m-%d')
            dia = _get_dia(key)
            dia['num_ordenes'] += 1
            items = o.items_cotizacion or []
            if isinstance(items, str):
                try:
                    import json as _j; items = _j.loads(items)
                except Exception:
                    items = []
            if not isinstance(items, list):
                continue
            for it in items:
                precio_u = float(it.get('precio_unitario', 0) or 0)
                cant = float(it.get('cantidad', 1) or 1)
                total = precio_u * cant
                cat = (it.get('categoria') or '').strip().lower()
                ref = (it.get('referencia') or it.get('ref') or '').strip()
                nombre = (it.get('nombre') or '').strip()
                es_mo = cat in ('servicio', 'mano de obra') or ref == 'MANO-DE-OBRA' or 'mano' in nombre.lower()
                if es_mo:
                    dia['gan_mo'] += total
                else:
                    costo_u = costos_map.get(ref, 0) if ref else 0
                    dia['gan_rep'] += total - (costo_u * cant)

        # ── Notas de venta ──
        for n in db.query(NotaVenta).filter_by(estado='pagada').all():
            if not n.fecha:
                continue
            try:
                nf = n.fecha if hasattr(n.fecha, 'strftime') else _parse_fecha_d(str(n.fecha)[:10])
                if not nf or nf < inicio_dt:
                    continue
                key = nf.strftime('%Y-%m-%d')
            except Exception:
                continue
            dia = _get_dia(key)
            items_n = n.items or []
            if isinstance(items_n, str):
                try:
                    import json as _j; items_n = _j.loads(items_n)
                except Exception:
                    items_n = []
            for it in (items_n if isinstance(items_n, list) else []):
                precio_u = float(it.get('precio', 0) or 0)
                cant = float(it.get('cantidad', 1) or 1)
                total = precio_u * cant
                ref = (it.get('codigo') or '').strip()
                costo_u = costos_map.get(ref, 0) if ref else 0
                dia['gan_rep'] += total - (costo_u * cant)

        for d in dias_data.values():
            d['gan_total'] = round(d['gan_rep'] + d['gan_mo'], 2)
            d['gan_rep'] = round(d['gan_rep'], 2)
            d['gan_mo'] = round(d['gan_mo'], 2)

        historial = sorted(dias_data.values(), key=lambda x: x['fecha'], reverse=True)

        return json_ok({
            'dias': dias,
            'desde': inicio_dt.strftime('%Y-%m-%d'),
            'historial': historial,
        })
    except Exception as e:
        return json_err(str(e))
    finally:
        db.close()


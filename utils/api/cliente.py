"""utils.api.cliente — portal cliente + clientes/vehiculos CRUD."""
from __future__ import annotations
import json
import os
import secrets
from datetime import datetime
from starlette.requests import Request
from starlette.responses import JSONResponse, FileResponse
from sqlalchemy import text as _sa_text
from utils.models import get_db, Cliente, Vehiculo, Orden
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

async def api_vehiculos_cliente(request: Request) -> JSONResponse:
    """GET /api/clientes/{id}/vehiculos"""
    user = _require_admin(request)
    if isinstance(user, JSONResponse):
        return user
    cliente_id = request.path_params.get('id', '')
    db = get_db()
    try:
        vehiculos = db.query(Vehiculo).filter_by(cliente_id=cliente_id).all()
        return json_ok([{
            'placa': v.placa, 'marca': v.marca, 'modelo': v.modelo,
            'año': getattr(v, 'año', getattr(v, 'anio', '')),
        } for v in vehiculos])
    finally:
        db.close()


async def api_clientes_list(request: Request) -> JSONResponse:
    """GET /api/clientes — shape coherente con /admin/api/clientes (routers/clientes.py).
    Soporta ?q= y ?limit=."""
    user = _require_admin(request)
    if isinstance(user, JSONResponse):
        return user
    # 2026-05-05 P0 IDOR FIX (sync-guardian audit): filtro explícito taller_id
    taller_id = user.get('taller_id')
    if not taller_id:
        return json_err('taller_id ausente en sesión', 401)
    db = get_db()
    try:
        q = request.query_params.get('q', '') or ''
        try:
            limit = max(1, min(500, int(request.query_params.get('limit', '200'))))
        except (ValueError, TypeError):
            limit = 200
        query = db.query(Cliente).filter(Cliente.taller_id == taller_id)
        if q:
            query = query.filter(
                Cliente.nombre.ilike(f'%{q}%') |
                Cliente.apellidos.ilike(f'%{q}%') |
                Cliente.telefono.ilike(f'%{q}%') |
                Cliente.documento.ilike(f'%{q}%') |
                Cliente.id.ilike(f'%{q}%')
            )
        clientes = query.order_by(Cliente.nombre).limit(limit).all()
        return json_ok([{
            'id': c.id,
            'nombre': f'{c.nombre or ""} {c.apellidos or ""}'.strip(),
            'nombre_raw': c.nombre,
            'apellidos': c.apellidos or '',
            'telefono': c.telefono or '',
            'email': c.email or '',
            'direccion': c.direccion or '',
            'ciudad': getattr(c, 'ciudad', '') or '',
            'tipo': getattr(c, 'tipo', '') or '',
            'documento': (getattr(c, 'documento', '') or ''),
        } for c in clientes])
    finally:
        db.close()


async def api_cliente_create(request: Request) -> JSONResponse:
    user = _require_admin(request)
    if isinstance(user, JSONResponse):
        return user
    try:
        body = await request.json()
    except Exception:
        return json_err('Body inválido')
    db = get_db()
    try:
        if db.query(Cliente).filter_by(id=body.get('id', '')).first():
            return json_err('DNI/RUC ya existe')
        c = Cliente(
            id=body['id'], nombre=body['nombre'],
            apellidos=body.get('apellidos', ''),
            telefono=body.get('telefono', ''),
            email=body.get('email', ''),
            direccion=body.get('direccion', ''),
        )
        db.add(c)
        db.commit()
        return json_ok({'ok': True, 'id': c.id}, 201)
    except Exception as e:
        db.rollback()
        return json_err(str(e))
    finally:
        db.close()


async def api_vehiculos_list(request: Request) -> JSONResponse:
    user = _require_admin(request)
    if isinstance(user, JSONResponse):
        return user
    # 2026-05-05 P0 IDOR FIX (sync-guardian audit): filtro taller_id + campos
    # adicionales para sincronizar con admin SPA PC (color, conductor, año).
    taller_id = user.get('taller_id')
    if not taller_id:
        return json_err('taller_id ausente en sesión', 401)
    db = get_db()
    try:
        vehiculos = (db.query(Vehiculo)
                     .filter(Vehiculo.taller_id == taller_id)
                     .order_by(Vehiculo.placa)
                     .limit(200).all())
        return json_ok([{
            'placa': v.placa, 'marca': v.marca,
            'modelo': v.modelo,
            'año': getattr(v, 'año', getattr(v, 'anio', '')) or '',
            'anio': getattr(v, 'año', getattr(v, 'anio', '')) or '',
            'color': getattr(v, 'color', '') or '',
            'tipo': getattr(v, 'tipo', '') or '',
            'cliente_id': v.cliente_id,
            'conductor_nombre': getattr(v, 'conductor_nombre', '') or '',
            'conductor_telefono': getattr(v, 'conductor_telefono', '') or '',
            'conductor_dni': getattr(v, 'conductor_dni', '') or '',
            'conductor_activo': bool(getattr(v, 'conductor_activo', True)),
        } for v in vehiculos])
    finally:
        db.close()


async def api_vehiculo_create(request: Request) -> JSONResponse:
    """POST /api/vehiculos/nuevo"""
    user = _require_admin(request)
    if isinstance(user, JSONResponse):
        return user
    try:
        body = await request.json()
    except Exception:
        return json_err('Body inválido')
    db = get_db()
    try:
        placa = (body.get('placa') or '').strip().upper()
        if not placa:
            return json_err('Placa es obligatoria')
        if db.query(Vehiculo).filter_by(placa=placa).first():
            return json_err('Placa ya registrada')
        kw = dict(
            placa=placa,
            cliente_id=body.get('cliente_id') or None,
            marca=body.get('marca', ''),
            modelo=body.get('modelo', ''),
            color=body.get('color', ''),
            tipo=body.get('tipo', 'Sedán'),
        )
        # Soporte para campo año con o sin tilde
        año_val = str(body.get('año', body.get('anio', '')))
        try:
            setattr(Vehiculo, '__test__', None)  # dummy
            v = Vehiculo(**kw)
            try: v.año = año_val
            except Exception: pass
            try: v.anio = año_val
            except Exception: pass
        except Exception:
            v = Vehiculo(**kw)
        db.add(v)
        db.commit()
        return json_ok({'ok': True, 'placa': placa}, 201)
    except Exception as e:
        db.rollback()
        return json_err(str(e))
    finally:
        db.close()


async def api_cliente_mis_ordenes(request: Request) -> JSONResponse:
    user = _require_auth(request)
    if isinstance(user, JSONResponse):
        return user
    rol = user.get('rol')
    if rol not in ('cliente', 'conductor'):
        return json_err('Solo para clientes o conductores', 403)
    db = get_db()
    try:
        # CRITICAL: setear GUC app.taller_id para que RLS deje pasar las queries
        # a vehiculos (necesario para devolver datos del conductor asignado).
        taller_id = int(user.get('taller_id') or 1)
        _setup_flota_ctx(db, taller_id)
        if rol == 'conductor':
            placa = (user.get('placa') or '').strip()
            if not placa:
                return json_err('Conductor sin placa asignada', 400)
            ordenes = db.query(Orden).filter_by(
                vehiculo_placa=placa
            ).order_by(Orden.fecha.desc()).all()
        else:
            ordenes = db.query(Orden).filter_by(
                cliente_id=user['id']
            ).order_by(Orden.fecha.desc()).all()
        result = []
        for o in ordenes:
            veh = db.query(Vehiculo).filter_by(placa=o.vehiculo_placa).first() if o.vehiculo_placa else None
            # Parsear campos JSON que SQLAlchemy puede devolver como string
            def _parse(val, default):
                if val is None: return default
                if isinstance(val, (list, dict)): return val
                if isinstance(val, str):
                    try: return json.loads(val)
                    except: return default
                return default
            items = _parse(o.items_cotizacion, [])
            fotos = _parse(o.fotos_evidencia, [])
            checklist = _parse(o.checklist_reparacion, {})
            dd = checklist.get('diagnostic_details', {}) if isinstance(checklist, dict) else {}
            scanner_path = dd.get('scanner_path', '') if isinstance(dd, dict) else ''
            result.append({
                'id': o.consecutivo,
                'consecutivo': o.consecutivo,
                'fecha': str(o.fecha or ''),
                'estado': o.estado or '',
                'vehiculo_placa': o.vehiculo_placa or '',
                'vehiculo_marca': veh.marca if veh else '',
                'vehiculo_modelo': veh.modelo if veh else '',
                'vehiculo_anio': str(getattr(veh, 'año', '') or '') if veh else '',
                'vehiculo_color': (veh.color or '') if veh else '',
                'conductor_nombre':   (getattr(veh, 'conductor_nombre', '') or '') if veh else '',
                'conductor_dni':      (getattr(veh, 'conductor_dni', '') or '') if veh else '',
                'conductor_telefono': (getattr(veh, 'conductor_telefono', '') or '') if veh else '',
                'conductor_email':    (getattr(veh, 'conductor_email', '') or '') if veh else '',
                'conductor_activo':   bool(getattr(veh, 'conductor_activo', True)) if veh else False,
                'has_conductor':      bool(getattr(veh, 'conductor_nombre', '')) if veh else False,
                'updated_at': str(getattr(o, 'updated_at', None) or getattr(o, 'fecha_dt', None) or o.fecha or ''),
                'motivo': o.motivo or '',
                'descripcion': o.motivo or '',
                'tecnico': o.tecnico or '',
                'km': o.km or '',
                'diagnostico': o.diagnostico or '',
                'observaciones': o.observaciones or '',
                'items_cotizacion': items,
                'fotos_evidencia': fotos,
                'factura_sunat': getattr(o, 'factura_sunat', '') or '',
                'checklist_reparacion': checklist,
                'quality_control': checklist.get('quality_control',{}) if isinstance(checklist,dict) else {},
                'repair_logs': checklist.get('repair_logs',[]) if isinstance(checklist,dict) else [],
                'findings': checklist.get('findings',[]) if isinstance(checklist,dict) else [],
                'quick_check': checklist.get('quick_check',{}) if isinstance(checklist,dict) else {},
                                'scanner_path': scanner_path,
                'notas_entrega': o.notas_entrega or '',
                'evidence_cats': checklist.get('evidence_cats', {}) if isinstance(checklist, dict) else {},
                'repair_logs': checklist.get('repair_logs', []) if isinstance(checklist, dict) else [],
                'quality_control': checklist.get('quality_control', {}) if isinstance(checklist, dict) else {},
                'proximo_mantenimiento': o.proximo_mantenimiento or '',
                'report_token': o.report_token or '',
                'approval_token': (lambda t: '' if (not t or str(t).startswith('USED_')) else str(t))(getattr(o, 'approval_token', None)),
                'approval_status': (str(o.approval_status).lower() if o.approval_status else ''),
                'approval_date': str(o.approval_date or ''),
                'total': sum(
                    (float(it.get('total') or it.get('subtotal') or
                           (float(it.get('cantidad', 1) or 1) * float(it.get('precio_unitario', 0) or 0)))
                     for it in items if isinstance(it, dict)
                     and str(it.get('categoria') or '') not in ('Resumen','Impuesto','Total')),
                    0.0,
                ),
                'monto_cobrado': float(o.monto_cobrado or 0),
            })
        return json_ok(result)
    finally:
        db.close()


async def api_cliente_mis_citas(request: Request) -> JSONResponse:
    user = _require_auth(request)
    if isinstance(user, JSONResponse):
        return user
    db = get_db()
    try:
        taller_id = int(user.get('taller_id') or 1)
        _setup_flota_ctx(db, taller_id)
        placa = user.get('placa', '')
        citas = db.query(Cita).filter_by(
            cliente_id=user['id']
        ).order_by(Cita.id.desc()).limit(20).all()
        return json_ok([{
            'id': c.id, 'fecha': c.fecha_cita,
            'descripcion': c.motivo or '',
            'estado': c.estado or '',
        } for c in citas])
    finally:
        db.close()


async def api_cliente_aprobar(request: Request) -> JSONResponse:
    """POST /api/cliente/aprobar  {consecutivo, aprobado: true|false}"""
    user = _require_auth(request)
    if isinstance(user, JSONResponse):
        return user
    try:
        body = await request.json()
    except Exception:
        return json_err('Body inválido')
    db = get_db()
    try:
        cons = body.get('consecutivo') or body.get('orden_id', '')
        _t_id = int(user.get('taller_id') or 1)
        try:
            _setup_flota_ctx(db, _t_id)
        except Exception:
            pass
        o = db.query(Orden).filter_by(consecutivo=str(cons), taller_id=_t_id).first()
        if not o:
            return json_err('Orden no encontrada', 404)
        if o.cliente_id != user['id']:
            return json_err('No autorizado', 403)
        if (o.approval_status or '') == 'aprobado':
            return json_err('Esta cotización ya fue aprobada', 400)
        if (o.estado or '').upper() not in ('APROBACIÓN', 'APROBACION', 'REPUESTOS'):
            return json_err('La orden no está pendiente de aprobación', 400)
        aprobado = body.get('aprobado', True)
        o.estado = 'REPARACIÓN' if aprobado else 'ARCHIVADO'
        o.approval_status = 'aprobado' if aprobado else 'rechazado'
        o.approval_date = datetime.now().strftime('%Y-%m-%d %H:%M')
        db.commit()
        return json_ok({'ok': True, 'estado': o.estado})
    except Exception as e:
        db.rollback()
        return json_err(str(e))
    finally:
        db.close()


async def api_portal_notificaciones(request: Request) -> JSONResponse:
    """GET /api/portal/notificaciones"""
    user = _require_auth(request)
    if isinstance(user, JSONResponse): return user
    
    from utils.notifications import get_client_notifications
    # Nota: la placa ya no es estrictamente necesaria si buscamos por cliente_id
    notifs = get_client_notifications(user['id'], '')
    return json_ok(notifs)


async def api_portal_marcar_leidas(request: Request) -> JSONResponse:
    """POST /api/portal/notificaciones/marcar-leidas {ids: []}"""
    user = _require_auth(request)
    if isinstance(user, JSONResponse): return user
    try:
        body = await request.json()
        ids = body.get('ids', [])
    except: return json_err('Body inválido')
    
    from utils.notifications import marcar_notifs_leidas_cliente
    marcar_notifs_leidas_cliente(user['id'], ids)
    return json_ok({'ok': True})


async def api_cliente_historial_pagos(request):
    user = _require_auth(request)
    if isinstance(user, JSONResponse): return user
    if user.get("rol") != "cliente": return json_err("Solo clientes", 403)
    db = get_db()
    try:
        import json as _j
        placa = user.get("placa","")
        ordenes = db.query(Orden).filter_by(vehiculo_placa=placa).all()
        pagos_all = []
        for o in ordenes:
            pagos = o.pagos or []
            if isinstance(pagos, str):
                try: pagos = _j.loads(pagos)
                except: pagos = []
            items = o.items_cotizacion or []
            if isinstance(items, str):
                try: items = _j.loads(items)
                except: items = []
            presupuesto = sum(float(it.get("total",0) or 0) for it in (items if isinstance(items,list) else []))
            for p in (pagos if isinstance(pagos, list) else []):
                pagos_all.append({"consecutivo": o.consecutivo, "motivo": o.motivo or "",
                    "estado": o.estado or "", "presupuesto": presupuesto,
                    "fecha": p.get("fecha",""), "monto": float(p.get("monto",0)),
                    "metodo": p.get("metodo",""), "nota": p.get("nota","")})
        pagos_all.sort(key=lambda x: x.get("fecha",""), reverse=True)
        return json_ok({"pagos": pagos_all})
    finally:
        db.close()


async def api_cliente_aprobar_portal(request: Request):
    user = _require_auth(request)
    if isinstance(user, JSONResponse): return user
    if user.get("rol") != "cliente": return json_err("Solo clientes", 403)
    try:
        body = await request.json()
        consecutivo = body.get("consecutivo","")
        decision = body.get("decision","")
        comentario = body.get("comentario","")
        if decision not in ("aprobado","rechazado"): return json_err("decision invalida", 400)
        db = get_db()
        try:
            # Filtrar por cliente_id (no placa) — un cliente puede tener varios vehículos.
            o = db.query(Orden).filter_by(consecutivo=consecutivo, cliente_id=user.get("id","")).first()
            if not o: return json_err("Orden no encontrada", 404)
            if o.approval_status in ("aprobado","rechazado"): return json_err("Ya fue respondido", 409)
            import secrets as _sec
            o.approval_status = decision
            o.approval_date = datetime.now().strftime("%Y-%m-%d %H:%M")
            o.approval_token = "USED_" + _sec.token_hex(8)
            if decision == "aprobado":
                if o.estado in ("RECEPCION","RECEPCIóN","RECEPCIÓN"): o.estado = "DIAGNÓSTICO"
                else: o.estado = "REPARACIÓN"
            log_actividad("Cliente aprobo orden " + consecutivo + " via portal", "ordenes")
            taller_id_o = int(getattr(o, 'taller_id', None) or user.get('taller_id') or 1)
            db.commit()
            # Push: avisar al conductor que el jefe aprobó
            try:
                from utils.flota import notify_orden_event
                notify_orden_event(db, taller_id=taller_id_o, consecutivo=consecutivo,
                                   evento=('aprobado' if decision == 'aprobado' else 'rechazado'))
            except Exception:
                pass
            return json_ok({"ok": True, "estado": o.estado, "decision": decision})
        finally:
            db.close()
    except Exception as e:
        return json_err(str(e))


async def api_cliente_calificar(request: Request):
    user = _require_auth(request)
    if isinstance(user, JSONResponse): return user
    if user.get("rol") != "cliente": return json_err("Solo clientes", 403)
    try:
        body = await request.json()
        consecutivo = body.get("consecutivo","")
        estrellas = int(body.get("estrellas", 0))
        comentario = body.get("comentario","")
        if not (1 <= estrellas <= 5): return json_err("estrellas 1-5", 400)
        db = get_db()
        try:
            o = db.query(Orden).filter_by(consecutivo=consecutivo, cliente_id=user.get("id","")).first()
            if not o: return json_err("Orden no encontrada", 404)
            import json as _j
            enc = o.encuesta or {}
            if isinstance(enc, str):
                try: enc = _j.loads(enc)
                except: enc = {}
            enc["estrellas"] = estrellas; enc["comentario"] = comentario
            enc["fecha_calificacion"] = datetime.now().strftime("%Y-%m-%d %H:%M")
            o.encuesta = enc; db.commit()
            return json_ok({"ok": True})
        finally:
            db.close()
    except Exception as e:
        return json_err(str(e))


async def api_cliente_presupuesto_pdf(request: Request):
    """GET /api/cliente/ordenes/{id}/presupuesto.pdf — PDF presupuesto con firma del titular."""
    from starlette.responses import FileResponse
    user = _require_auth(request)
    if isinstance(user, JSONResponse):
        return user
    orden_id = request.path_params.get('id', '')
    if not orden_id:
        return json_err('Consecutivo vacio', 400)
    db = get_db()
    try:
        taller_id = int(user.get('taller_id') or 1)
        try:
            _setup_flota_ctx(db, taller_id)
        except Exception:
            pass
        rol = user.get('rol')
        if rol == 'cliente':
            o = db.query(Orden).filter_by(consecutivo=orden_id, cliente_id=user.get('id', '')).first()
        elif rol == 'conductor':
            o = db.query(Orden).filter_by(consecutivo=orden_id, vehiculo_placa=user.get('placa', '')).first()
        else:
            o = db.query(Orden).filter_by(consecutivo=orden_id, taller_id=taller_id).first()
        if not o:
            return json_err('Orden no encontrada', 404)
        try:
            # Generar PDF de cotización usando generate_pdf (mismo método que approval.py)
            from utils.pdf_generator import generate_pdf
            from utils.models import Cliente, Vehiculo
            c_obj = db.query(Cliente).filter_by(id=o.cliente_id).first() if o.cliente_id else None
            v_obj = db.query(Vehiculo).filter_by(placa=o.vehiculo_placa).first() if o.vehiculo_placa else None
            o_dict = {col.name: getattr(o, col.name) for col in o.__table__.columns}
            o_dict['fotos_evidencia'] = o.fotos_evidencia
            c_dict = {col.name: getattr(c_obj, col.name) for col in c_obj.__table__.columns} if c_obj else {}
            v_dict = {col.name: getattr(v_obj, col.name) for col in v_obj.__table__.columns} if v_obj else {}
            import os as _os
            _os.makedirs('pdfs', exist_ok=True)
            pdf_path = 'pdfs/Presupuesto_' + str(orden_id).replace('/','_').replace('#','') + '.pdf'
            generate_pdf(o_dict, c_dict, v_dict, 'cotizacion', pdf_path)
        except Exception as e:
            import traceback
            traceback.print_exc()
            return json_err('Error generando presupuesto: ' + str(e), 500)
        if not _os_path_exists(pdf_path):
            return json_err('PDF no generado', 500)
        return FileResponse(pdf_path, media_type='application/pdf', filename='Presupuesto_' + orden_id + '.pdf')
    finally:
        db.close()


async def api_admin_nuevas_ordenes(request):
    user = _require_admin(request)
    if isinstance(user, JSONResponse): return user
    db = get_db()
    try:
        desde = request.query_params.get("desde", "")
        q = db.query(Orden).filter(Orden.estado != "ARCHIVADO")
        if desde: q = q.filter(Orden.fecha > desde)
        nuevas = q.order_by(Orden.fecha.desc()).limit(10).all()
        result = [{"consecutivo": o.consecutivo, "fecha": str(o.fecha or "")[:16],
                   "placa": o.vehiculo_placa or "", "motivo": (o.motivo or "")[:60],
                   "estado": o.estado or ""} for o in nuevas]
        return json_ok({"ordenes": result, "count": len(result)})
    finally:
        db.close()



# === CODART LOOKUP (RUC/DNI) ===
import os as _os_codart
import time as _time_codart
try:
    import requests as _req_codart
except Exception:
    _req_codart = None

_CODART_BASE = "https://api-codart.cgrt.org/api/v1/consultas"
_CODART_TTL = 24 * 3600
_codart_cache: dict = {}


async def api_cliente_cambiar_pin(request: Request) -> JSONResponse:
    actor_tipo, actor_id, ip, user = _flota_actor_meta(request)
    if isinstance(user, JSONResponse): return user
    rol = user.get('rol')
    if rol not in ('cliente', 'conductor'):
        return json_err('Solo cliente o conductor', 403)
    try: body = await request.json()
    except: return json_err('Body inválido', 400)
    actual = str(body.get('actual') or '')
    nuevo = str(body.get('nuevo') or '').strip()
    if len(nuevo) < 4 or len(nuevo) > 32:
        return json_err('Nuevo PIN: entre 4 y 32 caracteres', 400)
    taller_id = int(user.get('taller_id') or 1)
    db = get_db()
    try:
        _setup_flota_ctx(db, taller_id)
        if rol == 'cliente':
            row = db.execute(_sa_text("SELECT pin_acceso, documento FROM clientes WHERE id=:c AND taller_id=:t"),
                             {'c': user['id'], 't': taller_id}).fetchone()
            if not row: return json_err('Cliente no encontrado', 404)
            pin_actual_hash, doc = row[0] or '', row[1] or ''
            if pin_actual_hash:
                if not verify_password(actual, pin_actual_hash):
                    return json_err('PIN actual incorrecto', 401)
            else:
                if actual.strip() != str(doc).strip():
                    return json_err('PIN actual incorrecto', 401)
            from utils.flota import cliente_change_password
            cliente_change_password(db, taller_id=taller_id, cliente_id=user['id'],
                                    new_password=nuevo, bcrypt_hash=hash_password, ip=ip)
        else:
            placa = user.get('placa', '')
            row = db.execute(_sa_text("""
                SELECT v.conductor_pin_hash, c.documento
                  FROM vehiculos v
                  LEFT JOIN clientes c ON c.id = v.cliente_id AND c.taller_id = v.taller_id
                 WHERE v.placa=:p AND v.taller_id=:t
            """), {'p': placa, 't': taller_id}).fetchone()
            if not row: return json_err('Vehículo no encontrado', 404)
            pin_actual_hash, doc = row[0] or '', row[1] or ''
            if pin_actual_hash:
                if not verify_password(actual, pin_actual_hash):
                    return json_err('PIN actual incorrecto', 401)
            else:
                if actual.strip() != str(doc).strip():
                    return json_err('PIN actual incorrecto', 401)
            from utils.flota import conductor_change_pin
            conductor_change_pin(db, taller_id=taller_id, placa=placa,
                                 new_pin=nuevo, bcrypt_hash=hash_password, ip=ip)
        return json_ok({'ok': True})
    except ValueError as e:
        return json_err(str(e), 400)
    finally:
        db.close()


async def api_cliente_perfil_completo(request: Request) -> JSONResponse:
    """GET /api/clientes/{id}/perfil-completo — cliente + vehiculos + ordenes + total"""
    user = _require_admin(request)
    if isinstance(user, JSONResponse):
        return user
    cliente_id = request.path_params.get('id', '')
    db = get_db()
    try:
        cli = db.query(Cliente).filter_by(id=cliente_id).first()
        if not cli:
            return json_err('Cliente no encontrado', 404)
        vehiculos = db.query(Vehiculo).filter_by(cliente_id=cliente_id).all()
        total_pagado = 0
        vehiculos_data = []
        for v in vehiculos:
            ordenes = db.query(Orden).filter_by(vehiculo_placa=v.placa).order_by(Orden.fecha.desc()).all()
            ordenes_data = []
            total_vehiculo = 0
            for o in ordenes:
                items = o.items_cotizacion or []
                if isinstance(items, str):
                    try:
                        import json as _json
                        items = _json.loads(items)
                    except: items = []
                total_ord = sum(float(it.get('total', 0) or 0) for it in (items if isinstance(items, list) else []))
                total_vehiculo += total_ord
                ordenes_data.append({
                    'consecutivo': o.consecutivo,
                    'fecha': str(o.fecha or '')[:10],
                    'estado': o.estado or '',
                    'motivo': o.motivo or '',
                    'tecnico': o.tecnico or '',
                    'total': total_ord,
                })
            total_pagado += total_vehiculo
            vehiculos_data.append({
                'placa': v.placa,
                'marca': v.marca or '',
                'modelo': v.modelo or '',
                'tipo': v.tipo or '',
                'total_pagado': total_vehiculo,
                'ordenes': ordenes_data,
            })
        return json_ok({
            'id': cli.id,
            'nombre': cli.nombre or '',
            'apellidos': getattr(cli, 'apellidos', '') or '',
            'telefono': getattr(cli, 'telefono', '') or '',
            'email': getattr(cli, 'email', '') or '',
            'direccion': getattr(cli, 'direccion', '') or '',
            'total_pagado': total_pagado,
            'n_vehiculos': len(vehiculos),
            'vehiculos': vehiculos_data,
        })
    finally:
        db.close()


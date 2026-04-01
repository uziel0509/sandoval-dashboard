"""
SANDOVAL Dashboard - REST API Service
Provee endpoints JSON para la PWA móvil (Admin + Cliente)
Token-based auth (secrets token stored in memory)
"""

import secrets
import hashlib
from datetime import datetime, timedelta
from typing import Optional

from starlette.requests import Request
from starlette.responses import JSONResponse

from utils.models import (
    get_db, Usuario, Cliente, Vehiculo, ItemInventario,
    Orden, Cita, NotaVenta, Proveedor, log_actividad,
    verify_password, hash_password
)

# ──────────────────────────────────────────────────────────────────────────────
# Token store en SQLite (persistente entre reinicios)
# ──────────────────────────────────────────────────────────────────────────────
import sqlite3 as _sqlite3
import json as _json
import os as _os

TOKEN_TTL_MINUTES = 60 * 8  # 8 horas
_SESSIONS_DB = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), 'data', 'sessions.db')

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
    conn = _get_sessions_db()
    try:
        row = conn.execute('SELECT user_json, expires FROM sessions WHERE token=?', (token,)).fetchone()
        if not row:
            return None
        if datetime.now() > datetime.fromisoformat(row[1]):
            conn.execute('DELETE FROM sessions WHERE token=?', (token,))
            conn.commit()
            return None
        # Renovar TTL
        new_exp = (datetime.now() + timedelta(minutes=TOKEN_TTL_MINUTES)).isoformat()
        conn.execute('UPDATE sessions SET expires=? WHERE token=?', (new_exp, token))
        conn.commit()
        return _json.loads(row[0])
    finally:
        conn.close()


def _extract_token(request: Request) -> Optional[str]:
    auth = request.headers.get('Authorization', '')
    if auth.startswith('Bearer '):
        return auth[7:]
    return request.cookies.get('sandoval_api_token')


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


def _cors(response: JSONResponse) -> JSONResponse:
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Authorization, Content-Type'
    return response


def json_ok(data, status=200) -> JSONResponse:
    return _cors(JSONResponse(data, status_code=status))


def json_err(msg, status=400) -> JSONResponse:
    return _cors(JSONResponse({'error': msg}, status_code=status))


# ──────────────────────────────────────────────────────────────────────────────
# AUTH
# ──────────────────────────────────────────────────────────────────────────────

async def api_login(request: Request) -> JSONResponse:
    """POST /api/auth/login  {username, password, tipo: 'staff'|'cliente', placa?}"""
    try:
        body = await request.json()
    except Exception:
        return json_err('Body JSON inválido')

    tipo = body.get('tipo', 'staff')
    db = get_db()
    try:
        if tipo == 'staff':
            username = (body.get('username') or '').strip()
            password = body.get('password') or ''
            user = db.query(Usuario).filter_by(username=username, activo=True).first()
            if not user or not verify_password(password, user.password_hash):
                return json_err('Usuario o contraseña incorrectos', 401)
            user.ultimo_login = datetime.now()
            db.commit()
            user_dict = {
                'id': user.id, 'username': user.username,
                'nombre': user.nombre, 'rol': user.rol,
                'email': user.email or '', 'tipo': 'empleado',
            }
            token = _new_token(user_dict)
            return json_ok({'token': token, 'user': user_dict})

        else:  # cliente
            placa = (body.get('placa') or '').strip().upper()
            password = (body.get('password') or '').strip()
            v = db.query(Vehiculo).filter_by(placa=placa).first()
            if not v:
                return json_err('Placa no registrada', 401)
            cliente = db.query(Cliente).filter_by(id=v.cliente_id).first()
            if not cliente:
                return json_err('Cliente no encontrado', 401)
            ok = False
            if cliente.pin_acceso:
                ok = verify_password(password, cliente.pin_acceso)
            else:
                # Contraseña inicial = DNI/RUC. Al primer login correcto, hashearla.
                ok = (password == str(cliente.id))
                if ok:
                    cliente.pin_acceso = hash_password(password)
                    db.commit()
            if not ok:
                return json_err('Contraseña incorrecta', 401)
            user_dict = {
                'id': cliente.id, 'nombre': f'{cliente.nombre} {cliente.apellidos}'.strip(),
                'rol': 'cliente', 'placa': placa, 'tipo': 'cliente',
            }
            token = _new_token(user_dict)
            return json_ok({'token': token, 'user': user_dict})
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
    return json_ok({'ok': True})


# ──────────────────────────────────────────────────────────────────────────────
# DASHBOARD
# ──────────────────────────────────────────────────────────────────────────────

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
                for est in ['RECEPCIÓN', 'DIAGNÓSTICO', 'REPUESTOS', 'COTIZACIÓN',
                            'APROBACIÓN', 'REPARACIÓN', 'CONTROL CALIDAD', 'ARCHIVADO']
            },
        })
    finally:
        db.close()


# ──────────────────────────────────────────────────────────────────────────────
# ÓRDENES
# ──────────────────────────────────────────────────────────────────────────────

async def api_ordenes_list(request: Request) -> JSONResponse:
    user = _require_admin(request)
    if isinstance(user, JSONResponse):
        return user
    db = get_db()
    try:
        estado = request.query_params.get('estado')
        q = db.query(Orden).order_by(Orden.fecha.desc())
        if estado:
            q = q.filter(Orden.estado == estado)
        ordenes = q.limit(500).all()
        data = []
        for o in ordenes:
            cli = db.query(Cliente).filter_by(id=o.cliente_id).first()
            data.append({
                'id': o.consecutivo,
                'consecutivo': o.consecutivo,
                'fecha': str(o.fecha or ''),
                'estado': o.estado,
                'cliente_nombre': f'{cli.nombre} {cli.apellidos}'.strip() if cli else '—',
                'vehiculo_placa': o.vehiculo_placa or '',
                'descripcion': o.motivo or '',
            })
        return json_ok(data)
    finally:
        db.close()



async def api_orden_get(request: Request) -> JSONResponse:
    user = _require_admin(request)
    if isinstance(user, JSONResponse):
        return user
    cons = request.path_params.get('id', '')
    db = get_db()
    try:
        o = db.query(Orden).filter_by(consecutivo=cons).first()
        if not o:
            return json_err('Orden no encontrada', 404)
        cli = db.query(Cliente).filter_by(id=o.cliente_id).first()
        veh = db.query(Vehiculo).filter_by(placa=o.vehiculo_placa).first() if o.vehiculo_placa else None
        return json_ok({
            'id': o.consecutivo,
            'consecutivo': o.consecutivo,
            'fecha': str(o.fecha or ''), 'estado': o.estado,
            'cliente_id': o.cliente_id,
            'cliente_nombre': f'{cli.nombre} {cli.apellidos}'.strip() if cli else '—',
            'cliente_telefono': cli.telefono if cli else '',
            'vehiculo_placa': o.vehiculo_placa or '',
            'vehiculo_marca': veh.marca if veh else '',
            'vehiculo_modelo': veh.modelo if veh else '',
            'descripcion': o.motivo or '',
            'km': o.km or '',
            'tecnico': o.tecnico or '',
            'tipo': o.tipo or 'Express',
            'items': o.items_cotizacion or [],
            'observaciones': o.observaciones or '',
            'diagnostico': o.diagnostico or '',
            'fotos_evidencia': o.fotos_evidencia or [],
            'checklist_reparacion': o.checklist_reparacion or [],
            'notas_entrega': o.notas_entrega or '',
            'proximo_mantenimiento': o.proximo_mantenimiento or '',
            'motivo': o.motivo or '',
            'factura_sunat': o.factura_sunat or '',
        })
    finally:
        db.close()



async def api_orden_estado(request: Request) -> JSONResponse:
    """PUT /api/ordenes/{id}/estado  {estado: ...}"""
    user = _require_auth(request)
    if isinstance(user, JSONResponse):
        return user
    # Clientes no pueden cambiar estado de órdenes directamente
    if user.get('rol') == 'cliente':
        return json_err('Acceso denegado', 403)
    cons = request.path_params.get('id', '')
    try:
        body = await request.json()
    except Exception:
        return json_err('Body inválido')
    nuevo_estado = body.get('estado', '').strip()
    db = get_db()
    try:
        o = db.query(Orden).filter_by(consecutivo=cons).first()
        if not o:
            return json_err('Orden no encontrada', 404)
        o.estado = nuevo_estado
        db.commit()
        return json_ok({'ok': True, 'estado': nuevo_estado})
    except Exception as e:
        db.rollback()
        return json_err(str(e))
    finally:
        db.close()


async def api_orden_create(request: Request) -> JSONResponse:
    """POST /api/ordenes/nueva — admin Y cliente pueden crear"""
    user = _require_auth(request)
    if isinstance(user, JSONResponse):
        return user
    try:
        body = await request.json()
    except Exception:
        return json_err('Body inválido')
    db = get_db()
    try:
        # Generar consecutivo
        now = datetime.now()
        consecutivo = f'#ODS-{now.strftime("%Y%m%d-%H%M")}'
        # Si ya existe ese consecutivo, agregar segundos
        existing = db.query(Orden).filter_by(consecutivo=consecutivo).first()
        if existing:
            consecutivo = f'#ODS-{now.strftime("%Y%m%d-%H%M%S")}'
        o = Orden(
            consecutivo=consecutivo,
            fecha=now.strftime('%Y-%m-%d %H:%M'),
            cliente_id=body.get('cliente_id') or None,
            vehiculo_placa=body.get('vehiculo_placa') or None,
            motivo=body.get('motivo', ''),
            km=body.get('km', ''),
            tecnico=body.get('tecnico', ''),
            tipo=body.get('tipo', 'Express'),
            observaciones=body.get('observaciones', ''),
            estado='RECEPCIÓN',
            approval_token=secrets.token_hex(16),
            report_token=secrets.token_hex(16),
        )
        db.add(o)
        db.commit()
        log_actividad(f'Nueva orden {consecutivo} creada desde app', 'api')
        return json_ok({'ok': True, 'consecutivo': consecutivo}, 201)
    except Exception as e:
        db.rollback()
        return json_err(str(e))
    finally:
        db.close()


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


async def api_orden_evidencia(request: Request) -> JSONResponse:
    """POST /api/ordenes/{id}/evidencia - sube foto/video de evidencia"""
    user = _require_admin(request)
    if isinstance(user, JSONResponse):
        return user
    cons = request.path_params.get('id', '')
    import os
    try:
        form = await request.form()
        file = form.get('file')
        if not file:
            return json_err('Sin archivo')
        # Validar tamaño máximo: 50 MB
        content = await file.read()
        MAX_SIZE = 50 * 1024 * 1024
        if len(content) > MAX_SIZE:
            return json_err('Archivo demasiado grande (máx. 50 MB)')
        # Extensión real del archivo
        ext = 'jpg'
        orig_name = getattr(file, 'filename', '') or ''
        if '.' in orig_name:
            ext = orig_name.rsplit('.', 1)[-1].lower()
        # Detectar tipo: video o foto
        content_type = getattr(file, 'content_type', '') or ''
        is_video = content_type.startswith('video/') or ext in ('mp4','mov','webm','3gp','avi','mkv')
        tipo = 'video' if is_video else 'foto'
        # Fase enviada desde el cliente (faseId del formulario)
        fase = (form.get('fase') or 'RECEPCION').strip()
        # Limpiar consecutivo para nombre de archivo
        cons_safe = cons.replace('#','').replace('/','-').replace(' ','_')
        filename = f"{cons_safe}_{fase}_{secrets.token_hex(4)}.{ext}"
        # Guardar en static/evidencia/
        os.makedirs('static/evidencia', exist_ok=True)
        filepath = os.path.join('static', 'evidencia', filename)
        with open(filepath, 'wb') as f:
            f.write(content)
        # URL pública accesible
        url = f"/evidencia/{filename}"
        # Guardar en BD
        db = get_db()
        try:
            o = db.query(Orden).filter_by(consecutivo=cons).first()
            if o:
                fotos = list(o.fotos_evidencia or [])
                fotos.append({'path': url, 'fase': fase, 'tipo': tipo})
                o.fotos_evidencia = fotos
                db.commit()
        finally:
            db.close()
        return json_ok({'ok': True, 'url': url, 'tipo': tipo, 'fase': fase})
    except Exception as e:
        return json_err(str(e))




# ──────────────────────────────────────────────────────────────────────────────
# CLIENTES
# ──────────────────────────────────────────────────────────────────────────────

async def api_clientes_list(request: Request) -> JSONResponse:
    user = _require_admin(request)
    if isinstance(user, JSONResponse):
        return user
    db = get_db()
    try:
        q = request.query_params.get('q', '')
        query = db.query(Cliente)
        if q:
            query = query.filter(
                Cliente.nombre.ilike(f'%{q}%') |
                Cliente.apellidos.ilike(f'%{q}%') |
                Cliente.id.ilike(f'%{q}%')
            )
        clientes = query.order_by(Cliente.nombre).limit(50).all()
        return json_ok([{
            'id': c.id, 'nombre': c.nombre, 'apellidos': c.apellidos,
            'telefono': c.telefono or '', 'email': c.email or '',
            'direccion': c.direccion or '',
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


# ──────────────────────────────────────────────────────────────────────────────
# VEHÍCULOS
# ──────────────────────────────────────────────────────────────────────────────

async def api_vehiculos_list(request: Request) -> JSONResponse:
    user = _require_admin(request)
    if isinstance(user, JSONResponse):
        return user
    db = get_db()
    try:
        vehiculos = db.query(Vehiculo).order_by(Vehiculo.placa).limit(100).all()
        return json_ok([{
            'placa': v.placa, 'marca': v.marca,
            'modelo': v.modelo, 'año': getattr(v, 'áño', getattr(v, 'anio', '')),
            'cliente_id': v.cliente_id,
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



# ──────────────────────────────────────────────────────────────────────────────
# INVENTARIO
# ──────────────────────────────────────────────────────────────────────────────

async def api_inventario_list(request: Request) -> JSONResponse:
    user = _require_auth(request)
    if isinstance(user, JSONResponse):
        return user
    db = get_db()
    try:
        items = db.query(ItemInventario).order_by(ItemInventario.nombre).all()
        return json_ok([{
            'codigo': i.codigo, 'nombre': i.nombre,
            'categoria': i.categoria, 'tipo': i.tipo,
            'costo': i.costo, 'precio': i.precio,
            'stock': i.stock, 'stock_minimo': i.stock_minimo,
        } for i in items])
    finally:
        db.close()


# ──────────────────────────────────────────────────────────────────────────────
# NOTAS DE VENTA
# ──────────────────────────────────────────────────────────────────────────────

async def api_notas_list(request: Request) -> JSONResponse:
    user = _require_admin(request)
    if isinstance(user, JSONResponse):
        return user
    db = get_db()
    try:
        notas = db.query(NotaVenta).order_by(NotaVenta.fecha.desc()).limit(50).all()
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
    try:
        body = await request.json()
    except Exception:
        return json_err('Body inválido')
    items = body.get('items', [])
    if not items:
        return json_err('Sin ítems')
    db = get_db()
    try:
        last = db.query(NotaVenta).order_by(NotaVenta.id.desc()).first()
        seq = (last.id + 1) if last else 1
        numero = f"NV-{datetime.now().year}-{seq:04d}"
        sub = sum(it.get('subtotal', 0) for it in items)
        igv = round(sub * 0.18, 2)
        tot = round(sub + igv, 2)
        # Descontar stock
        for it in items:
            p = db.query(ItemInventario).filter_by(codigo=it.get('codigo')).first()
            if p:
                p.stock = max(0, p.stock - it.get('cantidad', 0))
        nv = NotaVenta(
            numero=numero, fecha=datetime.now(),
            cliente_nombre=body.get('cliente_nombre', 'Mostrador'),
            subtotal=sub, igv=igv, total=tot,
            estado='pagada', items=items,
        )
        db.add(nv)
        db.commit()
        return json_ok({'ok': True, 'numero': numero, 'total': tot}, 201)
    except Exception as e:
        db.rollback()
        return json_err(str(e))
    finally:
        db.close()


# ──────────────────────────────────────────────────────────────────────────────
# CITAS
# ──────────────────────────────────────────────────────────────────────────────

async def api_citas_list(request: Request) -> JSONResponse:
    user = _require_admin(request)
    if isinstance(user, JSONResponse):
        return user
    db = get_db()
    try:
        citas = db.query(Cita).order_by(Cita.id.desc()).limit(50).all()
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
        except: pass
        return json_ok({'ok': True, 'id': c.id}, 201)
    except Exception as e:
        db.rollback()
        return json_err(str(e))
    finally:
        db.close()


# ──────────────────────────────────────────────────────────────────────────────
# PORTAL CLIENTE
# ──────────────────────────────────────────────────────────────────────────────

async def api_cliente_mis_ordenes(request: Request) -> JSONResponse:
    user = _require_auth(request)
    if isinstance(user, JSONResponse):
        return user
    if user.get('rol') != 'cliente':
        return json_err('Solo para clientes', 403)
    db = get_db()
    try:
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
                'motivo': o.motivo or '',
                'descripcion': o.motivo or '',
                'tecnico': o.tecnico or '',
                'km': o.km or '',
                'diagnostico': o.diagnostico or '',
                'observaciones': o.observaciones or '',
                'items_cotizacion': items,
                'fotos_evidencia': fotos,
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
            })
        return json_ok(result)
    finally:
        db.close()




async def api_delete_orden(request: Request) -> JSONResponse:
    """DELETE /api/ordenes/{orden_id} — Eliminar orden (solo admin/recepcionista)"""
    auth = _require_auth(request)
    if isinstance(auth, JSONResponse): return auth
    if auth.get('rol') not in ('admin','recepcionista'):
        return json_err('Sin permisos para eliminar ordenes', 403)
    orden_id = request.path_params.get('orden_id','')
    db = get_db()
    try:
        from .models import Orden
        o = db.query(Orden).filter_by(consecutivo=orden_id).first()
        if not o:
            # Intentar por id numerico
            try:
                o = db.query(Orden).filter_by(id=int(orden_id)).first()
            except Exception:
                pass
        if not o:
            return json_err('Orden no encontrada', 404)
        db.delete(o)
        db.commit()
        return json_ok({'msg': f'Orden {orden_id} eliminada'})
    except Exception as e:
        db.rollback()
        return json_err(f'Error al eliminar: {e}', 500)
    finally:
        db.close()


async def api_cliente_mis_citas(request: Request) -> JSONResponse:
    user = _require_auth(request)
    if isinstance(user, JSONResponse):
        return user
    db = get_db()
    try:
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
        o = db.query(Orden).filter_by(consecutivo=str(cons)).first()
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


# ──────────────────────────────────────────────────────────────────────────────
# REGISTRO DE RUTAS
# ──────────────────────────────────────────────────────────────────────────────


async def api_orden_guardar_diagnostico(request: Request) -> JSONResponse:
    """POST /api/ordenes/{id}/diagnostico — guarda diagnostic_details en checklist"""
    user = _require_auth(request)
    if isinstance(user, JSONResponse): return user
    cons = request.path_params.get('id','')
    try: body = await request.json()
    except: return json_err('Body invalido')
    db = get_db()
    try:
        o = db.query(Orden).filter_by(consecutivo=cons).first()
        if not o: return json_err('Orden no encontrada',404)
        import json as _j
        cl = {}
        try:
            raw = o.checklist_reparacion
            if isinstance(raw,str): cl = _j.loads(raw)
            elif isinstance(raw,dict): cl = raw
        except: cl = {}
        if not isinstance(cl,dict): cl = {}
        cl['diagnostic_details'] = {
            'system': body.get('system',''),
            'codes': body.get('codes',''),
            'tests': body.get('tests',''),
            'analysis': body.get('analysis',''),
            'solution': body.get('solution',''),
            'scanner_path': body.get('scanner_path', cl.get('diagnostic_details',{}).get('scanner_path','') if isinstance(cl.get('diagnostic_details'),dict) else ''),
        }
        if body.get('diagnostico'): o.diagnostico = body['diagnostico']
        import copy as _copy
        o.checklist_reparacion = _copy.deepcopy(cl)
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(o, 'checklist_reparacion')
        db.commit()
        return json_ok({'ok':True})
    except Exception as e:
        db.rollback(); return json_err(str(e))
    finally: db.close()


async def api_orden_guardar_items(request: Request) -> JSONResponse:
    """POST /api/ordenes/{id}/items — guarda items_cotizacion"""
    user = _require_auth(request)
    if isinstance(user, JSONResponse): return user
    cons = request.path_params.get('id','')
    try: body = await request.json()
    except: return json_err('Body invalido')
    db = get_db()
    try:
        o = db.query(Orden).filter_by(consecutivo=cons).first()
        if not o: return json_err('Orden no encontrada',404)
        items = body.get('items',[])
        if not isinstance(items,list): return json_err('items debe ser lista')
        o.items_cotizacion = items
        db.commit()
        total = sum(float(it.get('total',0) or 0) for it in items)
        return json_ok({'ok':True,'total':total,'count':len(items)})
    except Exception as e:
        db.rollback(); return json_err(str(e))
    finally: db.close()


async def api_orden_guardar_checklist(request: Request) -> JSONResponse:
    """POST /api/ordenes/{id}/checklist — guarda quality_control, entrega, etc."""
    user = _require_auth(request)
    if isinstance(user, JSONResponse): return user
    cons = request.path_params.get('id','')
    try: body = await request.json()
    except: return json_err('Body invalido')
    db = get_db()
    try:
        o = db.query(Orden).filter_by(consecutivo=cons).first()
        if not o: return json_err('Orden no encontrada',404)
        import json as _j
        cl = {}
        try:
            raw = o.checklist_reparacion
            if isinstance(raw,str): cl = _j.loads(raw)
            elif isinstance(raw,dict): cl = raw
        except: cl = {}
        if not isinstance(cl,dict): cl = {}
        # Actualizar selectivamente lo que venga en el body
        if 'quality_control' in body: cl['quality_control'] = body['quality_control']
        if 'repair_logs' in body: cl['repair_logs'] = body['repair_logs']
        if 'findings' in body: cl['findings'] = body['findings']
        if 'quick_check' in body: cl['quick_check'] = body['quick_check']
        if 'is_mantenimiento' in body: cl['is_mantenimiento'] = body['is_mantenimiento']
        if 'notas_entrega' in body: o.notas_entrega = body['notas_entrega']
        if 'proximo_mantenimiento' in body: o.proximo_mantenimiento = body['proximo_mantenimiento']
        if 'km' in body: o.km = body['km']
        if 'tecnico' in body: o.tecnico = body['tecnico']
        if 'observaciones' in body: o.observaciones = body['observaciones']
        import copy as _cp
        o.checklist_reparacion = _cp.deepcopy(cl)
        from sqlalchemy.orm.attributes import flag_modified as _fm2
        _fm2(o, 'checklist_reparacion')
        db.commit()
        return json_ok({'ok':True})
    except Exception as e:
        db.rollback(); return json_err(str(e))
    finally: db.close()



async def api_inventario_crear(request: Request) -> JSONResponse:
    """POST /api/inventario/nuevo — crea un nuevo item en inventario"""
    user = _require_admin(request)
    if isinstance(user, JSONResponse): return user
    try: body = await request.json()
    except: return json_err('Body invalido')
    nombre = (body.get('nombre') or '').strip()
    if not nombre: return json_err('Nombre requerido')
    db = get_db()
    try:
        import secrets as _sec
        codigo = body.get('codigo') or 'INV-'+_sec.token_hex(3).upper()
        item = ItemInventario(
            codigo=codigo,
            nombre=nombre,
            categoria=body.get('categoria','General'),
            precio=float(body.get('precio',0) or 0),
            stock=int(body.get('stock',0) or 0),
            stock_minimo=int(body.get('stock_minimo',1) or 1),
            unidad=body.get('unidad','und'),
            descripcion=body.get('descripcion',''),
        )
        db.add(item)
        db.commit()
        return json_ok({'ok':True,'codigo':codigo,'nombre':nombre})
    except Exception as e:
        db.rollback(); return json_err(str(e))
    finally: db.close()



async def api_orden_subir_factura(request: Request) -> JSONResponse:
    """POST /api/ordenes/{id}/factura — sube PDF/imagen de factura"""
    user = _require_auth(request)
    if isinstance(user, JSONResponse): return user
    cons = request.path_params.get('id', '')
    import os
    try:
        form = await request.form()
        file = form.get('file')
        if not file:
            return json_err('Sin archivo')
        orig = getattr(file, 'filename', '') or 'factura'
        ext = orig.rsplit('.', 1)[-1].lower() if '.' in orig else 'pdf'
        cons_safe = cons.replace('#','').replace('/','-').replace(' ','_')
        filename = f"factura_{cons_safe}_{secrets.token_hex(4)}.{ext}"
        os.makedirs('static/facturas', exist_ok=True)
        filepath = os.path.join('static', 'facturas', filename)
        content = await file.read()
        with open(filepath, 'wb') as f2:
            f2.write(content)
        url = f"/facturas/{filename}"
        db = get_db()
        try:
            o = db.query(Orden).filter_by(consecutivo=cons).first()
            if not o: return json_err('Orden no encontrada', 404)
            o.factura_sunat = url
            db.commit()
        finally:
            db.close()
        return json_ok({'ok': True, 'url': url})
    except Exception as e:
        return json_err(str(e))


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


def register_api_routes(app):
    """Registra todas las rutas /api/* en la app NiceGUI/FastAPI"""
    app.add_api_route('/api/auth/login',              api_login,               methods=['POST', 'OPTIONS'])
    app.add_api_route('/api/auth/me',                 api_me,                  methods=['GET',  'OPTIONS'])
    app.add_api_route('/api/auth/logout',             api_logout,              methods=['POST', 'OPTIONS'])
    app.add_api_route('/api/dashboard',               api_dashboard,           methods=['GET',  'OPTIONS'])
    app.add_api_route('/api/ordenes',                 api_ordenes_list,        methods=['GET',  'OPTIONS'])
    app.add_api_route('/api/ordenes/nueva',           api_orden_create,        methods=['POST', 'OPTIONS'])
    app.add_api_route('/api/ordenes/{id}/estado',     api_orden_estado,        methods=['PUT',  'OPTIONS'])
    app.add_api_route('/api/ordenes/{id}/evidencia',  api_orden_evidencia,     methods=['POST', 'OPTIONS'])
    app.add_api_route('/api/ordenes/{orden_id}/eliminar', api_delete_orden, methods=['POST','OPTIONS'])
    app.add_api_route('/api/ordenes/{id}',            api_orden_get,           methods=['GET',  'OPTIONS'])
    app.add_api_route('/api/ordenes/{id}/diagnostico',  api_orden_guardar_diagnostico, methods=['POST','OPTIONS'])
    app.add_api_route('/api/ordenes/{id}/items',        api_orden_guardar_items,       methods=['POST','OPTIONS'])
    app.add_api_route('/api/ordenes/{id}/checklist',    api_orden_guardar_checklist,   methods=['POST','OPTIONS'])



    app.add_api_route('/api/clientes',                api_clientes_list,       methods=['GET',  'OPTIONS'])
    app.add_api_route('/api/clientes/nuevo',          api_cliente_create,      methods=['POST', 'OPTIONS'])
    app.add_api_route('/api/clientes/{id}/vehiculos', api_vehiculos_cliente,   methods=['GET',  'OPTIONS'])
    app.add_api_route('/api/clientes/{id}/perfil-completo', api_cliente_perfil_completo, methods=['GET', 'OPTIONS'])
    app.add_api_route('/api/vehiculos',               api_vehiculos_list,      methods=['GET',  'OPTIONS'])
    app.add_api_route('/api/vehiculos/nuevo',         api_vehiculo_create,     methods=['POST', 'OPTIONS'])
    app.add_api_route('/api/inventario',              api_inventario_list,     methods=['GET',  'OPTIONS'])
    app.add_api_route('/api/reportes/ganancia',       api_reportes_ganancia,   methods=['GET',  'OPTIONS'])
    app.add_api_route('/api/notas-venta',             api_notas_list,          methods=['GET',  'OPTIONS'])
    app.add_api_route('/api/notas-venta/nueva',       api_nota_create,         methods=['POST', 'OPTIONS'])
    app.add_api_route('/api/citas',                   api_citas_list,          methods=['GET',  'OPTIONS'])
    app.add_api_route('/api/citas/nueva',             api_cita_create,         methods=['POST', 'OPTIONS'])
    app.add_api_route('/api/cliente/mis-ordenes',     api_cliente_mis_ordenes, methods=['GET',  'OPTIONS'])
    app.add_api_route('/api/cliente/mis-citas',       api_cliente_mis_citas,   methods=['GET',  'OPTIONS'])
    app.add_api_route('/api/cliente/aprobar',         api_cliente_aprobar,     methods=['POST', 'OPTIONS'])
    app.add_api_route('/api/portal/notificaciones', api_portal_notificaciones, methods=['GET', 'OPTIONS'])
    app.add_api_route('/api/portal/notificaciones/marcar-leidas', api_portal_marcar_leidas, methods=['POST', 'OPTIONS'])



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

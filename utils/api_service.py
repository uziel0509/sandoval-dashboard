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
# Token store en memoria  {token: {user_dict, expires_at}}
# ──────────────────────────────────────────────────────────────────────────────
_tokens: dict[str, dict] = {}
TOKEN_TTL_MINUTES = 60 * 8  # 8 horas


def _new_token(user_dict: dict) -> str:
    token = secrets.token_hex(32)
    _tokens[token] = {
        'user': user_dict,
        'expires': datetime.now() + timedelta(minutes=TOKEN_TTL_MINUTES),
    }
    return token


def _get_user_from_token(token: str) -> Optional[dict]:
    entry = _tokens.get(token)
    if not entry:
        return None
    if datetime.now() > entry['expires']:
        del _tokens[token]
        return None
    # Renovar TTL
    entry['expires'] = datetime.now() + timedelta(minutes=TOKEN_TTL_MINUTES)
    return entry['user']


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
                ok = (password == cliente.id)
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
    if token and token in _tokens:
        del _tokens[token]
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
        activas = [o for o in ordenes if o.estado not in ('ARCHIVADO', 'ENTREGA')]
        completadas = [o for o in ordenes if o.estado in ('ARCHIVADO', 'ENTREGA')]
        total_ingresos = sum(
            float(it.get('total', 0) or 0)
            for o in ordenes
            for it in (o.items_cotizacion or [])
        )
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
                for est in ['RECEPCIÓN', 'DIAGNÓSTICO', 'REPUESTOS', 'APROBACIÓN',
                            'REPARACIÓN', 'CONTROL', 'ENTREGA', 'ARCHIVADO']
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
        ordenes = q.limit(50).all()
        data = []
        for o in ordenes:
            cli = db.query(Cliente).filter_by(id=o.cliente_id).first()
            data.append({
                'id': o.id, 'consecutivo': o.consecutivo,
                'fecha': str(o.fecha or ''), 'estado': o.estado,
                'cliente_nombre': f'{cli.nombre} {cli.apellidos}'.strip() if cli else '—',
                'vehiculo_placa': o.vehiculo_placa or '',
                'descripcion': o.descripcion_problema or '',
            })
        return json_ok(data)
    finally:
        db.close()


async def api_orden_get(request: Request) -> JSONResponse:
    user = _require_admin(request)
    if isinstance(user, JSONResponse):
        return user
    orden_id = int(request.path_params.get('id', 0))
    db = get_db()
    try:
        o = db.query(Orden).filter_by(id=orden_id).first()
        if not o:
            return json_err('Orden no encontrada', 404)
        cli = db.query(Cliente).filter_by(id=o.cliente_id).first()
        return json_ok({
            'id': o.id, 'consecutivo': o.consecutivo,
            'fecha': str(o.fecha or ''), 'estado': o.estado,
            'cliente_id': o.cliente_id,
            'cliente_nombre': f'{cli.nombre} {cli.apellidos}'.strip() if cli else '—',
            'cliente_telefono': cli.telefono if cli else '',
            'vehiculo_placa': o.vehiculo_placa or '',
            'vehiculo_marca': o.vehiculo_marca or '',
            'vehiculo_modelo': o.vehiculo_modelo or '',
            'descripcion': o.descripcion_problema or '',
            'items': o.items_cotizacion or [],
            'notas': o.notas_tecnico or '',
        })
    finally:
        db.close()


async def api_orden_estado(request: Request) -> JSONResponse:
    """PUT /api/ordenes/{id}/estado  {estado: 'DIAGNÓSTICO' | ...}"""
    user = _require_admin(request)
    if isinstance(user, JSONResponse):
        return user
    orden_id = int(request.path_params.get('id', 0))
    try:
        body = await request.json()
    except Exception:
        return json_err('Body inválido')
    nuevo_estado = body.get('estado', '').strip()
    db = get_db()
    try:
        o = db.query(Orden).filter_by(id=orden_id).first()
        if not o:
            return json_err('Orden no encontrada', 404)
        o.estado = nuevo_estado
        db.commit()
        log_actividad(f'Orden {o.consecutivo} → {nuevo_estado}', 'api')
        return json_ok({'ok': True, 'estado': nuevo_estado})
    except Exception as e:
        db.rollback()
        return json_err(str(e))
    finally:
        db.close()


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
            'id': v.id, 'placa': v.placa, 'marca': v.marca,
            'modelo': v.modelo, 'año': v.anio,
            'cliente_id': v.cliente_id,
        } for v in vehiculos])
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
        citas = db.query(Cita).order_by(Cita.fecha_pnt.desc()).limit(50).all()
        return json_ok([{
            'id': c.id, 'fecha': str(c.fecha_pnt or ''),
            'descripcion': c.descripcion or '',
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
            fecha_pnt=fecha,
            descripcion=body.get('descripcion', ''),
            estado='Pendiente',
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
        return json_ok([{
            'id': o.id, 'consecutivo': o.consecutivo,
            'fecha': str(o.fecha or ''), 'estado': o.estado,
            'vehiculo_placa': o.vehiculo_placa or '',
            'vehiculo_marca': o.vehiculo_marca or '',
            'descripcion': o.descripcion_problema or '',
            'items': o.items_cotizacion or [],
            'report_token': o.report_token or '',
        } for o in ordenes])
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
        ).order_by(Cita.fecha_pnt.desc()).limit(20).all()
        return json_ok([{
            'id': c.id, 'fecha': str(c.fecha_pnt or ''),
            'descripcion': c.descripcion or '',
            'estado': c.estado or '',
        } for c in citas])
    finally:
        db.close()


async def api_cliente_aprobar(request: Request) -> JSONResponse:
    """POST /api/cliente/aprobar  {orden_id, aprobado: true|false}"""
    user = _require_auth(request)
    if isinstance(user, JSONResponse):
        return user
    try:
        body = await request.json()
    except Exception:
        return json_err('Body inválido')
    db = get_db()
    try:
        o = db.query(Orden).filter_by(id=body.get('orden_id')).first()
        if not o:
            return json_err('Orden no encontrada', 404)
        if o.cliente_id != user['id']:
            return json_err('No autorizado', 403)
        aprobado = body.get('aprobado', True)
        o.estado = 'REPARACIÓN' if aprobado else 'ARCHIVADO'
        db.commit()
        return json_ok({'ok': True, 'estado': o.estado})
    except Exception as e:
        db.rollback()
        return json_err(str(e))
    finally:
        db.close()


# ──────────────────────────────────────────────────────────────────────────────
# REGISTRO DE RUTAS
# ──────────────────────────────────────────────────────────────────────────────

def register_api_routes(app):
    """Registra todas las rutas /api/* en la app NiceGUI/FastAPI"""
    app.add_api_route('/api/auth/login',              api_login,               methods=['POST', 'OPTIONS'])
    app.add_api_route('/api/auth/me',                 api_me,                  methods=['GET',  'OPTIONS'])
    app.add_api_route('/api/auth/logout',             api_logout,              methods=['POST', 'OPTIONS'])
    app.add_api_route('/api/dashboard',               api_dashboard,           methods=['GET',  'OPTIONS'])
    app.add_api_route('/api/ordenes',                 api_ordenes_list,        methods=['GET',  'OPTIONS'])
    app.add_api_route('/api/ordenes/{id}',            api_orden_get,           methods=['GET',  'OPTIONS'])
    app.add_api_route('/api/ordenes/{id}/estado',     api_orden_estado,        methods=['PUT',  'OPTIONS'])
    app.add_api_route('/api/clientes',                api_clientes_list,       methods=['GET',  'OPTIONS'])
    app.add_api_route('/api/clientes/nuevo',          api_cliente_create,      methods=['POST', 'OPTIONS'])
    app.add_api_route('/api/vehiculos',               api_vehiculos_list,      methods=['GET',  'OPTIONS'])
    app.add_api_route('/api/inventario',              api_inventario_list,     methods=['GET',  'OPTIONS'])
    app.add_api_route('/api/notas-venta',             api_notas_list,          methods=['GET',  'OPTIONS'])
    app.add_api_route('/api/notas-venta/nueva',       api_nota_create,         methods=['POST', 'OPTIONS'])
    app.add_api_route('/api/citas',                   api_citas_list,          methods=['GET',  'OPTIONS'])
    app.add_api_route('/api/citas/nueva',             api_cita_create,         methods=['POST', 'OPTIONS'])
    app.add_api_route('/api/cliente/mis-ordenes',     api_cliente_mis_ordenes, methods=['GET',  'OPTIONS'])
    app.add_api_route('/api/cliente/mis-citas',       api_cliente_mis_citas,   methods=['GET',  'OPTIONS'])
    app.add_api_route('/api/cliente/aprobar',         api_cliente_aprobar,     methods=['POST', 'OPTIONS'])


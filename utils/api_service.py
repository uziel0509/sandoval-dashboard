# === B16 SHIM 2026-04-29 ===
# api_service.py se convirtio en shim. Las funciones reales viven en utils/api/.
# Por compatibilidad con modulos que aun importan desde aqui:
#   utils.api_extensions / utils.api_mobile_admin: _require_auth, _require_admin, json_ok, json_err
#   utils.push_api: _require_auth
#   utils.rls_session: _get_user_from_token
#   tests/test_cookies_dual_auth: _extract_token
#
# El register_api_routes ya NO se importa desde aqui (main.py apunta a utils.api.routes).
# Las definiciones originales abajo siguen presentes para evitar romper imports residuales,
# pero el sistema usa los modulos utils.api.* como source-of-truth.
# === FIN SHIM ===

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
from utils.security_events import track_login_failure as _track_login_fail
from utils.auth_cookies import (
    get_token_from_request, set_token_cookie, clear_token_cookie,
    COOKIE_CLIENT_NAME, COOKIE_ADMIN_NAME
)

from sqlalchemy import text as _sa_text  # global para todas las funciones

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
    # 1) Intentar como sesión SQLite (PWA / portal cliente)
    conn = _get_sessions_db()
    try:
        row = conn.execute('SELECT user_json, expires FROM sessions WHERE token=?', (token,)).fetchone()
        if row:
            if datetime.now() > datetime.fromisoformat(row[1]):
                conn.execute('DELETE FROM sessions WHERE token=?', (token,))
                conn.commit()
                return None
            new_exp = (datetime.now() + timedelta(minutes=TOKEN_TTL_MINUTES)).isoformat()
            conn.execute('UPDATE sessions SET expires=? WHERE token=?', (new_exp, token))
            conn.commit()
            return _json.loads(row[0])
    finally:
        conn.close()
    # 2) Intentar como JWT del admin SPA (routers/_common.py)
    try:
        from routers._common import _secret
        import jwt as _pyjwt
        payload = _pyjwt.decode(token, _secret(), algorithms=['HS256'])
        # El JWT del admin SPA usa 'sub' o 'id' para el usuario; normalizamos.
        if 'id' not in payload and 'sub' in payload:
            payload['id'] = payload['sub']
        if 'rol' not in payload:
            payload['rol'] = 'admin'
        return payload
    except Exception:
        return None


def _extract_token(request: Request) -> Optional[str]:
    """2026-04-29 P1-EtA: dual-auth. Lee token desde:
    1) Cookie HttpOnly sandoval_token (admin)
    2) Cookie HttpOnly sandoval_client_token (cliente/conductor)
    3) Cookie sandoval_api_token (legacy, compat)
    4) Header Authorization: Bearer (legacy localStorage)
    """
    # Header Authorization (legacy)
    auth = request.headers.get('Authorization', '') or request.headers.get('authorization', '')
    if auth.startswith('Bearer '):
        return auth[7:]
    # Cookies (preferido post-migracion)
    return (request.cookies.get('sandoval_token') or
            request.cookies.get('sandoval_client_token') or
            request.cookies.get('sandoval_api_token'))


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



def _require_staff(request: Request) -> dict | JSONResponse:
    """Alias semantico de _require_admin (acepta admin/recepcionista/tecnico).

    El nombre _require_admin es legacy y engañoso: en realidad valida que
    el usuario sea staff (cualquier rol con acceso al portal). Para forzar
    admin estricto, usar _require_admin_strict.
    """
    return _require_admin(request)


def _require_admin_strict(request: Request) -> dict | JSONResponse:
    """Solo permite rol='admin' duro (no recepcionista, no tecnico).

    2026-04-29 audit V6: nuevo helper para endpoints donde la verificacion
    laxa de _require_admin no era apropiada (ej. crear/eliminar usuarios,
    cambiar configuracion sensible).
    """
    user = _require_auth(request)
    if isinstance(user, JSONResponse):
        return user
    if user.get("rol") != "admin":
        return JSONResponse(
            {"error": "Solo administradores pueden acceder a este recurso"},
            status_code=403
        )
    return user


# 2026-05-04 P1-A4 FIX (SHIM legacy): wildcard CORS eliminado, CORSMiddleware
# estricto en main.py se encarga de los headers cross-origin de forma unificada.
def json_ok(data, status=200) -> JSONResponse:
    return JSONResponse(data, status_code=status)


def json_err(msg, status=400) -> JSONResponse:
    return JSONResponse({'error': msg}, status_code=status)

# ──────────────────────────────────────────────────────────────────────────────
# Rate Limiting - máx 5 intentos fallidos por IP cada 15 minutos
# ──────────────────────────────────────────────────────────────────────────────
import threading as _threading
from collections import defaultdict as _defaultdict
_login_attempts = _defaultdict(list)  # {ip: [timestamp, ...]}
_rl_lock = _threading.Lock()

def _check_rate_limit(ip: str) -> bool:
    """Retorna True si la IP está bloqueada (demasiados intentos)"""
    from datetime import datetime, timedelta
    now = datetime.now()
    window = timedelta(minutes=15)
    with _rl_lock:
        attempts = [t for t in _login_attempts[ip] if now - t < window]
        _login_attempts[ip] = attempts
        return len(attempts) >= 5

def _record_failed_attempt(ip: str):
    from datetime import datetime
    with _rl_lock:
        _login_attempts[ip].append(datetime.now())

def _clear_attempts(ip: str):
    with _rl_lock:
        _login_attempts[ip] = []




# ──────────────────────────────────────────────────────────────────────────────
# AUTH
# ──────────────────────────────────────────────────────────────────────────────

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
                for est in ['RECEPCIÓN', 'DIAGNÓSTICO', 'REPUESTOS',
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
        cli_ids = list({o.cliente_id for o in ordenes if o.cliente_id})
        placas = list({o.vehiculo_placa for o in ordenes if o.vehiculo_placa})
        cli_map = {c.id: c for c in db.query(Cliente).filter(Cliente.id.in_(cli_ids)).all()} if cli_ids else {}
        veh_map = {v.placa: v for v in db.query(Vehiculo).filter(Vehiculo.placa.in_(placas)).all()} if placas else {}
        data = []
        for o in ordenes:
            cli = cli_map.get(o.cliente_id)
            veh = veh_map.get(o.vehiculo_placa)
            items_raw = o.items_cotizacion or []
            total = 0.0
            if isinstance(items_raw, dict):
                try: total = float(items_raw.get('total', 0) or 0)
                except Exception: total = 0.0
                if not total:
                    for i in (items_raw.get('items') or []):
                        if not isinstance(i, dict): continue
                        if str(i.get('categoria') or '') in ('Resumen','Impuesto','Total'): continue
                        try:
                            total += float(i.get('total') or i.get('subtotal') or (float(i.get('precio_unitario',0) or 0) * float(i.get('cantidad',1) or 1)))
                        except Exception: pass
            elif isinstance(items_raw, list):
                for i in items_raw:
                    if not isinstance(i, dict): continue
                    if str(i.get('categoria') or '') in ('Resumen','Impuesto','Total'): continue
                    try:
                        total += float(i.get('total') or i.get('subtotal') or (float(i.get('precio_unitario',0) or 0) * float(i.get('cantidad',1) or 1)))
                    except Exception: pass
            cobrado = float(o.monto_cobrado or 0)
            pago_estado = 'PAGADO' if (cobrado >= total and total > 0) else ('PARCIAL' if cobrado > 0 else 'PENDIENTE')
            data.append({
                'id': o.consecutivo,
                'consecutivo': o.consecutivo,
                'fecha': str(o.fecha or ''),
                'updated_at': str(getattr(o, 'updated_at', None) or getattr(o, 'fecha_dt', None) or o.fecha or ''),
                'estado': o.estado,
                'cliente_nombre': f'{cli.nombre} {cli.apellidos}'.strip() if cli else '—',
                'vehiculo_placa': o.vehiculo_placa or '',
                'vehiculo_marca': veh.marca if veh else '',
                'vehiculo_modelo': veh.modelo if veh else '',
                'vehiculo_anio': str(getattr(veh, 'año', '') or '') if veh else '',
                'vehiculo_color': (veh.color or '') if veh else '',
                # Conductor asignado a la moto (campos en tabla vehiculos)
                'conductor_nombre':   (getattr(veh, 'conductor_nombre', '') or '') if veh else '',
                'conductor_dni':      (getattr(veh, 'conductor_dni', '') or '') if veh else '',
                'conductor_telefono': (getattr(veh, 'conductor_telefono', '') or '') if veh else '',
                'conductor_email':    (getattr(veh, 'conductor_email', '') or '') if veh else '',
                'conductor_activo':   bool(getattr(veh, 'conductor_activo', True)) if veh else False,
                'has_conductor':      bool(getattr(veh, 'conductor_nombre', '')) if veh else False,
                'descripcion': o.motivo or '',
                'motivo': o.motivo or '',
                'tecnico': o.tecnico or '',
                'total': round(total, 2),
                'cobrado': cobrado,
                'pago_estado': pago_estado,
            })
        return json_ok(data)
    finally:
        db.close()



async def api_orden_get(request: Request) -> JSONResponse:
    user = _require_admin(request)
    if isinstance(user, JSONResponse):
        return user
    cons = request.path_params.get('id', '')
    _t_id = int(user.get('taller_id') or 1)
    db = get_db()
    try:
        try:
            _setup_flota_ctx(db, _t_id)
        except Exception:
            pass
        o = db.query(Orden).filter_by(consecutivo=cons, taller_id=_t_id).first()
        if not o:
            return json_err('Orden no encontrada', 404)
        cli = db.query(Cliente).filter_by(id=o.cliente_id).first()
        veh = db.query(Vehiculo).filter_by(placa=o.vehiculo_placa).first() if o.vehiculo_placa else None
        items_raw = o.items_cotizacion or []
        if isinstance(items_raw, dict):
            items = items_raw.get('items', [])
            total = float(items_raw.get('total', 0) or 0)
        elif isinstance(items_raw, list):
            items = items_raw
            total = 0.0
            for i in items:
                if not isinstance(i, dict):
                    continue
                cat = str(i.get('categoria') or '').strip()
                if cat in ('Resumen', 'Impuesto', 'Total'):
                    continue
                if 'total' in i:
                    try: total += float(i.get('total') or 0)
                    except Exception: pass
                elif 'subtotal' in i:
                    try: total += float(i.get('subtotal') or 0)
                    except Exception: pass
                else:
                    try:
                        total += float(i.get('precio_unitario', 0) or 0) * float(i.get('cantidad', 1) or 1)
                    except Exception: pass
        else:
            items = []
            total = 0.0
        pagos = o.pagos or []
        if not isinstance(pagos, list):
            pagos = []
        cobrado = float(o.monto_cobrado or 0)
        if cobrado >= total and total > 0:
            pago_estado = 'PAGADO'
        elif cobrado > 0:
            pago_estado = 'PARCIAL'
        else:
            pago_estado = 'PENDIENTE'
        approval_token = getattr(o, 'approval_token', None) or ''
        if (not approval_token) or str(approval_token).startswith('USED_'):
            import uuid as _uuid
            approval_token = _uuid.uuid4().hex
            try:
                o.approval_token = approval_token
                db.commit()
            except Exception:
                db.rollback()
        approval_status = ''
        try:
            aps = str(getattr(o, 'approval_status', '') or '').lower()
            if aps in ('aprobado','approved','ok','si','sí'): approval_status = 'aprobado'
            elif aps in ('rechazado','rejected','no'): approval_status = 'rechazado'
        except Exception: pass
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
            'vehiculo_anio': getattr(veh, 'año', None) or getattr(veh, 'anio', None) or '',
            'descripcion': o.motivo or '',
            'km': o.km or '',
            'tecnico': o.tecnico or '',
            'tipo': o.tipo or 'Express',
            'items': items,
            'items_cotizacion': items,
            'total': round(total, 2),
            'pagos': pagos,
            'monto_cobrado': cobrado,
            'pago_estado': pago_estado,
            'observaciones': o.observaciones or '',
            'diagnostico': o.diagnostico or '',
            'fotos_evidencia': o.fotos_evidencia or [],
            'evidencia': o.fotos_evidencia or [],
            'checklist_reparacion': o.checklist_reparacion or {},
            'notas_entrega': o.notas_entrega or '',
            'proximo_mantenimiento': o.proximo_mantenimiento or '',
            'motivo': o.motivo or '',
            'factura_sunat': o.factura_sunat or '',
            'approval_token': approval_token,
            'approval_status': approval_status,
            'approval_date': str(getattr(o, 'approval_date', '') or ''),
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
        _t_id = int(user.get('taller_id') or 1)
        try:
            _setup_flota_ctx(db, _t_id)
        except Exception:
            pass
        o = db.query(Orden).filter_by(consecutivo=cons, taller_id=_t_id).first()
        if not o:
            return json_err('Orden no encontrada', 404)
        o.estado = nuevo_estado
        taller_id_o = int(getattr(o, 'taller_id', None) or user.get('taller_id') or 1)
        db.commit()
        # Push según el nuevo estado
        try:
            from utils.flota import notify_orden_event
            est_norm = nuevo_estado.upper().replace('Ó','O').replace('Á','A').replace('É','E').replace('Í','I')
            evt = None
            if 'DIAGNOSTIC' in est_norm: evt = 'diagnostico_listo'
            elif 'REPUESTO' in est_norm or 'APROBAC' in est_norm: evt = 'presupuesto_listo'
            elif 'REPARAC' in est_norm: evt = 'reparacion_iniciada'
            elif 'CALIDAD' in est_norm or 'CONTROL' in est_norm: evt = 'lista_entrega'
            elif 'LISTO' in est_norm or 'ENTREGA' in est_norm: evt = 'lista_entrega'
            elif 'ARCHIV' in est_norm: evt = 'entregado'
            if evt:
                notify_orden_event(db, taller_id=taller_id_o, consecutivo=cons, evento=evt)
        except Exception:
            pass
        return json_ok({'ok': True, 'estado': nuevo_estado})
    except Exception as e:
        db.rollback()
        return json_err(str(e))
    finally:
        db.close()


def _coerce_km_int(v):
    """Normaliza km a entero. Acepta None, '', str con coma, float, int."""
    if v is None or v == '':
        return 0
    try:
        return int(float(str(v).replace(',', '').strip()))
    except (ValueError, TypeError):
        return 0


async def api_orden_create(request: Request) -> JSONResponse:
    """POST /api/ordenes/nueva — admin Y cliente pueden crear"""
    user = _require_auth(request)
    if isinstance(user, JSONResponse):
        return user
    # 2026-05-04 MULTI-TENANT FIX (SHIM legacy): taller_id desde sesion
    _t_id = int(user.get('taller_id') or 1)
    try:
        body = await request.json()
    except Exception:
        return json_err('Body inválido')
    db = get_db()
    try:
        # Fecha de ingreso editable (backdating). Default: ahora.
        now = datetime.now()
        fecha_raw = (body.get('fecha') or '').strip()
        fecha_dt = now
        if fecha_raw:
            base = fecha_raw.replace('T', ' ')[:19]
            try:
                if len(base) <= 10:
                    # Solo fecha: usar 08:00 (inicio de jornada) en vez de hora del servidor.
                    fecha_dt = datetime.strptime(base[:10], '%Y-%m-%d').replace(hour=8, minute=0, second=0)
                elif len(base) >= 19:
                    fecha_dt = datetime.strptime(base, '%Y-%m-%d %H:%M:%S')
                else:
                    fecha_dt = datetime.strptime(base[:16], '%Y-%m-%d %H:%M')
            except ValueError:
                fecha_dt = now
        # Generar consecutivo (usa la fecha de ingreso, no la de creación)
        consecutivo = f'#ODS-{fecha_dt.strftime("%Y%m%d-%H%M")}'
        existing = db.query(Orden).filter_by(consecutivo=consecutivo, taller_id=_t_id).first()
        if existing:
            consecutivo = f'#ODS-{fecha_dt.strftime("%Y%m%d-%H%M%S")}'
        # Placa normalizada
        placa = (body.get('vehiculo_placa') or '').strip().upper() or None
        o = Orden(
            consecutivo=consecutivo,
            fecha=fecha_dt.strftime('%Y-%m-%d %H:%M'),
            cliente_id=body.get('cliente_id') or None,
            vehiculo_placa=placa,
            motivo=body.get('motivo', ''),
            km=_coerce_km_int(body.get('km')),
            tecnico=body.get('tecnico', ''),
            tipo=body.get('tipo', 'Express'),
            observaciones=body.get('observaciones', ''),
            estado='RECEPCIÓN',
            approval_token=secrets.token_hex(16),
            report_token=secrets.token_hex(16),
        )
        db.add(o)
        db.flush()
        # fecha_dt no está en el modelo ORM; actualizar via SQL crudo
        # 2026-05-04 MULTI-TENANT FIX (SHIM legacy): taller_id desde JWT/sesion
        from sqlalchemy import text as _sql_text
        db.execute(_sql_text("UPDATE ordenes SET fecha_dt = :fdt WHERE consecutivo = :c AND taller_id = :t"),
                   {'fdt': fecha_dt, 'c': consecutivo, 't': _t_id})
        db.commit()
        log_actividad(f'Nueva orden {consecutivo} creada desde app', 'api')
        # Notificar bot de Telegram sobre nueva orden
        try:
            from utils.telegram_bot import notificar_nueva_orden
            import asyncio as _asyncio
            from telegram import Bot as _TGBot
            import os as _os
            _tg_token = _os.getenv('TELEGRAM_TOKEN','')
            if _tg_token:
                _bot = _TGBot(token=_tg_token)
                _asyncio.ensure_future(notificar_nueva_orden(_bot, consecutivo, body.get('vehiculo_placa',''), body.get('motivo','')))
        except Exception as _te:
            pass  # No romper si el bot falla
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
        # Detectar tipo: pdf, video o foto
        content_type = getattr(file, 'content_type', '') or ''
        is_pdf = content_type == 'application/pdf' or ext == 'pdf'
        is_video = (not is_pdf) and (
            content_type.startswith('video/')
            or ext in ('mp4','mov','webm','3gp','avi','mkv')
        )
        if is_pdf:
            tipo = 'pdf'
        elif is_video:
            tipo = 'video'
        else:
            tipo = 'foto'
        # Fase enviada desde el cliente (faseId del formulario)
        fase = (form.get('fase') or 'RECEPCION').strip()
        # Limpiar consecutivo para nombre de archivo
        cons_safe = cons.replace('#','').replace('/','-').replace(' ','_')
        filename = f"{cons_safe}_{fase}_{secrets.token_hex(4)}.{ext}"
        # Guardar en static/evidencia/
        os.makedirs('static/evidencia', exist_ok=True)
        os.makedirs('/var/www/sandoval/static/evidencia', exist_ok=True)
        filepath = os.path.join('/var/www/sandoval/static/evidencia', filename)
        with open(filepath, 'wb') as f:
            f.write(content)
        # Permisos 644 para que nginx (www-data) pueda servir el archivo.
        try: os.chmod(filepath, 0o644)
        except OSError: pass
        # URL pública accesible
        url = f"/evidencia/{filename}"
        # Guardar en BD
        db = get_db()
        try:
            _t_id = int(user.get('taller_id') or 1)
            try:
                _setup_flota_ctx(db, _t_id)
            except Exception:
                pass
            o = db.query(Orden).filter_by(consecutivo=cons, taller_id=_t_id).first()
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


# ─── Anti-SSRF helpers para URL→PDF (escaneo de QR del scanner) ─────────────
def _is_safe_public_host(host: str) -> bool:
    """True si `host` parece un dominio público válido para descargar
    contenido. Bloquea localhost, link-local, redes privadas, multicast.
    """
    import ipaddress
    if not host:
        return False
    h = host.lower().strip()
    # Bloquear hostnames especiales
    if h in ('localhost', 'localhost.localdomain', '0.0.0.0', '::',
             '::1', 'metadata.google.internal', 'metadata.aws.amazon.com'):
        return False
    if h.endswith('.local') or h.endswith('.internal'):
        return False
    # Si parece IP, validar
    try:
        ip = ipaddress.ip_address(h)
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_multicast or ip.is_reserved or ip.is_unspecified):
            return False
    except ValueError:
        pass  # No es IP, es hostname → OK pasar
    return True


def _safe_download_pdf(url: str, max_bytes: int = 50 * 1024 * 1024):
    """Descarga un PDF de una URL pública con protección SSRF.
    Devuelve (content_bytes, error_str). Si error_str no es None, content es None.
    """
    from urllib.parse import urlparse
    import socket
    import ipaddress
    try:
        import requests as _requests
    except ImportError:
        return None, 'requests no instalado'
    try:
        u = urlparse(url)
    except Exception:
        return None, 'URL inválida'
    if u.scheme not in ('https',):
        return None, 'Solo URLs HTTPS están permitidas'
    if not u.hostname:
        return None, 'URL sin host'
    if not _is_safe_public_host(u.hostname):
        return None, 'Host bloqueado (privado/local)'
    # Resolver DNS y verificar que NINGUNA IP es privada (defensa anti-DNS-rebinding)
    try:
        infos = socket.getaddrinfo(u.hostname, u.port or 443)
        for fam, _t, _p, _c, sa in infos:
            ip_str = sa[0]
            try:
                ip = ipaddress.ip_address(ip_str)
                if (ip.is_private or ip.is_loopback or ip.is_link_local
                        or ip.is_multicast or ip.is_reserved or ip.is_unspecified):
                    return None, f'Host resuelve a IP privada: {ip_str}'
            except ValueError:
                continue
    except socket.gaierror:
        return None, 'Host no resoluble'
    # Descarga con stream para abortar si pasa max_bytes
    try:
        with _requests.get(url, timeout=15, stream=True,
                            allow_redirects=False) as r:
            if r.status_code != 200:
                return None, f'HTTP {r.status_code} al descargar'
            ctype = (r.headers.get('content-type') or '').lower().split(';')[0].strip()
            # Aceptar application/pdf y application/octet-stream (algunos servers lo usan)
            if ctype not in ('application/pdf', 'application/octet-stream'):
                return None, f'Content-Type no es PDF: {ctype}'
            content = b''
            for chunk in r.iter_content(8192):
                content += chunk
                if len(content) > max_bytes:
                    return None, 'PDF demasiado grande (máx. 50 MB)'
            if not content.startswith(b'%PDF-'):
                return None, 'El archivo no es un PDF válido (cabecera incorrecta)'
            return content, None
    except _requests.exceptions.Timeout:
        return None, 'Timeout al descargar'
    except Exception as e:
        return None, f'Error de red: {e}'


async def api_orden_evidencia_from_url(request: Request) -> JSONResponse:
    """POST /api/ordenes/{id}/evidencia-from-url
    Body: {url: 'https://...', fase: 'diagnostico'}
    Descarga el PDF desde la URL (típicamente del cloud del scanner OBD)
    aplicando protección anti-SSRF, y lo guarda como evidencia de la fase.
    """
    user = _require_admin(request)
    if isinstance(user, JSONResponse):
        return user
    cons = request.path_params.get('id', '')
    try:
        body = await request.json()
    except Exception:
        return json_err('Body JSON inválido')
    url = (body.get('url') or '').strip()
    fase = (body.get('fase') or 'diagnostico').strip()
    if not url:
        return json_err('Falta url')

    content, err = _safe_download_pdf(url)
    if err:
        return json_err(err, 400)

    # Guardar (mismo flujo que api_orden_evidencia)
    import os as _os
    cons_safe = cons.replace('#', '').replace('/', '-').replace(' ', '_')
    filename = f"{cons_safe}_{fase}_qr_{secrets.token_hex(4)}.pdf"
    _os.makedirs('/var/www/sandoval/static/evidencia', exist_ok=True)
    filepath = _os.path.join('/var/www/sandoval/static/evidencia', filename)
    with open(filepath, 'wb') as f:
        f.write(content)
    try:
        _os.chmod(filepath, 0o644)
    except OSError:
        pass
    public_url = f"/evidencia/{filename}"
    db = get_db()
    try:
        _t_id = int(user.get('taller_id') or 1)
        try:
            _setup_flota_ctx(db, _t_id)
        except Exception:
            pass
        o = db.query(Orden).filter_by(consecutivo=cons, taller_id=_t_id).first()
        if o:
            from urllib.parse import urlparse as _up
            host = _up(url).hostname or ''
            fotos = list(o.fotos_evidencia or [])
            fotos.append({
                'path': public_url, 'url': public_url,
                'fase': fase, 'tipo': 'pdf',
                'nombre': f'scanner_qr_{host}.pdf',
                'origen_url': url[:200],
                'fecha': datetime.now().strftime('%Y-%m-%d %H:%M'),
            })
            o.fotos_evidencia = fotos
            db.commit()
    finally:
        db.close()
    return json_ok({'ok': True, 'url': public_url, 'tipo': 'pdf',
                     'fase': fase, 'size': len(content)})


# ──────────────────────────────────────────────────────────────────────────────
# CLIENTES
# ──────────────────────────────────────────────────────────────────────────────

async def api_clientes_list(request: Request) -> JSONResponse:
    """GET /api/clientes — shape coherente con /admin/api/clientes (routers/clientes.py).
    Soporta ?q= y ?limit=."""
    user = _require_admin(request)
    if isinstance(user, JSONResponse):
        return user
    db = get_db()
    try:
        q = request.query_params.get('q', '') or ''
        try:
            limit = max(1, min(500, int(request.query_params.get('limit', '200'))))
        except (ValueError, TypeError):
            limit = 200
        query = db.query(Cliente)
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
            'modelo': v.modelo, 'año': getattr(v, 'año', getattr(v, 'anio', '')),
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
# FACTURAS (Mobile) — Fase D.3: OCR Groq Vision + guardar + merge a inventario
# ──────────────────────────────────────────────────────────────────────────────

async def api_mobile_facturas_ocr(request: Request) -> JSONResponse:
    """POST /api/mobile/facturas/ocr {imagen_base64, media_type}
    Usa Groq vision (LLaMA 4 Maverick) para extraer datos estructurados.
    Devuelve proveedor, ruc, numero, fecha, items, subtotal, igv, total."""
    import re as _re
    user = _require_admin(request)
    if isinstance(user, JSONResponse):
        return user
    try:
        body = await request.json()
    except Exception:
        return json_err('Body inválido')
    imagen_b64 = body.get('imagen_base64') or ''
    # El frontend puede mandar 'mime' o 'media_type' indistintamente.
    media_type = body.get('media_type') or body.get('mime') or 'image/jpeg'
    if not imagen_b64:
        return json_err('Sin imagen')
    # Normalizar: si viene como data URL completo (canvas.toDataURL()), extraer
    # SOLO la parte base64; si no, dejarlo tal cual. Groq rechaza data URLs
    # anidados ("invalid base64 url") si lo envolvemos dos veces.
    if imagen_b64.startswith('data:'):
        _head, _, _b64 = imagen_b64.partition(',')
        if _b64:
            # Detectar media_type del propio data URL
            _m = _re.match(r'data:([^;]+);base64', _head)
            if _m:
                media_type = _m.group(1)
            imagen_b64 = _b64
    # Eliminar espacios, saltos de línea que pudieran haber venido.
    imagen_b64 = imagen_b64.replace('\n', '').replace('\r', '').replace(' ', '')
    taller_id = int(user.get('taller_id') or 1)

    from sqlalchemy import text as _sql_text
    db = get_db()
    try:
        row = db.execute(_sql_text(
            "SELECT valor FROM config_sistema WHERE taller_id=:t AND clave='groq_api_key'"
        ), {'t': taller_id}).fetchone()
    finally:
        db.close()
    if not row or not row[0]:
        return json_err('No hay API key Groq configurada', 400)
    groq_key = row[0].strip()

    try:
        from groq import Groq as _Groq
    except ImportError:
        return json_err('Librería groq no instalada', 500)

    # RUC del taller (comprador) — hay que IGNORARLO al extraer, porque el
    # campo "ruc" del JSON debe ser el del PROVEEDOR (emisor de la factura).
    _mi_ruc = _os.getenv('TALLER_RUC', '20608755111')
    _mi_nombre = _os.getenv('TALLER_NOMBRE', 'MECANICA Y REPUESTOS SANDOVAL EIRL')
    _prompt = (
        "Eres un contador peruano experto. Lee la factura/boleta COMPLETA de ARRIBA hacia ABAJO con máxima precisión, sin saltarte ningún ítem aunque la lista sea larga.\n\n"
        "⚠️ IDENTIFICACIÓN DE PARTES (CRÍTICO — no te equivoques):\n"
        f"  RUC de MI empresa (RECEPTOR / COMPRADOR / ADQUIRIENTE) = {_mi_ruc}\n"
        f"  Razón social de MI empresa = {_mi_nombre} (variantes: 'SANDOVAL', 'MECANICA SANDOVAL', 'REPUESTOS SANDOVAL', 'E.I.R.L.', 'EIRL').\n"
        f"  ❌ Si ves {_mi_ruc} o cualquier mención a 'SANDOVAL' en la sección de CLIENTE/ADQUIRIENTE/COMPRADOR/RECEPTOR → ESE NO ES el proveedor. NO lo pongas en 'ruc' ni en 'proveedor'.\n"
        "  ✅ El PROVEEDOR (lo que sí quiero) es el OTRO RUC distinto al mío, que aparece en la CABECERA de la factura (parte superior) junto al logo/razón social del emisor — la empresa que ME VENDIÓ.\n"
        f"  Si el único RUC visible es {_mi_ruc} (mío), deja 'ruc' y 'proveedor' VACÍOS — no inventes.\n\n"
        "REGLAS DE LECTURA DE ITEMS:\n"
        "- Lee EVERY ítem de la tabla, de la primera fila a la última, en orden. Si la factura tiene 30 ítems, devuelve los 30.\n"
        "- Para cada ítem, extrae: nombre completo, cantidad, precio_unitario, total (subtotal del ítem).\n"
        "- VERIFICACIÓN ARITMÉTICA: la suma de los 'total' de los ítems debe ser ≈ subtotal_sin_igv. Si no cuadra, revisa los ítems.\n"
        "- Si un ítem dice 'GRATIS'/'OBSEQUIO'/'BONIFICACION' o tiene precio 0 → es_gratis=true, precio=0, total=0.\n\n"
        "REGLAS CRÍTICAS DE ARITMÉTICA TOTAL:\n"
        "1. Precios YA INCLUYEN IGV (18%). NUNCA sumes IGV adicional.\n"
        "2. El TOTAL FINAL impreso en la factura es la fuente de verdad absoluta.\n"
        "3. Fórmula: IGV = Total × 18/118 | Subtotal sin IGV = Total − IGV.\n"
        "4. Moneda: 'S/.' o 'PEN' → 'PEN'; '$' o 'USD' → 'USD'. Default 'PEN'.\n"
        "5. Fechas en formato YYYY-MM-DD.\n\n"
        "Responde ÚNICAMENTE con este JSON exacto (sin markdown, sin texto adicional):\n"
        '{"proveedor":"","ruc":"","numero_factura":"","fecha":"YYYY-MM-DD","moneda":"PEN",'
        '"items":[{"nombre":"","cantidad":1,"precio_unitario":0.00,"total":0.00,"es_gratis":false}],'
        '"subtotal_sin_igv":0.00,"igv_monto":0.00,"total_con_igv":0.00,'
        '"notas":"","confianza":"alta|media|baja"}'
    )

    # Modelos de visión de Groq en orden de preferencia. Si Groq descontinúa
    # uno, caemos al siguiente automáticamente en vez de devolver 500.
    _vision_models = [
        'meta-llama/llama-4-scout-17b-16e-instruct',
        'meta-llama/llama-4-maverick-17b-128e-instruct',
        'llama-3.2-90b-vision-preview',
        'llama-3.2-11b-vision-preview',
    ]
    resp = None
    last_err = None
    try:
        from groq import NotFoundError as _GroqNotFound, AuthenticationError as _GroqAuth
    except Exception:
        _GroqNotFound = Exception
        _GroqAuth = Exception
    try:
        client = _Groq(api_key=groq_key)
        for _model in _vision_models:
            try:
                resp = client.chat.completions.create(
                    model=_model,
                    messages=[{'role': 'user', 'content': [
                        {'type': 'text', 'text': _prompt},
                        {'type': 'image_url', 'image_url': {'url': f'data:{media_type};base64,{imagen_b64}'}},
                    ]}],
                    temperature=0, max_tokens=2000,
                )
                break  # éxito
            except _GroqNotFound as e:
                last_err = e
                continue  # probar siguiente modelo
            except _GroqAuth as e:
                # API key inválida/expirada: no tiene sentido probar otros modelos.
                return json_err(
                    'API key de Groq inválida o expirada. Renuévala en https://console.groq.com/keys '
                    'y actualiza GROQ_API_KEY en /var/www/sandoval/.env',
                    503,
                )
        if resp is None:
            raise last_err or RuntimeError('Ningún modelo de visión Groq disponible')
    except Exception:
        import traceback; traceback.print_exc()
        return json_err('Error al procesar imagen con OCR', 500)

    raw = (resp.choices[0].message.content or '').strip()
    raw = _re.sub(r'^```(?:json)?\s*', '', raw)
    raw = _re.sub(r'\s*```$', '', raw)
    m = _re.search(r'\{[\s\S]+\}', raw)
    if not m:
        return json_err('OCR no devolvió JSON válido', 500)
    try:
        import json as _json
        data = _json.loads(m.group(0))
    except Exception:
        return json_err('JSON malformado desde OCR', 500)

    total = float(data.get('total_con_igv') or 0)
    if total > 0:
        data['igv_monto'] = round(total * 18 / 118, 2)
        data['subtotal_sin_igv'] = round(total - data['igv_monto'], 2)
    for it in (data.get('items') or []):
        if it.get('es_gratis'):
            it['precio_unitario'] = 0; it['total'] = 0

    # Defensa post-OCR: si el modelo se confundió y devolvió MI propio RUC
    # como proveedor, lo descartamos y avisamos al frontend.
    _warnings = []
    _ruc_extraido = (str(data.get('ruc') or '')).strip().replace(' ', '').replace('-', '')
    _prov_extraido = (str(data.get('proveedor') or '')).upper()
    _mi_nombre_norm = _mi_nombre.upper().replace('.', '').replace(',', '')
    _es_mi_empresa = (
        _ruc_extraido == _mi_ruc
        or 'SANDOVAL' in _prov_extraido
        or any(t and t in _prov_extraido for t in _mi_nombre_norm.split())
    )
    if _es_mi_empresa:
        data['ruc'] = ''
        data['proveedor'] = ''
        _warnings.append(
            'Se detectó tu propio RUC/empresa como proveedor; campo descartado. '
            'Verifica el RUC del emisor manualmente.'
        )
    if _warnings:
        data['_warnings'] = _warnings
    return json_ok(data)


async def api_mobile_facturas_crear(request: Request) -> JSONResponse:
    """POST /api/mobile/facturas/crear
    Body: {proveedor, ruc, numero, fecha, subtotal, igv, total, items, moneda, notas, imagen_base64?, media_type?}
    Crea la factura + guarda imagen si se envía."""
    import base64 as _b64, os as _os, secrets as _secrets, json as _json
    from sqlalchemy import text as _sql_text
    user = _require_admin(request)
    if isinstance(user, JSONResponse):
        return user
    try:
        body = await request.json()
    except Exception:
        return json_err('Body inválido')
    taller_id = int(user.get('taller_id') or 1)

    imagen_path = ''
    if body.get('imagen_base64'):
        try:
            media = (body.get('media_type') or 'image/jpeg').lower()
            ext = 'jpg' if 'jpeg' in media or 'jpg' in media else ('png' if 'png' in media else 'img')
            save_dir = '/var/www/sandoval/static/facturas'
            _os.makedirs(save_dir, exist_ok=True)
            fname = f"factura_m_{int(datetime.now().timestamp())}_{_secrets.token_hex(3)}.{ext}"
            with open(_os.path.join(save_dir, fname), 'wb') as f:
                f.write(_b64.b64decode(body['imagen_base64']))
            imagen_path = f'/facturas/{fname}'
        except Exception:
            imagen_path = ''

    db = get_db()
    try:
        fecha = body.get('fecha') or datetime.now().strftime('%Y-%m-%d')
        new_id = db.execute(_sql_text("""
            INSERT INTO facturas (taller_id, tipo, subtipo_gasto, proveedor, ruc_proveedor,
                numero_factura, fecha, subtotal, igv, total, estado, notas,
                items_json, moneda, imagen_path, fecha_registro)
            VALUES (:t, :tipo, '', :prov, :ruc, :num, :fecha, :sub, :igv, :tot,
                    'procesada', :notas, :items, :moneda, :img, NOW())
            RETURNING id
        """), {
            't': taller_id,
            'tipo': body.get('tipo', 'mercaderia'),
            'prov': (body.get('proveedor') or '').strip(),
            'ruc': (body.get('ruc') or body.get('ruc_proveedor') or '').strip(),
            'num': (body.get('numero') or body.get('numero_factura') or '').strip(),
            'fecha': fecha,
            'sub': float(body.get('subtotal') or 0),
            'igv': float(body.get('igv') or 0),
            'tot': float(body.get('total') or 0),
            'notas': body.get('notas', ''),
            'items': _json.dumps(body.get('items', [])),
            'moneda': body.get('moneda', 'PEN'),
            'img': imagen_path,
        }).scalar()
        db.commit()
        return json_ok({'ok': True, 'id': int(new_id), 'imagen_path': imagen_path})
    except Exception:
        db.rollback()
        import traceback; traceback.print_exc()
        return json_err('Error al guardar factura', 500)
    finally:
        db.close()


async def api_mobile_factura_agregar_stock(request: Request) -> JSONResponse:
    """POST /api/mobile/facturas/{fid}/agregar-stock
    Suma los items de la factura al inventario con match fuzzy."""
    import unicodedata as _u
    from sqlalchemy import text as _sql_text
    def _norm(s):
        s = _u.normalize('NFKD', s or '').encode('ASCII', 'ignore').decode()
        return ''.join(c if (c.isalnum() or c == ' ') else ' ' for c in s.lower()).strip()[:150]

    user = _require_admin(request)
    if isinstance(user, JSONResponse):
        return user
    fid_raw = request.path_params.get('fid', '')
    try:
        fid = int(fid_raw)
    except Exception:
        return json_err('ID inválido', 400)
    taller_id = int(user.get('taller_id') or 1)
    db = get_db()
    try:
        row = db.execute(_sql_text(
            "SELECT items_json, proveedor, ruc_proveedor FROM facturas "
            "WHERE id=:id AND taller_id=:t"
        ), {'id': fid, 't': taller_id}).fetchone()
        if not row:
            return json_err('Factura no encontrada', 404)
        import json as _json
        items = _json.loads(row[0] or '[]')
        proveedor = row[1] or ''
        ruc = row[2] or ''
        added = 0; updated = 0; skipped = []
        hoy = datetime.now().strftime('%Y-%m-%d')
        for it in items:
            nombre = (it.get('nombre') or '').strip()
            if not nombre:
                skipped.append(it); continue
            upe = int(it.get('unidades_por_empaque') or 1)
            if upe < 1: upe = 1
            qty = float(it.get('cantidad') or 1)
            qty_stock = qty * upe
            precio_emp = float(it.get('precio_unitario') or 0)
            costo_unit = round(precio_emp / upe, 4) if upe else precio_emp
            # Margen/rentabilidad: si el item lo trae (desde el review), úsalo;
            # si no, default 40% que era el viejo hardcoded *1.4.
            try:
                margen_pct = float(it.get('rentabilidad') or it.get('margen') or 40)
            except (ValueError, TypeError):
                margen_pct = 40.0
            if margen_pct < 0: margen_pct = 0.0
            precio_venta = round(costo_unit * (1 + margen_pct/100), 2)
            nombre_norm = _norm(nombre)
            codigo_provided = (it.get('codigo') or '').strip()
            codigo_barras = (it.get('codigo_barras') or '').strip()
            categoria = (it.get('categoria') or 'Repuesto').strip() or 'Repuesto'
            match = None
            # Prioridad de match: codigo_barras > codigo interno > nombre+ruc > nombre
            if codigo_barras:
                match = db.execute(_sql_text(
                    "SELECT codigo FROM inventario WHERE codigo_barras=:cb AND taller_id=:t"
                ), {'cb': codigo_barras, 't': taller_id}).fetchone()
            if not match and codigo_provided:
                match = db.execute(_sql_text(
                    "SELECT codigo FROM inventario WHERE codigo=:c AND taller_id=:t"
                ), {'c': codigo_provided, 't': taller_id}).fetchone()
            if not match and ruc:
                match = db.execute(_sql_text(
                    "SELECT codigo FROM inventario WHERE nombre_norm=:nn AND ruc_proveedor=:r AND taller_id=:t LIMIT 1"
                ), {'nn': nombre_norm, 'r': ruc, 't': taller_id}).fetchone()
            if not match:
                match = db.execute(_sql_text(
                    "SELECT codigo FROM inventario WHERE nombre_norm=:nn AND taller_id=:t LIMIT 1"
                ), {'nn': nombre_norm, 't': taller_id}).fetchone()
            if match:
                # Existe: sumar stock + actualizar costo/proveedor. NO tocamos precio
                # ni rentabilidad (conservan lo que el admin configuró antes).
                # Si viene codigo_barras y el producto no lo tenía, asignarlo.
                db.execute(_sql_text("""
                    UPDATE inventario SET stock = COALESCE(stock,0) + :q, costo = :cv,
                        proveedor = CASE WHEN :pv<>'' THEN :pv ELSE proveedor END,
                        ruc_proveedor = CASE WHEN :r<>'' THEN :r ELSE ruc_proveedor END,
                        codigo_barras = CASE WHEN :cb<>'' AND (codigo_barras IS NULL OR codigo_barras='')
                                              THEN :cb ELSE codigo_barras END,
                        unidades_por_empaque = :upe, fecha_ultimo_ingreso = CAST(:h AS date)
                    WHERE codigo=:c AND taller_id=:t
                """), {'q': qty_stock, 'cv': costo_unit, 'pv': proveedor, 'r': ruc,
                       'cb': codigo_barras, 'upe': upe, 'h': hoy, 'c': match[0], 't': taller_id})
                updated += 1
            else:
                codigo_new = codigo_provided or nombre[:12].upper().replace(' ', '_')[:20]
                existing = db.execute(_sql_text(
                    "SELECT 1 FROM inventario WHERE codigo=:c AND taller_id=:t"
                ), {'c': codigo_new, 't': taller_id}).fetchone()
                if existing:
                    import time as _t
                    codigo_new = (codigo_new[:15] + '_' + str(int(_t.time()) % 10000))[:20]
                db.execute(_sql_text("""
                    INSERT INTO inventario (codigo, codigo_barras, nombre, nombre_norm, categoria,
                        precio, costo, rentabilidad, stock, proveedor, ruc_proveedor,
                        unidades_por_empaque, fecha_ultimo_ingreso, taller_id)
                    VALUES (:cod, :cb, :nom, :nn, :cat, :pv, :cv, :rent, :st, :prov, :r, :upe,
                            CAST(:h AS date), :t)
                """), {'cod': codigo_new, 'cb': codigo_barras, 'nom': nombre, 'nn': nombre_norm,
                       'cat': categoria, 'pv': precio_venta, 'cv': costo_unit, 'rent': margen_pct,
                       'st': qty_stock, 'prov': proveedor, 'r': ruc, 'upe': upe, 'h': hoy, 't': taller_id})
                added += 1
        estado_agr = 1 if not skipped else 2
        db.execute(_sql_text(
            "UPDATE facturas SET agregado_inventario=:e WHERE id=:id AND taller_id=:t"
        ), {'e': estado_agr, 'id': fid, 't': taller_id})
        db.commit()
        return json_ok({'ok': True, 'items_added': added, 'items_updated': updated,
                        'items_skipped': len(skipped), 'parcial': bool(skipped)})
    except Exception:
        db.rollback()
        import traceback; traceback.print_exc()
        return json_err('Error al agregar items al inventario', 500)
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
        except Exception: pass
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
        _t_id = int(user.get('taller_id') or 1)
        try:
            _setup_flota_ctx(db, _t_id)
        except Exception:
            pass
        o = db.query(Orden).filter_by(consecutivo=orden_id, taller_id=_t_id).first()
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
        _t_id = int(user.get('taller_id') or 1)
        try:
            _setup_flota_ctx(db, _t_id)
        except Exception:
            pass
        o = db.query(Orden).filter_by(consecutivo=cons, taller_id=_t_id).first()
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
        _t_id = int(user.get('taller_id') or 1)
        try:
            _setup_flota_ctx(db, _t_id)
        except Exception:
            pass
        o = db.query(Orden).filter_by(consecutivo=cons, taller_id=_t_id).first()
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
        _t_id = int(user.get('taller_id') or 1)
        try:
            _setup_flota_ctx(db, _t_id)
        except Exception:
            pass
        o = db.query(Orden).filter_by(consecutivo=cons, taller_id=_t_id).first()
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
    """POST /api/ordenes/{id}/factura — sube PDF/imagen de factura.

    2026-04-29 fix: anadido _setup_flota_ctx + filtro taller_id (resolvia
    "Orden no encontrada" silencioso por RLS strict sin GUC seteado).
    Tambien magic-bytes validation (consistente con FASE 8 audit).
    """
    user = _require_auth(request)
    if isinstance(user, JSONResponse): return user
    cons = request.path_params.get('id', '')
    if not cons:
        return json_err('Consecutivo de orden requerido', 400)
    import os
    taller_id = int(user.get('taller_id') or 1)
    try:
        form = await request.form()
        file = form.get('file')
        if not file:
            return json_err('Sin archivo', 400)
        orig = getattr(file, 'filename', '') or 'factura'
        # Extension validada
        from utils.upload_validator import safe_extension, validate_upload_bytes
        ext = safe_extension(orig, '.pdf')
        if ext not in ('.pdf', '.jpg', '.jpeg', '.png', '.webp'):
            return json_err(f'Tipo de archivo no permitido: {ext}. Acepta PDF/JPG/PNG/WEBP', 400)
        # Leer contenido y validar magic bytes
        content = await file.read()
        ok, kind = validate_upload_bytes(content, ext)
        if not ok:
            try:
                from utils.security_events import track_upload_rejected
                ip = request.client.host if request.client else ''
                track_upload_rejected(ip, str(user.get('id', '')), orig, f'magic_mismatch:{kind}')
            except Exception:
                pass
            return json_err(f'Contenido del archivo invalido (esperaba {ext}, magic={kind})', 400)
        # Setear contexto RLS antes de cualquier query a tabla forzada
        db = get_db()
        try:
            try:
                _setup_flota_ctx(db, taller_id)
            except Exception:
                pass
            # Buscar orden con filtro taller_id explicito (anti-IDOR + anti-RLS-leak)
            o = db.query(Orden).filter_by(consecutivo=cons, taller_id=taller_id).first()
            if not o:
                return json_err('Orden no encontrada', 404)
            # Solo escribir el archivo cuando la orden este verificada
            cons_safe = cons.replace('#', '').replace('/', '-').replace(' ', '_')
            filename = f"factura_{cons_safe}_{secrets.token_hex(4)}{ext}"
            os.makedirs('/var/www/sandoval/static/facturas', exist_ok=True)
            filepath = os.path.join('/var/www/sandoval/static/facturas', filename)
            with open(filepath, 'wb') as f2:
                f2.write(content)
            try:
                os.chmod(filepath, 0o644)
            except OSError:
                pass
            url = f"/facturas/{filename}"
            o.factura_sunat = url
            db.commit()
        finally:
            db.close()
        return json_ok({'ok': True, 'url': url})
    except Exception as e:
        import logging as _lg
        _lg.getLogger(__name__).warning('api_orden_subir_factura error: %s', e, exc_info=True)
        return json_err(f'Error al subir factura: {type(e).__name__}', 500)


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



async def api_orden_registrar_abono(request: Request) -> JSONResponse:
    """POST /api/ordenes/{id}/abono — registra un abono parcial en la orden"""
    user = _require_admin(request)
    if isinstance(user, JSONResponse):
        return user
    orden_id = request.path_params.get('id', '')
    try:
        body = await request.json()
    except Exception:
        return json_err('Body invalido')
    monto = float(body.get('monto', 0) or 0)
    if monto <= 0:
        return json_err('Monto debe ser mayor a 0')
    metodo = body.get('metodo', 'Efectivo')
    nota = body.get('nota', '')
    from datetime import datetime as _dt
    db = get_db()
    try:
        _t_id = int(user.get('taller_id') or 1)
        try:
            _setup_flota_ctx(db, _t_id)
        except Exception:
            pass
        o = db.query(Orden).filter_by(consecutivo=orden_id, taller_id=_t_id).first()
        if not o:
            return json_err('Orden no encontrada', 404)
        pagos_list = list(o.pagos or [])
        nuevo_pago = {
            'fecha': _dt.now().strftime('%Y-%m-%d %H:%M:%S'),
            'monto': round(monto, 2),
            'metodo': metodo,
            'nota': nota,
            'usuario': user.get('nombre', 'App Movil'),
        }
        pagos_list.append(nuevo_pago)
        o.pagos = pagos_list
        o.monto_cobrado = round(sum(float(p.get('monto', 0)) for p in pagos_list), 2)
        historial = list(o.historial or [])
        historial.append({
            'fecha': nuevo_pago['fecha'],
            'accion': f"Abono S/ {monto:.2f} via {metodo} (App Movil)",
            'usuario': user.get('nombre', 'App Movil'),
        })
        o.historial = historial
        db.commit()
        # Calcular saldo
        items_reales = [
            it for it in (o.items_cotizacion or [])
            if isinstance(it, dict)
            and it.get('id') not in ('subtotal_line', 'igv_line', 'total_line')
            and it.get('categoria') not in ('Resumen', 'Impuesto', 'Total')
        ]
        presupuesto = sum(float(it.get('total', 0) or 0) for it in items_reales)
        total_pagado = o.monto_cobrado or 0
        saldo = round(presupuesto - total_pagado, 2)
        return JSONResponse({
            'ok': True,
            'total_pagado': total_pagado,
            'saldo': saldo,
            'pagos': pagos_list,
        })
    except Exception as e:
        db.rollback()
        return json_err(str(e))
    finally:
        db.close()


async def api_orden_get_pagos(request: Request) -> JSONResponse:
    """GET /api/ordenes/{id}/pagos — obtiene historial de abonos de la orden"""
    user = _require_admin(request)
    if isinstance(user, JSONResponse):
        return user
    orden_id = request.path_params.get('id', '')
    db = get_db()
    try:
        _t_id = int(user.get('taller_id') or 1)
        try:
            _setup_flota_ctx(db, _t_id)
        except Exception:
            pass
        o = db.query(Orden).filter_by(consecutivo=orden_id, taller_id=_t_id).first()
        if not o:
            return json_err('Orden no encontrada', 404)
        pagos_list = list(o.pagos or [])
        items_reales = [
            it for it in (o.items_cotizacion or [])
            if isinstance(it, dict)
            and it.get('id') not in ('subtotal_line', 'igv_line', 'total_line')
            and it.get('categoria') not in ('Resumen', 'Impuesto', 'Total')
        ]
        presupuesto = sum(float(it.get('total', 0) or 0) for it in items_reales)
        total_pagado = sum(float(p.get('monto', 0)) for p in pagos_list)
        saldo = round(presupuesto - total_pagado, 2)
        return JSONResponse({
            'ok': True,
            'presupuesto': round(presupuesto, 2),
            'total_pagado': round(total_pagado, 2),
            'saldo': saldo,
            'pagos': pagos_list,
        })
    finally:
        db.close()



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

async def api_orden_pdf_download(request):
    user = _require_auth(request)
    if isinstance(user, JSONResponse): return user
    orden_id = request.path_params.get("id","")
    db = get_db()
    try:
        _t_id = int(user.get("taller_id") or 1)
        try:
            _setup_flota_ctx(db, _t_id)
        except Exception:
            pass
        if user.get("rol") == "cliente":
            o = db.query(Orden).filter_by(consecutivo=orden_id, vehiculo_placa=user.get("placa","")).first()
        else:
            o = db.query(Orden).filter_by(consecutivo=orden_id, taller_id=_t_id).first()
        if not o: return json_err("Orden no encontrada", 404)
        if not o.pdf_cotizacion: return json_err("PDF no disponible", 404)
        pdf_url = "/" + o.pdf_cotizacion.replace("\\", "/").lstrip("/")
        return json_ok({"pdf_url": pdf_url, "disponible": True})
    finally:
        db.close()




def _os_path_exists(p):
    import os as _os
    return _os.path.isfile(p) if p else False
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


async def api_orden_informe_pdf(request: Request):
    """GET /api/ordenes/{id}/informe-final.pdf — genera y devuelve el informe completo de la orden.
    Acceso: staff (taller del JWT) o cliente (solo su placa)."""
    from starlette.responses import FileResponse
    user = _require_auth(request)
    if isinstance(user, JSONResponse):
        return user
    orden_id = request.path_params.get('id', '')
    if not orden_id:
        return json_err('Consecutivo vacío', 400)
    db = get_db()
    try:
        rol = user.get('rol')
        _t_id = int(user.get('taller_id') or 1)
        try:
            _setup_flota_ctx(db, _t_id)
        except Exception:
            pass
        if rol == 'cliente':
            o = db.query(Orden).filter_by(
                consecutivo=orden_id, cliente_id=user.get('id', '')
            ).first()
        elif rol == 'conductor':
            o = db.query(Orden).filter_by(
                consecutivo=orden_id, vehiculo_placa=user.get('placa', '')
            ).first()
        else:
            o = db.query(Orden).filter_by(consecutivo=orden_id, taller_id=_t_id).first()
        if not o:
            return json_err('Orden no encontrada', 404)
        taller_id = int(getattr(o, 'taller_id', None) or user.get('taller_id') or 1)
    finally:
        db.close()
    try:
        from utils.pdf_informe_orden import generar_informe_orden
        pdf_path = generar_informe_orden(orden_id, taller_id)
    except ValueError as e:
        return json_err(str(e), 404)
    except Exception as e:
        import traceback; traceback.print_exc()
        return json_err(f'Error generando informe: {e}', 500)
    import os as _os_ifr
    if not _os_ifr.path.isfile(pdf_path):
        return json_err('PDF no se generó', 500)
    safe_name = orden_id.replace('/', '_').replace(' ', '_').replace('#', '')
    return FileResponse(
        pdf_path,
        media_type='application/pdf',
        filename=f'informe_{safe_name}.pdf',
        headers={'Cache-Control': 'no-store'},
    )

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

def _codart_headers():
    tok = (_os_codart.environ.get("CODART_TOKEN") or "").strip()
    if not tok:
        return None
    return {
        "Authorization": f"Bearer {tok}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

def _codart_cache_get(key):
    row = _codart_cache.get(key)
    if not row: return None
    ts, payload = row
    if _time_codart.time() - ts > _CODART_TTL:
        _codart_cache.pop(key, None); return None
    return payload

def _codart_cache_put(key, payload):
    _codart_cache[key] = (_time_codart.time(), payload)

async def api_lookup_ruc(request: Request) -> JSONResponse:
    user = _require_auth(request)
    if isinstance(user, JSONResponse): return user
    ruc = (request.path_params.get("ruc") or "").strip()
    if not ruc.isdigit() or len(ruc) != 11:
        return json_err("RUC debe tener 11 dígitos", 400)
    cached = _codart_cache_get(f"ruc:{ruc}")
    if cached: return json_ok(cached)
    headers = _codart_headers()
    if headers is None:
        return json_err("CODART_TOKEN no configurado", 500)
    if _req_codart is None:
        return json_err("requests no disponible", 500)
    try:
        r = _req_codart.get(f"{_CODART_BASE}/sunat/ruc/{ruc}", headers=headers, timeout=8)
    except Exception as e:
        return json_err(f"Error SUNAT: {e}", 502)
    if r.status_code != 200:
        return json_err(f"SUNAT respondió {r.status_code}", 502)
    try:
        data = r.json()
    except Exception:
        return json_err("Respuesta SUNAT inválida", 502)
    if not data.get("success") or not data.get("result"):
        return json_ok({"ok": False, "error": data.get("message") or "No encontrado"})
    res = data["result"]
    payload = {
        "ok": True,
        "ruc": res.get("numero_documento") or ruc,
        "nombre": (res.get("razon_social") or "").strip(),
        "direccion": (res.get("direccion") or "").strip(),
        "estado": res.get("estado") or "",
        "condicion": res.get("condicion") or "",
        "distrito": res.get("distrito") or "",
        "provincia": res.get("provincia") or "",
        "departamento": res.get("departamento") or "",
        "tipo": res.get("tipo") or "",
        "actividad": res.get("actividad_economica") or "",
    }
    _codart_cache_put(f"ruc:{ruc}", payload)
    return json_ok(payload)

async def api_lookup_dni(request: Request) -> JSONResponse:
    user = _require_auth(request)
    if isinstance(user, JSONResponse): return user
    dni = (request.path_params.get("dni") or "").strip()
    if not dni.isdigit() or len(dni) != 8:
        return json_err("DNI debe tener 8 dígitos", 400)
    cached = _codart_cache_get(f"dni:{dni}")
    if cached: return json_ok(cached)
    headers = _codart_headers()
    if headers is None:
        return json_err("CODART_TOKEN no configurado", 500)
    if _req_codart is None:
        return json_err("requests no disponible", 500)
    try:
        r = _req_codart.get(f"{_CODART_BASE}/reniec/dni/{dni}", headers=headers, timeout=8)
    except Exception as e:
        return json_err(f"Error RENIEC: {e}", 502)
    if r.status_code != 200:
        return json_err(f"RENIEC respondió {r.status_code}", 502)
    try:
        data = r.json()
    except Exception:
        return json_err("Respuesta RENIEC inválida", 502)
    if not data.get("success") or not data.get("result"):
        return json_ok({"ok": False, "error": data.get("message") or "No encontrado"})
    res = data["result"]
    nombres = (res.get("first_name") or "").strip()
    ap_pat = (res.get("first_last_name") or "").strip()
    ap_mat = (res.get("second_last_name") or "").strip()
    payload = {
        "ok": True,
        "dni": res.get("document_number") or dni,
        "nombres": nombres,
        "apellido_paterno": ap_pat,
        "apellido_materno": ap_mat,
        "nombre_completo": " ".join(p for p in [nombres, ap_pat, ap_mat] if p),
    }
    _codart_cache_put(f"dni:{dni}", payload)
    return json_ok(payload)


async def api_orden_save_fase_data(request: Request) -> JSONResponse:
    """POST /api/ordenes/{id}/fase-data — guarda datos por fase en checklist_reparacion[fase]
    body: {fase: 'diagnostico'|'reparacion'|'control_calidad'|'entrega', datos: {...}}
    """
    user = _require_auth(request)
    if isinstance(user, JSONResponse): return user
    if user.get('rol') == 'cliente':
        return json_err('Acceso denegado', 403)
    cons = request.path_params.get('id','')
    try: body = await request.json()
    except: return json_err('Body invalido')
    fase = str(body.get('fase','')).strip()
    datos = body.get('datos', {})
    if not fase:
        return json_err('fase requerida')
    db = get_db()
    try:
        _t_id = int(user.get('taller_id') or 1)
        try:
            _setup_flota_ctx(db, _t_id)
        except Exception:
            pass
        o = db.query(Orden).filter_by(consecutivo=cons, taller_id=_t_id).first()
        if not o: return json_err('Orden no encontrada', 404)
        import json as _j, copy as _cp
        cl = {}
        raw = o.checklist_reparacion
        try:
            if isinstance(raw, str): cl = _j.loads(raw)
            elif isinstance(raw, dict): cl = raw
        except Exception: cl = {}
        if not isinstance(cl, dict): cl = {}
        cl[fase] = datos
        o.checklist_reparacion = _cp.deepcopy(cl)
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(o, 'checklist_reparacion')
        if fase == 'diagnostico' and isinstance(datos, dict) and datos.get('hallazgos'):
            o.diagnostico = datos['hallazgos']
        taller_id_o = int(getattr(o, 'taller_id', None) or user.get('taller_id') or 1)
        db.commit()
        # Trigger push automático según la fase guardada
        try:
            from utils.flota import notify_orden_event
            evento_map = {
                'diagnostico':     'diagnostico_listo',
                'repuestos':       'presupuesto_listo',
                'aprobacion':      'presupuesto_listo',
                'reparacion':      'reparacion_iniciada',
                'control_calidad': 'lista_entrega',
                'entrega':         'lista_entrega',
            }
            evt = evento_map.get(fase)
            if evt:
                notify_orden_event(db, taller_id=taller_id_o, consecutivo=cons, evento=evt)
        except Exception:
            pass  # push fallido no debe romper el guardado
        return json_ok({'ok': True})
    except Exception as e:
        db.rollback(); return json_err(str(e))
    finally: db.close()


async def api_orden_get_fase_data(request: Request) -> JSONResponse:
    """GET /api/ordenes/{id}/fase-data — devuelve checklist_reparacion completo"""
    user = _require_auth(request)
    if isinstance(user, JSONResponse): return user
    cons = request.path_params.get('id','')
    db = get_db()
    try:
        _t_id = int(user.get('taller_id') or 1)
        try:
            _setup_flota_ctx(db, _t_id)
        except Exception:
            pass
        o = db.query(Orden).filter_by(consecutivo=cons, taller_id=_t_id).first()
        if not o: return json_err('Orden no encontrada', 404)
        raw = o.checklist_reparacion or {}
        if isinstance(raw, str):
            import json as _j
            try: raw = _j.loads(raw)
            except: raw = {}
        return json_ok(raw if isinstance(raw, dict) else {})
    finally: db.close()


async def api_orden_share_link_mobile(request: Request) -> JSONResponse:
    """POST /api/ordenes/{id}/share-link — genera código corto para /aprobacion/"""
    user = _require_auth(request)
    if isinstance(user, JSONResponse): return user
    if user.get('rol') == 'cliente':
        return json_err('Acceso denegado', 403)
    cons = request.path_params.get('id','')
    import secrets as _sec, string as _str, uuid as _uuid
    from sqlalchemy import text as _sqltxt
    db = get_db()
    try:
        _t_id = int(user.get('taller_id') or 1)
        try:
            _setup_flota_ctx(db, _t_id)
        except Exception:
            pass
        o = db.query(Orden).filter_by(consecutivo=cons, taller_id=_t_id).first()
        if not o: return json_err('Orden no encontrada', 404)
        token = getattr(o, 'approval_token', None) or ''
        if (not token) or str(token).startswith('USED_'):
            token = _uuid.uuid4().hex
            o.approval_token = token
            db.commit()
        taller_id = getattr(o, 'taller_id', None) or 1
        existing = db.execute(_sqltxt(
            "SELECT code FROM short_links WHERE token=:tok AND taller_id=:t ORDER BY created_at DESC LIMIT 1"
        ), {"tok": token, "t": taller_id}).fetchone()
        if existing:
            return json_ok({'ok': True, 'code': existing[0], 'token': token})
        alphabet = _str.ascii_letters + _str.digits
        code = ''
        for _ in range(10):
            code = ''.join(_sec.choice(alphabet) for _ in range(6))
            dup = db.execute(_sqltxt("SELECT 1 FROM short_links WHERE code=:c"), {"c": code}).fetchone()
            if not dup: break
        else:
            return json_err('No se pudo generar codigo', 500)
        db.execute(_sqltxt(
            "INSERT INTO short_links (code, token, taller_id, kind) VALUES (:c, :tok, :t, 'aprobacion')"
        ), {"c": code, "tok": token, "t": taller_id})
        db.commit()
        return json_ok({'ok': True, 'code': code, 'token': token})
    except Exception as e:
        db.rollback(); return json_err(str(e))
    finally: db.close()


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
    # 2026-05-04 MULTI-TENANT FIX (SHIM legacy): taller_id desde sesion
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


# ══════════════════════════════════════════════════════════════════════════════
# FLOTA EMPRESARIAL + WEB PUSH — handlers HTTP
# (las funciones de lógica viven en utils/flota.py)
# ══════════════════════════════════════════════════════════════════════════════
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


# ─── ADMIN del taller ──────────────────────────────────────────────────────────
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


def _cliente_id_pertenece_taller(db, cliente_id: str, taller_id: int) -> bool:
    """Verificar que el cliente pertenece a este taller (RLS-safe)."""
    r = db.execute(_sa_text("SELECT 1 FROM clientes WHERE id=:c AND taller_id=:t"),
                   {'c': cliente_id, 't': taller_id}).fetchone()
    return r is not None


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


# ─── CLIENTE jefe ──────────────────────────────────────────────────────────────
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


# ─── Cambio de PIN propio (cliente o conductor) ────────────────────────────────
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


# ─── Web Push ──────────────────────────────────────────────────────────────────
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
    app.add_api_route('/api/ordenes/{id}/evidencia-from-url', api_orden_evidencia_from_url, methods=['POST', 'OPTIONS'])
    app.add_api_route('/api/ordenes/{orden_id}/eliminar', api_delete_orden, methods=['POST','OPTIONS'])
    app.add_api_route('/api/ordenes/{id}',            api_orden_get,           methods=['GET',  'OPTIONS'])
    app.add_api_route('/api/ordenes/{id}/diagnostico',  api_orden_guardar_diagnostico, methods=['POST','OPTIONS'])
    app.add_api_route('/api/ordenes/{id}/items',        api_orden_guardar_items,       methods=['POST','OPTIONS'])
    app.add_api_route('/api/ordenes/{id}/checklist',    api_orden_guardar_checklist,   methods=['POST','OPTIONS'])
    app.add_api_route('/api/ordenes/{id}/abono',        api_orden_registrar_abono,     methods=['POST', 'OPTIONS'])
    app.add_api_route('/api/ordenes/{id}/pagos',        api_orden_get_pagos,           methods=['GET',  'OPTIONS'])
    app.add_api_route('/api/ordenes/{id}/fase-data',    api_orden_save_fase_data,      methods=['POST', 'OPTIONS'])
    app.add_api_route('/api/ordenes/{id}/fase-data',    api_orden_get_fase_data,       methods=['GET',  'OPTIONS'])
    app.add_api_route('/api/ordenes/{id}/share-link',   api_orden_share_link_mobile,   methods=['POST', 'OPTIONS'])
    app.add_api_route('/api/inventario/{codigo}/usar', api_inventario_usar,            methods=['POST', 'OPTIONS'])
    app.add_api_route('/api/ordenes/{id}/factura',      api_orden_subir_factura,       methods=['POST', 'OPTIONS'])



    app.add_api_route('/api/clientes',                api_clientes_list,       methods=['GET',  'OPTIONS'])
    app.add_api_route('/api/clientes/nuevo',          api_cliente_create,      methods=['POST', 'OPTIONS'])
    app.add_api_route('/api/clientes/{id}/vehiculos', api_vehiculos_cliente,   methods=['GET',  'OPTIONS'])
    app.add_api_route('/api/clientes/{id}/perfil-completo', api_cliente_perfil_completo, methods=['GET', 'OPTIONS'])
    app.add_api_route('/api/vehiculos',               api_vehiculos_list,      methods=['GET',  'OPTIONS'])
    app.add_api_route('/api/vehiculos/nuevo',         api_vehiculo_create,     methods=['POST', 'OPTIONS'])
    app.add_api_route('/api/inventario',              api_inventario_list,     methods=['GET',  'OPTIONS'])
    app.add_api_route('/api/inventario/buscar',       api_inventario_buscar,   methods=['GET',  'OPTIONS'])
    # === CODART LOOKUP ROUTES ===
    app.add_api_route('/api/lookup/ruc/{ruc}', api_lookup_ruc, methods=['GET', 'OPTIONS'])
    app.add_api_route('/api/lookup/dni/{dni}', api_lookup_dni, methods=['GET', 'OPTIONS'])
    app.add_api_route('/api/mobile/facturas/ocr',                       api_mobile_facturas_ocr,          methods=['POST', 'OPTIONS'])
    app.add_api_route('/api/mobile/facturas/crear',                     api_mobile_facturas_crear,        methods=['POST', 'OPTIONS'])
    app.add_api_route('/api/mobile/facturas/{fid}/agregar-stock',       api_mobile_factura_agregar_stock, methods=['POST', 'OPTIONS'])
    app.add_api_route('/api/reportes/ganancia',        api_reportes_ganancia,        methods=['GET',  'OPTIONS'])
    app.add_api_route('/api/reportes/ganancia-diaria', api_reportes_ganancia_diaria, methods=['GET',  'OPTIONS'])
    app.add_api_route('/api/notas-venta',             api_notas_list,          methods=['GET',  'OPTIONS'])
    app.add_api_route('/api/notas-venta/nueva',       api_nota_create,         methods=['POST', 'OPTIONS'])
    app.add_api_route('/api/citas',                   api_citas_list,          methods=['GET',  'OPTIONS'])
    app.add_api_route('/api/citas/nueva',             api_cita_create,         methods=['POST', 'OPTIONS'])
    app.add_api_route('/api/cliente/mis-ordenes',     api_cliente_mis_ordenes, methods=['GET',  'OPTIONS'])
    app.add_api_route('/api/ordenes/{id}/informe-final.pdf',  api_orden_informe_pdf, methods=['GET','OPTIONS'])
    app.add_api_route('/api/cliente/ordenes/{id}/informe-final.pdf', api_orden_informe_pdf, methods=['GET','OPTIONS'])
    app.add_api_route('/api/cliente/ordenes/{id}/presupuesto.pdf', api_cliente_presupuesto_pdf, methods=['GET','OPTIONS'])
    app.add_api_route('/api/cliente/mis-citas',       api_cliente_mis_citas,   methods=['GET',  'OPTIONS'])
    app.add_api_route('/api/cliente/aprobar',         api_cliente_aprobar,     methods=['POST', 'OPTIONS'])
    app.add_api_route('/api/portal/notificaciones', api_portal_notificaciones, methods=['GET', 'OPTIONS'])
    app.add_api_route('/api/portal/notificaciones/marcar-leidas', api_portal_marcar_leidas, methods=['POST', 'OPTIONS'])
    app.add_api_route('/api/cliente/mis-pagos', api_cliente_historial_pagos, methods=['GET','OPTIONS'])
    app.add_api_route('/api/cliente/aprobar-presupuesto', api_cliente_aprobar_portal, methods=['POST','OPTIONS'])
    app.add_api_route('/api/cliente/calificar', api_cliente_calificar, methods=['POST','OPTIONS'])
    app.add_api_route('/api/ordenes/{id}/pdf', api_orden_pdf_download, methods=['GET','OPTIONS'])
    app.add_api_route('/api/admin/nuevas-ordenes', api_admin_nuevas_ordenes, methods=['GET','OPTIONS'])

    # ── Flota empresarial + Web Push ───────────────────────────────────
    # ADMIN del taller
    app.add_api_route('/admin/api/clientes/{cid}/flota',                    admin_listar_flota,            methods=['GET','OPTIONS'])
    app.add_api_route('/admin/api/clientes/{cid}/flota/{placa}/conductor',  admin_asignar_conductor,       methods=['POST','PUT','OPTIONS'])
    app.add_api_route('/admin/api/clientes/{cid}/flota/{placa}/conductor',  admin_quitar_conductor,        methods=['DELETE'])
    app.add_api_route('/admin/api/clientes/{cid}/flota/{placa}/reset-pin',  admin_reset_pin_conductor,     methods=['POST','OPTIONS'])
    app.add_api_route('/admin/api/clientes/{cid}/flota/{placa}/activo',     admin_toggle_conductor_activo, methods=['POST','OPTIONS'])
    app.add_api_route('/admin/api/clientes/{cid}/audit',                    admin_get_audit,               methods=['GET','OPTIONS'])
    app.add_api_route('/admin/api/clientes/{cid}/tipo',                     admin_set_tipo_cliente,        methods=['POST','OPTIONS'])
    app.add_api_route('/admin/api/clientes/{cid}/reset-pin-jefe',           admin_reset_pin_jefe,          methods=['POST','OPTIONS'])
    # CLIENTE jefe
    app.add_api_route('/api/cliente/mi-flota',                              cliente_mi_flota,              methods=['GET','OPTIONS'])
    app.add_api_route('/api/cliente/mi-flota/{placa}/conductor',            cliente_asignar_conductor,     methods=['POST','PUT','OPTIONS'])
    app.add_api_route('/api/cliente/mi-flota/{placa}/conductor',            cliente_quitar_conductor,      methods=['DELETE'])
    app.add_api_route('/api/cliente/mi-flota/{placa}/reset-pin',            cliente_reset_pin_conductor,   methods=['POST','OPTIONS'])
    app.add_api_route('/api/cliente/mi-flota/{placa}/activo',               cliente_toggle_conductor_activo, methods=['POST','OPTIONS'])
    app.add_api_route('/api/cliente/audit',                                 cliente_get_audit,             methods=['GET','OPTIONS'])
    # CAMBIO DE PIN propio
    app.add_api_route('/api/cliente/cambiar-pin',                           api_cliente_cambiar_pin,       methods=['POST','OPTIONS'])
    # WEB PUSH
    app.add_api_route('/api/push/vapid-key',                                api_push_vapid_key,            methods=['GET','OPTIONS'])
    app.add_api_route('/api/push/subscribe',                                api_push_subscribe,            methods=['POST','OPTIONS'])
    app.add_api_route('/api/push/unsubscribe',                              api_push_unsubscribe,          methods=['POST','OPTIONS'])
    # Notificación manual desde admin
    app.add_api_route('/admin/api/ordenes/{cons}/notificar',                admin_notificar_orden,         methods=['POST','OPTIONS'])

    try:
        from utils.api_mobile_admin import register_mobile_admin_routes
        register_mobile_admin_routes(app)
    except Exception as _e:
        import logging
        logging.getLogger(__name__).warning("Mobile admin endpoints no registrados: %s", _e)

    try:
        from utils.api_extensions import register_extensions_routes
        register_extensions_routes(app)
    except Exception as _e:
        import logging
        logging.getLogger(__name__).warning("Extensions endpoints no registrados: %s", _e)


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

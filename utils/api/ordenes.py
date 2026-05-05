"""utils.api.ordenes — endpoints CRUD orden de servicio."""
from __future__ import annotations
import os
import json
import secrets
from datetime import datetime
from typing import Optional
from starlette.requests import Request
from starlette.responses import JSONResponse, FileResponse
from sqlalchemy import text as _sa_text
from utils.models import get_db, Orden, Cliente, Vehiculo, ItemInventario
from utils.api.common import _require_auth, _require_admin, json_ok, json_err
from utils.api.tenant import _setup_flota_ctx, _flota_actor_meta
from utils.upload_validator import validate_upload_bytes, safe_extension


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

async def api_ordenes_list(request: Request) -> JSONResponse:
    user = _require_admin(request)
    if isinstance(user, JSONResponse):
        return user
    # 2026-05-05 P0 IDOR FIX (sync-guardian audit): filtrar explícitamente por
    # taller_id del JWT. Antes la query NO filtraba — RLS era la única defensa,
    # y si app.taller_id no estaba seteado un staff podía ver órdenes de otros
    # talleres. Ahora defense-in-depth: filtro app + RLS GUC.
    taller_id = user.get('taller_id')
    if not taller_id:
        return json_err('taller_id ausente en sesión', 401)
    db = get_db()
    try:
        estado = request.query_params.get('estado')
        q = db.query(Orden).filter(Orden.taller_id == taller_id).order_by(Orden.fecha.desc())
        if estado:
            q = q.filter(Orden.estado == estado)
        ordenes = q.limit(500).all()
        cli_ids = list({o.cliente_id for o in ordenes if o.cliente_id})
        placas = list({o.vehiculo_placa for o in ordenes if o.vehiculo_placa})
        cli_map = {c.id: c for c in db.query(Cliente).filter(Cliente.id.in_(cli_ids), Cliente.taller_id == taller_id).all()} if cli_ids else {}
        veh_map = {v.placa: v for v in db.query(Vehiculo).filter(Vehiculo.placa.in_(placas), Vehiculo.taller_id == taller_id).all()} if placas else {}
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
    # 2026-05-04 MULTI-TENANT FIX: definir _t_id desde sesion
    # (linea 310 lo usaba sin haberlo definido — NameError latente).
    _t_id = int(user.get('taller_id') or 1)
    try:
        body = await request.json()
    except Exception:
        return json_err('Body inválido')
    db = get_db()
    try:
        _setup_flota_ctx(db, _t_id)
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
        # 2026-05-04 MULTI-TENANT FIX: taller_id desde JWT/sesion (antes hardcoded =1)
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
        # 2026-05-04 P2-B4 FIX: validacion magic bytes anti polyglot files.
        # Antes confiabamos en content_type del cliente (manipulable). Ahora se
        # extrae extension del filename, se valida con safe_extension (whitelist),
        # y se compara con magic bytes reales (validate_upload_bytes).
        # Bloquea PDFs disfrazados de JPG, SVG con <script> disfrazado de PNG, etc.
        from utils.upload_validator import validate_upload_bytes, safe_extension
        orig_name = getattr(file, 'filename', '') or ''
        ext_with_dot = safe_extension(orig_name, default='.bin')
        if ext_with_dot == '.bin':
            return json_err('Extension no permitida (solo jpg/png/gif/webp/pdf/mp4/mov/avi)', 400)
        ok, kind = validate_upload_bytes(content, ext_with_dot)
        if not ok:
            return json_err(f'Archivo invalido (magic_mismatch): {kind}', 400)
        ext = ext_with_dot.lstrip('.')
        # Categorizar tipo desde el `kind` real (no del content_type del cliente)
        is_pdf   = kind == 'pdf'
        is_video = kind in ('mp4','mov','webm','avi','mkv','3gp')
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
        # 2026-05-04 P1-A1 FIX: usar `auth` (no `user` que era undefined → NameError)
        _t_id = int(auth.get('taller_id') or 1)
        try:
            _setup_flota_ctx(db, _t_id)
        except Exception:
            pass
        # 2026-05-04 P1-A1 FIX: eliminado fallback IDOR `filter_by(id=...)` SIN taller_id.
        # Antes: si no encontraba por consecutivo, intentaba por ID numérico SIN tenant filter
        # → permitía borrar órdenes de OTROS talleres adivinando el ID.
        # Ahora: solo busca por consecutivo Y taller_id (RLS-safe). Si no existe → 404.
        o = db.query(Orden).filter_by(consecutivo=orden_id, taller_id=_t_id).first()
        if not o:
            # Permitir búsqueda por id numérico SOLO con tenant filter explícito
            try:
                o = db.query(Orden).filter_by(id=int(orden_id), taller_id=_t_id).first()
            except (ValueError, TypeError):
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


"""
SANDOVAL Dashboard - Sistema de Notificaciones
Notificaciones in-app + preparación para WhatsApp/Email
"""

import os
import json
import os as _os
from datetime import datetime, timedelta

# URL base del sistema (configurable via .env o config BD)
BASE_URL = _os.getenv('BASE_URL', f'http://187.77.62.67:3000')
from utils.models import get_db, Actividad, Orden, ItemInventario, Cliente, Cita
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text
import logging
logger = logging.getLogger(__name__)

# Multi-tenant — mismo valor que routers._common.TALLER_ID
# 2026-04-29 audit V11: TALLER_ID configurable via env (default=1 para Sandoval anchor)
TALLER_ID = int(os.environ.get('SANDOVAL_TALLER_ID', '1'))


def _ensure_rls_context():
    """Cuando notifications.py se llama desde un contexto sin HTTP middleware
    (telegram bot, scripts), el ContextVar de RLS no está seteado y las
    queries serían bloqueadas por las policies STRICT. Forzamos el setting.
    """
    try:
        from utils.rls_session import set_current_taller_id
        set_current_taller_id(TALLER_ID)
    except Exception:
        pass


# ─── Notificaciones In-App ───

def get_notifications(limit=20) -> list:
    _ensure_rls_context()
    """Obtiene notificaciones/alertas del sistema (solo para admin/personal)"""
    notifs = []
    db = get_db()
    try:
        # 0. Citas nuevas agendadas por clientes (NO vistas aún por admin — van primero)
        import sqlalchemy as _sa
        citas_no_vistas = db.query(Cita).filter_by(estado='programada').filter(
            _sa.or_(Cita.vista_admin == None, Cita.vista_admin == 0)
        ).order_by(Cita.id.desc()).limit(10).all()
        citas_vistas = db.query(Cita).filter_by(estado='programada', vista_admin=1).order_by(Cita.id.desc()).limit(3).all()
        citas_para_mostrar = citas_no_vistas + citas_vistas

        clientes_map = {c.id: c for c in db.query(Cliente).all()}
        for cita in citas_para_mostrar:
            cliente = clientes_map.get(cita.cliente_id)
            nombre_cli = f'{cliente.nombre} {cliente.apellidos}'.strip() if cliente else 'Cliente'
            es_nueva = getattr(cita, 'vista_admin', 0) == 0
            notifs.append({
                'icon': 'event_available',
                'color': 'blue-7' if es_nueva else 'blue-4',
                'title': f'{"🔔 " if es_nueva else ""}Cita agendada por {nombre_cli}',
                'detail': f'Fecha: {cita.fecha_cita} {cita.hora or ""} · {cita.motivo or ""}',
                'time': cita.fecha_cita,
                'type': 'info' if not es_nueva else 'warning',
            })

        # 1. Órdenes pendientes de aprobación
        pendientes = db.query(Orden).filter_by(approval_status='pendiente').filter(
            Orden.estado.in_(['RECEPCIÓN', 'APROBACIÓN'])
        ).all()
        for o in pendientes:
            notifs.append({
                'icon': 'pending_actions',
                'color': 'orange-6',
                'title': f'Orden {o.consecutivo} pendiente de aprobación',
                'detail': f'Cliente no ha respondido aún',
                'time': o.fecha,
                'type': 'warning',
            })
        
        # 2. Stock bajo
        low_stock = db.query(ItemInventario).filter(
            ItemInventario.stock < ItemInventario.stock_minimo
        ).all()
        for item in low_stock:
            notifs.append({
                'icon': 'warning',
                'color': 'red-6',
                'title': f'Stock bajo: {item.nombre}',
                'detail': f'Quedan {item.stock} unidades (mín: {item.stock_minimo})',
                'time': datetime.now().strftime('%Y-%m-%d'),
                'type': 'danger',
            })
        
        # 3. Órdenes aprobadas recientemente
        aprobadas = db.query(Orden).filter_by(approval_status='aprobado').order_by(
            Orden.approval_date.desc()
        ).limit(5).all()
        for o in aprobadas:
            notifs.append({
                'icon': 'check_circle',
                'color': 'green-6',
                'title': f'Orden {o.consecutivo} aprobada por cliente',
                'detail': f'Fecha: {o.approval_date}',
                'time': o.approval_date or o.fecha,
                'type': 'success',
            })
        
        # 4. Órdenes rechazadas
        rechazadas = db.query(Orden).filter_by(approval_status='rechazado').order_by(
            Orden.approval_date.desc()
        ).limit(3).all()
        for o in rechazadas:
            notifs.append({
                'icon': 'cancel',
                'color': 'red-6',
                'title': f'Orden {o.consecutivo} RECHAZADA por cliente',
                'detail': f'Fecha: {o.approval_date}',
                'time': o.approval_date or o.fecha,
                'type': 'danger',
            })
        
        # Ordenar por tipo de urgencia
        priority = {'danger': 0, 'warning': 1, 'success': 2, 'info': 3}
        notifs.sort(key=lambda n: priority.get(n['type'], 99))
        
    finally:
        db.close()
    
    return notifs[:limit]


def get_notification_count() -> int:
    _ensure_rls_context()
    """Cuenta alertas activas (pendientes + stock bajo + citas no vistas por admin)"""
    db = get_db()
    try:
        pendientes = db.query(Orden).filter_by(approval_status='pendiente').filter(
            Orden.estado.in_(['RECEPCIÓN', 'APROBACIÓN'])
        ).count()
        low_stock = db.query(ItemInventario).filter(
            ItemInventario.stock < ItemInventario.stock_minimo
        ).count()
        # Solo citas programadas que el admin aún no ha visto
        import sqlalchemy as _sa
        citas_nuevas = db.query(Cita).filter_by(estado='programada').filter(
            _sa.or_(Cita.vista_admin == None, Cita.vista_admin == 0)
        ).count()
        return pendientes + low_stock + citas_nuevas
    except Exception:
        return 0
    finally:
        db.close()


def marcar_citas_vistas_admin():
    """Marca todas las citas programadas como vistas por el admin"""
    _ensure_rls_context()
    db = get_db()
    try:
        import sqlalchemy as _sa
        db.query(Cita).filter_by(estado='programada').filter(
            _sa.or_(Cita.vista_admin == None, Cita.vista_admin == 0)
        ).update({'vista_admin': 1})
        db.commit()
    except Exception as e:
        logger.warning('[NOTIF] Error marcando citas: %s', e)
    finally:
        db.close()


def marcar_notifs_leidas_cliente(cliente_id, ids: list):
    """Guarda en DB la lista de IDs de notificaciones leídas por el cliente (SQL directo, sin caché ORM)"""
    _ensure_rls_context()
    import json as _json
    from sqlalchemy import text as _text
    db = get_db()
    try:
        # Leer valor actual con SQL directo
        row = db.execute(
            _text("SELECT notifs_leidas FROM clientes WHERE id = :cid AND taller_id=:t"),
            {'cid': str(cliente_id), 't': TALLER_ID}
        ).fetchone()
        ya_leidas = []
        if row and row[0]:
            try:
                ya_leidas = _json.loads(row[0])
            except Exception:
                ya_leidas = []
        # Combinar sin duplicados
        nuevas = list(set(ya_leidas + ids))
        # Escribir con SQL directo
        db.execute(
            _text("UPDATE clientes SET notifs_leidas = :val WHERE id = :cid AND taller_id=:t"),
            {'val': _json.dumps(nuevas), 'cid': str(cliente_id), 't': TALLER_ID}
        )
        db.commit()
    except Exception as e:
        logger.warning('[NOTIF] Error guardando leidas: %s', e)
    finally:
        db.close()


def get_client_notifications(cliente_id, placa: str) -> list:
    """Notificaciones exclusivas para el portal del cliente"""
    # 2026-05-04 FIX: clientes.id migrado a CLI-YYYYMMDD-NNN (varchar). Sesiones
    # legacy traen integer; castear a str para evitar
    # `operator does not exist: character varying = integer` en queries Cita/Vehiculo.
    cliente_id = str(cliente_id) if cliente_id is not None else ""
    _ensure_rls_context()
    import json as _json
    from sqlalchemy import text as _text
    notifs = []
    db = get_db()
    try:
        # Leer notifs_leidas con SQL directo para evitar caché de SQLAlchemy
        try:
            row = db.execute(
                _text("SELECT notifs_leidas FROM clientes WHERE id = :cid AND taller_id=:t"),
                {'cid': str(cliente_id), 't': TALLER_ID}
            ).fetchone()
            leidas_raw = row[0] if row and row[0] else '[]'
            leidas = set(_json.loads(leidas_raw))
        except Exception:
            leidas = set()

        # Citas confirmadas del cliente
        citas_confirmadas = db.query(Cita).filter_by(
            cliente_id=cliente_id, estado='confirmada'
        ).order_by(Cita.id.desc()).limit(5).all()
        for cita in citas_confirmadas:
            notif_id = f'cita_conf_{cita.id}'
            notifs.append({
                'id': notif_id,
                'nueva': notif_id not in leidas,
                'icon_cls': 'verde',
                'icon': '✅',
                'titulo': 'Tu cita fue confirmada',
                'desc': f'Te esperamos el {cita.fecha_cita} a las {cita.hora or ""}. {cita.motivo or ""}',
                'tiempo': cita.fecha_cita,
            })

        # Orden activa del cliente
        todos_vehiculos = db.query(
            __import__('utils.models', fromlist=['Vehiculo']).Vehiculo
        ).filter_by(cliente_id=cliente_id).all()
        placas = [v.placa for v in todos_vehiculos]
        if placas:
            active_order = db.query(Orden).filter(
                Orden.vehiculo_placa.in_(placas),
                Orden.estado.notin_(['ARCHIVADO', 'ENTREGA'])
            ).order_by(Orden.fecha.desc()).first()

            if active_order:
                # 1. Notificación General de Estado de Fase
                nid_orden = f'orden_estado_{active_order.consecutivo}_{active_order.estado}'
                
                # Mensajes dinámicos según fase (FLORO)
                fase_msg = {
                    'RECEPCIÓN': 'Su vehículo ha ingresado a nuestras instalaciones y está listo para ser evaluado.',
                    'DIAGNÓSTICO': 'Nuestros técnicos especializados están analizando el estado de su vehículo.',
                    'REPUESTOS': 'Estamos cotizando los repuestos necesarios y verificando stock en almacén.',
                    'APROBACIÓN': '¡Atención! Su vehículo está a la espera de su verificación del presupuesto para poder proseguir.',
                    'REPARACIÓN': '¡Buenas noticias! Estamos ejecutando los trabajos técnicos en su vehículo.',
                    'CONTROL': 'Estamos realizando las pruebas finales para garantizar la máxima calidad del servicio.',
                    'ENTREGA': 'Su vehículo está listo. Puede pasar a recogerlo en nuestras instalaciones.'
                }
                
                notifs.append({
                    'id': nid_orden,
                    'nueva': nid_orden not in leidas,
                    'icon_cls': 'azul' if active_order.estado != 'APROBACIÓN' else 'naranja',
                    'icon': '🔧' if active_order.estado != 'APROBACIÓN' else '⚠️',
                    'titulo': f'Estado: {active_order.estado}',
                    'desc': fase_msg.get(active_order.estado, f'Su vehículo se encuentra en fase de {active_order.estado}.'),
                    'tiempo': f'Orden #{active_order.consecutivo} · Hoy',
                })

                # 2. Notificaciones Específicas de Aprobación
                if active_order.approval_status == 'aprobado':
                    nid_apr = f'aprobado_{active_order.consecutivo}'
                    notifs.append({
                        'id': nid_apr,
                        'nueva': nid_apr not in leidas,
                        'icon_cls': 'verde',
                        'icon': '✅',
                        'titulo': 'Presupuesto Aceptado',
                        'desc': 'Se ha registrado su autorización. El taller ha procedido con la reparación inmediata.',
                        'tiempo': active_order.approval_date or 'Reciente',
                    })
                elif active_order.approval_status == 'pendiente' and active_order.estado == 'APROBACIÓN':
                    nid_pend = f'pendiente_det_{active_order.consecutivo}'
                    notifs.append({
                        'id': nid_pend,
                        'nueva': nid_pend not in leidas,
                        'icon_cls': 'naranja',
                        'icon': '💰',
                        'titulo': 'Acción Requerida: Aprobación',
                        'desc': 'Su cotización está lista. Ingrese a ver el detalle y autorice los trabajos para continuar.',
                        'tiempo': 'Esperando respuesta',
                    })

        # Citas canceladas del cliente (Rechazadas por el taller)
        citas_canceladas = db.query(Cita).filter_by(
            cliente_id=cliente_id, estado='cancelada'
        ).order_by(Cita.id.desc()).limit(3).all()
        for cita in citas_canceladas:
            notif_id = f'cita_canc_{cita.id}'
            notifs.append({
                'id': notif_id,
                'nueva': notif_id not in leidas,
                'icon_cls': 'rojo',
                'icon': '❌',
                'titulo': 'Cita cancelada por el taller',
                'desc': f'El taller canceló su cita para el {cita.fecha_cita} debido a una alta demanda de reparaciones. Por favor, pruebe agendando para otro día.',
                'tiempo': cita.fecha_cita,
            })
    except Exception as e:
        logger.warning('[NOTIF_CLIENT] Error: %s', e)
    finally:
        db.close()
    return notifs[:6]


# ─── Generador de Links de Aprobación ───

def generate_approval_message(order_consecutivo: str, base_url: str = None) -> dict:
    if base_url is None:
        base_url = BASE_URL
    """Genera el mensaje de aprobación para enviar al cliente"""
    _ensure_rls_context()
    db = get_db()
    try:
        # 2026-04-29 audit-fix IDOR: filtrar por TALLER_ID configurable
        _tid = TALLER_ID  # de la constante configurable del modulo
        order = db.query(Orden).filter_by(consecutivo=order_consecutivo, taller_id=_tid).first()
        if not order:
            return {'error': 'Orden no encontrada'}
        
        client = db.query(Cliente).filter_by(id=order.cliente_id).first()
        
        # Si la orden ya fue aprobada/rechazada (por ejemplo en recepción), 
        # y estamos enviando una cotización de repuestos, reseteamos el estado 
        # para que el cliente pueda volver a interactuar con el nuevo presupuesto.
        if order.approval_status in ('aprobado', 'rechazado') or not order.approval_token:
            import secrets
            # Usar hex para evitar guiones que a veces causan truncamiento en links auto-detectados
            order.approval_token = secrets.token_hex(20) 
            order.approval_status = 'pendiente'
            order.approval_date = None
            db.commit()
        
        link = f"{base_url}/aprobacion/{order.approval_token}"
        
        # Calcular total
        total = sum(float(i.get('total', 0)) for i in (order.items_cotizacion or []))
        gran_total = total
        
        # --- PARSEO DE DIAGNÓSTICO Y CHECKLIST ---
        # Extraer datos estructurados si existen
        checklist_data = order.checklist_reparacion
        if isinstance(checklist_data, str):
            try: checklist_data = json.loads(checklist_data)
            except: checklist_data = {}
        
        diag_details = (checklist_data or {}).get('diagnostic_details', {})
        quick_check = (checklist_data or {}).get('quick_check', {})
        
        # 1. Formatear Diagnóstico
        diag_text = ""
        if diag_details:
            # Sistema y Análisis son los más importantes para el mensaje
            systems = diag_details.get('system', [])
            if isinstance(systems, str): systems = [systems]
            sys_str = ", ".join(systems) if systems else "General"
            
            analysis = diag_details.get('analysis', '').strip()
            solution = diag_details.get('solution', '').strip()
            
            diag_text = f"🔍 *DIAGNÓSTICO TÉCNICO:*\n"
            diag_text += f"• *Sistema:* {sys_str}\n"
            if analysis: diag_text += f"• *Hallazgo:* {analysis}\n"
            if solution: diag_text += f"• *Recomendación:* {solution}\n\n"
        elif order.diagnostico:
            # Fallback a texto plano si no hay estructura
            diag_text = f"🔍 *DIAGNÓSTICO:*\n{order.diagnostico}\n\n"

        # 2. Formatear Inspección Visual (Checklist)
        check_text = ""
        if quick_check:
            items_revisar = []
            for item, data in quick_check.items():
                status = data.get('status') if isinstance(data, dict) else data
                if status == 'REVISAR':
                    note = data.get('note', '') if isinstance(data, dict) else ''
                    items_revisar.append(f"❌ *{item}*: {note}" if note else f"❌ *{item}*")
            
            if items_revisar:
                check_text = "⚠️ *PUNTOS CRÍTICOS DETECTADOS:*\n"
                check_text += "\n".join(items_revisar) + "\n\n"
            else:
                check_text = "✅ *INSPECCIÓN DE SEGURIDAD:* Todo conforme.\n\n"

        # Mensaje para WhatsApp con diseño Premium
        whatsapp_msg = (
            f"🔧 *MECÁNICA Y REPUESTOS SANDOVAL*\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            f"Hola *{client.nombre if client else 'Cliente'}*,\n\n"
            f"Hemos finalizado la evaluación de su vehículo con placa *{order.vehiculo_placa}*.\n\n"
            f"{diag_text}"
            f"{check_text}"
            f"💰 *VALOR TOTAL DE INVERSIÓN:*\n"
            f"👉 *S/ {gran_total:.2f}*\n\n"
            f"Para ver el detalle completo de repuestos, fotos de evidencia y autorizar el servicio, por favor ingrese aquí:\n"
            f"🔗 {link}\n\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"MECÁNICA Y REPUESTOS SANDOVAL EIRL\n"
            f"📍 Piura, Perú\n"
            f"Gracias por elegir nuestra calidad técnica. ✨"
        )
        
        # Mensaje para Email
        email_subject = f"Orden de Servicio {order.consecutivo} - Aprobación Pendiente"
        email_body = (
            f"Estimado(a) {client.nombre if client else 'Cliente'},\n\n"
            f"Le informamos que su orden de servicio {order.consecutivo} "
            f"está lista para su revisión y aprobación.\n\n"
            f"Motivo: {order.motivo}\n"
            f"Vehículo: {order.vehiculo_placa}\n"
        )
        if gran_total > 0:
            email_body += f"Total estimado: S/ {gran_total:.2f}\n"
        email_body += (
            f"\nPuede revisar los detalles y aprobar/rechazar en el siguiente enlace:\n{link}\n\n"
            f"Atentamente,\nMECÁNICA Y REPUESTOS SANDOVAL EIRL\n"
            f"Piura, Perú | +51 999 999 999"
        )
        
        phone = client.telefono.replace(' ', '').replace('+', '') if client and client.telefono else ''
        whatsapp_link = f"https://wa.me/{phone}?text={_url_encode(whatsapp_msg)}" if phone else ''
        
        return {
            'link': link,
            'whatsapp_msg': whatsapp_msg,
            'whatsapp_link': whatsapp_link,
            'email_subject': email_subject,
            'email_body': email_body,
            'client_phone': client.telefono if client else '',
            'client_email': client.email if client else '',
            'total': gran_total,
        }
    finally:
        db.close()


def _url_encode(text: str) -> str:
    """URL encode para WhatsApp"""
    import urllib.parse
    return urllib.parse.quote(text)


# ==============================================================
# Push Notification Helpers -- 2026-04-29
# (a) inserta en notificaciones_push con RLS
# (b) envia VAPID via flota.send_push_to_user
# (c) nunca bloquea -- try/except total + log eventos_seguridad
# ==============================================================

import threading as _push_threading

_LOGO_ICON = '/assets/logo_sandoval_trans.png'
_SOUND_URL = '/assets/sounds/notify.mp3'
_VIBRATE = [200, 100, 200]


def _build_push_payload(*, title, body, tag, url, entity_type, entity_id):
    return {
        'title': title[:80], 'body': body[:200],
        'icon': _LOGO_ICON, 'badge': _LOGO_ICON,
        'tag': tag, 'url': url, 'sound': _SOUND_URL, 'vibrate': _VIBRATE,
        'data': {'type': entity_type, 'entity_id': entity_id},
    }


def _insert_notificacion_push(db, *, taller_id, tipo, titulo, cuerpo, entity_id,
                               destinatario_kind, destinatario_id, payload):
    import json as _j
    from sqlalchemy import text as _sqlt
    _K = 'app.taller_id'
    try:
        db.execute(_sqlt('SELECT set_config(:k, :v, false)'), {'k': _K, 'v': str(taller_id)})
        db.execute(_sqlt(
            'INSERT INTO notificaciones_push'
            ' (taller_id, tipo, titulo, cuerpo, entity_id,'
            '  destinatario_kind, destinatario_id, payload_json, created_at)'
            ' VALUES (:t, :tipo, :titulo, :cuerpo, :eid, :dkind, :did, :payload, NOW())'
        ), {
            't': taller_id, 'tipo': tipo, 'titulo': titulo[:200], 'cuerpo': cuerpo[:500],
            'eid': str(entity_id), 'dkind': destinatario_kind,
            'did': str(destinatario_id), 'payload': _j.dumps(payload, ensure_ascii=False),
        })
        db.commit()
    except Exception as _e:
        logger.warning('[PUSH][DB] notificaciones_push insert failed: %s', _e)
        try: db.rollback()
        except Exception: pass


def _log_push_error(taller_id, descripcion):
    def _do():
        try:
            from utils.security_events import log_event
            log_event(tipo='push_error', descripcion=descripcion,
                      severidad='WARN', taller_id=taller_id)
        except Exception: pass
    # 2026-05-04 FASE1.4: pool acotado + logging en lugar de Thread daemon
    from utils._async_helpers import fire_and_forget as _faf
    _faf(_do)


def _get_admin_staff_push_ids(db, taller_id):
    from sqlalchemy import text as _sqlt
    try:
        rows = db.execute(_sqlt(
            'SELECT DISTINCT ps.usuario_id FROM push_subscriptions ps'
            ' JOIN usuarios u ON u.id::text = ps.usuario_id::text'
            ' WHERE ps.taller_id = :t AND ps.enabled = TRUE'
            " AND u.rol IN ('admin', 'staff', 'mecanico')"
        ), {'t': taller_id}).fetchall()
        return [r[0] for r in rows if r[0]]
    except Exception: return []


# --- 1. notify_admin_nueva_cita ---

def notify_admin_nueva_cita(db, taller_id, cita_id):
    """Cuando un cliente agenda cita desde portal cliente.
    Destinatarios: admin/staff del taller con subscripciones activas.
    """
    try:
        from sqlalchemy import text as _sqlt
        from utils.flota import send_push_to_user
        row = db.execute(_sqlt(
            'SELECT ci.id, ci.fecha_cita, ci.hora, ci.motivo,'
            '       c.nombre, c.apellidos, ci.vehiculo_placa'
            '  FROM citas ci'
            '  LEFT JOIN clientes c ON c.id = ci.cliente_id'
            ' WHERE ci.id = :cid AND ci.taller_id = :t'
        ), {'cid': cita_id, 't': taller_id}).fetchone()
        if not row: return
        _, fecha, hora, motivo, nom, ape, placa = row
        cliente_nom = ((nom or '') + ' ' + (ape or '')).strip() or 'Cliente'
        hora_str = ' a las ' + hora if hora else ''
        title = 'Nueva cita agendada'
        body = (cliente_nom + ' -- ' + str(fecha) + hora_str + ('. ' + motivo if motivo else '')).strip()
        tag = 'cita-' + str(cita_id)
        url = '/admin/index.html#citas'
        payload = _build_push_payload(title=title, body=body, tag=tag, url=url,
                                      entity_type='cita', entity_id=cita_id)
        for uid in _get_admin_staff_push_ids(db, taller_id):
            try:
                _insert_notificacion_push(db, taller_id=taller_id, tipo='nueva_cita',
                    titulo=title, cuerpo=body, entity_id=cita_id,
                    destinatario_kind='admin', destinatario_id=str(uid), payload=payload)
                send_push_to_user(db, taller_id=taller_id, user_kind='admin',
                    user_id_str=str(uid), title=title, body=body,
                    url=url, icon=_LOGO_ICON, tag=tag, data=payload['data'])
            except Exception as _ie: logger.warning('[PUSH][cita] uid=%s: %s', uid, _ie)
    except Exception as _e:
        logger.error('[PUSH][nueva_cita] taller=%s cita=%s: %s', taller_id, cita_id, _e)
        _log_push_error(taller_id, 'notify_admin_nueva_cita cita_id=%s: %s' % (cita_id, _e))


# --- 2. notify_admin_orden_pendiente_aprobacion ---

def notify_admin_orden_pendiente_aprobacion(db, taller_id, orden_id):
    """Cuando se envia cotizacion a cliente (pendiente de aprobacion).
    Destinatarios: admin/staff del taller.

    TODO -- HOOK PARA OTRO AGENTE (sandoval-backend-engineer):
      Archivo: utils/api/ordenes.py  Funcion: api_orden_share_link_mobile (~linea 1069)
      Lugar: despues del db.commit() al insertar en short_links.
        import threading
        from utils.notifications import notify_admin_orden_pendiente_aprobacion
        threading.Thread(target=notify_admin_orden_pendiente_aprobacion,
            args=(db, taller_id, cons), daemon=True).start()
      Tambien en utils/api/ordenes.py cuando fase cambia a APROBACION.
    """
    try:
        from sqlalchemy import text as _sqlt
        from utils.flota import send_push_to_user
        cond = 'o.id=:oid' if isinstance(orden_id, int) else 'o.consecutivo=:oid'
        param = {'oid': orden_id, 't': taller_id}
        row = db.execute(_sqlt(
            'SELECT o.consecutivo, o.vehiculo_placa FROM ordenes o'
            ' WHERE ' + cond + ' AND o.taller_id=:t'
        ), param).fetchone()
        if not row: return
        cons, placa = row
        title = 'Cotizacion enviada -- Orden ' + str(cons)
        body = 'Placa ' + str(placa) + ' espera aprobacion del cliente.'
        tag = 'aprobacion-' + str(cons)
        url = '/admin/index.html#ordenes/' + str(cons)
        payload = _build_push_payload(title=title, body=body, tag=tag, url=url,
                                      entity_type='orden_aprobacion', entity_id=cons)
        for uid in _get_admin_staff_push_ids(db, taller_id):
            try:
                _insert_notificacion_push(db, taller_id=taller_id, tipo='orden_pendiente_aprobacion',
                    titulo=title, cuerpo=body, entity_id=cons,
                    destinatario_kind='admin', destinatario_id=str(uid), payload=payload)
                send_push_to_user(db, taller_id=taller_id, user_kind='admin',
                    user_id_str=str(uid), title=title, body=body,
                    url=url, icon=_LOGO_ICON, tag=tag, data=payload['data'])
            except Exception as _ie: logger.warning('[PUSH][aprobacion] uid=%s: %s', uid, _ie)
    except Exception as _e:
        logger.error('[PUSH][orden_aprobacion] taller=%s orden=%s: %s', taller_id, orden_id, _e)
        _log_push_error(taller_id, 'notify_admin_orden_pendiente_aprobacion orden=%s: %s' % (orden_id, _e))



# --- 3. notify_admin_resumen_dia ---

def notify_admin_resumen_dia(db, taller_id):
    """Cron 20:00 Lima. Resumen ordenes cerradas hoy + total cobrado."""
    try:
        from sqlalchemy import text as _sqlt
        from utils.flota import send_push_to_user
        db.execute(_sqlt("SELECT set_config('app.taller_id', :t, false)"), {"t": str(taller_id)})
        stats = db.execute(_sqlt(
            "SELECT COUNT(*), COALESCE(SUM(CAST(monto_cobrado AS NUMERIC)), 0)"
            "  FROM ordenes"
            " WHERE taller_id = :t AND estado IN ('ENTREGA', 'ARCHIVADO')"
            "   AND DATE(fecha) = CURRENT_DATE"
        ), {"t": taller_id}).fetchone()
        if not stats: return
        cnt, total = int(stats[0] or 0), float(stats[1] or 0)
        if cnt == 0 and total == 0: return
        caja = db.execute(_sqlt(
            "SELECT estado FROM cierres_caja WHERE taller_id = :t AND fecha = CURRENT_DATE ORDER BY id DESC LIMIT 1"
        ), {"t": taller_id}).fetchone()
        caja_estado = caja[0] if caja else "sin caja"
        title = "Resumen del dia -- SANDOVAL PRO"
        body = "%d orden(es) cerrada(s) . S/ %.2f cobrado . Caja: %s" % (cnt, total, caja_estado)
        tag = "resumen-dia-" + str(taller_id)
        url = "/admin/index.html#caja"
        payload = _build_push_payload(title=title, body=body, tag=tag, url=url,
                                      entity_type="resumen_dia", entity_id=taller_id)
        for uid in _get_admin_staff_push_ids(db, taller_id):
            try:
                _insert_notificacion_push(db, taller_id=taller_id, tipo="resumen_dia",
                    titulo=title, cuerpo=body, entity_id=taller_id,
                    destinatario_kind="admin", destinatario_id=str(uid), payload=payload)
                send_push_to_user(db, taller_id=taller_id, user_kind="admin",
                    user_id_str=str(uid), title=title, body=body,
                    url=url, icon=_LOGO_ICON, tag=tag, data=payload["data"])
            except Exception as _ie: logger.warning("[PUSH][resumen_dia] uid=%s: %s", uid, _ie)
    except Exception as _e:
        logger.error("[PUSH][resumen_dia] taller=%s: %s", taller_id, _e)
        _log_push_error(taller_id, "notify_admin_resumen_dia: %s" % _e)


# --- 4. notify_cliente_fase_avanzada ---

def notify_cliente_fase_avanzada(db, taller_id, orden_id, nueva_fase):
    """Al cambiar de fase en una orden. Destinatario: cliente dueno.
    TODO -- HOOK PARA OTRO AGENTE (sandoval-backend-engineer):
      Archivo: utils/api/ordenes.py  Funcion: api_cambiar_fase_orden
      Lugar: despues de guardar la nueva fase (thread separado):
        import threading; from utils.notifications import notify_cliente_fase_avanzada
        threading.Thread(target=notify_cliente_fase_avanzada,
            args=(db, taller_id, consecutivo, nueva_fase), daemon=True).start()
    """
    try:
        from sqlalchemy import text as _sqlt
        from utils.flota import send_push_to_user
        cond = "o.id=:oid" if isinstance(orden_id, int) else "o.consecutivo=:oid"
        param = {"oid": orden_id, "t": taller_id}
        row = db.execute(_sqlt(
            "SELECT o.consecutivo, o.vehiculo_placa, o.cliente_id, c.nombre, c.apellidos"
            "  FROM ordenes o"
            "  LEFT JOIN clientes c ON c.id = o.cliente_id AND c.taller_id = o.taller_id"
            " WHERE " + cond + " AND o.taller_id=:t"
        ), param).fetchone()
        if not row: return
        cons, placa, cliente_id, c_nom, c_ape = row
        if not cliente_id: return
        fase_msgs = {
            "RECEPCION":   "Su vehiculo ingreso al taller y esta siendo evaluado.",
            "DIAGNOSTICO": "Nuestros tecnicos estan diagnosticando su vehiculo.",
            "REPUESTOS":   "Estamos cotizando los repuestos necesarios.",
            "APROBACION":  "Su cotizacion esta lista. Por favor revisela y apruebela.",
            "REPARACION":  "Ya iniciamos la reparacion de su vehiculo.",
            "CONTROL":     "Realizando pruebas finales de calidad.",
            "ENTREGA":     "Su vehiculo esta listo para retirar.",
        }
        fase_key = nueva_fase.upper().replace(chr(193),"A").replace(chr(201),"E").replace(chr(211),"O")
        fase_body = fase_msgs.get(fase_key, "Su vehiculo avanzo a fase " + nueva_fase + ".")
        title = "Actualizacion -- Orden " + str(cons)
        body = "Fase: " + nueva_fase + ". " + fase_body
        tag = "orden-fase-" + str(cons)
        url = "/portal/index.html"
        payload = _build_push_payload(title=title, body=body, tag=tag, url=url,
                                      entity_type="orden_fase", entity_id=cons)
        _insert_notificacion_push(db, taller_id=taller_id, tipo="fase_avanzada",
            titulo=title, cuerpo=body, entity_id=cons,
            destinatario_kind="cliente", destinatario_id=str(cliente_id), payload=payload)
        send_push_to_user(db, taller_id=taller_id, user_kind="cliente",
            user_id_str=str(cliente_id), title=title, body=body,
            url=url, icon=_LOGO_ICON, tag=tag, data=payload["data"])
    except Exception as _e:
        logger.error("[PUSH][fase_avanzada] taller=%s orden=%s fase=%s: %s",
                     taller_id, orden_id, nueva_fase, _e)
        _log_push_error(taller_id, "notify_cliente_fase_avanzada orden=%s fase=%s: %s" % (orden_id, nueva_fase, _e))


# --- 5. notify_cliente_aprobacion_requerida ---

def notify_cliente_aprobacion_requerida(db, taller_id, orden_id):
    """Cuando hay cotizacion lista para aprobar. Destinatario: cliente.
    TODO -- HOOK PARA OTRO AGENTE (sandoval-backend-engineer):
      Archivo: utils/api/ordenes.py  Funcion: api_orden_share_link_mobile (~linea 1069)
      Lugar: despues del db.commit() al insertar en short_links:
        import threading; from utils.notifications import notify_cliente_aprobacion_requerida
        threading.Thread(target=notify_cliente_aprobacion_requerida,
            args=(db, taller_id, cons), daemon=True).start()
    """
    try:
        from sqlalchemy import text as _sqlt
        from utils.flota import send_push_to_user
        cond = "o.id=:oid" if isinstance(orden_id, int) else "o.consecutivo=:oid"
        param = {"oid": orden_id, "t": taller_id}
        row = db.execute(_sqlt(
            "SELECT o.consecutivo, o.vehiculo_placa, o.cliente_id, o.approval_token"
            "  FROM ordenes o WHERE " + cond + " AND o.taller_id=:t"
        ), param).fetchone()
        if not row: return
        cons, placa, cliente_id, approval_token = row
        if not cliente_id: return
        url = ("/aprobacion/" + str(approval_token)) if approval_token else "/portal/index.html"
        title = "Cotizacion lista -- Orden " + str(cons)
        body = "Placa " + str(placa) + ": su presupuesto esta listo. Toque para revisar y aprobar."
        tag = "cotiz-aprobacion-" + str(cons)
        payload = _build_push_payload(title=title, body=body, tag=tag, url=url,
                                      entity_type="cotizacion_aprobacion", entity_id=cons)
        _insert_notificacion_push(db, taller_id=taller_id, tipo="aprobacion_requerida",
            titulo=title, cuerpo=body, entity_id=cons,
            destinatario_kind="cliente", destinatario_id=str(cliente_id), payload=payload)
        send_push_to_user(db, taller_id=taller_id, user_kind="cliente",
            user_id_str=str(cliente_id), title=title, body=body,
            url=url, icon=_LOGO_ICON, tag=tag, data=payload["data"])
    except Exception as _e:
        logger.error("[PUSH][aprobacion_req] taller=%s orden=%s: %s", taller_id, orden_id, _e)
        _log_push_error(taller_id, "notify_cliente_aprobacion_requerida orden=%s: %s" % (orden_id, _e))


# --- 6. notify_cliente_listo_entrega ---

def notify_cliente_listo_entrega(db, taller_id, orden_id):
    """Al pasar a fase ENTREGA. Destinatario: cliente.
    TODO -- HOOK PARA OTRO AGENTE (sandoval-backend-engineer):
      Archivo: utils/api/ordenes.py
      Funcion: la que cambia estado a ENTREGA (buscar estado.*ENTREGA en ordenes.py)
      Lugar: despues de guardar (thread separado):
        import threading; from utils.notifications import notify_cliente_listo_entrega
        threading.Thread(target=notify_cliente_listo_entrega,
            args=(db, taller_id, consecutivo), daemon=True).start()
    """
    try:
        from sqlalchemy import text as _sqlt
        from utils.flota import send_push_to_user
        cond = "o.id=:oid" if isinstance(orden_id, int) else "o.consecutivo=:oid"
        param = {"oid": orden_id, "t": taller_id}
        row = db.execute(_sqlt(
            "SELECT o.consecutivo, o.vehiculo_placa, o.cliente_id"
            "  FROM ordenes o WHERE " + cond + " AND o.taller_id=:t"
        ), param).fetchone()
        if not row: return
        cons, placa, cliente_id = row
        if not cliente_id: return
        title = "Vehiculo listo -- Orden " + str(cons)
        body = "Su vehiculo " + str(placa) + " esta listo para retirar. Pase por el taller."
        tag = "entrega-" + str(cons)
        url = "/portal/index.html"
        payload = _build_push_payload(title=title, body=body, tag=tag, url=url,
                                      entity_type="orden_entrega", entity_id=cons)
        _insert_notificacion_push(db, taller_id=taller_id, tipo="listo_entrega",
            titulo=title, cuerpo=body, entity_id=cons,
            destinatario_kind="cliente", destinatario_id=str(cliente_id), payload=payload)
        send_push_to_user(db, taller_id=taller_id, user_kind="cliente",
            user_id_str=str(cliente_id), title=title, body=body,
            url=url, icon=_LOGO_ICON, tag=tag, data=payload["data"])
    except Exception as _e:
        logger.error("[PUSH][listo_entrega] taller=%s orden=%s: %s", taller_id, orden_id, _e)
        _log_push_error(taller_id, "notify_cliente_listo_entrega orden=%s: %s" % (orden_id, _e))

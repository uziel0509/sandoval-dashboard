"""
SANDOVAL Dashboard - Sistema de Notificaciones
Notificaciones in-app + preparación para WhatsApp/Email
"""

import json
from datetime import datetime, timedelta
from utils.models import get_db, Actividad, Orden, ItemInventario, Cliente, Cita
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text


# ─── Notificaciones In-App ───

def get_notifications(limit=20) -> list:
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
    db = get_db()
    try:
        import sqlalchemy as _sa
        db.query(Cita).filter_by(estado='programada').filter(
            _sa.or_(Cita.vista_admin == None, Cita.vista_admin == 0)
        ).update({'vista_admin': 1})
        db.commit()
    except Exception as e:
        print(f'[NOTIF] Error marcando citas: {e}')
    finally:
        db.close()


def marcar_notifs_leidas_cliente(cliente_id, ids: list):
    """Guarda en DB la lista de IDs de notificaciones leídas por el cliente (SQL directo, sin caché ORM)"""
    import json as _json
    from sqlalchemy import text as _text
    db = get_db()
    try:
        # Leer valor actual con SQL directo
        row = db.execute(
            _text("SELECT notifs_leidas FROM clientes WHERE id = :cid"),
            {'cid': str(cliente_id)}
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
            _text("UPDATE clientes SET notifs_leidas = :val WHERE id = :cid"),
            {'val': _json.dumps(nuevas), 'cid': str(cliente_id)}
        )
        db.commit()
    except Exception as e:
        print(f'[NOTIF] Error guardando leídas: {e}')
    finally:
        db.close()


def get_client_notifications(cliente_id, placa: str) -> list:
    """Notificaciones exclusivas para el portal del cliente"""
    import json as _json
    from sqlalchemy import text as _text
    notifs = []
    db = get_db()
    try:
        # Leer notifs_leidas con SQL directo para evitar caché de SQLAlchemy
        try:
            row = db.execute(
                _text("SELECT notifs_leidas FROM clientes WHERE id = :cid"),
                {'cid': str(cliente_id)}
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
                nid_orden = f'orden_estado_{active_order.consecutivo}_{active_order.estado}'
                notifs.append({
                    'id': nid_orden,
                    'nueva': nid_orden not in leidas,
                    'icon_cls': 'azul',
                    'icon': '🔧',
                    'titulo': f'Tu vehículo está en: {active_order.estado}',
                    'desc': f'Orden #{active_order.consecutivo} · {active_order.motivo or ""}',
                    'tiempo': f'Hoy · {datetime.now().strftime("%I:%M %p")}',
                })
                if active_order.approval_status == 'aprobado':
                    nid_apr = f'aprobado_{active_order.consecutivo}'
                    notifs.append({
                        'id': nid_apr,
                        'nueva': nid_apr not in leidas,
                        'icon_cls': 'verde',
                        'icon': '✅',
                        'titulo': 'Aprobación confirmada',
                        'desc': 'Tu presupuesto fue aprobado y se procedió a los trabajos.',
                        'tiempo': active_order.approval_date or 'Reciente',
                    })
                elif active_order.approval_status == 'pendiente' and active_order.estado == 'APROBACIÓN':
                    nid_pend = f'pendiente_{active_order.consecutivo}'
                    notifs.append({
                        'id': nid_pend,
                        'nueva': nid_pend not in leidas,
                        'icon_cls': 'naranja',
                        'icon': '⚠️',
                        'titulo': 'Aprobación pendiente',
                        'desc': 'Tu cotización está lista. Por favor revisa y aprueba el presupuesto.',
                        'tiempo': 'Pendiente de acción',
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
        print(f'[NOTIF_CLIENT] Error: {e}')
    finally:
        db.close()
    return notifs[:6]


# ─── Generador de Links de Aprobación ───

def generate_approval_message(order_consecutivo: str, base_url: str = 'http://localhost:8088') -> dict:
    """Genera el mensaje de aprobación para enviar al cliente"""
    db = get_db()
    try:
        order = db.query(Orden).filter_by(consecutivo=order_consecutivo).first()
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

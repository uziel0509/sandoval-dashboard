"""
SANDOVAL Dashboard - Página de Aprobación Pública
El cliente puede ver su orden y aprobar/rechazar sin login
Acceso: /aprobacion/{token}
"""

from nicegui import ui
from utils.models import get_db, Orden, Cliente, Vehiculo, log_actividad
from datetime import datetime
import os
from utils.pdf_generator import generate_orden_ingreso


def approval_page(token: str):
    """Página pública de aprobación de orden"""
    
    ui.add_head_html('''
        <style>
            body { 
                background: linear-gradient(135deg, #f5f5f7 0%, #ffffff 100%);
                margin: 0; font-family: 'Roboto', sans-serif;
                color: #383838;
            }
        </style>
    ''')
    
    db = get_db()
    try:
        order = db.query(Orden).filter_by(approval_token=token).first()
        
        if not order:
            _render_error('Enlace inválido', 'Este enlace de aprobación no es válido o ha expirado.')
            return
        
        client = db.query(Cliente).filter_by(id=order.cliente_id).first()
        vehicle = db.query(Vehiculo).filter_by(placa=order.vehiculo_placa).first()
        
        # Ya fue respondido?
        if order.approval_status in ('aprobado', 'rechazado'):
            _render_already_responded(order, client, vehicle)
            return
        
        _render_approval(order, client, vehicle, token)
    finally:
        db.close()


def _render_error(title, message):
    with ui.column().classes('w-full min-h-screen items-center justify-center p-4'):
        with ui.card().classes('w-full max-w-md bg-white border border-red-200 p-8 text-center shadow-lg'):
            ui.icon('error', size='64px').classes('text-red-500')
            ui.label(title).classes('text-2xl font-bold text-gray-800 mt-4')
            ui.label(message).classes('text-gray-600 mt-2')


def _render_already_responded(order, client, vehicle):
    color = 'green' if order.approval_status == 'aprobado' else 'red'
    icon = 'check_circle' if order.approval_status == 'aprobado' else 'cancel'
    
    is_budget = len(order.items_cotizacion or []) > 0
    
    if order.approval_status == 'aprobado':
        status_text = 'SU PRESUPUESTO FUE APROBADO' if is_budget else 'SU ORDEN FUE APROBADA'
    else:
        status_text = 'PRESUPUESTO RECHAZADO' if is_budget else 'ORDEN RECHAZADA'
    
    with ui.column().classes('w-full min-h-screen items-center justify-center p-4 bg-gray-50'):
        with ui.card().classes(f'w-full max-w-lg bg-white border-t-8 border-{color}-500 p-8 text-center shadow-xl'):
            ui.icon(icon, size='80px').classes(f'text-{color}-500 mb-4')
            
            ui.label(status_text).classes(f'text-3xl font-bold text-{color}-700 mb-2')
            
            ui.separator().classes('my-4')
            
            ui.label(f'Orden N° {order.consecutivo}').classes('text-xl text-gray-800 font-bold')
            ui.label(f'Confirmado el: {order.approval_date}').classes('text-gray-500 text-sm')
            
            ui.label('Gracias por su respuesta.').classes('text-gray-600 mt-6 text-lg')
            
            if order.approval_status == 'aprobado':
                 if is_budget:
                     ui.label('Su presupuesto ha sido formalizado y se procederá con el servicio.').classes('text-gray-500 text-sm mt-2 mb-6')
                 else:
                     ui.label('Se ha generado su reporte de ingreso con las evidencias fotográficas.').classes('text-gray-500 text-sm mt-2 mb-6')
                 
                 def download_pdf():
                     from utils import pdf_generator as pg
                     try:
                         # Convertir a dicts para el generador
                         o_dict = {c.name: getattr(order, c.name) for c in order.__table__.columns}
                         c_dict = {c.name: getattr(client, c.name) for c in client.__table__.columns} if client else {}
                         v_dict = {c.name: getattr(vehicle, c.name) for c in vehicle.__table__.columns} if vehicle else {}
                         o_dict['fotos_evidencia'] = order.fotos_evidencia
                         
                         os.makedirs('pdfs', exist_ok=True)
                         ts = datetime.now().strftime('%H%M%S')
                         if is_budget:
                             filename = f"pdfs/Cotizacion_{order.consecutivo.replace('#','')}_{ts}.pdf"
                             pg.generate_pdf(o_dict, c_dict, v_dict, 'cotizacion', filename)
                         else:
                             filename = f"pdfs/Ingreso_{order.consecutivo.replace('#','')}_{ts}.pdf"
                             pg.generate_pdf(o_dict, c_dict, v_dict, 'ingreso', filename)
                             
                         ui.download(filename)
                         ui.notify('Generando descarga...', type='positive')
                     except Exception as e:
                         print(f"Error PDF: {e}")
                         ui.notify(f'Error al generar PDF: {e}', type='negative')

                 btn_label = 'Descargar Cotización (PDF)' if is_budget else 'Descargar Reporte de Ingreso (PDF)'
                 ui.button(btn_label, icon='picture_as_pdf', on_click=download_pdf).props('unelevated color=green-7 text-color=white size=lg').classes('w-full font-bold shadow-lg')
                  
                 # Scanner Report Link (NUEVO)
                 import json
                 chk = order.checklist_reparacion
                 if isinstance(chk, str):
                     try: chk = json.loads(chk)
                     except: chk = {}
                  
                 scanner_path = (chk or {}).get('diagnostic_details', {}).get('scanner_path')
                 if scanner_path:
                     ui.button('Descargar Reporte de Escáner', icon='file_download', on_click=lambda: ui.download(scanner_path)).props('outline color=blue size=md').classes('w-full mt-4 font-bold')


def _render_approval(order, client, vehicle, token):
    _VIDEO_EXT = {'.mp4', '.mov', '.avi', '.webm', '.mkv', '.m4v', '.3gp', '.ogg'}
    def _ev_is_video(p):
        return os.path.splitext((p or '').lower())[1] in _VIDEO_EXT

    import json
    checklist_data = order.checklist_reparacion
    if isinstance(checklist_data, str):
        try: checklist_data = json.loads(checklist_data)
        except: checklist_data = {}
    diag_details = (checklist_data or {}).get('diagnostic_details', {})
    quick_check  = (checklist_data or {}).get('quick_check', {})
    items        = order.items_cotizacion or []

    with ui.column().classes('w-full min-h-screen items-center py-8 px-4 bg-gray-50'):

        # ── HEADER ────────────────────────────────────────────────────────
        with ui.card().classes('w-full max-w-2xl bg-white border border-gray-200 p-5 mb-4 shadow-sm rounded-2xl'):
            with ui.row().classes('w-full items-center justify-between'):
                with ui.row().classes('items-center gap-3'):
                    ui.icon('build_circle', size='40px').classes('text-lime-600')
                    with ui.column().classes('gap-0'):
                        ui.label('SANDOVAL').classes('text-2xl font-bold text-gray-800')
                        ui.label('Mecánica y Repuestos — Reporte de Servicio').classes('text-xs text-gray-500')
                with ui.column().classes('items-end gap-0'):
                    ui.label(f'Orden {order.consecutivo}').classes('text-lg font-bold text-gray-800')
                    ui.label(f'Estado: {order.estado}').classes('text-xs text-gray-400 font-mono')

        # ── VEHÍCULO ──────────────────────────────────────────────────────
        if vehicle:
            with ui.card().classes('w-full max-w-2xl bg-white border border-gray-200 p-5 mb-4 shadow-sm rounded-2xl'):
                ui.label('🚗 VEHÍCULO').classes('text-sm font-bold text-lime-700 uppercase tracking-widest mb-3')
                with ui.grid(columns=2).classes('w-full gap-3'):
                    _info_field('Marca / Modelo', f'{vehicle.marca} {vehicle.modelo}')
                    _info_field('Placa', vehicle.placa)
                    _info_field('Año', vehicle.año)
                    _info_field('Color', vehicle.color or '—')
                    _info_field('Kilometraje', f'{order.km or "—"} km')
                    _info_field('Técnico', order.tecnico or '—')

        # ── DIAGNÓSTICO TÉCNICO ───────────────────────────────────────────
        with ui.card().classes('w-full max-w-2xl bg-white border border-gray-200 p-5 mb-4 shadow-sm rounded-2xl'):
            ui.label('🔬 DIAGNÓSTICO TÉCNICO').classes('text-sm font-bold text-lime-700 uppercase tracking-widest mb-4')

            if diag_details:
                # Sistemas afectados
                systems = diag_details.get('system', [])
                if isinstance(systems, str): systems = [systems]
                if systems:
                    with ui.row().classes('items-center gap-2 mb-3'):
                        ui.label('Sistemas:').classes('text-xs font-black text-gray-400 uppercase')
                        for s in systems:
                            ui.label(s).classes('bg-lime-50 px-3 py-1 rounded-full text-[10px] font-bold border border-lime-200 text-lime-800 uppercase')

                def _diag_item(icon, label, value):
                    if not value: return
                    with ui.row().classes('w-full items-start gap-3 p-3 bg-slate-50 rounded-xl border border-slate-100 mb-2'):
                        ui.icon(icon, size='18px').classes('text-lime-600 mt-1 flex-shrink-0')
                        with ui.column().classes('gap-0 flex-1'):
                            ui.label(label).classes('text-[10px] font-black text-gray-400 uppercase tracking-widest mb-1')
                            ui.label(value).classes('text-sm text-gray-800 leading-relaxed font-medium')

                _diag_item('biotech',            'Pruebas Realizadas',          diag_details.get('tests'))
                _diag_item('manage_search',       'Códigos Detectados',           diag_details.get('codes'))
                _diag_item('psychology',          'Análisis Técnico / Hallazgo',  diag_details.get('analysis'))
                _diag_item('check_circle_outline','Solución Recomendada',         diag_details.get('solution'))

                if diag_details.get('scanner_path'):
                    with ui.row().classes('w-full justify-center mt-3'):
                        ui.button('VER REPORTE DE ESCÁNER', icon='description',
                                  on_click=lambda: ui.download(diag_details.get('scanner_path'))
                                  ).props('outline color=lime-9').classes('font-bold')

            elif order.diagnostico:
                ui.label(order.diagnostico).classes(
                    'text-gray-800 whitespace-pre-wrap text-sm leading-relaxed p-4 bg-slate-50 rounded-lg border border-slate-100')
            else:
                ui.label('El diagnóstico aún no ha sido redactado por el técnico.').classes('text-gray-400 italic text-sm')

        # ── INSPECCIÓN PREVENTIVA ─────────────────────────────────────────
        if quick_check:
            with ui.card().classes('w-full max-w-2xl bg-white border border-gray-200 p-5 mb-4 shadow-sm rounded-2xl'):
                ui.label('✅ INSPECCIÓN DE SEGURIDAD Y ESTADO').classes('text-sm font-bold text-lime-700 uppercase tracking-widest mb-4')
                with ui.grid(columns=1).classes('w-full gap-2'):
                    for item, data in quick_check.items():
                        status = data.get('status') if isinstance(data, dict) else data
                        note   = data.get('note', '') if isinstance(data, dict) else ''
                        is_ok  = status == 'OK'
                        bg_c   = 'bg-white' if is_ok else 'bg-red-50'
                        bd_c   = 'border-slate-100' if is_ok else 'border-red-100'
                        with ui.row().classes(f'w-full items-center justify-between p-3 rounded-xl border {bd_c} {bg_c} shadow-sm'):
                            with ui.row().classes('items-center gap-3'):
                                ui.icon('verified' if is_ok else 'warning', size='20px').classes(
                                    'text-green-500' if is_ok else 'text-red-500')
                                ui.label(item).classes('text-sm font-bold text-slate-700')
                            with ui.row().classes('items-center gap-4'):
                                if note:
                                    ui.label(note).classes('text-[11px] text-red-700 italic font-medium max-w-[200px] truncate')
                                lbl_s   = 'CONFORME' if is_ok else 'REVISAR'
                                chip_c  = 'bg-green-100 text-green-700' if is_ok else 'bg-red-100 text-red-700'
                                ui.label(lbl_s).classes(f'px-3 py-1 rounded-full text-[9px] font-black tracking-widest {chip_c}')

        # ── EVIDENCIA: FOTOS Y VIDEOS ─────────────────────────────────────
        medios = [p for p in (order.fotos_evidencia or []) if isinstance(p, str)]
        if medios:
            fotos_ev  = [p for p in medios if not _ev_is_video(p)]
            videos_ev = [p for p in medios if _ev_is_video(p)]

            with ui.card().classes('w-full max-w-2xl bg-white border border-gray-200 p-5 mb-4 shadow-sm rounded-2xl'):
                ui.label('📷 EVIDENCIA ADJUNTA').classes('text-sm font-bold text-lime-700 uppercase tracking-widest mb-4')

                if fotos_ev:
                    ui.label('Fotos:').classes('text-xs font-bold text-gray-500 mb-2')
                    with ui.row().classes('w-full gap-2 flex-wrap mb-4'):
                        for path in fotos_ev:
                            with ui.card().classes('w-36 h-36 p-0 relative border border-gray-200 rounded-xl overflow-hidden shadow-sm'):
                                ui.image(path).classes('w-full h-full object-cover')
                                ui.link('', path, new_tab=True).classes('absolute inset-0')

                if videos_ev:
                    ui.label('📹 Videos del técnico:').classes('text-xs font-bold text-blue-600 mb-3')
                    for path in videos_ev:
                        with ui.card().classes('w-full bg-slate-900 rounded-xl overflow-hidden border border-blue-200 shadow-md mb-3'):
                            ui.html(f'''
                                <video src="{path}" controls preload="metadata" playsinline
                                    style="width:100%;max-height:350px;display:block;">
                                    Tu navegador no soporta reproducción de video.
                                    <a href="{path}" target="_blank">Descargar video</a>
                                </video>
                            ''')
                            with ui.row().classes('p-3 items-center gap-2'):
                                ui.icon('videocam', size='xs').classes('text-blue-300')
                                ui.label('Haz clic en ▶ para reproducir el video del técnico').classes('text-slate-300 text-xs flex-1')
                                ui.html(f'<a href="{path}" target="_blank" style="color:#60a5fa;font-size:11px;font-weight:700;text-decoration:none;">Abrir →</a>')

        # ── COTIZACIÓN Y REPUESTOS ────────────────────────────────────────
        if items:
            with ui.card().classes('w-full max-w-2xl bg-white border border-gray-200 p-5 mb-4 shadow-sm rounded-2xl'):
                ui.label('🔩 COTIZACIÓN DE REPUESTOS Y SERVICIOS').classes('text-sm font-bold text-lime-700 uppercase tracking-widest mb-4')

                subtotal = 0.0
                for item in items:
                    item_total = float(item.get('total', 0))
                    subtotal  += item_total
                    with ui.row().classes('w-full justify-between items-center py-3 border-b border-gray-100'):
                        with ui.column().classes('gap-0 flex-1'):
                            ui.label(item.get('nombre', item.get('item', 'Ítem'))).classes('text-gray-800 text-sm font-bold')
                            ui.label(
                                f"Cant: {item.get('cantidad', 1)} × S/ {float(item.get('precio_unitario', 0)):.2f}  |  {item.get('categoria', 'Repuesto')}"
                            ).classes('text-gray-400 text-xs')
                        ui.label(f'S/ {item_total:.2f}').classes('text-gray-900 font-bold text-sm ml-4')

                base_sin_igv = subtotal / 1.18
                igv_inc      = subtotal - base_sin_igv
                ui.separator().classes('my-4')
                with ui.column().classes('w-full items-end gap-1'):
                    ui.html(f'''
                    <div style="font-size:12px;color:#94a3b8;text-align:right;margin-bottom:4px;">
                        Base imponible (inc.): S/ {base_sin_igv:.2f} &nbsp;|&nbsp; IGV 18% (inc.): S/ {igv_inc:.2f}
                    </div>
                    ''')
                    ui.label(f'TOTAL (Inc. IGV): S/ {subtotal:.2f}').classes('text-3xl font-bold text-lime-700')
        else:
            # No hay cotización aún — informar
            with ui.card().classes('w-full max-w-2xl bg-amber-50 border border-amber-200 p-4 mb-4 shadow-sm rounded-2xl'):
                with ui.row().classes('items-center gap-3'):
                    ui.icon('info', size='24px').classes('text-amber-500')
                    ui.label('La cotización de repuestos aún no ha sido preparada. Se enviará otro enlace cuando esté lista.').classes('text-amber-800 text-sm font-medium')

        # ── BOTONES DE APROBACIÓN ─────────────────────────────────────────
        with ui.card().classes('w-full max-w-2xl bg-white border-2 border-lime-300 p-6 mb-6 shadow-md rounded-2xl'):
            ui.label('📋 SU DECISIÓN').classes('text-sm font-bold text-lime-700 uppercase tracking-widest mb-2')
            if items:
                ui.label('¿Aprueba el diagnóstico y la cotización de repuestos indicada?').classes('text-gray-700 text-sm mb-1')
            else:
                ui.label('¿Aprueba el estado de ingreso de su vehículo y el diagnóstico inicial?').classes('text-gray-700 text-sm mb-1')
            ui.label('Al APROBAR, el taller procederá con los trabajos. Al RECHAZAR, el taller se comunicará con usted.').classes('text-gray-400 text-xs mb-4')

            comentario_inp = ui.textarea('Comentario u observación (opcional)',
                                         placeholder='Ej: Estoy de acuerdo, pueden proceder...'
                             ).props('outlined dense rows=2 bg-color=white').classes('w-full mb-4')

            with ui.row().classes('w-full justify-center gap-6'):
                def _rechazar():
                    _process_response(token, 'rechazado', comentario_inp.value)
                def _aprobar():
                    _process_response(token, 'aprobado', comentario_inp.value)

                ui.button('✗  RECHAZAR', on_click=_rechazar).classes('px-8 py-3 text-base font-bold').props('outline color=red-7 size=lg')
                ui.button('✓  APROBAR',  on_click=_aprobar ).classes('px-8 py-3 text-base font-bold').props('unelevated color=lime-8 text-color=black size=lg')

        # Footer
        ui.label('MECÁNICA Y REPUESTOS SANDOVAL EIRL — Documento de aprobación confidencial').classes('text-gray-400 text-xs mt-2')

def _info_field(label, value):
    with ui.column().classes('gap-0'):
        ui.label(label).classes('text-xs text-gray-500 uppercase font-bold')
        ui.label(str(value)).classes('text-gray-800 font-medium')


def confirm_dialog(title, msg, token, new_status):
    with ui.dialog() as dialog, ui.card().classes('bg-white border border-gray-200 p-6 w-96 text-center shadow-xl'):
        ui.label(title).classes('text-xl font-bold text-gray-800 mb-2')
        ui.label(msg).classes('text-gray-600 mb-6')
        
        with ui.row().classes('w-full justify-center gap-4'):
            ui.button('Cancelar', on_click=dialog.close).props('flat color=grey-8')
            
            def confirm():
                db = get_db()
                try:
                    o = db.query(Orden).filter_by(approval_token=token).first()
                    if o:
                        o.approval_status = new_status
                        o.approval_date = datetime.now().strftime('%Y-%m-%d %H:%M')

                        # Logic for state transition
                        if new_status == 'aprobado':
                            if o.estado == 'RECEPCIÓN':
                                o.estado = 'DIAGNÓSTICO'
                            else:
                                o.estado = 'REPARACIÓN'
                        elif new_status == 'rechazado':
                            if o.estado != 'RECEPCIÓN':
                                o.estado = 'DIAGNÓSTICO'

                        # ── Generar y guardar PDF combinado (diagnóstico + cotización) ──
                        # Solo si el cliente APRUEBA el presupuesto (no en recepción)
                        if new_status == 'aprobado' and o.items_cotizacion:
                            try:
                                from utils import pdf_generator as pg
                                from utils.models import Cliente, Vehiculo
                                c_row = db.query(Cliente).filter_by(id=o.cliente_id).first()
                                v_row = db.query(Vehiculo).filter_by(placa=o.vehiculo_placa).first()
                                o_dict = {c.name: getattr(o, c.name) for c in o.__table__.columns}
                                c_dict = {c.name: getattr(c_row, c.name) for c in c_row.__table__.columns} if c_row else {}
                                v_dict = {c.name: getattr(v_row, c.name) for c in v_row.__table__.columns} if v_row else {}
                                o_dict['fotos_evidencia'] = o.fotos_evidencia
                                os.makedirs('pdfs', exist_ok=True)
                                ts = datetime.now().strftime('%Y%m%d_%H%M%S')
                                safe_cons = o.consecutivo.replace('#', '').replace('/', '-')
                                pdf_path = f"pdfs/Aprobado_{safe_cons}_{ts}.pdf"
                                pg.generate_pdf(o_dict, c_dict, v_dict, 'cotizacion', pdf_path)
                                # Guardar ruta en la BD para el historial del cliente
                                o.pdf_cotizacion = pdf_path
                            except Exception as pdf_err:
                                print(f"[PDF] Error al generar PDF de aprobación: {pdf_err}")

                        log_actividad(f'Orden {o.consecutivo} {new_status} por cliente', 'ordenes')

                        # Add history
                        hist = list(o.historial or [])
                        hist.append({
                            'fecha': datetime.now().strftime('%Y-%m-%d %H:%M'),
                            'accion': f'Cliente {new_status.upper()} presupuesto',
                            'usuario': 'Cliente Web'
                        })
                        o.historial = hist

                        db.commit()
                        ui.notify('Respuesta registrada correctamente', type='positive')
                        dialog.close()
                        # Reload page to show status
                        ui.run_javascript('location.reload()')
                finally:
                    db.close()

            color = 'green' if new_status == 'aprobado' else 'red'
            ui.button('CONFIRMAR', on_click=confirm).props(f'unelevated color={color}-7')
    
    dialog.open()


def _process_response(token: str, status: str, comentario: str = ''):
    """Procesa la aprobación o rechazo (directo sin confirmacion extra si viene de botones grandes)"""
    # Nota: Los botones ya llaman a _process_response directamente en mi nueva lógica (simplificada)
    # PERO, en el código original, llamaban a confirm_dialog.
    # Aquí he cambiado los botones para llamar a _process_response O confirm_dialog.
    # Voy a mantener confirm_dialog para seguridad.
    
    confirm_dialog(
        'Aprobar Orden' if status == 'aprobado' else 'Rechazar Orden',
        '¿Está seguro de su respuesta?' if status == 'rechazado' else '¿Confirma la aprobación del presupuesto?',
        token, status
    )

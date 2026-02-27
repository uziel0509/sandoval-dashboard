"""
SANDOVAL Dashboard - Portal del Cliente v4.0 (Premium Design)
Seguimiento en vivo, historial y agendamiento con diseño corporativo avanzado.
"""

import json
from datetime import datetime, timedelta
from nicegui import ui
from utils.models import get_db, Cliente, Vehiculo, Orden, Cita
from utils.auth import get_current_user
import theme

def show_portal(container):
    """
    Portal de Cliente Premium basado en el diseño HTML/CSS solicitado.
    Mantiene la vinculación con la base de datos Sandoval.
    """
    user = get_current_user()
    if not user or user.get('rol') != 'cliente':
        ui.label('Acceso no autorizado').classes('text-red-500')
        return

    db = get_db()
    try:
        # 1. RECUPERACIÓN DE DATOS REALES
        user_id = user.get('id')
        user_plate = user.get('placa')
        
        cliente = db.query(Cliente).filter_by(id=user_id).first()
        vehiculo = db.query(Vehiculo).filter_by(placa=user_plate).first()
        ordenes_all = db.query(Orden).filter_by(vehiculo_placa=user_plate).order_by(Orden.fecha.desc()).all()
        citas_all = db.query(Cita).filter_by(cliente_id=user_id).all()
        
        if not cliente:
            ui.label('Error: Cliente no encontrado en DB').classes('text-red-500 p-10')
            return

        # Órdenes activas y métricas
        active_order = next((o for o in ordenes_all if o.estado not in ('ARCHIVADO', 'ENTREGA')), None)
        servicios_activos = 1 if active_order else 0
        visitas_totales = len(ordenes_all)
        vehiculos_totales = db.query(Vehiculo).filter_by(cliente_id=user_id).count()
        
        proxima_cita = "—"
        citas_futuras = [c for c in citas_all if c.fecha_cita >= datetime.now().strftime('%Y-%m-%d')]
        if citas_futuras:
            proxima_cita = sorted(citas_futuras, key=lambda x: x.fecha_cita)[0].fecha_cita

        # --- ESTILOS CSS INYECTADOS (Extraídos del diseño HTML) ---
        ui.add_head_html(f'''
        <style>
            :root {{
                --azul: #1a3a6b;
                --azul-med: #2356a8;
                --azul-claro: #3a7bd5;
                --azul-super-claro: #e8f0fb;
                --azul-borde: #c5d8f5;
                --gris-bg: #f4f7fc;
                --gris-texto: #6b7a99;
                --gris-borde: #dde4f0;
                --verde: #1db97a;
                --naranja: #f59e0b;
                --rojo: #ef4444;
                --texto: #1a2340;
                --sombra: 0 2px 16px rgba(26,58,107,.10);
            }}
            .card-premium {{
                background: white; border-radius: 16px; 
                border: 1.5px solid var(--gris-borde);
                box-shadow: var(--sombra); padding: 24px;
            }}
            .stat-icon-wrap {{
                width: 46px; height: 46px; border-radius: 12px;
                background: var(--azul-super-claro);
                display: flex; align-items: center; justify-content: center;
                font-size: 22px;
            }}
            .phase-item {{ display: flex; flex-direction: column; align-items: center; gap: 8px; position: relative; z-index: 2; flex: 1; }}
            .phase-circle {{
                width: 48px; height: 48px; border-radius: 50%;
                display: flex; align-items: center; justify-content: center;
                font-size: 18px; transition: all .25s;
            }}
            .phase-item.done .phase-circle {{ background: var(--azul); color: white; }}
            .phase-item.active .phase-circle {{ background: var(--azul-med); color: white; border: 4px solid var(--azul-super-claro); }}
            .phase-item.pending .phase-circle {{ background: white; border: 2.5px solid var(--gris-borde); color: var(--gris-texto); }}
            
            /* Calendar Strip Styles */
            .cal-strip {{ display: flex; gap: 8px; overflow-x: auto; padding-bottom: 8px; margin-bottom: 20px; }}
            .cal-day {{
                min-width: 58px; padding: 12px 0; border-radius: 12px;
                border: 1.5px solid var(--gris-borde); background: white;
                display: flex; flex-direction: column; align-items: center; cursor: pointer;
                transition: all 0.2s;
            }}
            .cal-day:hover {{ border-color: var(--azul-claro); background: var(--azul-super-claro); }}
            .cal-day.selected {{ background: var(--azul); border-color: var(--azul); color: white; box-shadow: 0 4px 12px rgba(26,58,107,0.3); }}
            .cal-dow {{ font-size: 10px; font-weight: 700; opacity: 0.6; text-transform: uppercase; margin-bottom: 2px; }}
            .cal-day.selected .cal-dow {{ opacity: 0.8; }}
            .cal-num {{ font-size: 20px; font-weight: 800; }}
            
            .label-premium {{ font-size: 11px; font-weight: 700; color: var(--gris-texto); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 6px; }}
            .form-input-premium {{ 
                background: var(--gris-bg); border: 1.5px solid var(--gris-borde); 
                border-radius: 12px; padding: 12px 16px; font-size: 14px; color: var(--texto);
                transition: all 0.2s;
            }}
            .form-input-premium:focus-within {{ border-color: var(--azul-claro); background: white; box-shadow: 0 0 0 4px rgba(58,123,213,0.1); }}
        </style>
        ''')

        with container.classes('w-full max-w-[1200px] mx-auto p-4 gap-6'):
            
            # 2. STATS ROW
            with ui.row().classes('w-full gap-4'):
                _quick_stat('🚗', str(vehiculos_totales), 'Mis vehículos')
                _quick_stat('🔧', str(servicios_activos), 'Servicio activo')
                _quick_stat('📋', str(visitas_totales), 'Visitas totales')
                _quick_stat('📅', str(proxima_cita), 'Próx. cita')

            # 3. TRACKER DE SEGUIMIENTO (Si hay orden activa)
            if active_order:
                with ui.element('div').classes('card-premium w-full mt-4'):
                    with ui.row().classes('w-full justify-between items-center mb-8'):
                        with ui.column().classes('gap-0'):
                            ui.label('SEGUIMIENTO EN VIVO').classes('text-[10px] font-black text-blue-800 tracking-widest uppercase opacity-50')
                            ui.label(f'Orden de Trabajo #{active_order.consecutivo}').classes('text-xl font-bold text-gray-900')
                        ui.label(f'📅 Entrega estimada: {getattr(active_order, "proximo_mantenimiento", "Pendiente") or "Pendiente"}').classes('text-xs font-bold text-blue-900 bg-blue-50 px-4 py-2 rounded-full border border-blue-100')
                    
                    _render_tracker(active_order.estado)
                    
                    with ui.element('div').classes('mt-8 p-4 bg-gray-50 rounded-xl border border-gray-100 flex items-center gap-4'):
                        ui.icon('info', color='blue-900', size='sm')
                        ui.label(f'Estado actual: {active_order.estado} — {active_order.motivo or "Procesando vehículo..."}').classes('text-sm text-gray-600')

            # 4. GRID CENTRAL: DATOS VEHÍCULO + COTIZACIÓN (Vertical Stack)
            with ui.column().classes('w-full gap-6 mt-4'):
                # Ficha Vehículo
                with ui.element('div').classes('card-premium w-full'):
                    ui.label('🚙 Estado de su Vehículo').classes('text-lg font-bold text-blue-900 mb-6 block')
                    
                    with ui.element('div').classes('w-full h-40 bg-blue-50 rounded-2xl mb-6 flex items-center justify-center border-2 border-dashed border-blue-100'):
                        ui.image('/assets/logo_sandoval.jpg').classes('w-20 opacity-20')
                    
                    with ui.column().classes('w-full gap-2.5'):
                        _data_row('Vehículo', f'{vehiculo.marca} {vehiculo.modelo} {vehiculo.año}')
                        _data_row('Placa', vehiculo.placa)
                        _data_row('KM actual', str(active_order.km if active_order else '—'))
                        _data_row('Técnico', str(active_order.tecnico if active_order else '—'))
                    
                    if active_order and active_order.observaciones:
                        ui.element('div').classes('h-[1px] bg-gray-100 my-4')
                        ui.label(active_order.observaciones).classes('text-xs text-gray-500 italic bg-gray-50 p-4 rounded-xl border-l-4 border-blue-300')

                # Cotización / Repuestos
                with ui.element('div').classes('card-premium w-full'):
                    ui.label('🔩 Repuestos y Servicios').classes('text-lg font-bold text-blue-900 mb-6 block')
                    
                    items = _safe_json(active_order.items_cotizacion) if active_order else []
                    if items:
                        total = 0
                        with ui.column().classes('w-full gap-3'):
                            for i in items:
                                val = float(i.get('total', 0) or 0)
                                total += val
                                with ui.row().classes('w-full justify-between items-center p-3 bg-gray-50 rounded-xl border border-gray-100'):
                                    with ui.column().classes('gap-0'):
                                        ui.label(i.get('item','')).classes('text-xs font-bold text-gray-800')
                                        ui.label(f'Cant: {i.get("cantidad", 1)}').classes('text-[10px] text-gray-400 font-bold')
                                    ui.label(f'S/ {val:,.2f}').classes('text-sm font-bold text-blue-900')
                        
                        with ui.element('div').classes('mt-6 p-4 bg-gray-50 rounded-xl border border-gray-100 flex flex-column gap-1'):
                            with ui.row().classes('w-full justify-between text-xs text-gray-400'):
                                ui.label('Subtotal')
                                ui.label(f'S/ {total/1.18:,.2f}')
                            with ui.row().classes('w-full justify-between text-xs text-gray-400'):
                                ui.label('IGV (18%)')
                                ui.label(f'S/ {total - (total/1.18):,.2f}')
                            with ui.row().classes('w-full justify-between items-center mt-2 pt-2 border-t border-gray-200'):
                                ui.label('TOTAL APROBADO').classes('text-sm font-black text-blue-900')
                                ui.label(f'S/ {total:,.2f}').classes('text-xl font-black text-blue-900')
                        
                        ui.button('VER FACTURA DETALLADA').classes('w-full mt-4 bg-white border-2 border-blue-100 text-blue-900 text-xs font-bold py-3 rounded-xl hover:bg-blue-50')
                    else:
                        with ui.column().classes('w-full items-center py-10 opacity-20'):
                            ui.image('/assets/logo_sandoval.jpg').classes('w-12 grayscale mb-2')
                            ui.label('No hay cargos activos').classes('text-xs font-bold')

            # 5. AGENDAR CITA + NOTIFICACIONES (Vertical Stack)
            with ui.column().classes('w-full gap-6 mt-4'):
                # Agendar Cita (VINCULADO AL DISEÑO PREMIUM)
                with ui.element('div').classes('card-premium w-full'):
                    with ui.row().classes('items-center gap-3 mb-6'):
                        with ui.element('div').classes('w-10 h-10 bg-blue-50 rounded-xl flex items-center justify-center text-blue-800 text-xl'):
                            ui.label('📅')
                        ui.label('Agendar Nueva Cita').classes('text-lg font-bold text-blue-900')
                    
                    # Generador de Días (Siguiente 10 días hábiles)
                    ui.label('SELECCIONAR FECHA').classes('label-premium')
                    with ui.element('div').classes('cal-strip') as strip:
                        selected_date = {'value': None}
                        current = datetime.now()
                        for i in range(12):
                            day = current + timedelta(days=i)
                            if day.weekday() >= 6: continue # Saltar Domingos
                            
                            dow = ['LUN', 'MAR', 'MIÉ', 'JUE', 'VIE', 'SÁB', 'DOM'][day.weekday()]
                            day_str = day.strftime('%Y-%m-%d')
                            day_num = day.strftime('%d')
                            
                            with ui.element('div').classes('cal-day') as d_btn:
                                ui.label(dow).classes('cal-dow')
                                ui.label(day_num).classes('cal-num')
                                
                                # Lógica de selección visual
                                d_btn.on('click', lambda d=day_str, b=d_btn: _handle_cal_select(strip, b, d, selected_date))
                    
                    # Formulario en Grid (2 columnas)
                    with ui.grid(columns=2).classes('w-full gap-4 mt-6'):
                        with ui.column().classes('w-full'):
                            ui.label('VEHÍCULO').classes('label-premium')
                            veh_select = ui.select({v.placa: f'{v.marca} {v.modelo} — {v.placa}' for v in db.query(Vehiculo).filter_by(cliente_id=user_id).all()}).classes('w-full form-input-premium')
                        
                        with ui.column().classes('w-full'):
                            ui.label('HORA DISPONIBLE').classes('label-premium')
                            hora_select = ui.select(['08:00 AM', '09:00 AM', '10:00 AM', '11:00 AM', '02:00 PM', '03:00 PM'], value='08:00 AM').classes('w-full form-input-premium')

                        with ui.column().classes('w-full'):
                            ui.label('TIPO DE SERVICIO').classes('label-premium')
                            serv_select = ui.select(['Mantenimiento General', 'Revisión de Frenos', 'Cambio de Aceite', 'Diagnóstico Eléctrico', 'Otro'], value='Mantenimiento General').classes('w-full form-input-premium')

                        with ui.column().classes('w-full'):
                            ui.label('PRIORIDAD').classes('label-premium')
                            prio_select = ui.select(['Normal', 'Urgente'], value='Normal').classes('w-full form-input-premium')

                    with ui.column().classes('w-full mt-4'):
                        ui.label('DESCRIPCIÓN DEL PROBLEMA (OPCIONAL)').classes('label-premium')
                        desc_input = ui.textarea().props('placeholder="Ej: El carro hace un ruido al frenar..."').classes('w-full form-input-premium h-24')

                    async def submit_appointment():
                        if not selected_date['value'] or not veh_select.value:
                            ui.notify('Por favor seleccione fecha y vehículo', type='warning', position='top')
                            return
                        # Guardar en DB
                        db_c = get_db()
                        try:
                            # Concatenar fecha y hora
                            db_c.add(Cita(
                                cliente_id=user_id,
                                vehiculo_placa=veh_select.value,
                                fecha_cita=selected_date['value'],
                                hora=hora_select.value,
                                motivo=f"[{serv_select.value}] {desc_input.value}"
                            ))
                            db_c.commit()
                            ui.notify('¡Cita solicitada con éxito!', type='positive', icon='cloud_done')
                            # Reset
                            desc_input.value = ''
                        except Exception as e:
                            ui.notify(f'Error: {str(e)}', type='negative')
                        finally: db_c.close()

                    with ui.button(on_click=submit_appointment).classes('w-full mt-6 bg-[#1a3a6b] text-white py-6 rounded-2xl shadow-xl hover:translate-y-[-1px] transition-all'):
                        with ui.row().classes('items-center gap-3'):
                            ui.label('📅').classes('text-xl')
                            ui.label('Confirmar Cita').classes('text-sm font-bold tracking-wider')

                # Notificaciones
                with ui.element('div').classes('card-premium w-full'):
                    with ui.row().classes('w-full justify-between items-center mb-6'):
                        ui.label('🔔 Notificaciones').classes('text-lg font-bold text-blue-900')
                        ui.button('Marcar todo como leído').props('flat no-caps').classes('text-[10px] font-bold text-blue-400')
                    
                    with ui.column().classes('w-full gap-3'):
                        _notif_item('engineering', 'Reparación iniciada', 'El técnico comenzó el trabajo en taller.', 'Hace 3 horas')
                        _notif_item('visibility', 'Diagnóstico subido', 'Ya puede revisar el informe técnico.', 'Hoy 08:00 AM')

            # 6. HISTORIAL DE SERVICIOS
            with ui.element('div').classes('card-premium w-full mt-4 overflow-hidden'):
                ui.label('📂 Historial de Servicios').classes('text-lg font-bold text-blue-900 mb-6')
                
                # Encabezados de tabla con NiceGUI puro
                with ui.row().classes('w-full bg-gray-50 p-4 border-b-2 border-gray-100 items-center hide-on-mobile'):
                    ui.label('FECHA').classes('flex-1 text-[11px] font-bold text-gray-400')
                    ui.label('SERVICIO').classes('flex-[2] text-[11px] font-bold text-gray-400')
                    ui.label('FOLIO').classes('flex-1 text-[11px] font-bold text-gray-400')
                    ui.label('COSTO').classes('flex-1 text-[11px] font-bold text-gray-400 text-center')
                    ui.label('ESTADO').classes('flex-1 text-[11px] font-bold text-gray-400 text-right')

                # Filas de la tabla
                with ui.column().classes('w-full gap-0'):
                    for o in ordenes_all[:8]:
                        with ui.row().classes('w-full p-4 border-b border-gray-100 items-center hover:bg-blue-50/30 transition-colors'):
                            ui.label(str(o.fecha)).classes('flex-1 text-sm text-gray-500')
                            ui.label(o.motivo[:40] + '...' if o.motivo and len(o.motivo)>40 else str(o.motivo or 'Revisión')).classes('flex-[2] text-sm font-bold text-gray-800')
                            ui.badge(str(o.consecutivo)).props('outline').classes('flex-1 text-blue-600 font-mono self-center m-0')
                            
                            o_total = sum(float(it.get('total', 0) or 0) for it in (o.items_cotizacion or []))
                            ui.label(f'S/ {o_total:,.2f}').classes('flex-1 text-sm font-bold text-blue-900 text-center')
                            
                            is_done = o.estado in ('ARCHIVADO', 'ENTREGA')
                            badge_color = 'green-1' if is_done else 'amber-1'
                            text_color = 'green-9' if is_done else 'amber-9'
                            with ui.element('div').classes('flex-1 flex justify-end'):
                                ui.button(icon='visibility', on_click=lambda _, order_obj=o: _view_order_details(order_obj)).props('flat round color=blue-9 size=sm')
                                ui.badge(o.estado).classes(f'bg-{badge_color} text-{text_color} px-3 py-1 rounded-full text-[10px] font-bold ml-2')

    except Exception as e:
        import traceback
        ui.label(f'Error al cargar portal: {e}').classes('p-10 text-red-500')
        ui.label(traceback.format_exc()).classes('p-10 text-xs font-mono text-gray-400')
    finally:
        db.close()

# --- HELPERS UI ---

def _handle_cal_select(parent, button, date_str, state_dict):
    # Deseleccionar todos buscando en los hijos del contenedor
    for child in parent:
        if 'cal-day' in str(child.classes):
            child.classes(remove='selected')
    # Seleccionar actual
    button.classes('selected')
    state_dict['value'] = date_str

def _quick_stat(icon, value, label):
    with ui.element('div').classes('stat-card flex-1 bg-white p-6 rounded-2xl border border-gray-100 flex items-center gap-4 shadow-sm'):
        with ui.element('div').classes('stat-icon-wrap'):
            ui.label(icon).classes('text-xl')
        with ui.column().classes('gap-0'):
            ui.label(value).classes('text-2xl font-extrabold text-[#1a3a6b]')
            ui.label(label).classes('text-[10px] text-gray-400 font-bold uppercase tracking-wider')

def _data_row(label, val):
    with ui.row().classes('w-full justify-between items-center text-sm'):
        ui.label(label).classes('text-gray-400 font-medium')
        ui.label(val).classes('font-bold text-gray-800 text-right')

def _notif_item(icon, title, desc, time):
    with ui.row().classes('w-full gap-3 p-3 bg-gray-50 rounded-xl border border-gray-100 items-start'):
        ui.icon(icon, color='blue-800', size='xs').classes('mt-1')
        with ui.column().classes('gap-0 flex-1'):
            ui.label(title).classes('text-xs font-bold text-gray-800')
            ui.label(desc).classes('text-[10px] text-gray-400 leading-tight')
            ui.label(time).classes('text-[9px] text-blue-300 font-bold mt-1')

def _render_tracker(current_state):
    phases = [
        ('RECEPCIÓN', 'login'), 
        ('DIAGNÓSTICO', 'search'), 
        ('REPUESTOS', 'precision_manufacturing'),
        ('APROBACIÓN', 'check_circle'), 
        ('REPARACIÓN', 'engineering'), 
        ('CONTROL', 'verified'), 
        ('ENTREGA', 'verified_user')
    ]
    
    current_idx = 0
    for i, (name, _) in enumerate(phases):
        if name == current_state: current_idx = i
    
    with ui.row().classes('w-full justify-between relative mt-4'):
        # Línea de progreso
        ui.element('div').classes('absolute top-[24px] left-0 right-0 h-1 bg-gray-100 shadow-inner')
        ui.element('div').classes('absolute top-[24px] left-0 h-1 bg-blue-900 transition-all duration-1000 shadow-lg').style(f'width: {(current_idx / (len(phases)-1)) * 100}%')
        
        for i, (name, icon) in enumerate(phases):
            status_cls = 'done' if i < current_idx else 'active' if i == current_idx else 'pending'
            with ui.column().classes(f'phase-item {status_cls}'):
                with ui.element('div').classes('phase-circle shadow-xl'):
                    if i < current_idx: ui.icon('check', size='sm')
                    elif i == current_idx: ui.icon(icon, size='sm')
                    else: ui.label(str(i+1)).classes('text-xs font-bold')
                
                ui.label(name).classes('text-[9px] font-black text-center whitespace-pre-wrap w-16')

def _safe_json(data):
    if not data: return []
    if isinstance(data, list): return data
    try: return json.loads(data)
    except: return []

def _view_order_details(o):
    with ui.dialog() as d, ui.card().classes('w-full max-w-lg p-0 bg-slate-50 overflow-hidden shadow-2xl rounded-t-3xl'):
        # Header Premium
        with ui.row().classes('w-full p-5 bg-[#1a3a6b] text-white items-center justify-between shadow-lg'):
            with ui.column().classes('gap-0'):
                ui.label(o.consecutivo).classes('text-xl font-black italic tracking-tighter')
                ui.label(f"Registrado el {o.fecha}").classes('text-[10px] opacity-80 uppercase font-bold')
            ui.button(icon='close', on_click=d.close).props('flat round color=white size=sm')

        with ui.scroll_area().classes('w-full p-5').style('height: 80vh'):
            # --- 1. SEGUIMIENTO DE 7 ETAPAS (PROFESIONAL) ---
            ui.label('SEGUIMIENTO EN TIEMPO REAL').classes('text-[10px] font-black text-slate-400 tracking-[0.3em] mb-4 p-1')
            
            # Reutilizar el tracker de 7 fases
            _render_tracker(o.estado)
            
            ui.separator().classes('my-8 opacity-40')

            # --- 2. DETALLES POR FASE ---
            
            # FASE 1: RECEPCIÓN
            with ui.column().classes('w-full gap-3 mb-8'):
                with ui.row().classes('items-center gap-2 mb-1'):
                    ui.icon('login', color='blue-9', size='18px')
                    ui.label('1. DETALLES DE RECEPCIÓN').classes('text-[11px] font-black text-blue-900 tracking-widest')
                
                with ui.card().classes('w-full p-4 bg-white border border-slate-200 shadow-sm rounded-xl'):
                    ui.label('SÍNTOMAS / MOTIVO:').classes('text-[9px] font-black text-slate-400')
                    ui.label(o.motivo or 'Revisión General').classes('text-sm text-slate-800 font-bold leading-relaxed')
                    with ui.row().classes('w-full mt-3 gap-6 border-t border-slate-100 pt-3'):
                        with ui.column().classes('gap-0'):
                            ui.label('KILOMETRAJE').classes('text-[9px] text-slate-400')
                            ui.label(f"{o.km or '-'} KM").classes('text-xs font-black text-slate-800')
                        with ui.column().classes('gap-0'):
                            ui.label('TÉCNICO').classes('text-[9px] text-slate-400')
                            ui.label(o.tecnico or 'Asignado').classes('text-xs font-black text-slate-800')
                
                # Fotos de Recepción
                _render_fase_media(o, 'RECEPCIÓN')

            # FASE 2: DIAGNÓSTICO
            if o.estado not in ('RECEPCIÓN'):
                with ui.column().classes('w-full gap-3 mb-8'):
                    with ui.row().classes('items-center gap-2 mb-1'):
                        ui.icon('search', color='blue-9', size='18px')
                        ui.label('2. DIAGNÓSTICO TÉCNICO').classes('text-[11px] font-black text-blue-900 tracking-widest')
                    
                    with ui.card().classes('w-full p-4 bg-white border border-slate-200 shadow-sm rounded-xl'):
                        ui.label('RESULTADO DEL DIAGNÓSTICO:').classes('text-[9px] font-black text-slate-400')
                        if o.diagnostico:
                            ui.label(o.diagnostico).classes('text-sm text-slate-800 leading-relaxed')
                        else:
                            ui.label('Diagnóstico en curso...').classes('text-sm text-slate-400 italic font-medium')
                    
                    # Fotos de Diagnóstico
                    _render_fase_media(o, 'DIAGNÓSTICO')

            # FASE 3: REPUESTOS
            if o.estado not in ('RECEPCIÓN', 'DIAGNÓSTICO'):
                with ui.column().classes('w-full gap-3 mb-8'):
                    with ui.row().classes('items-center gap-2 mb-1'):
                        ui.icon('inventory', color='blue-9', size='18px')
                        ui.label('3. PRESUPUESTO Y REPUESTOS').classes('text-[11px] font-black text-blue-900 tracking-widest')
                    
                    items = _safe_json(o.items_cotizacion)
                    if items:
                        with ui.column().classes('w-full gap-2'):
                            total_ods = 0
                            for it in items:
                                val = float(it.get('total', 0))
                                total_ods += val
                                with ui.card().classes('w-full p-3 bg-white border border-slate-100 flex-row items-center justify-between'):
                                    ui.label(it.get('nombre', 'Ítem')).classes('text-xs font-bold text-slate-700')
                                    ui.label(f"S/ {val:,.2f}").classes('text-xs font-black text-blue-900')
                            
                            with ui.card().classes('w-full p-4 bg-blue-50 border-2 border-blue-100 items-end'):
                                ui.label('TOTAL ESTIMADO').classes('text-[10px] font-black text-blue-900')
                                ui.label(f"S/ {total_ods:,.2f}").classes('text-2xl font-black text-[#1a3a6b]')
                    else:
                        ui.label('Preparando cotización de repuestos...').classes('text-xs text-slate-400 italic p-2')

            # Botón de contactar si está en etapas avanzadas
            with ui.row().classes('w-full mt-4'):
                ui.button('CONSULTAR POR WHATSAPP', icon='chat').props('unelevated color=green-6').classes('w-full h-14 rounded-2xl font-black text-sm')

        d.open()

def _render_fase_media(order, fase_nombre):
    """Filtra y renderiza la evidencia de una fase específica"""
    medios_raw = _safe_json(order.fotos_evidencia)
    # Filtrar solo los que pertenecen a esta fase (o los que no tienen fase si es RECEPCIÓN - retrocompatibilidad)
    medios = []
    for m in medios_raw:
        if isinstance(m, dict):
            if m.get('fase') == fase_nombre:
                medios.append(m.get('path'))
        elif isinstance(m, str) and fase_nombre == 'RECEPCIÓN':
            medios.append(m)
    
    if medios:
        with ui.row().classes('w-full gap-2 mt-2 overflow-x-auto no-wrap p-1'):
            for path in medios:
                ui.image(path).classes('w-24 h-24 rounded-lg shadow-md object-cover border-2 border-white')

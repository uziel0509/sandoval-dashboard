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
            
            /* Ajustes para Móvil */
            @media (max-width: 600px) {{
                .card-premium {{ padding: 16px; border-radius: 12px; }}
                .phase-circle {{ width: 28px; height: 28px; font-size: 12px; }}
                .phase-item label {{ font-size: 8px; width: 50px; }}
                .tracker-line {{ display: none !important; }}
                .tracker-progress {{ display: none !important; }}
                .hide-on-mobile {{ display: none !important; }}
                
                /* Vertical Tracker for Mobile */
                .tracker-container-mobile {{
                    display: flex;
                    flex-direction: column;
                    gap: 0px;
                    padding-left: 20px;
                    border-left: 2px solid var(--gris-borde);
                    margin-left: 10px;
                }}
                .phase-item-v {{
                    display: flex;
                    flex-direction: row;
                    align-items: center;
                    gap: 16px;
                    padding: 12px 0;
                    position: relative;
                }}
                .phase-item-v::before {{
                    content: '';
                    position: absolute;
                    left: -21px;
                    top: 0;
                    bottom: 0;
                    width: 2px;
                    background: var(--gris-borde);
                }}
                .phase-item-v.done::before, .phase-item-v.active::before {{
                    background: var(--azul);
                }}
                .phase-circle-v {{
                    width: 32px;
                    height: 32px;
                    border-radius: 50%;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    font-size: 14px;
                    background: white;
                    border: 2px solid var(--gris-borde);
                    z-index: 2;
                    margin-left: -37px;
                }}
                .done .phase-circle-v {{ background: var(--azul); color: white; border-color: var(--azul); }}
                .active .phase-circle-v {{ background: var(--azul-med); color: white; border-color: var(--azul-med); box-shadow: 0 0 10px rgba(35, 86, 168, 0.3); }}
            }}
            .tracker-line {{ position: absolute; height: 3px; background: var(--gris-borde); top: 24px; left: 0; right: 0; z-index: 1; }}
            .tracker-progress {{ position: absolute; height: 3px; background: var(--azul); top: 24px; left: 0; z-index: 1; transition: width 1s; }}
        </style>
        ''')

        with container.classes('w-full max-w-[1200px] mx-auto p-4 gap-6 pb-24 md:pb-6'):
            # Welcome Message
            with ui.column().classes('w-full gap-1 mb-2'):
                ui.label(f'¡Hola, {cliente.nombre}! 👋').classes('text-2xl font-black text-blue-950 tracking-tighter')
                ui.label('Aquí puedes ver el estado real de tu atención.').classes('text-xs text-gray-500 font-bold')
            
            
            # 2. STATS ROW
            with ui.row().classes('w-full gap-4 md:flex-nowrap flex-wrap'):
                _quick_stat('🚗', str(vehiculos_totales), 'Mis vehículos')
                _quick_stat('🔧', str(servicios_activos), 'Servicio activo')
                _quick_stat('📋', str(visitas_totales), 'Visitas totales')
                _quick_stat('📅', str(proxima_cita), 'Próx. cita')

            # 3. TRACKER DE SEGUIMIENTO (Si hay orden activa)
            if active_order:
                with ui.element('div').classes('card-premium w-full mt-4').props('id="seguimiento-en-vivo"'):
                    with ui.row().classes('w-full justify-between items-center mb-8'):
                        with ui.column().classes('gap-0'):
                            ui.label('SEGUIMIENTO EN VIVO').classes('text-[10px] font-black text-blue-800 tracking-widest uppercase opacity-50')
                            ui.label(f'Orden de Trabajo #{active_order.consecutivo}').classes('text-xl font-bold text-gray-900')
                        ui.label(f'📅 Entrega estimada: {getattr(active_order, "proximo_mantenimiento", "Pendiente") or "Pendiente"}').classes('text-xs font-bold text-blue-900 bg-blue-50 px-4 py-2 rounded-full border border-blue-100 mt-2 md:mt-0')
                    
                    # Horizontal tracker for Desktop, Vertical for Mobile
                    with ui.element('div').classes('w-full mt-4 md:block hidden'):
                        _render_tracker(active_order.estado)
                    
                    with ui.element('div').classes('w-full mt-4 md:hidden block'):
                        _render_tracker_vertical(active_order.estado)
                    
                    # ─── MÓDULO ESPECIAL DE APROBACIÓN (Fase 4) ───
                    if active_order.estado == 'APROBACIÓN':
                        _render_approval_module(active_order)
                    else:
                        # Evidencia de la fase actual (Para otras fases)
                        with ui.column().classes('w-full mt-6 gap-2'):
                            ui.label(f'EVIDENCIA DE {active_order.estado}').classes('text-[9px] font-black text-blue-900 tracking-widest opacity-60')
                            _render_fase_media(active_order, active_order.estado)

                        with ui.element('div').classes('mt-4 p-4 bg-gray-50 rounded-xl border border-gray-100 flex items-center gap-4'):
                            ui.icon('info', color='blue-900', size='sm')
                            ui.label(f'Estado: {active_order.estado} — {active_order.motivo or "Procesando vehiculo..."}').classes('text-sm text-gray-600')

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
                with ui.element('div').classes('card-premium w-full').props('id="agendar-cita"'):
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
            with ui.element('div').classes('card-premium w-full mt-4 overflow-hidden').props('id="historial-servicios"'):
                ui.label('📂 Historial de Servicios').classes('text-lg font-bold text-blue-900 mb-6')
                
                # Encabezados de tabla con NiceGUI puro
                with ui.row().classes('w-full bg-gray-50 p-4 border-b-2 border-gray-100 items-center hide-on-mobile'):
                    ui.label('FECHA').classes('flex-1 text-[11px] font-bold text-gray-400')
                    ui.label('SERVICIO').classes('flex-[2] text-[11px] font-bold text-gray-400')
                    ui.label('FOLIO').classes('flex-1 text-[11px] font-bold text-gray-400')
                    ui.label('COSTO').classes('flex-1 text-[11px] font-bold text-gray-400 text-center')
                    ui.label('ESTADO').classes('flex-1 text-[11px] font-bold text-gray-400 text-right')

                # Filas de la tabla / Tarjetas en Móvil
                with ui.column().classes('w-full gap-3 mt-2'):
                    for o in ordenes_all[:8]:
                        # Card for mobile
                        with ui.element('div').classes('md:hidden block bg-gray-50 p-4 rounded-2xl border border-gray-100 shadow-sm'):
                            with ui.row().classes('w-full justify-between items-center mb-2'):
                                ui.label(str(o.fecha)).classes('text-[10px] font-bold text-gray-400')
                                ui.badge(str(o.consecutivo)).props('outline').classes('text-blue-600 font-mono')
                            ui.label(o.motivo or 'Revisión').classes('text-sm font-black text-gray-800 mb-2')
                            with ui.row().classes('w-full justify-between items-center mt-2 pt-2 border-t border-gray-200/50'):
                                is_done = o.estado in ('ARCHIVADO', 'ENTREGA')
                                badge_color = 'green-1' if is_done else 'amber-1'
                                text_color = 'green-9' if is_done else 'amber-9'
                                ui.badge(o.estado).classes(f'bg-{badge_color} text-{text_color} px-3 py-1 rounded-full text-[10px] font-bold')
                                ui.button(icon='visibility', on_click=lambda _, order_obj=o: _view_order_details(order_obj)).props('flat round color=blue-9 size=sm')

                        # Row for desktop
                        with ui.row().classes('hide-on-mobile w-full p-4 border-b border-gray-100 items-center hover:bg-blue-50/30 transition-colors'):
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

            # Bottom Navigation for Mobile
            with ui.element('div').classes('bottom-nav md:hidden'):
                with ui.element('div').classes('nav-item'):
                    ui.icon('home', size='xs', color='blue-900')
                    ui.label('Inicio')
                with ui.element('div').classes('nav-item').on('click', lambda: ui.scroll_to('agendar-cita')):
                    ui.icon('event', size='xs')
                    ui.label('Citas')
                with ui.element('div').classes('nav-item').on('click', lambda: ui.scroll_to('seguimiento-en-vivo')):
                    ui.icon('build', size='xs')
                    ui.label('Taller')
                with ui.element('div').classes('nav-item').on('click', lambda: ui.scroll_to('historial-servicios')):
                    ui.icon('history', size='xs')
                    ui.label('Historial')

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
    with ui.element('div').classes('stat-card flex-1 min-w-[140px] bg-white p-6 rounded-2xl border border-gray-100 flex items-center gap-4 shadow-sm'):
        with ui.element('div').classes('stat-icon-wrap'):
            ui.label(icon).classes('text-xl')
        with ui.column().classes('gap-0'):
            ui.label(value).classes('text-2xl font-extrabold text-[#1a3a6b]')
            ui.label(label).classes('text-[10px] text-gray-400 font-bold uppercase tracking-wider')

def _data_row(label, val):
    with ui.row().classes('w-full justify-between items-center text-sm'):
        ui.label(label).classes('text-gray-400 font-medium')
        ui.label(val).classes('font-bold text-gray-800 text-right')

def _render_tracker_vertical(current_state):
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
    
    with ui.column().classes('tracker-container-mobile'):
        for i, (name, icon) in enumerate(phases):
            status_cls = 'done' if i < current_idx else 'active' if i == current_idx else 'pending'
            with ui.element('div').classes(f'phase-item-v {status_cls}'):
                with ui.element('div').classes('phase-circle-v shadow-sm'):
                    if i < current_idx: ui.icon('check', size='xs')
                    elif i == current_idx: ui.icon(icon, size='xs')
                    else: ui.label(str(i+1)).classes('text-[10px] font-bold')
                
                with ui.column().classes('gap-0'):
                    ui.label(name).classes('text-[11px] font-black tracking-tight')
                    if i == current_idx:
                        ui.label('EN PROGRESO').classes('text-[8px] font-bold text-blue-400 animate-pulse')
                    elif i < current_idx:
                        ui.label('COMPLETADO').classes('text-[8px] font-bold text-green-500')

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
    
    with ui.row().classes('w-full justify-between relative mt-4 md:no-wrap overflow-x-auto pb-4'):
        # Línea de progreso
        ui.element('div').classes('tracker-line shadow-inner')
        ui.element('div').classes('tracker-progress shadow-lg').style(f'width: {(current_idx / (len(phases)-1)) * 100}%')
        
        for i, (name, icon) in enumerate(phases):
            status_cls = 'done' if i < current_idx else 'active' if i == current_idx else 'pending'
            with ui.column().classes(f'phase-item {status_cls}'):
                with ui.element('div').classes('phase-circle shadow-xl'):
                    if i < current_idx: ui.icon('check', size='sm')
                    elif i == current_idx: ui.icon(icon, size='sm')
                    else: ui.label(str(i+1)).classes('text-xs font-bold')
                
                ui.label(name).classes('text-[9px] font-black text-center whitespace-pre-wrap w-16')

def _safe_json(data):
    if not data: return {}
    if isinstance(data, (list, dict)): return data
    if isinstance(data, str):
        try: return json.loads(data)
        except: return {}
    return {}

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
                ui.button('CONSULTAR POR WHATSAPP', icon='chat', on_click=lambda: ui.open('https://wa.me/51924980586')).props('unelevated color=green-6').classes('w-full h-14 rounded-2xl font-black text-sm')

        d.open()

def _render_fase_media(order, fase_nombre):
    """
    Filtra y renderiza la evidencia de una fase específica (RECEPCIÓN, DIAGNÓSTICO, REPARACIÓN).
    Unifica fotos de order.fotos_evidencia y order.checklist_reparacion['evidence_cats'].
    """
    import os
    # 1. Recoger todos los medios posibles
    medios_sources = []
    
    # Fuente A: fotos_evidencia (Legacy/Recepción/Carga simple)
    fev = order.fotos_evidencia
    if fev:
        if isinstance(fev, str):
            try: fev = json.loads(fev)
            except: fev = []
        if isinstance(fev, list):
            medios_sources.extend(fev)

    # Fuente B: checklist_reparacion (Advanced Repair)
    chk = _safe_json(order.checklist_reparacion)
    ev_cats = chk.get('evidence_cats', {})
    for cat, list_med in ev_cats.items():
        if isinstance(list_med, list):
            for m in list_med:
                if isinstance(m, str): medios_sources.append({'path': m, 'fase': cat})
                elif isinstance(m, dict): medios_sources.append(m)

    # 2. Normalizar y Filtrar
    def normalize(text):
        if not text: return ""
        t = str(text).upper().strip()
        replacements = {'Á': 'A', 'É': 'E', 'Í': 'I', 'Ó': 'O', 'Ú': 'U'}
        for k, v in replacements.items(): t = t.replace(k, v)
        return t

    fase_buscada = normalize(fase_nombre)
    final_medios = []

    for m in medios_sources:
        path = m.get('path') if isinstance(m, dict) else m
        fase_item = normalize(m.get('fase', 'RECEPCIÓN') if isinstance(m, dict) else 'RECEPCIÓN')
        
        # Heurística para strings puros
        if isinstance(m, str):
            if 'DIAG' in m.upper(): fase_item = 'DIAGNOSTICO'
            elif 'REP' in m.upper() or 'FIX' in m.upper(): fase_item = 'REPARACION'
        
        if path and fase_item == fase_buscada:
            final_medios.append(path)
    
    # 3. Renderizar (Imagen o Video)
    if final_medios:
        with ui.row().classes('w-full gap-3 mt-2 overflow-x-auto no-wrap p-2'):
            for path in final_medios:
                ext = os.path.splitext(path)[1].lower()
                is_video = ext in ['.mp4', '.mov', '.avi', '.webm']
                
                with ui.element('div').classes('flex-shrink-0 relative'):
                    if is_video:
                        ui.video(path).classes('w-48 h-32 rounded-xl shadow-lg border-2 border-white')
                    else:
                        ui.image(path).classes('w-32 h-32 rounded-lg shadow-md object-cover border-2 border-white hover:scale-105 transition-transform cursor-pointer').on('click', lambda p=path: ui.open(p, '_blank'))
    else:
        with ui.row().classes('w-full items-center justify-center py-6 opacity-30 border-2 border-dashed border-gray-100 rounded-xl'):
            ui.label(f'Sin archivos en {fase_nombre}').classes('text-[10px] uppercase font-bold text-gray-400')

def _render_approval_module(order):
    """Módulo premium para que el cliente apruebe el diagnóstico y presupuesto desde su celular"""
    with ui.column().classes('w-full mt-8 gap-6'):
        with ui.element('div').classes('p-8 rounded-[32px] border-2 border-orange-100 bg-white shadow-xl relative overflow-hidden'):
            # Decoración de fondo tenue
            ui.html('<div style="position:absolute;top:-20px;right:-20px;opacity:0.03;transform:rotate(-15deg);pointer-events:none;"><span class="material-icons-round" style="font-size:200px">verified_user</span></div>').classes('relative z-0')
            
            with ui.row().classes('w-full items-center gap-4 mb-8 relative z-10'):
                with ui.element('div').classes('w-14 h-14 bg-orange-50 rounded-2xl flex items-center justify-center text-orange-600 shadow-inner'):
                    ui.icon('verified_user', size='md')
                with ui.column().classes('gap-0'):
                    ui.label('CENTRO DE APROBACIÓN SANDOVAL').classes('text-blue-950 font-black tracking-tighter text-xl italic')
                    ui.label('REVISIÓN TÉCNICA E INFORME DE INVERSIÓN').classes('text-[9px] text-orange-700 font-black tracking-[0.2em] opacity-80')

            # --- 1. INFORME TÉCNICO (LABORATORIO STYLE) ---
            with ui.column().classes('w-full mb-8 relative z-10'):
                ui.label('📋 INFORME DEL ESPECIALISTA').classes('text-[10px] font-black text-slate-400 tracking-[0.25em] mb-3')
                with ui.element('div').classes('p-6 bg-slate-50 border-l-4 border-blue-900 rounded-r-2xl shadow-sm mb-4'):
                    ui.label(order.diagnostico or 'Diagnóstico técnico detallado pendiente...').classes('text-sm text-slate-700 leading-relaxed font-semibold italic whitespace-pre-wrap')
                
                # Botón Escáner Premium
                chk_data = _safe_json(order.checklist_reparacion)
                details = chk_data.get('diagnostic_details', {})
                scanner_pdf = details.get('scanner_path')
                
                if scanner_pdf:
                    ui.button('DESCARGAR REPORTE ELECTRÓNICO (PDF)', icon='analytics', 
                              on_click=lambda: ui.open(scanner_pdf, '_blank')).classes('w-full h-16 bg-slate-900 text-white rounded-2xl font-black shadow-2xl hover:bg-black transition-all mb-4 mt-2 tracking-widest text-xs')

                # Evidencia Visual
                ui.label('📸 EVIDENCIA TÉCNICA ADJUNTA').classes('text-[10px] font-black text-slate-400 tracking-[0.25em] mb-3 mt-4')
                _render_fase_media(order, 'DIAGNÓSTICO')

            # --- 2. PRESUPUESTO (PREMIUM TABLE) ---
            with ui.column().classes('w-full mb-10 relative z-10'):
                ui.label('🔩 DESGLOSE DE PRESUPUESTO').classes('text-[10px] font-black text-slate-400 tracking-[0.25em] mb-4')
                items = _safe_json(order.items_cotizacion)
                if items:
                    total_val = 0
                    with ui.column().classes('w-full gap-2.5 mb-6'):
                        for it in items:
                            sub_v = float(it.get('total', 0) or 0)
                            total_val += sub_v
                            with ui.row().classes('w-full justify-between items-center p-4 bg-white border border-slate-100 rounded-2xl hover:border-blue-200 transition-all shadow-sm'):
                                with ui.column().classes('gap-0'):
                                    ui.label(it.get('nombre', it.get('item', 'Repuesto/Servicio'))).classes('text-[13px] font-black text-slate-800 uppercase tracking-tighter')
                                    ui.label(f"Unidades: {it.get('cantidad', 1)}").classes('text-[10px] text-slate-400 font-bold')
                                ui.label(f"S/ {sub_v:,.2f}").classes('text-[15px] font-black text-blue-900 italic')
                    
                    # Total Pill
                    with ui.row().classes('w-full justify-between items-center p-8 bg-gradient-to-br from-blue-900 to-[#0f172a] text-white rounded-[32px] shadow-2xl mt-4 relative overflow-hidden'):
                         # Brillo secundario
                         ui.html('<div style="position:absolute;top:0;left:0;width:100%;height:100%;background:linear-gradient(45deg,transparent 0%, rgba(255,255,255,0.05) 50%, transparent 100%);"></div>')
                         with ui.column().classes('gap-0.5'):
                             ui.label('TOTAL INVERSIÓN').classes('text-[10px] font-black tracking-[0.3em] opacity-60')
                             ui.label(f"S/ {total_val:,.2f}").classes('text-4xl font-black tracking-tighter italic')
                         with ui.element('div').classes('w-14 h-14 bg-white/10 rounded-full flex items-center justify-center backdrop-blur-md'):
                             ui.icon('payments', size='md', color='white')

            # --- 3. POLÍTICA DE GESTIÓN (ADELANTO) ---
            with ui.row().classes('w-full p-6 bg-blue-50/50 border border-blue-100 rounded-[28px] gap-4 items-start relative z-10'):
                ui.icon('info', color='blue-600', size='md').classes('shrink-0 shadow-sm opacity-80')
                with ui.column().classes('gap-1.5 flex-1'):
                    ui.label('COMPROMISO DE CALIDAD Y GESTIÓN').classes('text-xs font-black text-blue-900 tracking-wider')
                    ui.label('Para asegurar la disponibilidad inmediata de repuestos y honrar el plazo de entrega proyectado, requerimos su aprobación digital. Una vez otorgada, por favor coordine con administración el adelanto correspondiente para formalizar el inicio de los trabajos técnico-mecánicos.').classes('text-[11px] text-slate-600 leading-relaxed font-semibold')

            # --- 4. PANEL DE CONTROL (SI NO ESTÁ APROBADO AÚN) ---
            if order.approval_status == 'aprobado':
                with ui.row().classes('w-full p-8 bg-emerald-50 rounded-[32px] border-2 border-emerald-100 items-center justify-center gap-4 mt-10 relative z-10'):
                    ui.icon('check_circle', color='emerald-500', size='lg').classes('drop-shadow-sm')
                    ui.label('PRESUPUESTO AUTORIZADO — TRABAJOS EN PROGRESO').classes('text-emerald-700 font-black tracking-widest text-xs tracking-tighter')
            else:
                async def approve_order_portal():
                    db_app = get_db()
                    try:
                        o_app = db_app.query(Orden).filter_by(consecutivo=order.consecutivo).first()
                        if o_app:
                            o_app.approval_status = 'aprobado'
                            o_app.estado = 'REPARACIÓN'
                            h_list = list(o_app.historial or [])
                            h_list.append({
                                'fecha': datetime.now().strftime('%Y-%m-%d %H:%M'),
                                'accion': 'Aprobación confirmada por cliente desde móvil/portal',
                                'usuario': 'Cliente'
                            })
                            o_app.historial = h_list
                            db_app.commit()
                            ui.notify('PRESUPUESTO AUTORIZADO CORRECTAMENTE', type='positive', icon='verified', position='center')
                            # Redirigir a WhatsApp
                            ui.run_javascript(f'setTimeout(() => window.location.href = "https://wa.me/51924980586?text=Hola,%20acabo%20de%20aprobar%20mi%20presupuesto%20desde%20el%20portal%20móvil%20(Orden%20{order.consecutivo.replace("#","%23")})", 2000)')
                    except Exception as ex:
                        ui.notify(f'Error al procesar: {ex}', type='negative')
                    finally:
                        db_app.close()

                # Botón de aprobación con animación de pulso (vía Tailwind animado o sombra)
                ui.button('AUTORIZAR INICIO DE REPARACIÓN', icon='bolt', on_click=approve_order_portal).classes('w-full mt-10 bg-emerald-500 text-white py-10 rounded-[28px] shadow-2xl hover:scale-[1.02] active:scale-95 transition-all font-black tracking-[0.1em] text-sm italic').style('box-shadow: 0 20px 40px -10px rgba(16, 185, 129, 0.4);')

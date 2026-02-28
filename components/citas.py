"""
SANDOVAL Dashboard - Sistema de Citas / Agenda
Programación y seguimiento de citas
"""

from nicegui import ui
from utils.models import get_db, Cita, Cliente, log_actividad
from utils.notifications import marcar_citas_vistas_admin
from datetime import datetime
import theme


def show_citas(container):
    marcar_citas_vistas_admin()
    with container:
        state = {'filter': 'todas'}
        
        # Header Corporativo Minimalista
        with ui.row().classes('w-full items-center justify-between mb-4 fade-in py-5 px-8 bg-white border border-gray-100 rounded-xl shadow-sm'):
            with ui.row().classes('items-center gap-4'):
                ui.icon('event', size='32px').classes('text-[#274495]')
                ui.label('AGENDA DE CITAS').classes('text-xl font-extrabold text-[#274495] tracking-tight')
            ui.button('Nueva Cita', icon='add',
                on_click=lambda: open_cita_dialog(table_container, state)
            ).classes('btn-sandoval')
        
        # Stats
        db = get_db()
        try:
            total = db.query(Cita).count()
            hoy = datetime.now().strftime('%Y-%m-%d')
            hoy_count = db.query(Cita).filter(Cita.fecha_cita.like(f'{hoy}%')).count()
            programadas = db.query(Cita).filter_by(estado='programada').count()
        finally:
            db.close()
        
        with ui.row().classes('w-full gap-4 mb-4'):
            _stat('TOTAL CITAS', str(total), 'event', 'blue-900')
            _stat('HOY', str(hoy_count), 'today', 'slate-700')
            _stat('PROGRAMADAS', str(programadas), 'schedule', 'blue-800')
        
        # Filtros White Bar
        with ui.row().classes('w-full bg-white p-4 border-x border-b border-gray-200 rounded-b-lg mb-6 gap-2 items-center shadow-sm'):
            ui.label('Filtrar:').classes('text-sm font-bold text-gray-600 mr-2')
            for f, label in [('todas', 'Todas'), ('programada', 'Programadas'), ('confirmada', 'Confirmadas'), ('completada', 'Completadas'), ('cancelada', 'Canceladas')]:
                color = 'primary' if state['filter'] == f else 'grey-4'
                text_color = 'white' if state['filter'] == f else 'grey-8'
                ui.button(label,
                    on_click=lambda flt=f: (state.update({'filter': flt}), refresh_table(table_container, state))
                ).props(f'unelevated color={color} text-color={text_color} dense size=sm').classes('px-3')
        
        table_container = ui.column().classes('w-full')
        refresh_table(table_container, state)


def _stat(title, value, icon, color):
    with ui.card().classes('flex-1 bg-white border border-gray-200 p-4 shadow-sm hover:border-blue-400 transition-colors'):
        with ui.row().classes('items-center justify-between w-full'):
            with ui.column().classes('gap-1'):
                ui.label(title).classes('text-xs font-bold text-gray-500 tracking-wider')
                ui.label(value).classes(f'text-3xl font-bold text-{color}')
            with ui.avatar(color=color.replace('-7','-1').replace('-8','-1'), text_color=color).classes('rounded-lg'):
                ui.icon(icon, size='md')


def refresh_table(container, state):
    container.clear()
    db = get_db()
    try:
        query = db.query(Cita)
        if state.get('filter') and state['filter'] != 'todas':
            query = query.filter_by(estado=state['filter'])
        citas = query.order_by(Cita.fecha_cita.desc()).all()
        
        clients = {c.id: c for c in db.query(Cliente).all()}
        
        with container:
            if not citas:
                with ui.card().classes('w-full bg-white border border-gray-200 p-8 text-center shadow-sm'):
                    ui.icon('event_busy', size='48px').classes('text-gray-400')
                    ui.label('No hay citas registradas').classes('text-gray-500 mt-2')
                return
            
            # Grid layout for cards
            with ui.grid().classes('w-full gap-4 grid-cols-1 md:grid-cols-2 lg:grid-cols-3'):
                for cita in citas:
                    client = clients.get(cita.cliente_id)
                    _render_cita_card(cita, client, container, state)
    finally:
        db.close()


def _render_cita_card(cita, client, container, state):
    color_map = {'programada': 'blue-1', 'confirmada': 'green-1', 'completada': 'grey-1', 'cancelada': 'red-1'}
    text_map = {'programada': 'blue-9', 'confirmada': 'green-9', 'completada': 'grey-8', 'cancelada': 'red-9'}
    border_map = {'programada': 'blue-200', 'confirmada': 'green-200', 'completada': 'grey-300', 'cancelada': 'red-200'}
    
    bg_color = color_map.get(cita.estado, 'gray-50')
    text_color = text_map.get(cita.estado, 'gray-800')
    border_color = border_map.get(cita.estado, 'gray-200')
    
    with ui.card().classes(f'w-full bg-white border border-{border_color} shadow-sm hover:shadow-md transition-all p-0'):
        # Card Header
        with ui.row().classes(f'w-full items-center justify-between p-3 bg-{bg_color} border-b border-{border_color}'):
            with ui.row().classes('items-center gap-2'):
                ui.icon('event', size='20px').classes(f'text-{text_color}')
                ui.label(cita.fecha_cita).classes(f'font-bold text-{text_color}')
            ui.badge(cita.estado.upper(), color=text_color.replace('-9','-7').replace('-8','-7'))
        
        # Card Body
        with ui.column().classes('p-4 w-full gap-2'):
            ui.label(cita.hora or "Sin hora").classes('text-lg font-bold text-gray-800')
            if client:
                with ui.row().classes('items-center gap-2'):
                    ui.icon('person', size='xs').classes('text-gray-400')
                    ui.label(f'{client.nombre} {client.apellidos}'.strip()).classes('text-gray-600 text-sm')
            if cita.vehiculo_placa:
                with ui.row().classes('items-center gap-2'):
                    ui.icon('directions_car', size='xs').classes('text-gray-400')
                    ui.label(f'{cita.vehiculo_placa}').classes('text-gray-600 text-sm')
            if cita.motivo:
                ui.label(cita.motivo).classes('text-gray-500 text-xs italic mt-1')
        
        # Card Actions
        with ui.row().classes('w-full justify-end p-2 bg-gray-50 border-t border-gray-100 gap-1'):
            if cita.estado == 'programada':
                ui.button(icon='check', on_click=lambda c=cita: update_estado(c.id, 'confirmada', container, state)).props('flat dense color=green-7 size=sm').tooltip('Confirmar')
            if cita.estado in ('programada', 'confirmada'):
                ui.button(icon='done_all', on_click=lambda c=cita: update_estado(c.id, 'completada', container, state)).props('flat dense color=blue-7 size=sm').tooltip('Completar')
                ui.button(icon='close', on_click=lambda c=cita: update_estado(c.id, 'cancelada', container, state)).props('flat dense color=red-7 size=sm').tooltip('Cancelar')
            ui.button(icon='delete', on_click=lambda c=cita: delete_cita(c.id, container, state)).props('flat dense color=grey-7 size=sm')


def update_estado(cita_id, nuevo_estado, container, state):
    db = get_db()
    try:
        cita = db.query(Cita).filter_by(id=cita_id).first()
        if cita:
            cita.estado = nuevo_estado
            cita.vista_admin = 1  # El admin la vio al cambiarle el estado
            db.commit()
            log_actividad(f'Cita {cita_id} → {nuevo_estado}', 'citas')
            if nuevo_estado == 'confirmada':
                theme.notify_success(f'✅ Cita confirmada — el cliente verá la notificación en su portal')
            elif nuevo_estado == 'completada':
                theme.notify_success(f'Cita marcada como completada')
            else:
                theme.notify_success(f'Cita actualizada a {nuevo_estado}')
    except Exception:
        db.rollback()
    finally:
        db.close()
    refresh_table(container, state)


def delete_cita(cita_id, container, state):
    def do_delete():
        db = get_db()
        try:
            db.query(Cita).filter_by(id=cita_id).delete()
            db.commit()
            theme.notify_success('Cita eliminada')
        except Exception:
            db.rollback()
        finally:
            db.close()
        refresh_table(container, state)
    
    theme.confirm_dialog('Eliminar Cita', '¿Eliminar esta cita?', on_confirm=do_delete)


def open_cita_dialog(table_container, state):
    db = get_db()
    try:
        clients = db.query(Cliente).all()
        client_options = {c.id: f'{c.nombre} {c.apellidos}'.strip() for c in clients}
    finally:
        db.close()
    
    with ui.dialog() as dialog, ui.card().classes('w-full max-w-lg bg-white p-0 border border-gray-200 shadow-xl'):
        # Header
        with ui.row().classes('w-full justify-between items-center p-4 border-b border-gray-200 bg-[#f5f5f9]'):
            ui.label('Nueva Cita').classes('text-xl font-bold text-gray-800')
            ui.button(icon='close', on_click=dialog.close).props('flat round color=grey-8 size=sm')
        
        with ui.column().classes('w-full p-6 gap-3'):
            cliente_select = ui.select(client_options, label='Cliente', with_input=True).props('outlined dense use-input bg-color=white').classes('w-full')
            vehiculo_input = ui.input('Placa del vehículo').props('outlined dense bg-color=white').classes('w-full')
            
            with ui.row().classes('w-full gap-4'):
                fecha_input = ui.input('Fecha *', value=datetime.now().strftime('%Y-%m-%d')).props('outlined dense bg-color=white type=date').classes('flex-1')
                hora_input = ui.input('Hora', value='09:00').props('outlined dense bg-color=white type=time').classes('flex-1')
            
            motivo_input = ui.textarea('Motivo de la cita').props('outlined dense rows=2 bg-color=white').classes('w-full')
            notas_input = ui.textarea('Notas adicionales').props('outlined dense rows=2 bg-color=white').classes('w-full')
        
        # Footer
        with ui.row().classes('w-full justify-end gap-3 p-4 border-t border-gray-200 bg-gray-50'):
            ui.button('Cancelar', on_click=dialog.close).props('flat color=grey-8')
            
            def guardar():
                if not fecha_input.value:
                    theme.notify_error('La fecha es obligatoria')
                    return

                db = get_db()
                try:
                    # Validar horario no ocupado
                    hora_val = hora_input.value.strip() if hora_input.value else ''
                    fecha_val = fecha_input.value.strip()
                    if hora_val:
                        ocupada = db.query(Cita).filter(
                            Cita.fecha_cita == fecha_val,
                            Cita.hora == hora_val,
                            Cita.estado.in_(['programada', 'confirmada'])
                        ).first()
                        if ocupada:
                            theme.notify_error(f'⚠ Horario ocupado: ya existe una cita el {fecha_val} a las {hora_val}. Elige otra hora.')
                            db.close()
                            return

                    cita = Cita(
                        cliente_id=cliente_select.value or None,
                        vehiculo_placa=vehiculo_input.value.strip() if vehiculo_input.value else '',
                        fecha_cita=fecha_val,
                        hora=hora_val,
                        motivo=motivo_input.value.strip() if motivo_input.value else '',
                        notas=notas_input.value.strip() if notas_input.value else '',
                        estado='programada',
                        vista_admin=1,  # El admin la ve al crearla él mismo
                    )
                    db.add(cita)
                    db.commit()
                    log_actividad(f'Cita creada para {fecha_val}', 'citas')
                    theme.notify_success('Cita programada exitosamente')
                except Exception as e:
                    db.rollback()
                    theme.notify_error(f'Error: {str(e)}')
                finally:
                    db.close()
                
                dialog.close()
                refresh_table(table_container, state)
            
            ui.button('Programar', icon='event', on_click=guardar).classes('btn-sandoval px-10')
    
    dialog.open()

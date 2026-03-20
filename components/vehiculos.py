"""
SANDOVAL Dashboard - Gestión de Vehículos
CRUD completo con SQLite
"""

from nicegui import ui
from utils.models import get_db, Vehiculo, Cliente, log_actividad
import theme

TIPOS_VEHICULO = ['Sedán', 'SUV', 'Camioneta', 'Hatchback', 'Coupé', 'Van', 'Camión', 'Moto', 'Otro']

def show_vehiculos(container):
    with container:
        state = {'search_query': ''}
        
        # Header Corporativo Minimalista
        with ui.row().classes('w-full items-center justify-between mb-4 fade-in py-5 px-8 bg-white border border-gray-100 rounded-xl shadow-sm'):
            with ui.row().classes('items-center gap-4'):
                ui.icon('directions_car', size='32px').classes('text-[#274495]')
                ui.label('GESTIÓN DE VEHÍCULOS').classes('text-xl font-extrabold text-[#274495] tracking-tight')
            with ui.row().classes('gap-3'):
                ui.button('EXCEL', icon='border_all', on_click=lambda: _export_excel(state)).classes('btn-sandoval bg-slate-100 !text-slate-700 shadow-none border border-slate-200 hover:bg-slate-200').props('unelevated')
                ui.button('Nuevo Vehículo', icon='add', on_click=lambda: open_vehicle_dialog(table_container, state)).classes('btn-sandoval')
        
        # Filter Bar White
        with ui.row().classes('w-full bg-white p-4 border-x border-b border-gray-200 rounded-b-lg mb-6 gap-4 items-center shadow-sm'):
            search_input = ui.input(placeholder='Buscar por placa, marca, modelo...').props('outlined dense clearable bg-color=white').classes('flex-1')
            def do_search():
                state['search_query'] = search_input.value or ''
                refresh_table(table_container, state)
            search_input.on('keydown.enter', lambda: do_search())
            ui.button('Buscar', icon='search', on_click=do_search).props('unelevated color=primary')
        
        table_container = ui.column().classes('w-full')
        refresh_table(table_container, state)

def refresh_table(container, state):
    container.clear()
    db = get_db()
    try:
        query = db.query(Vehiculo)
        if state.get('search_query'):
            q = f"%{state['search_query']}%"
            query = query.filter(
                (Vehiculo.placa.ilike(q)) | (Vehiculo.marca.ilike(q)) | (Vehiculo.modelo.ilike(q))
            )
        vehicles = query.all()
        clients = {c.id: c for c in db.query(Cliente).all()}
        
        with container:
            if not vehicles:
                with ui.card().classes('w-full bg-white border border-gray-200 p-8 text-center shadow-sm'):
                    ui.icon('directions_car', size='48px').classes('text-gray-400')
                    ui.label('No se encontraron vehículos').classes('text-gray-500 mt-2')
                return
            
            columns = [
                {'name': 'placa', 'label': 'Placa', 'field': 'placa', 'align': 'left', 'sortable': True},
                {'name': 'marca', 'label': 'Marca', 'field': 'marca', 'align': 'left', 'sortable': True},
                {'name': 'modelo', 'label': 'Modelo', 'field': 'modelo', 'align': 'left'},
                {'name': 'año', 'label': 'Año', 'field': 'año', 'align': 'center'},
                {'name': 'color', 'label': 'Color', 'field': 'color', 'align': 'center'},
                {'name': 'propietario', 'label': 'Propietario', 'field': 'propietario', 'align': 'left'},
            ]
            
            rows = []
            for v in vehicles:
                c = clients.get(v.cliente_id)
                rows.append({
                    'placa': v.placa, 'marca': v.marca, 'modelo': v.modelo,
                    'año': v.año, 'color': v.color,
                    'propietario': f"{c.nombre} {c.apellidos}".strip() if c else '-',
                })
            
            table = ui.table(columns=columns, rows=rows, row_key='placa').classes('w-full bg-white text-black')
            table.props('flat bordered dense rows-per-page-options="[10, 25, 50]" binary-state-sort')
            
            table.add_slot('body-cell-placa', r'''
                <q-td :props="props">
                    <div class="row items-center no-wrap">
                        <span class="q-mr-sm font-bold">{{ props.row.placa }}</span>
                        <q-btn flat dense icon="edit" color="primary" size="sm" @click="$parent.$emit('edit', props.row)" />
                        <q-btn flat dense icon="delete" color="red-6" size="sm" @click="$parent.$emit('delete', props.row)" />
                    </div>
                </q-td>
            ''')
            
            table.add_slot('body-cell-propietario', r'''
                <q-td :props="props">
                    <div class="row items-center no-wrap">
                        <span class="q-mr-sm">{{ props.row.propietario }}</span>
                        <q-btn flat dense icon="history" color="cyan-8" size="sm" @click="$parent.$emit('history', props.row)" />
                    </div>
                </q-td>
            ''')
            
            table.on('edit', lambda e: open_vehicle_dialog(container, state, (e.args['placa'] if isinstance(e.args, dict) else e.args[0]['placa'])))
            table.on('delete', lambda e: theme.confirm_dialog(
                'Eliminar', f'¿Eliminar vehículo {e.args["placa"] if isinstance(e.args, dict) else e.args[0]["placa"]}?',
                on_confirm=lambda p=(e.args['placa'] if isinstance(e.args, dict) else e.args[0]['placa']): (delete_vehicle(p), refresh_table(container, state))
            ))
            table.on('history', lambda e: show_vehicle_history((e.args['placa'] if isinstance(e.args, dict) else e.args[0]['placa'])))
    finally:
        db.close()

def _export_excel(state):
    """Exporta vehículos a Excel y lo descarga desde el navegador"""
    from utils.excel_tools import export_generic_excel
    from datetime import datetime
    import os
    db = get_db()
    try:
        query = db.query(Vehiculo)
        if state.get('search_query'):
            q = f"%{state['search_query']}%"
            query = query.filter(
                (Vehiculo.placa.ilike(q)) | (Vehiculo.marca.ilike(q)) | (Vehiculo.modelo.ilike(q))
            )
        vehicles = query.all()
        if not vehicles:
            theme.notify_warning('No hay datos para exportar')
            return
        
        # Generar archivo en carpeta exports
        os.makedirs('exports', exist_ok=True)
        filename = f"reporte_vehiculos_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        filepath = os.path.join('exports', filename)

        clients = {c.id: c for c in db.query(Cliente).all()}
            
        headers = ['Placa', 'Marca', 'Modelo', 'Año', 'Color', 'VIN', 'Propietario', 'ID Propietario']
        data = []
        for v in vehicles:
            c = clients.get(v.cliente_id)
            data.append([
                v.placa, v.marca, v.modelo, v.año, v.color, v.vin,
                f"{c.nombre} {c.apellidos}".strip() if c else '-',
                v.cliente_id or '-'
            ])
        
        export_generic_excel('REPORTE DE VEHÍCULOS', headers, data, 'reporte_vehiculos', filepath=filepath)
        
        # Descargar automáticamente desde el navegador
        ui.download(filepath, filename)
        theme.notify_success(f'Excel generado: {filename}')
        
    except Exception as e:
        theme.notify_error(f'Error al exportar: {e}')
    finally:
        db.close()

def delete_vehicle(placa):
    db = get_db()
    try:
        db.query(Vehiculo).filter_by(placa=placa).delete()
        db.commit()
        log_actividad(f'Vehículo eliminado: {placa}', 'vehiculos')
        theme.notify_success('Vehículo eliminado')
    except Exception as e:
        db.rollback()
        theme.notify_error(f'Error: {str(e)}')
    finally:
        db.close()

def open_vehicle_dialog(table_container, state, edit_placa=None, on_success=None):
    from utils.data_catalogs import VEHICULOS_DATA, get_marcas, get_modelos
    
    existing = None
    if edit_placa:
        db = get_db()
        try:
            v = db.query(Vehiculo).filter_by(placa=edit_placa).first()
            if v:
                existing = {'placa': v.placa, 'cliente_id': v.cliente_id, 'marca': v.marca,
                    'modelo': v.modelo, 'año': v.año, 'color': v.color, 'tipo': v.tipo,
                    'vin': v.vin, 'observaciones': v.observaciones}
        finally:
            db.close()
    
    db = get_db()
    try:
        client_opts = {c.id: f"{c.nombre} {c.apellidos}".strip() for c in db.query(Cliente).all()}
    finally:
        db.close()
    
    title = 'Nuevo Registro'
    
    with ui.dialog() as dialog, ui.card().classes('w-full max-w-3xl bg-white p-0 border border-gray-200 shadow-xl'):
        # Header
        with ui.row().classes('w-full justify-between items-center p-4 border-b border-gray-200 bg-[#f5f5f9]'):
            ui.label(title).classes('text-xl font-bold text-gray-800')
            ui.button(icon='close', on_click=dialog.close).props('flat round color=grey-8 size=sm')
            
        with ui.column().classes('w-full p-6 gap-4'):
            # El select de tipo ahora como input
            tipos = sorted(list(VEHICULOS_DATA.keys()))
            default_tipo = existing.get('tipo', 'Automóvil') if existing else 'Automóvil'
            tipo_sel = ui.select(tipos, value=default_tipo, label='Tipo').props('outlined dense prepend-icon=list options-dense bg-color=white').classes('w-full')
            
            # Marca (depende de tipo)
            default_marca = existing.get('marca', '') if existing else None
            marcas_opts = get_marcas(default_tipo)
            marca_sel = ui.select(marcas_opts, value=default_marca, with_input=True, label='Marca').props('outlined dense prepend-icon=list options-dense use-input new-value-mode="add-unique" bg-color=white').classes('w-full')
            
            # Modelo (depende de marca)
            default_modelo = existing.get('modelo', '') if existing else None
            modelos_opts = get_modelos(default_tipo, default_marca) if default_marca else []
            modelo_sel = ui.select(modelos_opts, value=default_modelo, with_input=True, label='Modelo').props('outlined dense prepend-icon=list options-dense use-input new-value-mode="add-unique" bg-color=white').classes('w-full')
            
            # Actualización en cascada
            def update_marcas():
                t = tipo_sel.value
                marca_sel.options = get_marcas(t)
                marca_sel.value = ''
                marca_sel.update()
                modelo_sel.options = []
                modelo_sel.value = ''
                modelo_sel.update()
                
            def update_modelos():
                t = tipo_sel.value
                m = marca_sel.value
                modelo_sel.options = get_modelos(t, m)
                modelo_sel.value = ''
                modelo_sel.update()
                
            tipo_sel.on('update:model-value', update_marcas)
            marca_sel.on('update:model-value', update_modelos)
            
            año_input = ui.input(value=existing.get('año', '') if existing else '').props('outlined dense prepend-icon=list placeholder="-AÑO-" bg-color=white').classes('w-full')
            
            placa_input = ui.input(value=existing['placa'] if existing else '').props('outlined dense prepend-icon=list placeholder="Placa del vehículo" bg-color=white' + (' readonly' if existing else '')).classes('w-full')
            
            color_input = ui.input(value=existing.get('color', '') if existing else '').props('outlined dense prepend-icon=list placeholder="Color del vehículo" bg-color=white').classes('w-full')
            
            vin_input = ui.input(value=existing.get('vin', '') if existing else '').props('outlined dense prepend-icon=list placeholder="Vin del vehículo" bg-color=white').classes('w-full')
            
            # Propietario (Select opcional si viene de la orden, pero útil)
            cliente_sel = ui.select(client_opts, value=existing.get('cliente_id', '') if existing else None, label='Propietario', with_input=True).props('outlined dense use-input prepend-icon=person bg-color=white').classes('w-full')
            
            with ui.row().classes('w-full gap-3'):
                resp_input = ui.input(value=existing.get('responsable', '') if existing else '', placeholder='Nombre del responsable').props('outlined dense prepend-icon=person_pin bg-color=white').classes('flex-1')
                tel_resp_input = ui.input(value=existing.get('tel_responsable', '') if existing else '', placeholder='Teléfono responsable').props('outlined dense prepend-icon=phone bg-color=white').classes('w-44')
            obs_input = ui.textarea(value=existing.get('observaciones', '') if existing else '').props('outlined dense prepend-icon=list rows=2 placeholder="Observaciones" bg-color=white').classes('w-full')

        # Footer Actions
        with ui.row().classes('w-full justify-end gap-3 p-4 border-t border-gray-200 bg-gray-50'):
            ui.button('SALIR', on_click=dialog.close).props('flat color=grey-8')
            
            def guardar():
                if not placa_input.value:
                    theme.notify_error('La placa es obligatoria')
                    return
                db = get_db()
                try:
                    if existing:
                        v = db.query(Vehiculo).filter_by(placa=edit_placa).first()
                        if v:
                            v.cliente_id = cliente_sel.value or None
                            v.marca = (marca_sel.value or '').strip()
                            v.modelo = (modelo_sel.value or '').strip()
                            v.año = (año_input.value or '').strip()
                            v.color = (color_input.value or '').strip()
                            v.tipo = tipo_sel.value
                            v.vin = (vin_input.value or '').strip()
                            v.observaciones = (obs_input.value or '').strip()
                            db.commit()
                            log_actividad(f'Vehículo editado: {v.placa}', 'vehiculos')
                            saved_vehicle = v
                    else:
                        if db.query(Vehiculo).filter_by(placa=placa_input.value.strip().upper()).first():
                            theme.notify_error('Ya existe un vehículo con esa placa')
                            return
                        new_v = Vehiculo(
                            placa=placa_input.value.strip().upper(), cliente_id=cliente_sel.value or None,
                            marca=(marca_sel.value or '').strip(), modelo=(modelo_sel.value or '').strip(),
                            año=(año_input.value or '').strip(), color=(color_input.value or '').strip(),
                            tipo=tipo_sel.value, vin=(vin_input.value or '').strip(),
                            responsable=(resp_input.value or '').strip(),
                            tel_responsable=(tel_resp_input.value or '').strip(),
                            observaciones=(obs_input.value or '').strip()
                        )
                        db.add(new_v)
                        db.commit()
                        log_actividad(f'Vehículo creado: {new_v.placa}', 'vehiculos')
                        saved_vehicle = new_v
                    
                    theme.notify_success('Registro guardado')
                    dialog.close()
                    if table_container and state:
                        refresh_table(table_container, state)
                        
                    if on_success and saved_vehicle:
                        on_success(saved_vehicle.placa)
                except Exception as e:
                    db.rollback()
                    theme.notify_error(f'Error: {str(e)}')
                finally:
                    db.close()
            
            ui.button('GUARDAR', on_click=guardar).classes('btn-sandoval px-10')
    dialog.open()


def show_vehicle_history(placa):
    """Muestra historial de servicios del vehículo"""
    from utils.models import Orden
    
    db = get_db()
    try:
        vehicle = db.query(Vehiculo).filter_by(placa=placa).first()
        orders = db.query(Orden).filter_by(vehiculo_placa=placa).order_by(Orden.fecha.desc()).all()
        client = db.query(Cliente).filter_by(id=vehicle.cliente_id).first() if vehicle and vehicle.cliente_id else None
        
        with ui.dialog() as dialog, ui.card().classes('w-full max-w-3xl bg-white p-0 border border-gray-200 shadow-xl'):
            with ui.row().classes('w-full items-center justify-between p-4 border-b border-gray-200 bg-[#f5f5f9]'):
                with ui.row().classes('items-center gap-3'):
                    ui.icon('history', size='28px').classes('text-blue-600')
                    ui.label(f'Historial de Servicios - {placa}').classes('text-xl font-bold text-gray-800')
                ui.button(icon='close', on_click=dialog.close).props('flat round color=grey-8 size=sm')
            
            with ui.column().classes('p-6 w-full'):
                if vehicle:
                    with ui.row().classes('w-full gap-4 mb-4'):
                        with ui.card().classes('flex-1 bg-gray-50 border border-gray-200 p-3 shadow-sm'):
                            ui.label(f'{vehicle.marca} {vehicle.modelo} {vehicle.año}').classes('text-gray-800 font-bold')
                            ui.label(f'Color: {vehicle.color} | VIN: {vehicle.vin or "-"}').classes('text-gray-600 text-sm')
                            if client:
                                ui.label(f'Propietario: {client.nombre} {client.apellidos}'.strip()).classes('text-gray-600 text-sm')
                        with ui.card().classes('bg-gray-50 border border-gray-200 p-3 shadow-sm'):
                            ui.label(str(len(orders))).classes('text-3xl font-bold text-blue-600')
                            ui.label('servicios').classes('text-gray-500 text-xs')
                
                if orders:
                    with ui.scroll_area().classes('w-full').style('max-height: 400px'):
                        for o in orders:
                            import theme as th
                            cfg = th.ESTADOS_CONFIG.get(o.estado, {'icon': 'build', 'color': 'grey-6'})
                            total = sum(float(i.get('total', 0)) for i in (o.items_cotizacion or []))
                            
                            with ui.card().classes('w-full bg-white border border-gray-200 p-4 mb-2 hover:border-blue-400 transition-colors shadow-sm'):
                                with ui.row().classes('w-full items-center justify-between'):
                                    with ui.row().classes('items-center gap-3'):
                                        ui.icon(cfg['icon'], size='20px').classes(f'text-{cfg["color"]}')
                                        with ui.column().classes('gap-0'):
                                            with ui.row().classes('items-center gap-2'):
                                                ui.label(o.consecutivo).classes('text-gray-800 font-bold')
                                                ui.badge(o.estado, color=cfg['color'])
                                            ui.label(o.motivo[:80] if o.motivo else '').classes('text-gray-600 text-sm')
                                            ui.label(f'{o.fecha} | Téc: {o.tecnico or "N/A"} | KM: {o.km or "-"}').classes('text-gray-500 text-xs')
                                    if total > 0:
                                        ui.label(f'S/ {total:.2f}').classes('text-green-600 font-bold')
                else:
                    with ui.column().classes('w-full items-center py-8'):
                        ui.icon('build', size='48px').classes('text-gray-300')
                        ui.label('Sin historial de servicios').classes('text-gray-400')
        
        dialog.open()
    finally:
        db.close()

"""
SANDOVAL Dashboard - Gestión de Clientes
CRUD completo con SQLite
"""

from nicegui import ui
from utils.models import get_db, Cliente, log_actividad, hash_password
from datetime import datetime
import theme

def show_clientes(container):
    with container:
        state = {'filter_tipo': 'Todos', 'search_query': ''}
        
        # Header Corporativo Minimalista
        with ui.row().classes('w-full items-center justify-between mb-4 fade-in py-5 px-8 bg-white border border-gray-100 rounded-xl shadow-sm'):
            with ui.row().classes('items-center gap-4'):
                ui.icon('people', size='32px').classes('text-[#274495]')
                ui.label('GESTIÓN DE CLIENTES').classes('text-xl font-extrabold text-[#274495] tracking-tight')
            with ui.row().classes('gap-3'):
                ui.button('EXCEL', icon='border_all', on_click=lambda: _export_excel(state)).classes('btn-sandoval bg-slate-100 !text-slate-700 shadow-none border border-slate-200 hover:bg-slate-200').props('unelevated')
                ui.button('Nuevo Cliente', icon='person_add', on_click=lambda: open_client_dialog(table_container, state)).classes('btn-sandoval')
        
        # Filter Bar White
        with ui.row().classes('w-full bg-white p-4 border-x border-b border-gray-200 rounded-b-lg mb-6 gap-4 items-center shadow-sm'):
            search_input = ui.input(placeholder='Buscar por nombre, DNI/RUC, email...').props('outlined dense clearable bg-color=white').classes('flex-1')
            tipo_select = ui.select(['Todos', 'Persona', 'Empresa'], value='Todos', label='Tipo').props('outlined dense bg-color=white').classes('w-40')
            
            def do_search():
                state['search_query'] = search_input.value or ''
                state['filter_tipo'] = tipo_select.value
                refresh_table(table_container, state)
            
            search_input.on('keydown.enter', lambda: do_search())
            tipo_select.on('update:model-value', lambda: do_search())
            ui.button('Buscar', icon='search', on_click=do_search).props('unelevated color=primary')
        
        db = get_db()
        try:
            total = db.query(Cliente).count()
            personas = db.query(Cliente).filter(Cliente.tipo.ilike('persona')).count()
            empresas = db.query(Cliente).filter(Cliente.tipo.ilike('empresa')).count()
        finally:
            db.close()
        
        with ui.row().classes('w-full gap-4 mb-6'):
            _stat('TOTAL CLIENTES', str(total), 'groups', 'blue-8')
            _stat('PERSONAS', str(personas), 'person', 'green-7')
            _stat('EMPRESAS', str(empresas), 'business', 'purple-7')
        
        table_container = ui.column().classes('w-full')
        refresh_table(table_container, state)

def _stat(title, value, icon, color):
    # Stats White Style
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
        query = db.query(Cliente)
        if state.get('filter_tipo') and state['filter_tipo'] != 'Todos':
            query = query.filter(Cliente.tipo.ilike(state['filter_tipo']))
        if state.get('search_query'):
            q = f"%{state['search_query']}%"
            query = query.filter(
                (Cliente.nombre.ilike(q)) | (Cliente.id.ilike(q)) |
                (Cliente.email.ilike(q)) | (Cliente.telefono.ilike(q)) |
                (Cliente.apellidos.ilike(q))
            )
        clients = query.all()
        
        with container:
            if not clients:
                with ui.card().classes('w-full bg-[#1c2025] border border-[#333] p-8 text-center'):
                    ui.icon('person_off', size='48px').classes('text-gray-500')
                    ui.label('No se encontraron clientes').classes('text-gray-400 mt-2')
                return
            
            columns = [
                {'name': 'id', 'label': 'DNI/RUC', 'field': 'id', 'align': 'left', 'sortable': True},
                {'name': 'nombre', 'label': 'Nombre', 'field': 'nombre', 'align': 'left', 'sortable': True},
                {'name': 'email', 'label': 'Email', 'field': 'email', 'align': 'left'},
                {'name': 'telefono', 'label': 'Teléfono', 'field': 'telefono', 'align': 'center'},
                {'name': 'ciudad', 'label': 'Ciudad', 'field': 'ciudad', 'align': 'center'},
                {'name': 'tipo', 'label': 'Tipo', 'field': 'tipo', 'align': 'center'},
            ]
            
            rows = [{'id': c.id, 'nombre': f"{c.nombre} {c.apellidos}".strip(), 'email': c.email, 'telefono': c.telefono, 'ciudad': c.ciudad, 'tipo': c.tipo} for c in clients]
            
            table = ui.table(columns=columns, rows=rows, row_key='id').classes('w-full bg-white text-black')
            table.props('flat bordered dense rows-per-page-options="[10, 25, 50]" binary-state-sort')
            
            table.add_slot('body-cell-tipo', '''
                <q-td :props="props">
                    <q-badge :color="props.row.tipo === 'Empresa' ? 'purple-6' : 'green-6'" :label="props.row.tipo" outline class="font-bold" />
                </q-td>
            ''')
            table.add_slot('body-cell-id', r'''
                <q-td :props="props">
                    <div class="row items-center no-wrap">
                        <span class="q-mr-sm text-bold">{{ props.row.id }}</span>
                        <q-btn flat dense icon="edit" color="primary" size="sm" @click="$parent.$emit('edit', props.row)" />
                        <q-btn flat dense icon="pin" color="teal-7" size="sm" @click="$parent.$emit('pin', props.row)" title="Gestionar PIN portal cliente" />
                        <q-btn flat dense icon="delete" color="red-6" size="sm" @click="$parent.$emit('delete', props.row)" />
                    </div>
                </q-td>
            ''')

            table.on('edit', lambda e: open_client_dialog(container, state, e.args['id']))
            table.on('pin',  lambda e: open_pin_dialog(e.args['id'], e.args['nombre']))
            table.on('delete', lambda e: theme.confirm_dialog(
                'Eliminar Cliente', f'¿Eliminar al cliente {e.args["nombre"]}?',
                on_confirm=lambda cid=e.args['id']: (delete_client(cid), refresh_table(container, state))
            ))
    finally:
        db.close()

def _export_excel(state):
    """Exporta clientes a Excel y lo descarga desde el navegador"""
    from utils.excel_tools import export_generic_excel
    import os
    
    db = get_db()
    try:
        query = db.query(Cliente)
        if state.get('filter_tipo') and state['filter_tipo'] != 'Todos':
            query = query.filter(Cliente.tipo.ilike(state['filter_tipo']))
        if state.get('search_query'):
            q = f"%{state['search_query']}%"
            query = query.filter(
                (Cliente.nombre.ilike(q)) | (Cliente.id.ilike(q)) |
                (Cliente.email.ilike(q)) | (Cliente.telefono.ilike(q)) |
                (Cliente.apellidos.ilike(q))
            )
        clients = query.all()
        if not clients:
            theme.notify_warning('No hay datos para exportar')
            return
        
        # Generar archivo en carpeta exports
        os.makedirs('exports', exist_ok=True)
        filename = f"reporte_clientes_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        filepath = os.path.join('exports', filename)
        
        headers = ['DNI/RUC', 'Nombre', 'Apellidos', 'Email', 'Teléfono', 'Ciudad', 'Dirección', 'Tipo']
        data = [[c.id, c.nombre, c.apellidos, c.email, c.telefono, c.ciudad, c.direccion, c.tipo] for c in clients]
        
        export_generic_excel('REPORTE DE CLIENTES', headers, data, 'reporte_clientes', filepath=filepath)
        
        # Descargar automáticamente desde el navegador
        ui.download(filepath, filename)
        theme.notify_success(f'Excel generado: {filename}')
        
    except Exception as e:
        theme.notify_error(f'Error al exportar: {e}')
    finally:
        db.close()

def delete_client(client_id):
    db = get_db()
    try:
        db.query(Cliente).filter_by(id=client_id).delete()
        db.commit()
        log_actividad(f'Cliente eliminado: {client_id}', 'clientes')
        theme.notify_success('Cliente eliminado')
    except Exception as e:
        db.rollback()
        theme.notify_error(f'Error: {str(e)}')
    finally:
        db.close()

def open_client_dialog(table_container, state, edit_id=None, on_success=None):
    from utils.data_catalogs import UBIGEO_PERU
    
    existing = None
    if edit_id:
        db = get_db()
        try:
            c = db.query(Cliente).filter_by(id=edit_id).first()
            if c:
                existing = {'id': c.id, 'nombre': c.nombre, 'apellidos': c.apellidos, 'email': c.email,
                    'telefono': c.telefono, 'direccion': c.direccion, 'ciudad': c.ciudad, 'pais': c.pais,
                    'tipo': c.tipo, 'observaciones': c.observaciones}
        finally:
            db.close()
    
    title = 'Nuevo Registro'
    
    with ui.dialog() as dialog, ui.card().classes('w-full max-w-4xl bg-white p-0 border border-gray-200 shadow-xl'):
        # Header
        with ui.row().classes('w-full justify-between items-center p-4 border-b border-gray-200'):
            ui.label(title).classes('text-xl font-bold text-gray-800')
            ui.button(icon='close', on_click=dialog.close).props('flat round color=grey-8')
            
        with ui.column().classes('w-full p-6 gap-6'):
            # Form
            with ui.row().classes('w-full gap-6'):
                # Columna Izquierda
                with ui.column().classes('flex-1 gap-4'):
                    ui.label('Tipo de persona').classes('text-gray-600 text-xs mb-[-5px]')
                    tipo = ui.select(['Persona', 'Empresa'], value=existing.get('tipo', 'Persona') if existing else 'Persona').props('outlined dense options-dense bg-color=white').classes('w-full')
                    
                    lbl_id = ui.label('Número de identificación (DNI)').classes('text-gray-600 text-xs mb-[-5px]')
                    id_input = ui.input(value=existing['id'] if existing else '').props('outlined dense placeholder="# Documento" bg-color=white' + (' readonly' if existing else '')).classes('w-full')
                    
                    def toggle_id_label():
                        lbl_id.text = 'RUC' if tipo.value == 'Empresa' else 'Número de identificación (DNI)'
                    
                    tipo.on('update:model-value', toggle_id_label)
                    toggle_id_label() # Init
                    
                    ui.label('Nombres').classes('text-gray-600 text-xs mb-[-5px]')
                    nombre_input = ui.input(value=existing.get('nombre', '') if existing else '').props('outlined dense placeholder="Nombre del cliente" bg-color=white').classes('w-full')
                    
                    ui.label('Apellidos').classes('text-gray-600 text-xs mb-[-5px]')
                    apellidos_input = ui.input(value=existing.get('apellidos', '') if existing else '').props('outlined dense placeholder="Apellido del cliente" bg-color=white').classes('w-full')
                    
                    ui.label('País').classes('text-gray-600 text-xs mb-[-5px]')
                    pais_input = ui.select(['PERÚ (+51)', 'CHILE (+56)', 'ECUADOR (+593)', 'COLOMBIA (+57)', 'OTRO'], value=existing.get('pais', 'PERÚ (+51)') if existing else 'PERÚ (+51)').props('outlined dense options-dense bg-color=white').classes('w-full')

                # Columna Derecha
                with ui.column().classes('flex-1 gap-4'):
                    dep_opts = sorted(list(UBIGEO_PERU.keys()))
                    # Intentar adivinar departamento si existe ciudad, o default None
                    default_dep = None
                    default_city = existing.get('ciudad', '') if existing else None
                    
                    # Lógica simple para pre-seleccionar departamento si la ciudad coincide
                    if default_city:
                        for d, cities in UBIGEO_PERU.items():
                            if default_city in cities:
                                default_dep = d
                                break
                    
                    ui.label('Departamento/Estado/Provincia').classes('text-gray-600 text-xs mb-[-5px]')
                    dep_sel = ui.select(dep_opts, value=default_dep, with_input=True).props('outlined dense placeholder="-DEP/EST/PROV-" bg-color=white').classes('w-full')

                    ui.label('Ciudad').classes('text-gray-600 text-xs mb-[-5px]')
                    ciudad_initial_opts = sorted(UBIGEO_PERU[default_dep]) if default_dep else []
                    ciudad_sel = ui.select(ciudad_initial_opts, value=default_city, with_input=True).props('outlined dense placeholder="-SELECCIONA-" bg-color=white').classes('w-full')
                    
                    def update_cities():
                        d = dep_sel.value
                        if d and d in UBIGEO_PERU:
                            ciudad_sel.options = sorted(UBIGEO_PERU[d])
                            ciudad_sel.value = ''
                            ciudad_sel.update()
                        else:
                            ciudad_sel.options = []
                            ciudad_sel.update()
                            
                    dep_sel.on('update:model-value', update_cities)
                    # Inicializar ciudades si hay departamento
                    if default_dep:
                        ciudad_sel.options = sorted(UBIGEO_PERU[default_dep])

                    ui.label('Dirección').classes('text-gray-600 text-xs mb-[-5px]')
                    direccion_input = ui.input(value=existing.get('direccion', '') if existing else '').props('outlined dense placeholder="Dirección de residencia" bg-color=white').classes('w-full')

                    ui.label('Email').classes('text-gray-600 text-xs mb-[-5px]')
                    email_input = ui.input(value=existing.get('email', '') if existing else '').props('outlined dense placeholder="Email" type=email bg-color=white').classes('w-full')

                    ui.label('Móvil (Sin indicativo)').classes('text-gray-600 text-xs mb-[-5px]')
                    with ui.row().classes('w-full gap-0 no-wrap'):
                        ui.input(value='+51').props('outlined dense readonly bg-color=grey-3').classes('w-16')
                        telefono_input = ui.input(value=existing.get('telefono', '') if existing else '').props('outlined dense placeholder="Celular (Sin indicativo)" bg-color=white').classes('flex-1')
                    
                    ui.label('Observaciones').classes('text-gray-600 text-xs mb-[-5px]')
                    observaciones_input = ui.textarea(value=existing.get('observaciones', '') if existing else '').props('outlined dense rows=2 placeholder="Observaciones" bg-color=white').classes('w-full')

        # Footer Actions
        with ui.row().classes('w-full justify-end gap-3 p-4 border-t border-gray-200'):
            ui.button('SALIR', on_click=dialog.close).props('unelevated color=purple-6 text-color=white').classes('px-6 font-bold')
            
            def guardar():
                if not id_input.value or not nombre_input.value:
                    theme.notify_error('ID y Nombre son obligatorios')
                    return
                
                db = get_db()
                try:
                    if existing:
                        c = db.query(Cliente).filter_by(id=edit_id).first()
                        if c:
                            c.nombre = nombre_input.value.strip()
                            c.apellidos = (apellidos_input.value or '').strip()
                            c.email = (email_input.value or '').strip()
                            c.telefono = (telefono_input.value or '').strip()
                            c.direccion = (direccion_input.value or '').strip()
                            # Unificamos input de ciudad
                            c.ciudad = (ciudad_sel.value or '').strip()
                            c.pais = pais_input.value
                            c.tipo = tipo.value
                            c.observaciones = (observaciones_input.value or '').strip()
                            db.commit()
                            log_actividad(f'Cliente editado: {c.nombre}', 'clientes')
                            saved_client = c
                    else:
                        if db.query(Cliente).filter_by(id=id_input.value.strip()).first():
                            theme.notify_error('Ya existe un cliente con ese ID')
                            return
                        new_c = Cliente(
                            id=id_input.value.strip(), nombre=nombre_input.value.strip(),
                            apellidos=(apellidos_input.value or '').strip(), email=(email_input.value or '').strip(),
                            telefono=(telefono_input.value or '').strip(), direccion=(direccion_input.value or '').strip(),
                            ciudad=(ciudad_sel.value or '').strip(), pais=pais_input.value,
                            tipo=tipo.value, observaciones=(observaciones_input.value or '').strip(),
                            fecha_registro=datetime.now()
                        )
                        db.add(new_c)
                        db.commit()
                        log_actividad(f'Cliente creado: {new_c.nombre}', 'clientes')
                        saved_client = new_c
                    
                    theme.notify_success('Registro guardado')
                    dialog.close()
                    if table_container and state:
                        refresh_table(table_container, state)
                    
                    if on_success and saved_client:
                        on_success(saved_client.id)
                        
                except Exception as e:
                    db.rollback()
                    theme.notify_error(f'Error: {str(e)}')
                finally:
                    db.close()
            
            ui.button('GUARDAR', on_click=guardar).classes('btn-sandoval px-10')
    dialog.open()


def open_pin_dialog(client_id: str, client_nombre: str):
    """
    Diálogo para asignar o cambiar el PIN de acceso al portal del cliente.
    Ideal para clientes corporativos (ej. Caja Piura) donde el PIN es por
    cliente/empresa, no por vehículo individual.
    """
    db = get_db()
    try:
        c = db.query(Cliente).filter_by(id=client_id).first()
        tiene_pin = bool(c and c.pin_acceso)
    finally:
        db.close()

    with ui.dialog() as dialog, ui.card().classes('w-full max-w-sm bg-white p-0 border border-gray-200 shadow-xl'):
        # Header
        with ui.row().classes('w-full justify-between items-center p-4 border-b border-gray-100 bg-teal-50'):
            with ui.row().classes('items-center gap-2'):
                ui.icon('pin', size='24px').classes('text-teal-700')
                with ui.column().classes('gap-0'):
                    ui.label('PIN Portal Cliente').classes('text-base font-bold text-teal-800')
                    ui.label(f'{client_nombre} · {client_id}').classes('text-xs text-teal-600')
            ui.button(icon='close', on_click=dialog.close).props('flat round dense color=grey-7')

        with ui.column().classes('w-full p-6 gap-4'):
            if tiene_pin:
                with ui.row().classes('items-center gap-2 bg-green-50 border border-green-200 p-3 rounded-lg'):
                    ui.icon('check_circle', size='18px').classes('text-green-600')
                    ui.label('Este cliente ya tiene PIN configurado').classes('text-sm text-green-700 font-medium')
            else:
                with ui.row().classes('items-center gap-2 bg-amber-50 border border-amber-200 p-3 rounded-lg'):
                    ui.icon('warning_amber', size='18px').classes('text-amber-600')
                    ui.label('Sin PIN — usa DNI/RUC como fallback temporal').classes('text-sm text-amber-700 font-medium')

            ui.label('Nuevo PIN (4 a 8 caracteres)').classes('text-xs font-bold text-gray-500 uppercase tracking-wide')
            pin_inp = ui.input(
                placeholder='Ej: 1234  o  MOTO25',
                password=True,
                password_toggle_button=True
            ).props('outlined dense').classes('w-full')

            ui.label('Confirmar PIN').classes('text-xs font-bold text-gray-500 uppercase tracking-wide')
            pin_conf = ui.input(
                placeholder='Repita el PIN',
                password=True,
                password_toggle_button=True
            ).props('outlined dense').classes('w-full')

            ui.label(
                '💡 Tip Caja Piura: Use el mismo PIN para todos los motivos del mismo cliente, '
                'independientemente de la placa asignada.'
            ).classes('text-[10px] text-gray-400 leading-relaxed')

        with ui.row().classes('w-full justify-between gap-3 p-4 border-t border-gray-100'):
            ui.button('Cancelar', on_click=dialog.close).props('flat color=grey-7')

            def guardar_pin():
                p1 = (pin_inp.value or '').strip()
                p2 = (pin_conf.value or '').strip()
                if len(p1) < 4:
                    ui.notify('El PIN debe tener al menos 4 caracteres', type='warning', position='top')
                    return
                if p1 != p2:
                    ui.notify('Los PINs no coinciden', type='negative', position='top')
                    return
                db2 = get_db()
                try:
                    cli = db2.query(Cliente).filter_by(id=client_id).first()
                    if cli:
                        cli.pin_acceso = hash_password(p1)
                        db2.commit()
                        log_actividad(f'PIN portal actualizado para cliente {client_id}', 'clientes')
                        ui.notify(f'✅ PIN actualizado para {client_nombre}', type='positive', position='top')
                        dialog.close()
                    else:
                        ui.notify('Cliente no encontrado', type='negative')
                except Exception as ex:
                    db2.rollback()
                    ui.notify(f'Error: {ex}', type='negative')
                finally:
                    db2.close()

            ui.button('Guardar PIN', icon='save', on_click=guardar_pin).props('unelevated color=teal-7').classes('font-bold px-6')

    dialog.open()


def _import_dialog(tipo, table_container, state):
    """Diálogo para importar desde Excel"""
    with ui.dialog() as dialog, ui.card().classes('w-full max-w-md bg-white p-6 border border-gray-200 shadow-xl'):
        ui.label('Importar desde Excel').classes('text-2xl font-bold text-gray-800 mb-4')
        ui.label('Sube un archivo .xlsx con las columnas: DNI/RUC, Nombre, Apellidos, Email, Teléfono, Dirección, Ciudad, Tipo').classes('text-gray-600 text-sm mb-4')
        
        result_label = ui.label('').classes('text-gray-800 font-bold')
        
        async def handle_upload(e):
            try:
                content = e.content.read()
                from utils.excel_tools import import_clientes_excel
                count, errors = import_clientes_excel(content)
                result_label.text = f'✅ {count} clientes importados'
                if errors:
                    result_label.text += f' ({len(errors)} errores)'
                theme.notify_success(f'{count} clientes importados')
                refresh_table(table_container, state)
            except Exception as ex:
                result_label.text = f'❌ Error: {str(ex)}'
                theme.notify_error(f'Error: {str(ex)}')
        
        ui.upload(on_upload=handle_upload, auto_upload=True, label='Seleccionar archivo Excel').props(
            'accept=.xlsx,.xls color=lime-13 text-color=black'
        ).classes('w-full')
        
        ui.button('Cerrar', on_click=dialog.close).props('flat color=grey-8').classes('mt-4')
    dialog.open()

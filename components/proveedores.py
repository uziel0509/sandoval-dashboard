"""
SANDOVAL Dashboard - Gestión de Proveedores
CRUD completo con SQLite
"""

from nicegui import ui
from utils.models import get_db, Proveedor, log_actividad
import theme

def show_proveedores(container):
    with container:
        state = {'search_query': ''}
        
        # Header Corporativo Minimalista
        with ui.row().classes('w-full items-center justify-between mb-4 fade-in py-5 px-8 bg-white border border-gray-100 rounded-xl shadow-sm'):
            with ui.row().classes('items-center gap-4'):
                ui.icon('store', size='32px').classes('text-[#274495]')
                ui.label('GESTIÓN DE PROVEEDORES').classes('text-xl font-extrabold text-[#274495] tracking-tight')
            with ui.row().classes('gap-3'):
                ui.button('EXCEL', icon='border_all', on_click=lambda: _export_excel(state)).classes('btn-sandoval bg-slate-100 !text-slate-700 shadow-none border border-slate-200 hover:bg-slate-200').props('unelevated')
                ui.button('Nuevo Proveedor', icon='add_business', on_click=lambda: open_provider_dialog(table_container, state)).classes('btn-sandoval')
        
        # Filter Bar White
        with ui.row().classes('w-full bg-white p-4 border-x border-b border-gray-200 rounded-b-lg mb-6 gap-4 items-center shadow-sm'):
            search_input = ui.input(placeholder='Buscar proveedor...').props('outlined dense clearable bg-color=white').classes('flex-1')
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
        query = db.query(Proveedor)
        if state.get('search_query'):
            q = f"%{state['search_query']}%"
            query = query.filter((Proveedor.nombre.ilike(q)) | (Proveedor.id.ilike(q)) | (Proveedor.productos.ilike(q)))
        providers = query.all()
        
        with container:
            if not providers:
                with ui.card().classes('w-full bg-white border border-gray-200 p-8 text-center shadow-sm'):
                    ui.icon('store_mall_directory', size='48px').classes('text-gray-400')
                    ui.label('No se encontraron proveedores').classes('text-gray-500 mt-2')
                return
            
            columns = [
                {'name': 'id', 'label': 'RUC/DNI', 'field': 'id', 'align': 'left', 'sortable': True},
                {'name': 'nombre', 'label': 'Nombre', 'field': 'nombre', 'align': 'left', 'sortable': True},
                {'name': 'email', 'label': 'Email', 'field': 'email', 'align': 'left'},
                {'name': 'telefono', 'label': 'Teléfono', 'field': 'telefono', 'align': 'center'},
                {'name': 'productos', 'label': 'Productos', 'field': 'productos', 'align': 'left'},
            ]
            rows = [{'id': p.id, 'nombre': p.nombre, 'email': p.email, 'telefono': p.telefono, 'productos': p.productos} for p in providers]
            
            table = ui.table(columns=columns, rows=rows, row_key='id').classes('w-full bg-white text-black')
            table.props('flat bordered dense rows-per-page-options="[10, 25, 50]" binary-state-sort')
            
            table.add_slot('body-cell-id', r'''
                <q-td :props="props">
                    <div class="row items-center no-wrap">
                        <span class="q-mr-sm text-bold">{{ props.row.id }}</span>
                        <q-btn flat dense icon="edit" color="primary" size="sm" @click="$parent.$emit('edit', props.row)" />
                        <q-btn flat dense icon="delete" color="red-6" size="sm" @click="$parent.$emit('delete', props.row)" />
                    </div>
                </q-td>
            ''')
            table.on('edit', lambda e: open_provider_dialog(container, state, e.args['id']))
            table.on('delete', lambda e: theme.confirm_dialog('Eliminar', f'¿Eliminar proveedor {e.args["nombre"]}?',
                on_confirm=lambda pid=e.args['id']: (delete_provider(pid), refresh_table(container, state))))
    finally:
        db.close()

def _export_excel(state):
    """Exporta proveedores a Excel y lo descarga desde el navegador"""
    from utils.excel_tools import export_generic_excel
    from datetime import datetime
    import os
    db = get_db()
    try:
        query = db.query(Proveedor)
        if state.get('search_query'):
            q = f"%{state['search_query']}%"
            query = query.filter((Proveedor.nombre.ilike(q)) | (Proveedor.id.ilike(q)) | (Proveedor.productos.ilike(q)))
        providers = query.all()
        if not providers:
            theme.notify_warning('No hay datos para exportar')
            return
        
        # Generar archivo en carpeta exports
        os.makedirs('exports', exist_ok=True)
        filename = f"reporte_proveedores_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        filepath = os.path.join('exports', filename)

        headers = ['RUC/DNI', 'Nombre', 'Email', 'Teléfono', 'Productos', 'Dirección', 'Ciudad', 'Tipo']
        data = [[p.id, p.nombre, p.email, p.telefono, p.productos, p.direccion, p.ciudad, p.tipo] for p in providers]
        
        export_generic_excel('REPORTE DE PROVEEDORES', headers, data, 'reporte_proveedores', filepath=filepath)
        
        # Descargar automáticamente desde el navegador
        ui.download(filepath, filename)
        theme.notify_success(f'Excel generado: {filename}')
        
    except Exception as e:
        theme.notify_error(f'Error al exportar: {e}')
    finally:
        db.close()

def delete_provider(pid):
    db = get_db()
    try:
        db.query(Proveedor).filter_by(id=pid).delete()
        db.commit()
        log_actividad(f'Proveedor eliminado: {pid}', 'proveedores')
        theme.notify_success('Eliminado')
    except Exception:
        db.rollback()
    finally:
        db.close()

def open_provider_dialog(table_container, state, edit_id=None):
    existing = None
    if edit_id:
        db = get_db()
        try:
            p = db.query(Proveedor).filter_by(id=edit_id).first()
            if p:
                existing = {'id': p.id, 'nombre': p.nombre, 'email': p.email, 'telefono': p.telefono,
                    'direccion': p.direccion, 'ciudad': p.ciudad, 'productos': p.productos, 'tipo': p.tipo}
        finally:
            db.close()
    
    title = 'Editar Proveedor' if existing else 'Nuevo Proveedor'
    
    with ui.dialog() as dialog, ui.card().classes('w-full max-w-lg bg-white p-0 border border-gray-200 shadow-xl'):
        # Header
        with ui.row().classes('w-full justify-between items-center p-4 border-b border-gray-200 bg-[#f5f5f9]'):
            ui.label(title).classes('text-xl font-bold text-gray-800')
            ui.button(icon='close', on_click=dialog.close).props('flat round color=grey-8 size=sm')

        with ui.column().classes('w-full p-6 gap-4'):
             tipo = ui.toggle(['Persona', 'Empresa'], value=existing.get('tipo', 'Empresa') if existing else 'Empresa').props('color=indigo-9').classes('mb-2')
             
             with ui.column().classes('w-full gap-3'):
                id_input = ui.input('RUC/DNI *', value=existing['id'] if existing else '').props('outlined dense bg-color=white' + (' readonly' if existing else '')).classes('w-full')
                nombre_input = ui.input('Nombre *', value=existing.get('nombre', '') if existing else '').props('outlined dense bg-color=white').classes('w-full')
                with ui.row().classes('w-full gap-4'):
                    email_input = ui.input('Email', value=existing.get('email', '') if existing else '').props('outlined dense type=email bg-color=white').classes('flex-1')
                    telefono_input = ui.input('Teléfono', value=existing.get('telefono', '') if existing else '').props('outlined dense bg-color=white').classes('flex-1')
                direccion_input = ui.input('Dirección', value=existing.get('direccion', '') if existing else '').props('outlined dense bg-color=white').classes('w-full')
                ciudad_input = ui.input('Ciudad', value=existing.get('ciudad', '') if existing else '').props('outlined dense bg-color=white').classes('w-full')
                productos_input = ui.textarea('Productos', value=existing.get('productos', '') if existing else '').props('outlined dense rows=2 bg-color=white').classes('w-full')
        
        # Footer
        with ui.row().classes('w-full justify-end gap-3 p-4 border-t border-gray-200 bg-gray-50'):
            ui.button('Cancelar', on_click=dialog.close).props('flat color=grey-8')
            
            def guardar():
                if not id_input.value or not nombre_input.value:
                    theme.notify_error('RUC/DNI y Nombre son obligatorios')
                    return
                db = get_db()
                try:
                    if existing:
                        p = db.query(Proveedor).filter_by(id=edit_id).first()
                        if p:
                            p.nombre = nombre_input.value.strip()
                            p.email = (email_input.value or '').strip()
                            p.telefono = (telefono_input.value or '').strip()
                            p.direccion = (direccion_input.value or '').strip()
                            p.ciudad = (ciudad_input.value or '').strip()
                            p.productos = (productos_input.value or '').strip()
                            p.tipo = tipo.value
                            db.commit()
                    else:
                        if db.query(Proveedor).filter_by(id=id_input.value.strip()).first():
                            theme.notify_error('Ya existe con ese ID')
                            return
                        db.add(Proveedor(id=id_input.value.strip(), nombre=nombre_input.value.strip(),
                            email=(email_input.value or '').strip(), telefono=(telefono_input.value or '').strip(),
                            direccion=(direccion_input.value or '').strip(), ciudad=(ciudad_input.value or '').strip(),
                            productos=(productos_input.value or '').strip(), tipo=tipo.value))
                        db.commit()
                    theme.notify_success('Proveedor guardado')
                    dialog.close()
                    refresh_table(table_container, state)
                except Exception as e:
                    db.rollback()
                    theme.notify_error(f'Error: {str(e)}')
                finally:
                    db.close()
            
            ui.button('GUARDAR', icon='save', on_click=guardar).classes('btn-sandoval px-10')
    dialog.open()

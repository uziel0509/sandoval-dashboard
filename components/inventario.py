"""
SANDOVAL Dashboard - Gestión de Inventario
CRUD completo con SQLite
"""

from nicegui import ui
from utils.models import get_db, ItemInventario, log_actividad
import theme

CATEGORIAS = ['Repuestos', 'Filtros', 'Aceites', 'Frenos', 'Suspensión', 'Eléctrico', 'Motor', 'Transmisión', 'Servicios', 'Otros']
TIPOS_ITEM = ['Repuesto', 'Mano de Obra', 'Servicio']

def show_inventario(container):
    with container:
        state = {'search_query': '', 'filter_tipo': 'Todos'}
        
        # Header Corporativo Minimalista
        with ui.row().classes('w-full items-center justify-between mb-4 fade-in py-5 px-8 bg-white border border-gray-100 rounded-xl shadow-sm'):
            with ui.row().classes('items-center gap-4'):
                ui.icon('inventory_2', size='32px').classes('text-[#274495]')
                ui.label('GESTIÓN DE INVENTARIO').classes('text-xl font-extrabold text-[#274495] tracking-tight')
            ui.button('Nuevo Ítem', icon='add_box',
                on_click=lambda: open_item_dialog(table_container, state)
            ).classes('btn-sandoval')
        
        db = get_db()
        try:
            total = db.query(ItemInventario).count()
            low = db.query(ItemInventario).filter(ItemInventario.stock < ItemInventario.stock_minimo).count()
            from sqlalchemy import func
            val = db.query(func.sum(ItemInventario.costo * ItemInventario.stock)).scalar() or 0
        finally:
            db.close()
        
        with ui.row().classes('w-full gap-4 mb-4'):
            _stat('TOTAL ÍTEMS', str(total), 'inventory_2', 'blue-8')
            _stat('STOCK BAJO', str(low), 'warning', 'red-7' if low > 0 else 'green-7')
            _stat('VALOR INVENTARIO', f'S/ {val:,.2f}', 'attach_money', 'green-7')
        
        # Filter Bar White
        with ui.row().classes('w-full bg-white p-4 border-x border-b border-gray-200 rounded-b-lg mb-6 gap-4 items-center shadow-sm'):
            search_input = ui.input(placeholder='Buscar ítem...').props('outlined dense clearable bg-color=white').classes('flex-1')
            tipo_select = ui.select(['Todos'] + TIPOS_ITEM, value='Todos', label='Tipo').props('outlined dense bg-color=white').classes('w-40')
            def do_search():
                state['search_query'] = search_input.value or ''
                state['filter_tipo'] = tipo_select.value
                refresh_table(table_container, state)
            search_input.on('keydown.enter', lambda: do_search())
            tipo_select.on('update:model-value', lambda: do_search())
            ui.button('Buscar', icon='search', on_click=do_search).props('unelevated color=primary')
        
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
        query = db.query(ItemInventario)
        if state.get('filter_tipo') and state['filter_tipo'] != 'Todos':
            query = query.filter_by(tipo=state['filter_tipo'])
        if state.get('search_query'):
            q = f"%{state['search_query']}%"
            query = query.filter((ItemInventario.nombre.ilike(q)) | (ItemInventario.codigo.ilike(q)) | (ItemInventario.categoria.ilike(q)))
        items = query.all()
        
        with container:
            if not items:
                with ui.card().classes('w-full bg-white border border-gray-200 p-8 text-center shadow-sm'):
                    ui.icon('inventory_2', size='48px').classes('text-gray-400')
                    ui.label('No se encontraron ítems').classes('text-gray-500 mt-2')
                return
            
            columns = [
                {'name': 'codigo', 'label': 'Código', 'field': 'codigo', 'align': 'left', 'sortable': True},
                {'name': 'nombre', 'label': 'Nombre', 'field': 'nombre', 'align': 'left', 'sortable': True},
                {'name': 'categoria', 'label': 'Categoría', 'field': 'categoria', 'align': 'center'},
                {'name': 'tipo', 'label': 'Tipo', 'field': 'tipo', 'align': 'center'},
                {'name': 'costo', 'label': 'Costo', 'field': 'costo', 'align': 'right'},
                {'name': 'precio', 'label': 'Precio', 'field': 'precio', 'align': 'right'},
                {'name': 'stock', 'label': 'Stock', 'field': 'stock', 'align': 'center'},
            ]
            rows = [{'codigo': i.codigo, 'nombre': i.nombre, 'categoria': i.categoria, 'tipo': i.tipo,
                'costo': f"S/ {i.costo:.2f}", 'precio': f"S/ {i.precio:.2f}", 'stock': i.stock} for i in items]
            
            table = ui.table(columns=columns, rows=rows, row_key='codigo').classes('w-full bg-white text-black')
            table.props('flat bordered dense rows-per-page-options="[10, 25, 50]" binary-state-sort')
            
            table.add_slot('body-cell-stock', '''
                <q-td :props="props">
                    <q-badge :color="props.row.stock < 5 ? 'red-6' : (props.row.stock < 10 ? 'orange-6' : 'green-6')" :label="props.row.stock" />
                </q-td>
            ''')
            table.add_slot('body-cell-codigo', r'''
                <q-td :props="props">
                    <div class="row items-center no-wrap">
                        <span class="q-mr-sm text-bold">{{ props.row.codigo }}</span>
                        <q-btn flat dense icon="edit" color="primary" size="sm" @click="$parent.$emit('edit', props.row)" />
                        <q-btn flat dense icon="delete" color="red-6" size="sm" @click="$parent.$emit('delete', props.row)" />
                    </div>
                </q-td>
            ''')
            table.on('edit', lambda e: open_item_dialog(container, state, e.args['codigo'] if isinstance(e.args, dict) else e.args[0]['codigo']))
            table.on('delete', lambda e: theme.confirm_dialog('Eliminar', f'¿Eliminar {e.args["codigo"] if isinstance(e.args, dict) else e.args[0]["codigo"]}?',
                on_confirm=lambda c=(e.args['codigo'] if isinstance(e.args, dict) else e.args[0]['codigo']): (delete_item(c), refresh_table(container, state))))
    finally:
        db.close()

def delete_item(code):
    db = get_db()
    try:
        db.query(ItemInventario).filter_by(codigo=code).delete()
        db.commit()
        theme.notify_success('Eliminado')
    except Exception:
        db.rollback()
    finally:
        db.close()

def open_item_dialog(table_container, state, edit_code=None, on_success=None):
    existing = None
    if edit_code:
        db = get_db()
        try:
            i = db.query(ItemInventario).filter_by(codigo=edit_code).first()
            if i:
                existing = {'codigo': i.codigo, 'nombre': i.nombre, 'categoria': i.categoria, 'tipo': i.tipo,
                    'descripcion': i.descripcion, 'costo': i.costo, 'rentabilidad': i.rentabilidad,
                    'precio': i.precio, 'stock': i.stock}
        finally:
            db.close()
    
    title = 'Editar Ítem' if existing else 'Nuevo Ítem'
    
    with ui.dialog() as dialog, ui.card().classes('w-full max-w-lg bg-white p-0 border border-gray-200 shadow-xl'):
        # Header
        with ui.row().classes('w-full justify-between items-center p-4 border-b border-gray-200 bg-[#f5f5f9]'):
            ui.label(title).classes('text-xl font-bold text-gray-800')
            ui.button(icon='close', on_click=dialog.close).props('flat round color=grey-8 size=sm')
        
        with ui.column().classes('w-full p-6 gap-3'):
            tipo = ui.select(TIPOS_ITEM, value=existing.get('tipo', 'Repuesto') if existing else 'Repuesto', label='Tipo *').props('outlined dense bg-color=white').classes('w-full')
            with ui.row().classes('w-full gap-4'):
                codigo_input = ui.input('Código *', value=existing['codigo'] if existing else '').props('outlined dense bg-color=white' + (' readonly' if existing else '')).classes('flex-1')
                cat_select = ui.select(CATEGORIAS, value=existing.get('categoria', 'Repuestos') if existing else 'Repuestos', label='Categoría').props('outlined dense bg-color=white').classes('flex-1')
            nombre_input = ui.input('Nombre *', value=existing.get('nombre', '') if existing else '').props('outlined dense bg-color=white').classes('w-full')
            desc_input = ui.textarea('Descripción', value=existing.get('descripcion', '') if existing else '').props('outlined dense rows=2 bg-color=white').classes('w-full')
            with ui.row().classes('w-full gap-4'):
                costo_input = ui.input('Costo (S/)', value=str(existing.get('costo', 0)) if existing else '0').props('outlined dense type=number bg-color=white').classes('flex-1')
                rent_input = ui.input('Rentabilidad (%)', value=str(existing.get('rentabilidad', 0)) if existing else '30').props('outlined dense type=number bg-color=white').classes('flex-1')
            with ui.row().classes('w-full gap-4'):
                precio_input = ui.input('Precio Venta (S/)', value=str(existing.get('precio', 0)) if existing else '0').props('outlined dense type=number bg-color=white').classes('flex-1')
                stock_input = ui.input('Stock', value=str(existing.get('stock', 0)) if existing else '0').props('outlined dense type=number bg-color=white').classes('flex-1')
            
            def calc_precio():
                try:
                    c = float(costo_input.value or 0)
                    r = float(rent_input.value or 0)
                    precio_input.value = str(round(c * (1 + r / 100), 2))
                except ValueError:
                    pass
            costo_input.on('blur', lambda: calc_precio())
            rent_input.on('blur', lambda: calc_precio())
        
        # Footer
        with ui.row().classes('w-full justify-end gap-3 p-4 border-t border-gray-200 bg-gray-50'):
            ui.button('Cancelar', on_click=dialog.close).props('flat color=grey-8')
            
            def guardar():
                if not codigo_input.value or not nombre_input.value:
                    theme.notify_error('Código y Nombre obligatorios')
                    return
                db = get_db()
                try:
                    if existing:
                        i = db.query(ItemInventario).filter_by(codigo=edit_code).first()
                        if i:
                            i.nombre = nombre_input.value.strip()
                            i.categoria = cat_select.value
                            i.tipo = tipo.value
                            i.descripcion = (desc_input.value or '').strip()
                            i.costo = float(costo_input.value or 0)
                            i.rentabilidad = float(rent_input.value or 0)
                            i.precio = float(precio_input.value or 0)
                            i.stock = int(float(stock_input.value or 0))
                            db.commit()
                    else:
                        if db.query(ItemInventario).filter_by(codigo=codigo_input.value.strip()).first():
                            theme.notify_error('Código ya existe')
                            return
                        db.add(ItemInventario(
                            codigo=codigo_input.value.strip(), nombre=nombre_input.value.strip(),
                            categoria=cat_select.value, tipo=tipo.value,
                            descripcion=(desc_input.value or '').strip(),
                            costo=float(costo_input.value or 0), rentabilidad=float(rent_input.value or 0),
                            precio=float(precio_input.value or 0), stock=int(float(stock_input.value or 0))
                        ))
                        db.commit()
                    theme.notify_success('Ítem guardado')
                    dialog.close()
                    if table_container and state:
                        refresh_table(table_container, state)
                    
                    if on_success and not existing:
                        on_success(codigo_input.value.strip())
                        
                except Exception as e:
                    db.rollback()
                    theme.notify_error(f'Error: {str(e)}')
                finally:
                    db.close()
            
            ui.button('Guardar', icon='save', on_click=guardar).classes('btn-sandoval px-10')
    dialog.open()

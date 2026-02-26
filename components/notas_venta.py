"""
SANDOVAL Dashboard - Notas de Venta
Venta directa de repuestos vinculada al inventario, clientes,
dashboard de métricas, reportes y rentabilidad.
"""

from datetime import datetime
from nicegui import ui
from utils.models import (
    get_db, NotaVenta, Cliente, ItemInventario, log_actividad
)
import theme

IGV = 0.18   # 18 %


# ─────────────────────────────────────────────────────────────────────────────
#  ENTRADA PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────

def show_notas_venta(container):
    with container:
        state = {'search': '', 'filter_estado': 'Todos'}

        # ── Header ───────────────────────────────────────────────────────────
        with ui.row().classes(
            'w-full items-center justify-between mb-4 fade-in '
            'py-5 px-8 bg-white border border-gray-100 rounded-xl shadow-sm'
        ):
            with ui.row().classes('items-center gap-4'):
                ui.icon('receipt_long', size='32px').classes('text-[#274495]')
                with ui.column().classes('gap-0'):
                    ui.label('NOTAS DE VENTA').classes(
                        'text-xl font-extrabold text-[#274495] tracking-tight')
                    ui.label('Venta directa de repuestos e insumos').classes(
                        'text-xs text-gray-400 font-medium')
            ui.button('Nueva Nota', icon='add',
                      on_click=lambda: open_nota_dialog(list_container, state)
                      ).classes('btn-sandoval')

        # ── KPIs ─────────────────────────────────────────────────────────────
        db = get_db()
        try:
            notas = db.query(NotaVenta).all()
            pagadas   = [n for n in notas if n.estado == 'pagada']
            total_mes = sum(
                n.total for n in pagadas
                if n.fecha and n.fecha.month == datetime.now().month
                   and n.fecha.year == datetime.now().year
            )
            total_acum = sum(n.total for n in pagadas)
            n_mes = len([
                n for n in pagadas
                if n.fecha and n.fecha.month == datetime.now().month
                   and n.fecha.year == datetime.now().year
            ])
        finally:
            db.close()

        with ui.row().classes('w-full gap-4 mb-4'):
            _kpi('VENTAS DEL MES', f'S/ {total_mes:,.2f}', 'trending_up', 'green-7')
            _kpi('TOTAL ACUMULADO', f'S/ {total_acum:,.2f}', 'payments', 'blue-8')
            _kpi('NOTAS ESTE MES', str(n_mes), 'receipt_long', 'purple-7')
            _kpi('TOTAL NOTAS', str(len(pagadas)), 'inventory', 'amber-7')

        # ── Barra de búsqueda ─────────────────────────────────────────────────
        with ui.row().classes(
            'w-full bg-white p-4 border border-gray-200 rounded-xl mb-4 gap-4 items-center shadow-sm'
        ):
            search_in = ui.input(placeholder='Buscar por número, cliente…'
                                 ).props('outlined dense clearable bg-color=white').classes('flex-1')
            estado_sel = ui.select(
                ['Todos', 'pagada', 'borrador', 'anulada'],
                value='Todos', label='Estado'
            ).props('outlined dense bg-color=white').classes('w-40')

            def do_search():
                state['search'] = search_in.value or ''
                state['filter_estado'] = estado_sel.value
                _refresh(list_container, state)

            search_in.on('keydown.enter', do_search)
            estado_sel.on('update:model-value', do_search)
            ui.button('Buscar', icon='search', on_click=do_search
                      ).props('unelevated color=primary')

        # ── Lista ─────────────────────────────────────────────────────────────
        list_container = ui.column().classes('w-full gap-3')
        _refresh(list_container, state)


# ─────────────────────────────────────────────────────────────────────────────
#  KPI CARD
# ─────────────────────────────────────────────────────────────────────────────

def _kpi(title, value, icon, color):
    with ui.card().classes(
        'flex-1 bg-white border border-gray-200 p-4 shadow-sm '
        'hover:border-blue-400 transition-colors'
    ):
        with ui.row().classes('items-center justify-between w-full'):
            with ui.column().classes('gap-1'):
                ui.label(title).classes('text-xs font-bold text-gray-500 tracking-wider')
                ui.label(value).classes(f'text-3xl font-bold text-{color}')
            with ui.avatar(
                color=color.replace('-7', '-1').replace('-8', '-1'),
                text_color=color
            ).classes('rounded-lg'):
                ui.icon(icon, size='md')


# ─────────────────────────────────────────────────────────────────────────────
#  LISTA DE NOTAS
# ─────────────────────────────────────────────────────────────────────────────

_ESTADO_STYLE = {
    'pagada':   ('bg-green-100 text-green-800',  'check_circle'),
    'borrador': ('bg-amber-100 text-amber-800',  'edit_note'),
    'anulada':  ('bg-red-100 text-red-800',      'cancel'),
}


def _refresh(container, state):
    container.clear()
    db = get_db()
    try:
        q = db.query(NotaVenta).order_by(NotaVenta.fecha.desc())
        if state['filter_estado'] != 'Todos':
            q = q.filter(NotaVenta.estado == state['filter_estado'])
        if state['search']:
            s = f"%{state['search']}%"
            q = q.filter(
                NotaVenta.numero.ilike(s) | NotaVenta.cliente_nombre.ilike(s)
            )
        notas = q.limit(50).all()

        with container:
            if not notas:
                with ui.card().classes(
                    'w-full bg-white border border-gray-200 p-12 text-center'
                ):
                    ui.icon('receipt_long', size='56px').classes('text-gray-200 mb-2')
                    ui.label('No hay notas de venta').classes('text-gray-400 text-lg')
                    ui.label('Haz clic en "Nueva Nota" para registrar una venta.'
                             ).classes('text-gray-300 text-sm')
                return

            # Cabecera tabla
            with ui.element('div').classes(
                'hidden md:grid w-full px-5 py-2 bg-gray-50 border border-gray-200 '
                'rounded-t-xl text-[10px] font-black text-gray-400 tracking-widest'
            ).style('grid-template-columns:120px 1fr 120px 120px 120px 100px'):
                for h in ['NÚMERO', 'CLIENTE', 'FECHA', 'SUBTOTAL', 'TOTAL', 'ESTADO']:
                    ui.label(h)

            for nota in notas:
                _nota_row(container, state, nota)
    finally:
        db.close()


def _nota_row(container, state, nota):
    css, ico = _ESTADO_STYLE.get(nota.estado, ('bg-gray-100 text-gray-700', 'help'))
    fecha_str = nota.fecha.strftime('%d/%m/%Y') if nota.fecha else '—'
    nombre = nota.cliente_nombre or '—'
    if len(nombre) > 28:
        nombre = nombre[:28] + '…'

    with ui.element('div').classes(
        'w-full grid items-center px-5 py-4 bg-white border border-gray-200 '
        'hover:bg-blue-50/30 transition-colors cursor-pointer border-t-0 '
        'rounded-b-none last:rounded-b-xl'
    ).style('grid-template-columns:120px 1fr 120px 120px 120px 100px'):
        ui.label(nota.numero).classes('text-sm font-black text-[#274495]')
        ui.label(nombre).classes('text-sm font-semibold text-gray-700 truncate')
        ui.label(fecha_str).classes('text-xs text-gray-500')
        ui.label(f'S/ {nota.subtotal:,.2f}').classes('text-sm text-gray-700 font-medium')
        ui.label(f'S/ {nota.total:,.2f}').classes('text-sm font-black text-green-700')
        with ui.row().classes('items-center gap-2'):
            with ui.element('span').classes(f'px-2 py-1 rounded-full text-[10px] font-black {css}'):
                ui.label(nota.estado.upper())
            ui.button(icon='visibility', on_click=lambda n=nota: open_nota_dialog(
                container, state, nota_id=n.id
            )).props('flat round dense color=primary size=xs')
            if nota.estado != 'anulada':
                ui.button(icon='cancel', on_click=lambda n=nota: _anular(
                    container, state, n.id
                )).props('flat round dense color=red-7 size=xs')


# ─────────────────────────────────────────────────────────────────────────────
#  ANULAR NOTA
# ─────────────────────────────────────────────────────────────────────────────

def _anular(container, state, nota_id):
    def confirm_anular():
        db = get_db()
        try:
            nota = db.query(NotaVenta).filter_by(id=nota_id).first()
            if nota and nota.estado == 'pagada':
                # Restaurar stock
                for item in (nota.items or []):
                    prod = db.query(ItemInventario).filter_by(
                        codigo=item.get('codigo')).first()
                    if prod:
                        prod.stock += int(item.get('cantidad', 0))
                nota.estado = 'anulada'
                db.commit()
                log_actividad(f'Nota de venta {nota.numero} anulada', 'notas_venta')
                theme.notify_success('Nota anulada y stock restaurado')
            elif nota:
                nota.estado = 'anulada'
                db.commit()
                theme.notify_success('Nota anulada')
        except Exception as e:
            db.rollback()
            theme.notify_error(f'Error: {e}')
        finally:
            db.close()
        _refresh(container, state)

    theme.confirm_dialog('Anular nota', '¿Anular esta nota de venta? Se restaurará el stock.',
                         on_confirm=confirm_anular)


# ─────────────────────────────────────────────────────────────────────────────
#  DIALOG CREAR / VER NOTA
# ─────────────────────────────────────────────────────────────────────────────

def open_nota_dialog(list_container, state, nota_id=None):
    """Abre el diálogo de nueva nota o vista de nota existente."""

    # Cargar nota existente para modo vista
    existing = None
    if nota_id:
        db = get_db()
        try:
            existing = db.query(NotaVenta).filter_by(id=nota_id).first()
            if existing:
                existing = {
                    'id': existing.id, 'numero': existing.numero,
                    'fecha': existing.fecha, 'cliente_id': existing.cliente_id,
                    'cliente_nombre': existing.cliente_nombre,
                    'subtotal': existing.subtotal, 'igv': existing.igv,
                    'total': existing.total, 'estado': existing.estado,
                    'notas': existing.notas, 'items': list(existing.items or [])
                }
        finally:
            db.close()

    read_only = existing and existing['estado'] in ('pagada', 'anulada')
    title = f"Nota {existing['numero']}" if existing else 'Nueva Nota de Venta'

    with ui.dialog() as dialog, ui.card().classes(
        'w-full bg-white p-0 border border-gray-100 shadow-2xl rounded-2xl'
    ).style('max-width:920px;width:95vw'):

        # Header
        with ui.row().classes(
            'w-full justify-between items-center px-6 py-4 '
            'border-b border-gray-100 bg-[#f5f7ff] rounded-t-2xl'
        ):
            with ui.row().classes('items-center gap-3'):
                ui.icon('receipt_long', size='24px').classes('text-[#274495]')
                ui.label(title).classes('text-lg font-black text-[#274495]')
            ui.button(icon='close', on_click=dialog.close
                      ).props('flat round color=grey-8 size=sm')

        with ui.row().classes('w-full p-6 gap-6').style('align-items:flex-start'):

            # ── Columna izquierda: encabezado de la nota ──────────────────────
            with ui.column().classes('gap-4').style('flex:1'):

                # Cliente
                ui.label('CLIENTE').classes('text-[10px] font-black text-gray-400 tracking-widest')

                db = get_db()
                clientes = db.query(Cliente).order_by(Cliente.nombre).all()
                opciones_cli = {f"{c.nombre} {c.apellidos}".strip(): c.id for c in clientes}
                db.close()

                nombre_lbl = ui.label(
                    existing['cliente_nombre'] if existing else ''
                ).classes('text-sm font-bold text-gray-700')

                if not read_only:
                    cli_search = ui.input(
                        'Buscar cliente registrado…'
                    ).props('outlined dense bg-color=white clearable').classes('w-full')

                    cli_select = ui.select(
                        list(opciones_cli.keys()),
                        label='Seleccionar cliente',
                        value=None
                    ).props('outlined dense bg-color=white').classes('w-full')

                    cli_libre = ui.input(
                        'O nombre libre (sin registro)'
                    ).props('outlined dense bg-color=white').classes('w-full')

                    estado_nota = ui.select(
                        ['pagada', 'borrador'],
                        value='pagada', label='Estado'
                    ).props('outlined dense bg-color=white').classes('w-full')

                    notas_in = ui.textarea(
                        'Notas / Observaciones', placeholder='Opcional…'
                    ).props('outlined dense rows=2 bg-color=white').classes('w-full')
                else:
                    ui.label(
                        f"Estado: {existing['estado'].upper()}"
                    ).classes('text-sm font-bold')
                    ui.label(existing.get('notas') or '').classes('text-xs text-gray-500')

            # ── Columna derecha: ítems ────────────────────────────────────────
            with ui.column().classes('gap-3').style('flex:1.4'):
                ui.label('ÍTEMS DE VENTA').classes('text-[10px] font-black text-gray-400 tracking-widest')

                # Estado reactivo de los ítems
                items_state: list[dict] = list(existing['items']) if existing else []
                items_container = ui.column().classes('w-full gap-2')

                totales_lbl = ui.label('').classes('text-sm font-bold text-gray-700 text-right w-full')

                def calc_totales():
                    sub = sum(it.get('subtotal', 0) for it in items_state)
                    igv = sub * IGV
                    tot = sub + igv
                    totales_lbl.set_text(
                        f'Subtotal: S/ {sub:,.2f}  |  IGV 18%: S/ {igv:,.2f}  |  '
                        f'TOTAL: S/ {tot:,.2f}'
                    )

                def render_items():
                    items_container.clear()
                    with items_container:
                        if not items_state:
                            ui.label('Sin ítems aún').classes('text-gray-300 text-sm text-center py-4')
                            return
                        for i, it in enumerate(items_state):
                            with ui.row().classes(
                                'w-full items-center gap-2 bg-gray-50 rounded-xl p-3 border border-gray-200'
                            ):
                                with ui.column().classes('flex-1 gap-0'):
                                    ui.label(it['nombre']).classes('text-sm font-bold text-gray-800')
                                    ui.label(it.get('codigo', '')).classes('text-[10px] text-gray-400')
                                ui.label(f"x{it['cantidad']}").classes('text-xs font-black text-[#274495] w-8')
                                ui.label(f"S/ {it['precio']:,.2f}").classes('text-xs text-gray-600 w-20 text-right')
                                ui.label(f"S/ {it['subtotal']:,.2f}").classes('text-sm font-black text-green-700 w-24 text-right')
                                if not read_only:
                                    ui.button(icon='delete', on_click=lambda idx=i: (
                                        items_state.pop(idx),
                                        render_items(),
                                        calc_totales()
                                    )).props('flat round dense color=red-6 size=xs')
                    calc_totales()

                render_items()

                # Añadir ítem (solo modo edición)
                if not read_only:
                    ui.separator().classes('my-2')
                    ui.label('AÑADIR PRODUCTO DEL INVENTARIO').classes(
                        'text-[10px] font-black text-gray-400 tracking-widest')

                    db2 = get_db()
                    inv = db2.query(ItemInventario).filter(
                        ItemInventario.tipo.in_(['Repuesto', 'Servicio'])
                    ).order_by(ItemInventario.nombre).all()
                    db2.close()

                    prod_opts = {f"{p.nombre} ({p.codigo}) — Stock: {p.stock}": p.codigo
                                 for p in inv if p.stock > 0}

                    prod_sel = ui.select(
                        list(prod_opts.keys()),
                        label='Buscar producto…',
                        with_input=True
                    ).props('outlined dense bg-color=white').classes('w-full')

                    with ui.row().classes('w-full gap-2 items-end'):
                        cant_in = ui.input('Cant.', value='1').props(
                            'outlined dense type=number bg-color=white').classes('w-24')
                        precio_in = ui.input('Precio unit. (S/)').props(
                            'outlined dense type=number bg-color=white').classes('flex-1')

                        def on_prod_change():
                            code = prod_opts.get(prod_sel.value, '')
                            if not code:
                                return
                            db3 = get_db()
                            try:
                                p = db3.query(ItemInventario).filter_by(codigo=code).first()
                                if p:
                                    precio_in.value = str(p.precio)
                            finally:
                                db3.close()

                        prod_sel.on('update:model-value', lambda: on_prod_change())

                        def add_item():
                            code = prod_opts.get(prod_sel.value, '')
                            if not code:
                                theme.notify_error('Selecciona un producto')
                                return
                            try:
                                qty = int(float(cant_in.value or 1))
                                price = float(precio_in.value or 0)
                            except ValueError:
                                theme.notify_error('Cantidad/precio inválidos')
                                return
                            if qty <= 0 or price < 0:
                                theme.notify_error('Valores inválidos')
                                return

                            db4 = get_db()
                            try:
                                p = db4.query(ItemInventario).filter_by(codigo=code).first()
                                if not p:
                                    theme.notify_error('Producto no encontrado')
                                    return
                                if p.stock < qty:
                                    theme.notify_error(f'Stock insuficiente (hay {p.stock})')
                                    return
                                # Ver si ya está en la lista
                                for ex in items_state:
                                    if ex['codigo'] == code:
                                        ex['cantidad'] += qty
                                        ex['subtotal'] = round(ex['cantidad'] * ex['precio'], 2)
                                        render_items()
                                        return
                                items_state.append({
                                    'codigo': p.codigo, 'nombre': p.nombre,
                                    'cantidad': qty, 'precio': price,
                                    'subtotal': round(qty * price, 2)
                                })
                                render_items()
                            finally:
                                db4.close()

                        ui.button('Agregar', icon='add', on_click=add_item
                                  ).props('unelevated color=primary')

        # ── Footer ────────────────────────────────────────────────────────────
        with ui.row().classes(
            'w-full justify-end gap-3 px-6 py-4 border-t border-gray-100 bg-gray-50 rounded-b-2xl'
        ):
            ui.button('Cerrar' if read_only else 'Cancelar',
                      on_click=dialog.close).props('flat color=grey-8')

            if not read_only:
                def guardar(cerrar_como='pagada'):
                    if not items_state:
                        theme.notify_error('Agrega al menos un producto')
                        return

                    # Nombre del cliente
                    c_nombre = ''
                    c_id = None
                    if cli_select.value and cli_select.value in opciones_cli:
                        c_id = opciones_cli[cli_select.value]
                        c_nombre = cli_select.value
                    elif cli_libre.value and cli_libre.value.strip():
                        c_nombre = cli_libre.value.strip()
                    else:
                        c_nombre = 'Cliente mostrador'

                    sub = sum(it['subtotal'] for it in items_state)
                    igv_val = round(sub * IGV, 2)
                    tot = round(sub + igv_val, 2)

                    db = get_db()
                    try:
                        # Generar número correlativo
                        last = db.query(NotaVenta).order_by(NotaVenta.id.desc()).first()
                        seq = (last.id + 1) if last else 1
                        numero = f"NV-{datetime.now().year}-{seq:04d}"

                        # Descontar stock
                        for it in items_state:
                            prod = db.query(ItemInventario).filter_by(
                                codigo=it['codigo']).first()
                            if prod:
                                prod.stock -= it['cantidad']
                                if prod.stock < 0:
                                    prod.stock = 0

                        nv = NotaVenta(
                            numero=numero,
                            fecha=datetime.now(),
                            cliente_id=c_id,
                            cliente_nombre=c_nombre,
                            subtotal=sub,
                            igv=igv_val,
                            total=tot,
                            estado=cerrar_como,
                            notas=(notas_in.value or '').strip(),
                            items=list(items_state),
                        )
                        db.add(nv)
                        db.commit()
                        log_actividad(f'Nota de venta {numero} creada — S/ {tot:.2f}',
                                      'notas_venta', f'{len(items_state)} ítems')
                        theme.notify_success(f'Nota {numero} guardada ✓')
                        dialog.close()
                        _refresh(list_container, state)
                    except Exception as e:
                        db.rollback()
                        theme.notify_error(f'Error al guardar: {e}')
                    finally:
                        db.close()

                ui.button('Guardar como borrador', icon='edit_note',
                          on_click=lambda: guardar('borrador')
                          ).props('flat color=amber-8')
                ui.button('Registrar Venta', icon='point_of_sale',
                          on_click=lambda: guardar('pagada')
                          ).classes('btn-sandoval px-8')

    dialog.open()

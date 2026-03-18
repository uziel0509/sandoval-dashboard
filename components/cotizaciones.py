"""
SANDOVAL Dashboard - Módulo de Cotizaciones
"""
from nicegui import ui
from utils.models import get_db, Cotizacion, CotizacionItem, Cliente, ConfigSistema, log_actividad
from utils.auth import get_current_user
from datetime import datetime
import traceback

def _gen_numero():
    db = get_db()
    try:
        hoy = datetime.now().strftime('%Y%m')
        count = db.query(Cotizacion).filter(Cotizacion.numero.like(f'COT-{hoy}%')).count()
        return f'COT-{hoy}-{count + 1:04d}'
    finally:
        db.close()

def show_cotizaciones(container):
    with container:
        with ui.row().classes('w-full items-center justify-between mb-6'):
            with ui.column().classes('gap-0'):
                ui.label('Cotizaciones').classes('text-3xl font-black text-gray-900')
                ui.label('Presupuestos para clientes · No afecta inventario').classes('text-sm text-gray-400 font-medium')
            ui.button('+ Nueva Cotización', on_click=lambda: _abrir_modal_nueva(tabla_container)).classes('btn-sandoval shadow-md px-6 h-10')
        tabla_container = ui.column().classes('w-full')
        _render_tabla(tabla_container)

def _render_tabla(container):
    container.clear()
    db = get_db()
    try:
        cotizaciones = db.query(Cotizacion).order_by(Cotizacion.fecha_creacion.desc()).all()
        with container:
            if not cotizaciones:
                with ui.card().classes('w-full p-12 text-center border border-dashed border-gray-200'):
                    ui.icon('request_quote', size='48px').classes('text-gray-300 mb-3')
                    ui.label('Sin cotizaciones aún').classes('text-gray-400 text-lg font-semibold')
                    ui.label('Crea una desde el botón de arriba o pídele a Jarvis por Telegram').classes('text-gray-300 text-sm mt-1')
                return
            with ui.card().classes('w-full shadow-sm border border-gray-100'):
                with ui.row().classes('w-full bg-gray-50 px-6 py-3 rounded-t-xl text-xs font-black text-gray-400 uppercase tracking-widest'):
                    ui.label('Número').classes('w-44')
                    ui.label('Cliente').classes('flex-1')
                    ui.label('Fecha').classes('w-32')
                    ui.label('Total').classes('w-28 text-right')
                    ui.label('Estado').classes('w-28 text-center')
                    ui.label('Acciones').classes('w-36 text-center')
                for c in cotizaciones:
                    _render_fila(c, tabla_container)
    finally:
        db.close()

def _estado_color(estado):
    return {'PENDIENTE':'bg-yellow-100 text-yellow-700','APROBADA':'bg-green-100 text-green-700','RECHAZADA':'bg-red-100 text-red-700','ENVIADA':'bg-blue-100 text-blue-700'}.get(estado,'bg-gray-100 text-gray-500')

def _render_fila(c, tabla_ref):
    with ui.row().classes('w-full px-6 py-4 items-center border-t border-gray-50 hover:bg-blue-50/30 transition-colors'):
        ui.label(c.numero).classes('w-44 font-mono text-sm font-bold text-[#274495]')
        ui.label(c.nombre_cliente or '—').classes('flex-1 text-sm text-gray-700')
        ui.label(c.fecha_creacion.strftime('%d/%m/%Y') if c.fecha_creacion else '—').classes('w-32 text-sm text-gray-500')
        ui.label(f'S/ {c.total:.2f}').classes('w-28 text-right text-sm font-bold text-gray-800')
        with ui.element('div').classes('w-28 flex justify-center'):
            ui.label(c.estado).classes(f'text-xs font-bold px-3 py-1 rounded-full {_estado_color(c.estado)}')
        with ui.row().classes('w-36 justify-center gap-1'):
            ui.button(icon='visibility', on_click=lambda cid=c.id: _ver_detalle(cid, tabla_ref)).props('flat round dense color=blue-7').tooltip('Ver')
            ui.button(icon='picture_as_pdf', on_click=lambda cid=c.id: _generar_pdf(cid)).props('flat round dense color=red-7').tooltip('PDF')
            ui.button(icon='delete', on_click=lambda cid=c.id, tr=tabla_ref: _confirmar_eliminar(cid, tr)).props('flat round dense color=red-4').tooltip('Eliminar')

def _abrir_modal_nueva(tabla_ref, prefill=None):
    items_temp = list(prefill.get('items', [])) if prefill else []
    with ui.dialog() as dialog, ui.card().classes('w-full max-w-3xl p-0 overflow-hidden shadow-2xl'):
        with ui.row().classes('w-full bg-[#274495] px-8 py-5 items-center justify-between'):
            with ui.column().classes('gap-0'):
                ui.label('Nueva Cotización').classes('text-xl font-black text-white')
                ui.label('Los ítems NO se descuentan del inventario').classes('text-xs text-blue-200 mt-0.5')
            ui.button(icon='close', on_click=dialog.close).props('flat round color=white')
        with ui.column().classes('w-full p-8 gap-6'):
            with ui.row().classes('w-full gap-4'):
                nombre_input = ui.input('Nombre del cliente *', value=prefill.get('nombre_cliente','') if prefill else '').props('outlined dense').classes('flex-1')
                cliente_id_ref = {'value': prefill.get('cliente_id') if prefill else None}
                db = get_db()
                try:
                    clientes = db.query(Cliente).order_by(Cliente.nombre).all()
                    opciones = {f"{c.nombre} {c.apellidos}".strip(): c.id for c in clientes}
                finally:
                    db.close()
                def on_sel(e):
                    nombre_input.value = e.value
                    cliente_id_ref['value'] = opciones.get(e.value)
                ui.select(list(opciones.keys()), label='Buscar cliente registrado', on_change=on_sel, with_input=True, clearable=True).props('outlined dense').classes('flex-1')
            nota_input = ui.textarea('Nota / Observaciones').props('outlined dense rows=2').classes('w-full')
            ui.separator()
            ui.label('ÍTEMS').classes('text-xs font-black text-gray-400 tracking-widest')
            items_container = ui.column().classes('w-full gap-2')
            total_label = ui.label('TOTAL: S/ 0.00').classes('text-2xl font-black text-[#274495] text-right w-full')
            def _recalc():
                t = sum(int(it.get('cantidad',1))*float(it.get('precio_unitario',0)) for it in items_temp)
                total_label.text = f'TOTAL: S/ {t:.2f}'
            def _render_items():
                items_container.clear()
                with items_container:
                    if not items_temp:
                        ui.label('Sin ítems. Agrega repuestos o mano de obra.').classes('text-gray-300 text-sm italic py-2')
                        return
                    for idx, it in enumerate(items_temp):
                        _render_item_row(idx, it, items_temp, _render_items, _recalc)
            def _agregar(tipo='repuesto'):
                items_temp.append({'descripcion':'','tipo':tipo,'cantidad':1,'precio_unitario':0.0})
                _render_items()
            with ui.row().classes('gap-2 mt-1'):
                ui.button('+ Repuesto', icon='inventory_2', on_click=lambda: _agregar('repuesto')).props('outlined dense color=blue-7').classes('text-xs')
                ui.button('+ Mano de Obra', icon='build', on_click=lambda: _agregar('mano_obra')).props('outlined dense color=orange-7').classes('text-xs')
            _render_items()
            ui.separator()
            with ui.row().classes('w-full justify-end gap-3 pt-2'):
                ui.button('Cancelar', on_click=dialog.close).props('flat color=gray-6')
                async def guardar():
                    nombre = (nombre_input.value or '').strip()
                    if not nombre:
                        ui.notify('Ingresa el nombre del cliente', type='warning'); return
                    if not items_temp:
                        ui.notify('Agrega al menos un ítem', type='warning'); return
                    total = sum(int(it.get('cantidad',1))*float(it.get('precio_unitario',0)) for it in items_temp)
                    db2 = get_db()
                    try:
                        numero = _gen_numero()
                        cot = Cotizacion(numero=numero, nombre_cliente=nombre, cliente_id=cliente_id_ref['value'], nota=nota_input.value or '', total=total, estado='PENDIENTE', creado_por=(get_current_user() or {}).get('nombre','Sistema'))
                        db2.add(cot); db2.flush()
                        for it in items_temp:
                            qty=int(it.get('cantidad',1)); price=float(it.get('precio_unitario',0))
                            db2.add(CotizacionItem(cotizacion_id=cot.id, descripcion=it.get('descripcion',''), tipo=it.get('tipo','repuesto'), cantidad=qty, precio_unitario=price, subtotal=qty*price))
                        db2.commit()
                        log_actividad(f'Cotización creada: {numero}','cotizaciones',f'Cliente: {nombre} | Total: S/ {total:.2f}')
                        ui.notify(f'Cotización {numero} creada ✓', type='positive')
                        dialog.close(); _render_tabla(tabla_ref)
                    except Exception:
                        db2.rollback(); ui.notify('Error al guardar', type='negative'); print(traceback.format_exc())
                    finally:
                        db2.close()
                ui.button('Guardar Cotización', icon='save', on_click=guardar).classes('btn-sandoval px-6')
    dialog.open()

def _render_item_row(idx, item, items_temp, refresh_fn, recalc_fn):
    with ui.card().classes('w-full p-3 border border-gray-100 bg-gray-50/50'):
        with ui.row().classes('w-full items-center gap-3'):
            ico = 'inventory_2' if item.get('tipo')=='repuesto' else 'build'
            col = 'text-blue-600' if item.get('tipo')=='repuesto' else 'text-orange-600'
            ui.icon(ico, size='18px').classes(col)
            desc = ui.input(placeholder='Descripción', value=item.get('descripcion','')).props('dense borderless').classes('flex-1 bg-white rounded px-2')
            qty  = ui.number(label='Cant.', value=item.get('cantidad',1), min=1, step=1).props('dense outlined').classes('w-20')
            price= ui.number(label='Precio unit.', value=item.get('precio_unitario',0), min=0, step=0.5, prefix='S/').props('dense outlined').classes('w-32')
            def make_upd(i,d,q,p):
                def upd(_=None):
                    items_temp[i]['descripcion']=d.value or ''
                    items_temp[i]['cantidad']=int(q.value or 1)
                    items_temp[i]['precio_unitario']=float(p.value or 0)
                    items_temp[i]['subtotal']=items_temp[i]['cantidad']*items_temp[i]['precio_unitario']
                    recalc_fn()
                return upd
            u=make_upd(idx,desc,qty,price)
            desc.on('blur',u); qty.on('update:model-value',u); price.on('update:model-value',u)
            def make_del(i):
                def d(): items_temp.pop(i); refresh_fn(); recalc_fn()
                return d
            ui.button(icon='close', on_click=make_del(idx)).props('flat round dense color=red-4')
        sub=item.get('cantidad',1)*item.get('precio_unitario',0)
        ui.label(f'Subtotal: S/ {sub:.2f}').classes('text-xs text-gray-400 text-right w-full mt-1 pr-10')

def _ver_detalle(cotizacion_id, tabla_ref):
    db = get_db()
    try:
        c = db.query(Cotizacion).filter_by(id=cotizacion_id).first()
        if not c: ui.notify('No encontrada', type='warning'); return
        with ui.dialog() as dlg, ui.card().classes('w-full max-w-2xl p-0 shadow-2xl overflow-hidden'):
            with ui.row().classes('w-full bg-[#274495] px-8 py-5 items-center justify-between'):
                with ui.column().classes('gap-0'):
                    ui.label(c.numero).classes('text-xl font-black text-white font-mono')
                    ui.label(c.nombre_cliente).classes('text-sm text-blue-200')
                ui.button(icon='close', on_click=dlg.close).props('flat round color=white')
            with ui.column().classes('p-8 gap-4 w-full'):
                with ui.row().classes('w-full items-center gap-4'):
                    ui.label(c.estado).classes(f'text-sm font-bold px-4 py-1 rounded-full {_estado_color(c.estado)}')
                    ui.label(f'Creada: {c.fecha_creacion.strftime("%d/%m/%Y %H:%M") if c.fecha_creacion else "—"}').classes('text-xs text-gray-400')
                    ui.label(f'Por: {c.creado_por or "—"}').classes('text-xs text-gray-400')
                if c.nota:
                    ui.label(c.nota).classes('text-sm text-gray-600 bg-gray-50 rounded-lg px-4 py-3 w-full italic')
                ui.separator()
                with ui.column().classes('w-full gap-2'):
                    for it in c.items:
                        ico='inventory_2' if it.tipo=='repuesto' else 'build'
                        col='text-blue-600' if it.tipo=='repuesto' else 'text-orange-600'
                        with ui.row().classes('w-full justify-between items-center px-3 py-2 bg-gray-50 rounded-lg border border-gray-100'):
                            with ui.row().classes('items-center gap-2 flex-1'):
                                ui.icon(ico, size='16px').classes(col)
                                ui.label(it.descripcion).classes('text-sm text-gray-700')
                            ui.label(f'{it.cantidad} × S/ {it.precio_unitario:.2f}').classes('text-xs text-gray-400 mx-4')
                            ui.label(f'S/ {it.subtotal:.2f}').classes('text-sm font-bold text-gray-800 w-24 text-right')
                ui.separator()
                ui.label(f'TOTAL: S/ {c.total:.2f}').classes('text-2xl font-black text-[#274495] text-right w-full')
                estados=['PENDIENTE','ENVIADA','APROBADA','RECHAZADA']
                with ui.row().classes('w-full justify-between items-center pt-2'):
                    estado_sel=ui.select(estados, value=c.estado, label='Cambiar estado').props('outlined dense').classes('w-40')
                    async def cambiar():
                        db2=get_db()
                        try:
                            cot=db2.query(Cotizacion).filter_by(id=cotizacion_id).first()
                            if cot: cot.estado=estado_sel.value; db2.commit(); ui.notify('Estado actualizado ✓',type='positive'); dlg.close(); _render_tabla(tabla_ref)
                        finally: db2.close()
                    ui.button('Actualizar estado', icon='check', on_click=cambiar).props('outlined color=blue-7 dense')
                    ui.button('Descargar PDF', icon='picture_as_pdf', on_click=lambda: _generar_pdf(cotizacion_id)).props('outlined color=red-7 dense')
        dlg.open()
    finally:
        db.close()

def _generar_pdf(cotizacion_id):
    try:
        from utils.pdf_cotizacion import generar_pdf_cotizacion
        path = generar_pdf_cotizacion(cotizacion_id)
        if path:
            filename = path.replace('\\','/').split('/')[-1]
            ui.download(f'/pdfs/{filename}')
            ui.notify('PDF generado ✓', type='positive')
        else:
            ui.notify('Error generando PDF', type='negative')
    except Exception:
        ui.notify('Error generando PDF', type='negative')
        print(traceback.format_exc())

def _confirmar_eliminar(cotizacion_id, tabla_ref):
    with ui.dialog() as dlg, ui.card().classes('p-6 max-w-sm'):
        ui.label('¿Eliminar cotización?').classes('text-lg font-bold text-gray-800 mb-2')
        ui.label('Esta acción no se puede deshacer.').classes('text-sm text-gray-500 mb-4')
        with ui.row().classes('w-full justify-end gap-3'):
            ui.button('Cancelar', on_click=dlg.close).props('flat color=gray')
            def eliminar():
                db=get_db()
                try:
                    cot=db.query(Cotizacion).filter_by(id=cotizacion_id).first()
                    if cot: db.delete(cot); db.commit(); ui.notify('Eliminada',type='info')
                    dlg.close(); _render_tabla(tabla_ref)
                except Exception: db.rollback(); ui.notify('Error',type='negative')
                finally: db.close()
            ui.button('Eliminar', icon='delete', on_click=eliminar).props('color=red-7')
    dlg.open()

"""
SANDOVAL Dashboard - Modulo de Cotizaciones
"""
from nicegui import ui
from utils.models import get_db, Cotizacion, CotizacionItem, Cliente, log_actividad
from utils.auth import get_current_user
from datetime import datetime
import traceback, json

def _gen_numero():
    db = get_db()
    try:
        hoy = datetime.now().strftime('%Y%m')
        count = db.query(Cotizacion).filter(Cotizacion.numero.like(f'COT-{hoy}%')).count()
        return f'COT-{hoy}-{count + 1:04d}'
    finally:
        db.close()

def _estado_color(estado):
    return {'PENDIENTE':'bg-yellow-100 text-yellow-700','APROBADA':'bg-green-100 text-green-700','RECHAZADA':'bg-red-100 text-red-700','ENVIADA':'bg-blue-100 text-blue-700'}.get(estado,'bg-gray-100 text-gray-500')

def show_cotizaciones(container):
    ref = {}
    with container:
        with ui.row().classes('w-full items-center justify-between mb-6'):
            with ui.column().classes('gap-0'):
                ui.label('Cotizaciones').classes('text-3xl font-black text-gray-900')
                ui.label('Presupuestos para clientes - No afecta inventario').classes('text-sm text-gray-400 font-medium')
            ui.button('+ Nueva Cotizacion', on_click=lambda: _abrir_modal(ref['tabla'])).classes('btn-sandoval shadow-md px-6 h-10')
        tabla = ui.column().classes('w-full')
        ref['tabla'] = tabla
        _render_tabla(tabla)

def _render_tabla(container):
    container.clear()
    db = get_db()
    try:
        rows = db.query(Cotizacion).order_by(Cotizacion.fecha_creacion.desc()).all()
        with container:
            if not rows:
                with ui.card().classes('w-full p-12 text-center border border-dashed border-gray-200'):
                    ui.icon('request_quote', size='48px').classes('text-gray-300 mb-3')
                    ui.label('Sin cotizaciones aun').classes('text-gray-400 text-lg font-semibold')
                    ui.label('Crea una desde el boton o pidele a Jarvis por Telegram').classes('text-gray-300 text-sm mt-1')
                return
            with ui.card().classes('w-full shadow-sm border border-gray-100'):
                with ui.row().classes('w-full bg-gray-50 px-6 py-3 rounded-t-xl text-xs font-black text-gray-400 uppercase tracking-widest'):
                    ui.label('Numero').classes('w-44')
                    ui.label('Cliente').classes('flex-1')
                    ui.label('Fecha').classes('w-32')
                    ui.label('Total').classes('w-28 text-right')
                    ui.label('Estado').classes('w-28 text-center')
                    ui.label('Acciones').classes('w-36 text-center')
                for c in rows:
                    _fila(c, container)
    finally:
        db.close()

def _fila(c, tabla_ref):
    with ui.row().classes('w-full px-6 py-4 items-center border-t border-gray-50 hover:bg-blue-50/30 transition-colors'):
        ui.label(c.numero).classes('w-44 font-mono text-sm font-bold text-[#274495]')
        ui.label(c.nombre_cliente or '-').classes('flex-1 text-sm text-gray-700')
        ui.label(c.fecha_creacion.strftime('%d/%m/%Y') if c.fecha_creacion else '-').classes('w-32 text-sm text-gray-500')
        ui.label(f'S/ {c.total:.2f}').classes('w-28 text-right text-sm font-bold text-gray-800')
        with ui.element('div').classes('w-28 flex justify-center'):
            ui.label(c.estado).classes(f'text-xs font-bold px-3 py-1 rounded-full {_estado_color(c.estado)}')
        with ui.row().classes('w-36 justify-center gap-1'):
            ui.button(icon='visibility', on_click=lambda cid=c.id: _ver(cid, tabla_ref)).props('flat round dense color=blue-7').tooltip('Ver')
            ui.button(icon='picture_as_pdf', on_click=lambda cid=c.id: _pdf(cid)).props('flat round dense color=red-7').tooltip('PDF')
            ui.button(icon='delete', on_click=lambda cid=c.id, tr=tabla_ref: _eliminar(cid, tr)).props('flat round dense color=red-4').tooltip('Eliminar')

def _abrir_modal(tabla_ref):
    items_temp = []
    with ui.dialog() as dlg, ui.card().classes('w-full max-w-3xl p-0 overflow-hidden shadow-2xl'):
        with ui.row().classes('w-full bg-[#274495] px-8 py-5 items-center justify-between'):
            with ui.column().classes('gap-0'):
                ui.label('Nueva Cotizacion').classes('text-xl font-black text-white')
                ui.label('Los items NO se descuentan del inventario').classes('text-xs text-blue-200 mt-0.5')
            ui.button(icon='close', on_click=dlg.close).props('flat round color=white')
        with ui.column().classes('w-full p-8 gap-6'):
            with ui.row().classes('w-full gap-4'):
                nombre_in = ui.input('Nombre del cliente *').props('outlined dense').classes('flex-1')
                cid_ref = {'v': None}
                db = get_db()
                try:
                    clientes = db.query(Cliente).order_by(Cliente.nombre).all()
                    ops = {f"{c.nombre} {c.apellidos or ''}".strip(): c.id for c in clientes}
                finally:
                    db.close()
                def on_sel(e):
                    nombre_in.value = e.value
                    cid_ref['v'] = ops.get(e.value)
                ui.select(list(ops.keys()), label='Buscar cliente', on_change=on_sel, with_input=True, clearable=True).props('outlined dense').classes('flex-1')
            with ui.row().classes('w-full gap-3'):
                placa_in    = ui.input('Placa', placeholder='Ej: ABC-123').props('outlined dense').classes('w-36')
                vehiculo_in = ui.input('Vehiculo', placeholder='Ej: Toyota Corolla 2020').props('outlined dense').classes('flex-1')
                km_in       = ui.input('Kilometraje', placeholder='Ej: 45000').props('outlined dense').classes('w-36')
            nota_in = ui.textarea('Nota / Observaciones').props('outlined dense rows=2').classes('w-full')
            ui.separator()
            items_box = ui.column().classes('w-full gap-2')
            total_lbl = ui.label('TOTAL: S/ 0.00').classes('text-2xl font-black text-[#274495] text-right w-full')
            def recalc():
                t = sum(int(x.get('cantidad',1))*float(x.get('precio_unitario',0)) for x in items_temp)
                total_lbl.text = f'TOTAL: S/ {t:.2f}'
            def render_items():
                items_box.clear()
                with items_box:
                    if not items_temp:
                        ui.label('Sin items aun').classes('text-gray-300 text-sm italic py-2')
                        return
                    for i, it in enumerate(items_temp):
                        with ui.card().classes('w-full p-3 border border-gray-100'):
                            with ui.row().classes('w-full items-center gap-3'):
                                ico = 'inventory_2' if it.get('tipo')=='repuesto' else 'build'
                                ui.icon(ico, size='18px').classes('text-blue-600' if it.get('tipo')=='repuesto' else 'text-orange-600')
                                d = ui.input(placeholder='Descripcion', value=it.get('descripcion','')).props('dense borderless').classes('flex-1 bg-white rounded px-2')
                                q = ui.number(label='Cant.', value=it.get('cantidad',1), min=1, step=1).props('dense outlined').classes('w-20')
                                p = ui.number(label='Precio', value=it.get('precio_unitario',0), min=0, step=0.5, prefix='S/').props('dense outlined').classes('w-32')
                                def mk(idx,dd,qq,pp):
                                    def u(_=None):
                                        items_temp[idx]['descripcion']=dd.value or ''
                                        items_temp[idx]['cantidad']=int(qq.value or 1)
                                        items_temp[idx]['precio_unitario']=float(pp.value or 0)
                                        items_temp[idx]['subtotal']=items_temp[idx]['cantidad']*items_temp[idx]['precio_unitario']
                                        recalc()
                                    return u
                                u=mk(i,d,q,p)
                                d.on('blur',u); q.on('update:model-value',u); p.on('update:model-value',u)
                                def mk_del(idx):
                                    def fn(): items_temp.pop(idx); render_items(); recalc()
                                    return fn
                                ui.button(icon='close', on_click=mk_del(i)).props('flat round dense color=red-4')
            with ui.row().classes('gap-2 mt-1'):
                def add(tipo):
                    items_temp.append({'descripcion':'','tipo':tipo,'cantidad':1,'precio_unitario':0.0,'subtotal':0.0})
                    render_items()
                ui.button('+ Repuesto', icon='inventory_2', on_click=lambda: add('repuesto')).props('outlined dense color=blue-7').classes('text-xs')
                ui.button('+ Mano de Obra', icon='build', on_click=lambda: add('mano_obra')).props('outlined dense color=orange-7').classes('text-xs')
            render_items()
            ui.separator()
            with ui.row().classes('w-full justify-end gap-3 pt-2'):
                ui.button('Cancelar', on_click=dlg.close).props('flat color=gray-6')
                async def guardar():
                    nombre = (nombre_in.value or '').strip()
                    if not nombre: ui.notify('Ingresa el nombre del cliente', type='warning'); return
                    if not items_temp: ui.notify('Agrega al menos un item', type='warning'); return
                    total = sum(int(x.get('cantidad',1))*float(x.get('precio_unitario',0)) for x in items_temp)
                    db2 = get_db()
                    try:
                        num = _gen_numero()
                        nota_final = nota_in.value or ''
                        extra = []
                        if placa_in.value: extra.append(f"Placa: {placa_in.value.strip().upper()}")
                        if vehiculo_in.value: extra.append(f"Vehículo: {vehiculo_in.value.strip()}")
                        if km_in.value: extra.append(f"KM: {km_in.value.strip()}")
                        if extra: nota_final = ' | '.join(extra) + (' | ' + nota_final if nota_final else '')
                        cot = Cotizacion(numero=num, nombre_cliente=nombre, cliente_id=cid_ref['v'], nota=nota_final, total=total, estado='PENDIENTE', creado_por=(get_current_user() or {}).get('nombre','Sistema'))
                        db2.add(cot); db2.flush()
                        for x in items_temp:
                            qty=int(x.get('cantidad',1)); pr=float(x.get('precio_unitario',0))
                            db2.add(CotizacionItem(cotizacion_id=cot.id, descripcion=x.get('descripcion',''), tipo=x.get('tipo','repuesto'), cantidad=qty, precio_unitario=pr, subtotal=qty*pr))
                        db2.commit()
                        log_actividad(f'Cotizacion {num} creada','cotizaciones',f'Cliente: {nombre}')
                        ui.notify(f'Cotizacion {num} creada', type='positive')
                        dlg.close(); _render_tabla(tabla_ref)
                    except Exception:
                        db2.rollback(); ui.notify('Error al guardar', type='negative'); print(traceback.format_exc())
                    finally:
                        db2.close()
                ui.button('Guardar', icon='save', on_click=guardar).classes('btn-sandoval px-6')
    dlg.open()

def _ver(cotizacion_id, tabla_ref):
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
                with ui.row().classes('w-full items-center gap-3'):
                    ui.label(c.estado).classes(f'text-sm font-bold px-4 py-1 rounded-full {_estado_color(c.estado)}')
                    ui.label(f'Creada: {c.fecha_creacion.strftime("%d/%m/%Y %H:%M") if c.fecha_creacion else "-"}').classes('text-xs text-gray-400')
                    ui.label(f'Por: {c.creado_por or "-"}').classes('text-xs text-gray-400')
                if c.nota:
                    ui.label(c.nota).classes('text-sm text-gray-600 bg-gray-50 rounded-lg px-4 py-3 w-full italic')
                ui.separator()
                for it in c.items:
                    with ui.row().classes('w-full justify-between items-center px-3 py-2 bg-gray-50 rounded-lg border border-gray-100'):
                        with ui.row().classes('items-center gap-2 flex-1'):
                            ui.icon('inventory_2' if it.tipo=='repuesto' else 'build', size='16px').classes('text-blue-600' if it.tipo=='repuesto' else 'text-orange-600')
                            ui.label(it.descripcion).classes('text-sm text-gray-700')
                        ui.label(f'{it.cantidad} x S/ {it.precio_unitario:.2f}').classes('text-xs text-gray-400 mx-4')
                        ui.label(f'S/ {it.subtotal:.2f}').classes('text-sm font-bold text-gray-800 w-24 text-right')
                ui.separator()
                ui.label(f'TOTAL: S/ {c.total:.2f}').classes('text-2xl font-black text-[#274495] text-right w-full')
                estados=['PENDIENTE','ENVIADA','APROBADA','RECHAZADA']
                with ui.row().classes('w-full justify-between items-center pt-2'):
                    est_sel=ui.select(estados, value=c.estado, label='Cambiar estado').props('outlined dense').classes('w-40')
                    async def cambiar():
                        db2=get_db()
                        try:
                            co=db2.query(Cotizacion).filter_by(id=cotizacion_id).first()
                            if co: co.estado=est_sel.value; db2.commit(); ui.notify('Actualizado',type='positive'); dlg.close(); _render_tabla(tabla_ref)
                        finally: db2.close()
                    ui.button('Actualizar estado', icon='check', on_click=cambiar).props('outlined color=blue-7 dense')
                    ui.button('PDF', icon='picture_as_pdf', on_click=lambda: _pdf(cotizacion_id)).props('outlined color=red-7 dense')
        dlg.open()
    finally:
        db.close()

def _pdf(cotizacion_id):
    try:
        from utils.models import get_db, Cotizacion, Cliente
        from utils.pdf_generator import generate_cotizacion
        import os
        db = get_db()
        try:
            cot = db.query(Cotizacion).filter_by(id=cotizacion_id).first()
            if not cot:
                ui.notify('Cotizacion no encontrada', type='negative')
                return
            # Cliente
            client = {'nombre': cot.nombre_cliente, 'apellidos': '', 'id': '', 'telefono': ''}
            if cot.cliente_id:
                c = db.query(Cliente).filter_by(id=cot.cliente_id).first()
                if c:
                    client = {'nombre': c.nombre, 'apellidos': c.apellidos or '', 'id': str(c.id), 'telefono': c.telefono or ''}
            # Parsear placa, vehiculo, km desde nota
            nota = cot.nota or ''
            placa = ''; vehiculo = ''; km = ''; motivo = nota
            for parte in nota.split('|'):
                parte = parte.strip()
                if parte.startswith('Placa:'): placa = parte.replace('Placa:','').strip()
                elif parte.startswith('Vehículo:'): vehiculo = parte.replace('Vehículo:','').strip()
                elif parte.startswith('KM:'): km = parte.replace('KM:','').strip()
                else: motivo = parte
            # Vehiculo: intentar buscar por placa
            marca = ''; modelo = ''
            if placa:
                from utils.models import Vehiculo
                v = db.query(Vehiculo).filter_by(placa=placa).first()
                if v: marca = v.marca or ''; modelo = v.modelo or ''
            if vehiculo and not marca:
                partes = vehiculo.split(' ', 1)
                marca = partes[0]; modelo = partes[1] if len(partes) > 1 else ''
            order   = {'consecutivo': cot.numero, 'km': km, 'motivo': motivo}
            vehicle = {'placa': placa, 'marca': marca, 'modelo': modelo}
            items   = [{'item': it.descripcion, 'tipo': it.tipo, 'cantidad': it.cantidad,
                        'precio_unitario': it.precio_unitario, 'total': it.subtotal} for it in cot.items]
            os.makedirs('/var/www/sandoval/pdfs', exist_ok=True)
            filepath = f'/var/www/sandoval/pdfs/COT_{cot.numero.replace("-","_")}.pdf'
            generate_cotizacion(order, client, vehicle, items, filepath)
            ui.download(f'/pdfs/COT_{cot.numero.replace("-","_")}.pdf')
            ui.notify('PDF generado ✓', type='positive')
        finally:
            db.close()
    except Exception:
        ui.notify('Error generando PDF', type='negative')
        print(traceback.format_exc())

def _eliminar(cotizacion_id, tabla_ref):
    with ui.dialog() as dlg, ui.card().classes('p-6 max-w-sm'):
        ui.label('Eliminar cotizacion?').classes('text-lg font-bold text-gray-800 mb-2')
        ui.label('Esta accion no se puede deshacer.').classes('text-sm text-gray-500 mb-4')
        with ui.row().classes('w-full justify-end gap-3'):
            ui.button('Cancelar', on_click=dlg.close).props('flat color=gray')
            def fn():
                db=get_db()
                try:
                    co=db.query(Cotizacion).filter_by(id=cotizacion_id).first()
                    if co: db.delete(co); db.commit(); ui.notify('Eliminada',type='info')
                    dlg.close(); _render_tabla(tabla_ref)
                except Exception: db.rollback(); ui.notify('Error',type='negative')
                finally: db.close()
            ui.button('Eliminar', icon='delete', on_click=fn).props('color=red-7')
    dlg.open()

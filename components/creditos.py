"""
SANDOVAL Dashboard - Módulo de Créditos / Ventas al Fiado
Con integración de inventario, fecha de amortización y descuento de stock al pagar
"""
from nicegui import ui
from utils.models import get_db, log_actividad, ItemInventario
from utils.auth import get_current_user
from datetime import datetime, date
import traceback, json


def _get_creditos(filtro='todos'):
    from sqlalchemy import text
    db = get_db()
    try:
        db.execute(text("""UPDATE creditos SET estado='VENCIDO'
            WHERE fecha_amortizacion != '' AND fecha_amortizacion IS NOT NULL
            AND fecha_amortizacion < :hoy AND estado IN ('PENDIENTE','PARCIAL')"""),
            {'hoy': date.today().isoformat()})
        db.commit()
        rows = db.execute(text("SELECT * FROM creditos ORDER BY fecha_venta DESC")).fetchall()
        result = [dict(r._mapping) for r in rows]
        if filtro == 'pendientes':
            result = [r for r in result if r['estado'] in ('PENDIENTE','PARCIAL')]
        elif filtro == 'vencidos':
            result = [r for r in result if r['estado'] == 'VENCIDO']
        elif filtro == 'pagados':
            result = [r for r in result if r['estado'] == 'PAGADO']
        return result
    finally:
        db.close()

def _get_abonos(credito_id):
    from sqlalchemy import text
    db = get_db()
    try:
        rows = db.execute(text("SELECT * FROM abonos_credito WHERE credito_id=:cid ORDER BY fecha DESC"), {'cid': credito_id}).fetchall()
        return [dict(r._mapping) for r in rows]
    finally:
        db.close()

def _estado_color(estado):
    return {'PENDIENTE':'bg-yellow-100 text-yellow-700','PARCIAL':'bg-blue-100 text-blue-700',
            'PAGADO':'bg-green-100 text-green-700','VENCIDO':'bg-red-100 text-red-700'}.get(estado,'bg-gray-100 text-gray-500')

def _actualizar_estado(credito_id):
    from sqlalchemy import text
    db = get_db()
    try:
        cred = db.execute(text("SELECT * FROM creditos WHERE id=:id"), {'id': credito_id}).fetchone()
        if not cred: return
        cred = dict(cred._mapping)
        ab = db.execute(text("SELECT COALESCE(SUM(monto),0) as t FROM abonos_credito WHERE credito_id=:cid"), {'cid': credito_id}).fetchone()
        total_ab = float(ab._mapping['t'])
        pendiente = round(float(cred['total']) - total_ab, 2)
        fecha_amort = cred.get('fecha_amortizacion','')
        vencido = fecha_amort and fecha_amort < date.today().isoformat()
        if pendiente <= 0: estado = 'PAGADO'
        elif vencido: estado = 'VENCIDO'
        elif total_ab > 0: estado = 'PARCIAL'
        else: estado = 'PENDIENTE'
        era_pagado = cred.get('estado') == 'PAGADO'
        db.execute(text("UPDATE creditos SET pendiente=:p, estado=:e WHERE id=:id"), {'p': max(pendiente,0), 'e': estado, 'id': credito_id})
        db.commit()
        if estado == 'PAGADO' and not era_pagado:
            _descontar_stock(cred.get('items_json','[]'))
    finally:
        db.close()

def _descontar_stock(items_json):
    db = get_db()
    try:
        items = json.loads(items_json) if isinstance(items_json, str) else (items_json or [])
        for item in items:
            if item.get('item_id'):
                prod = db.query(ItemInventario).filter_by(codigo=item['item_id']).first()
                if prod:
                    prod.stock = max(0, prod.stock - int(item.get('cantidad', 1)))
        db.commit()
    except Exception:
        print(traceback.format_exc())
    finally:
        db.close()

def _init_tablas():
    from sqlalchemy import text
    db = get_db()
    try:
        db.execute(text("""CREATE TABLE IF NOT EXISTS creditos (
            id INTEGER PRIMARY KEY AUTOINCREMENT, cliente_nombre TEXT NOT NULL,
            telefono TEXT DEFAULT '', descripcion TEXT DEFAULT '',
            items_json TEXT DEFAULT '[]', total REAL DEFAULT 0,
            pendiente REAL DEFAULT 0, estado TEXT DEFAULT 'PENDIENTE',
            nota TEXT DEFAULT '', fecha_venta TEXT DEFAULT '',
            fecha_amortizacion TEXT DEFAULT '', creado_por TEXT DEFAULT '')"""))
        for col in ['items_json TEXT DEFAULT "[]"', 'fecha_amortizacion TEXT DEFAULT ""']:
            try: db.execute(text(f"ALTER TABLE creditos ADD COLUMN {col}"))
            except: pass
        db.execute(text("""CREATE TABLE IF NOT EXISTS abonos_credito (
            id INTEGER PRIMARY KEY AUTOINCREMENT, credito_id INTEGER NOT NULL,
            monto REAL DEFAULT 0, nota TEXT DEFAULT '', fecha TEXT DEFAULT '',
            metodo_pago TEXT DEFAULT 'Efectivo')"""))
        try:
            db.execute(text("ALTER TABLE abonos_credito ADD COLUMN metodo_pago TEXT DEFAULT 'Efectivo'"))
        except Exception:
            pass
        db.commit()
    finally:
        db.close()

def show_creditos(container):
    _init_tablas()
    ref = {'tabla': None}
    with container:
        with ui.row().classes('w-full items-center justify-between mb-6'):
            with ui.column().classes('gap-0'):
                ui.label('Créditos / Ventas al Fiado').classes('text-3xl font-black text-gray-900')
                ui.label('Stock se descuenta automáticamente al marcar como PAGADO').classes('text-sm text-gray-400')
            ui.button('+ Nuevo Crédito', on_click=lambda: _modal_nuevo(ref['tabla'])).classes('btn-sandoval shadow-md px-6 h-10')
        _render_kpis()
        with ui.row().classes('gap-2 mb-4'):
            for label, key in [('Todos','todos'),('Pendientes','pendientes'),('Vencidos','vencidos'),('Pagados','pagados')]:
                def mk(k): return lambda: _render_tabla(ref['tabla'], k)
                ui.button(label, on_click=mk(key)).props(f'{"unelevated" if key=="todos" else "outlined"} dense color=blue-7').classes('text-xs px-3')
        tabla = ui.column().classes('w-full')
        ref['tabla'] = tabla
        _render_tabla(tabla, 'todos')

def _render_kpis():
    from sqlalchemy import text
    db = get_db()
    try:
        rows = db.execute(text("SELECT estado, pendiente FROM creditos")).fetchall()
        deuda = sum(float(r._mapping['pendiente']) for r in rows if r._mapping['estado'] in ('PENDIENTE','PARCIAL','VENCIDO'))
        vencidos = sum(1 for r in rows if r._mapping['estado']=='VENCIDO')
        pagados = sum(1 for r in rows if r._mapping['estado']=='PAGADO')
        total = len(rows)
    finally:
        db.close()
    with ui.row().classes('w-full gap-4 mb-4'):
        for icon, label, valor, color in [
            ('account_balance_wallet','Por Cobrar',f'S/ {deuda:,.2f}','#274495'),
            ('people','Créditos',str(total),'#059669'),
            ('warning','Vencidos',str(vencidos),'#DC2626'),
            ('check_circle','Pagados',str(pagados),'#6B7280')]:
            with ui.card().classes('flex-1 p-4 bg-white border border-gray-100 shadow-sm rounded-xl'):
                with ui.row().classes('items-center gap-3'):
                    ui.icon(icon, size='28px').style(f'color:{color}')
                    with ui.column().classes('gap-0'):
                        ui.label(valor).classes('text-xl font-black text-gray-900')
                        ui.label(label).classes('text-xs text-gray-400 font-medium')

def _render_tabla(container, filtro='todos'):
    container.clear()
    creditos = _get_creditos(filtro)
    with container:
        if not creditos:
            with ui.card().classes('w-full p-12 text-center border border-dashed border-gray-200'):
                ui.icon('credit_card_off', size='48px').classes('text-gray-300 mb-3')
                ui.label('Sin créditos registrados').classes('text-gray-400 text-lg font-semibold')
            return
        with ui.card().classes('w-full shadow-sm border border-gray-100'):
            with ui.row().classes('w-full bg-gray-50 px-6 py-3 rounded-t-xl text-xs font-black text-gray-400 uppercase tracking-widest'):
                ui.label('Cliente').classes('flex-1')
                ui.label('Teléfono').classes('w-28')
                ui.label('Vence').classes('w-24')
                ui.label('Total').classes('w-24 text-right')
                ui.label('Pendiente').classes('w-24 text-right')
                ui.label('Estado').classes('w-24 text-center')
                ui.label('Acciones').classes('w-28 text-center')
            for c in creditos:
                _fila(c, container, filtro)

def _fila(c, tabla_ref, filtro):
    pendiente = float(c.get('pendiente',0))
    total = float(c.get('total',0))
    estado = c.get('estado','PENDIENTE')
    vence = c.get('fecha_amortizacion','') or '—'
    vencido = vence != '—' and vence < date.today().isoformat() and estado != 'PAGADO'
    with ui.row().classes('w-full px-6 py-4 items-center border-t border-gray-50 hover:bg-blue-50/30 transition-colors'):
        with ui.column().classes('flex-1 gap-0'):
            ui.label(c.get('cliente_nombre','—')).classes('text-sm font-bold text-gray-800')
            if c.get('nota'): ui.label(c['nota'][:40]).classes('text-xs text-gray-400 italic')
        ui.label(c.get('telefono','—')).classes('w-28 text-sm text-gray-500')
        ui.label(vence[:10] if vence != '—' else '—').classes(f'w-24 text-sm {"text-red-600 font-bold" if vencido else "text-gray-500"}')
        ui.label(f'S/ {total:.2f}').classes('w-24 text-right text-sm text-gray-700')
        ui.label(f'S/ {pendiente:.2f}').classes(f'w-24 text-right text-sm {"text-red-600 font-black" if pendiente>0 else "text-green-600 font-bold"}')
        with ui.element('div').classes('w-24 flex justify-center'):
            ui.label(estado).classes(f'text-xs font-bold px-2 py-1 rounded-full {_estado_color(estado)}')
        with ui.row().classes('w-28 justify-center gap-1'):
            ui.button(icon='payments', on_click=lambda cid=c['id']: _modal_abono(cid, tabla_ref, filtro)).props('flat round dense color=green-7').tooltip('Abonar')
            ui.button(icon='visibility', on_click=lambda cid=c['id']: _modal_detalle(cid, tabla_ref, filtro)).props('flat round dense color=blue-7').tooltip('Detalle')
            ui.button(icon='delete', on_click=lambda cid=c['id']: _confirmar_eliminar(cid, tabla_ref, filtro)).props('flat round dense color=red-4').tooltip('Eliminar')

def _modal_nuevo(tabla_ref):
    items_state = []
    with ui.dialog() as dlg, ui.card().classes('w-full max-w-3xl p-0 overflow-hidden shadow-2xl').style('max-height:90vh;display:flex;flex-direction:column'):
        with ui.row().classes('w-full bg-[#274495] px-8 py-5 items-center justify-between'):
            with ui.column().classes('gap-0'):
                ui.label('Nuevo Crédito / Fiado').classes('text-xl font-black text-white')
                ui.label('Stock NO se descuenta hasta que esté PAGADO').classes('text-xs text-blue-200')
            ui.button(icon='close', on_click=dlg.close).props('flat round color=white')
        with ui.scroll_area().style('height:75vh;width:100%'):
            with ui.column().classes('w-full p-8 gap-5'):
                ui.label('DATOS DEL CLIENTE').classes('text-xs font-black text-gray-400 tracking-widest')
            with ui.row().classes('w-full gap-3'):
                nombre_in = ui.input('Nombre *').props('outlined dense').classes('flex-1')
                tel_in = ui.input('Teléfono *').props('outlined dense').classes('w-40')
                amort_in_ref = {'v': ''}
            db = get_db()
            try:
                from utils.models import Cliente
                clientes = db.query(Cliente).order_by(Cliente.nombre).all()
                ops = {f"{c.nombre} {c.apellidos or ''}".strip()+f" ({c.telefono or 'sin tel'})": {'nombre': f"{c.nombre} {c.apellidos or ''}".strip(), 'tel': c.telefono or ''} for c in clientes}
            finally:
                db.close()
            def on_sel(e):
                if e.value and e.value in ops:
                    nombre_in.value = ops[e.value]['nombre']
                    tel_in.value = ops[e.value]['tel']
            ui.select(list(ops.keys()), label='Buscar cliente registrado (opcional)', on_change=on_sel, with_input=True, clearable=True).props('outlined dense').classes('w-full')
            ui.separator()
            ui.label('PRODUCTOS').classes('text-xs font-black text-gray-400 tracking-widest')
            ui.label('⚠️ El stock NO se descuenta hasta que el crédito esté PAGADO').classes('text-xs text-orange-500')
            items_container = ui.column().classes('w-full gap-2')
            total_label = ui.label('TOTAL: S/ 0.00').classes('text-xl font-black text-gray-900 text-right w-full')
            def recalc():
                t = sum(float(it.get('precio',0))*int(it.get('cantidad',1)) for it in items_state)
                total_label.text = f'TOTAL: S/ {t:.2f}'
            def render_items():
                items_container.clear()
                with items_container:
                    if not items_state:
                        ui.label('Sin productos — busca abajo para agregar').classes('text-sm text-gray-300 italic py-2')
                    for i, item in enumerate(items_state):
                        with ui.row().classes('w-full items-center gap-2 bg-blue-50 rounded-lg px-3 py-2'):
                            with ui.column().classes('flex-1 gap-0'):
                                ui.label(item['nombre']).classes('text-sm font-bold text-gray-800')
                                ui.label(f'Stock actual: {item.get("stock_actual",0)}').classes('text-xs text-gray-400')
                            def make_cant_handler(idx):
                                def h(e):
                                    try:
                                        items_state[idx]['cantidad'] = max(1, int(float(e.args if e.args else 1)))
                                        recalc()
                                    except: pass
                                return h
                            def make_price_handler(idx):
                                def h(e):
                                    try:
                                        items_state[idx]['precio'] = max(0, float(e.args if e.args else 0))
                                        recalc()
                                    except: pass
                                return h
                            cant = ui.number(value=item.get('cantidad',1), min=1, label='Cant').props('outlined dense').classes('w-20')
                            cant.on('update:model-value', make_cant_handler(i))
                            precio = ui.number(value=item.get('precio',0), min=0, step=0.5, prefix='S/', label='Precio').props('outlined dense').classes('w-28')
                            precio.on('update:model-value', make_price_handler(i))
                            subtotal = float(item.get('precio',0))*int(item.get('cantidad',1))
                            ui.label(f'S/ {subtotal:.2f}').classes('w-20 text-right text-sm font-bold text-blue-700')
                            ui.button(icon='close', on_click=lambda idx=i: [items_state.pop(idx), render_items(), recalc()]).props('flat round dense color=red-4')
                recalc()
            render_items()
            prod_map = {}
            # ── MANO DE OBRA ─────────────────────────────────────────────
            with ui.row().classes('w-full gap-2 items-center mb-2'):
                mo_desc = ui.input('Mano de obra (descripción)').props('outlined dense').classes('flex-1')
                mo_precio = ui.number(value=0, min=0, step=5, prefix='S/', label='Precio').props('outlined dense').classes('w-28')
                def agregar_mo():
                    desc = (mo_desc.value or '').strip()
                    precio = float(mo_precio.value or 0)
                    if not desc:
                        ui.notify('Escribe la descripción', type='warning'); return
                    if precio <= 0:
                        ui.notify('Precio debe ser mayor a 0', type='warning'); return
                    items_state.append({'item_id': None, 'nombre': f'🔧 {desc}', 'precio': precio, 'cantidad': 1, 'stock_actual': 0, 'tipo': 'mano_obra'})
                    mo_desc.value = ''
                    mo_precio.value = 0
                    render_items()
                ui.button('+ Mano de Obra', icon='build', on_click=agregar_mo).props('outlined color=orange-7 dense').classes('h-10 text-xs')
            ui.separator().classes('my-1')
            with ui.row().classes('w-full gap-2 items-end'):
                buscar_in = ui.input('Buscar producto...').props('outlined dense').classes('flex-1')
                prod_sel = ui.select([], label='Selecciona producto', with_input=True, clearable=True).props('outlined dense').classes('flex-1')
                def buscar(e=None):
                    texto = (buscar_in.value or '').strip()
                    if len(texto) < 2:
                        ui.notify('Escribe al menos 2 caracteres', type='warning')
                        return
                    db2 = get_db()
                    try:
                        prods = db2.query(ItemInventario).filter(ItemInventario.nombre.ilike(f'%{texto}%')).limit(10).all()
                        if not prods:
                            ui.notify(f'No se encontraron productos con "{texto}"', type='warning')
                            return
                        prod_map.clear()
                        for p in prods:
                            k = f'{p.nombre} — S/{p.precio:.2f} (stock:{p.stock})'
                            prod_map[k] = {'item_id': p.codigo, 'nombre': p.nombre, 'precio': float(p.precio), 'stock': p.stock}
                        prod_sel.options = list(prod_map.keys())
                        prod_sel.value = None
                        prod_sel.update()
                        ui.notify(f'{len(prods)} producto(s) encontrado(s)', type='positive')
                    finally:
                        db2.close()
                buscar_in.on('keyup.enter', buscar)
                def agregar():
                    sel = prod_sel.value
                    if not sel: ui.notify('Selecciona un producto del dropdown', type='warning'); return
                    if sel not in prod_map: ui.notify('Busca primero el producto', type='warning'); return
                    p = prod_map[sel]
                    items_state.append({'item_id': p['item_id'], 'nombre': p['nombre'], 'precio': float(p['precio']), 'cantidad': 1, 'stock_actual': int(p['stock'])})
                    render_items()
                    prod_sel.set_value(None)
                ui.button('Buscar', icon='search', on_click=buscar).props('outlined dense color=blue-7')
                ui.button('+ Agregar', icon='add', on_click=agregar).props('unelevated dense color=blue-7')
            nota_in = ui.input('Nota (opcional)').props('outlined dense').classes('w-full')
            with ui.row().classes('w-full justify-end gap-3 pt-2'):
                ui.button('Cancelar', on_click=dlg.close).props('flat color=gray-6')
                async def guardar():
                    nombre = (nombre_in.value or '').strip()
                    tel = (tel_in.value or '').strip()
                    if not nombre: ui.notify('Ingresa el nombre', type='warning'); return
                    if not tel: ui.notify('Ingresa el teléfono', type='warning'); return
                    if not items_state: ui.notify('Agrega al menos un producto', type='warning'); return
                    total = sum(float(it.get('precio',0))*int(it.get('cantidad',1)) for it in items_state)
                    desc = ', '.join(f"{it['cantidad']}x {it['nombre']}" for it in items_state)
                    from sqlalchemy import text as sqlt
                    db2 = get_db()
                    try:
                        db2.execute(sqlt("""INSERT INTO creditos (cliente_nombre,telefono,descripcion,items_json,total,pendiente,estado,nota,fecha_venta,fecha_amortizacion,creado_por)
                            VALUES (:cn,:tel,:desc,:items,:total,:total,'PENDIENTE',:nota,:fecha,:amort,:user)"""),
                            {'cn':nombre,'tel':tel,'desc':desc,'items':json.dumps(items_state),'total':total,
                             'nota':(nota_in.value or '').strip(),'fecha':datetime.now().isoformat(),
                             'amort':amort_in_ref.get('v',''),'user':(get_current_user() or {}).get('nombre','Sistema')})
                        db2.commit()
                        ui.notify(f'Crédito S/ {total:.2f} para {nombre} registrado ✓', type='positive')
                        dlg.close(); _render_tabla(tabla_ref, 'todos')
                    except Exception:
                        db2.rollback(); ui.notify('Error al guardar', type='negative'); print(traceback.format_exc())
                    finally:
                        db2.close()
                ui.button('Guardar Crédito', icon='save', on_click=guardar).classes('btn-sandoval px-6')
    dlg.open()

def _modal_abono(credito_id, tabla_ref, filtro):
    from sqlalchemy import text
    db = get_db()
    try:
        cred = db.execute(text("SELECT * FROM creditos WHERE id=:id"), {'id': credito_id}).fetchone()
        if not cred: ui.notify('No encontrado', type='warning'); return
        cred = dict(cred._mapping)
    finally:
        db.close()
    pendiente = float(cred.get('pendiente',0))
    with ui.dialog() as dlg, ui.card().classes('w-full max-w-md p-0 overflow-hidden shadow-2xl'):
        with ui.row().classes('w-full bg-green-700 px-8 py-5 items-center justify-between'):
            with ui.column().classes('gap-0'):
                ui.label('Registrar Abono').classes('text-xl font-black text-white')
                ui.label(cred['cliente_nombre']).classes('text-sm text-green-200')
            ui.button(icon='close', on_click=dlg.close).props('flat round color=white')
        with ui.column().classes('w-full p-8 gap-4'):
            ui.label(f'Pendiente: S/ {pendiente:.2f}').classes('text-2xl font-black text-red-600')
            if cred.get('fecha_amortizacion'):
                venc = cred['fecha_amortizacion'] < date.today().isoformat()
                ui.label(f'Fecha límite: {cred["fecha_amortizacion"]} {"⚠️ VENCIDO" if venc else ""}').classes(f'text-sm {"text-red-500 font-bold" if venc else "text-gray-500"}')
            monto_in = ui.number('Monto S/ *', min=0.5, step=0.5, max=pendiente, prefix='S/').props('outlined dense').classes('w-full')
            metodo_abono = ui.select(['Efectivo', 'Yape', 'Transferencia', 'Tarjeta'], value='Efectivo', label='Método de pago').props('outlined dense').classes('w-full')
            nota_in = ui.input('Nota (opcional)').props('outlined dense').classes('w-full')
            with ui.row().classes('w-full justify-end gap-3 pt-2'):
                ui.button('Cancelar', on_click=dlg.close).props('flat color=gray-6')
                async def abonar():
                    monto = float(monto_in.value or 0)
                    if monto <= 0: ui.notify('Ingresa el monto', type='warning'); return
                    from sqlalchemy import text as sqlt
                    db2 = get_db()
                    try:
                        db2.execute(sqlt("INSERT INTO abonos_credito (credito_id,monto,nota,fecha,metodo_pago) VALUES (:cid,:monto,:nota,:fecha,:mp)"),
                            {'cid':credito_id,'monto':monto,'nota':(nota_in.value or '').strip(),'fecha':datetime.now().isoformat(),'mp':metodo_abono.value or 'Efectivo'})
                        db2.commit()
                        _actualizar_estado(credito_id)
                        ui.notify(f'Abono S/ {monto:.2f} registrado ✓', type='positive')
                        dlg.close(); _render_tabla(tabla_ref, filtro)
                    except Exception:
                        db2.rollback(); ui.notify('Error', type='negative'); print(traceback.format_exc())
                    finally:
                        db2.close()
                ui.button('Registrar Abono', icon='payments', on_click=abonar).classes('bg-green-700 text-white px-6 rounded-lg font-bold')
    dlg.open()

def _modal_detalle(credito_id, tabla_ref, filtro):
    from sqlalchemy import text
    db = get_db()
    try:
        cred = db.execute(text("SELECT * FROM creditos WHERE id=:id"), {'id': credito_id}).fetchone()
        if not cred: ui.notify('No encontrado', type='warning'); return
        cred = dict(cred._mapping)
        abonos = _get_abonos(credito_id)
    finally:
        db.close()
    items = json.loads(cred.get('items_json','[]') or '[]')
    with ui.dialog() as dlg, ui.card().classes('w-full max-w-xl p-0 shadow-2xl overflow-hidden'):
        with ui.row().classes('w-full bg-[#274495] px-8 py-5 items-center justify-between'):
            with ui.column().classes('gap-0'):
                ui.label(cred['cliente_nombre']).classes('text-xl font-black text-white')
                ui.label(f"Tel: {cred.get('telefono','—')}").classes('text-sm text-blue-200')
            ui.button(icon='close', on_click=dlg.close).props('flat round color=white')
        with ui.column().classes('p-8 gap-4 w-full'):
            with ui.row().classes('w-full items-center gap-4 flex-wrap'):
                ui.label(cred['estado']).classes(f'text-sm font-bold px-4 py-1 rounded-full {_estado_color(cred["estado"])}')
                ui.label(f'Total: S/ {float(cred["total"]):.2f}').classes('text-sm text-gray-600')
                ui.label(f'Pendiente: S/ {float(cred["pendiente"]):.2f}').classes('text-sm font-black text-red-600')
                if cred.get('fecha_amortizacion'):
                    ui.label(f'Vence: {cred["fecha_amortizacion"]}').classes('text-sm text-orange-600 font-semibold')
            if items:
                ui.separator()
                ui.label('PRODUCTOS').classes('text-xs font-black text-gray-400 tracking-widest')
                for it in items:
                    with ui.row().classes('w-full justify-between px-2 py-1 bg-blue-50 rounded'):
                        ui.label(f'{it.get("cantidad",1)}x {it["nombre"]}').classes('text-sm text-gray-700')
                        ui.label(f'S/ {float(it.get("precio",0))*int(it.get("cantidad",1)):.2f}').classes('text-sm font-bold text-blue-700')
            elif cred.get('descripcion'):
                ui.label(cred['descripcion']).classes('text-sm text-gray-700 bg-gray-50 rounded-lg px-4 py-3 w-full')
            if cred.get('nota'): ui.label(f'📝 {cred["nota"]}').classes('text-xs text-gray-500 italic')
            ui.separator()
            ui.label('HISTORIAL DE ABONOS').classes('text-xs font-black text-gray-400 tracking-widest')
            if not abonos:
                ui.label('Sin abonos aún').classes('text-sm text-gray-300 italic py-2')
            else:
                total_ab = 0
                for a in abonos:
                    m = float(a['monto']); total_ab += m
                    with ui.row().classes('w-full justify-between items-center px-3 py-2 bg-green-50 rounded-lg border border-green-100'):
                        with ui.column().classes('gap-0'):
                            ui.label(f'S/ {m:.2f}').classes('text-sm font-bold text-green-700')
                            if a.get('nota'): ui.label(a['nota']).classes('text-xs text-gray-400')
                        ui.label(str(a['fecha'])[:16]).classes('text-xs text-gray-400')
                ui.separator()
                ui.label(f'Total abonado: S/ {total_ab:.2f}').classes('text-sm font-bold text-green-700 text-right w-full')
            ui.separator()
            with ui.row().classes('w-full justify-between pt-2'):
                est_sel = ui.select(['PENDIENTE','PARCIAL','PAGADO','VENCIDO'], value=cred['estado'], label='Cambiar estado').props('outlined dense').classes('w-40')
                async def cambiar():
                    from sqlalchemy import text as sqlt
                    db2 = get_db()
                    try:
                        era_pagado = cred['estado'] == 'PAGADO'
                        db2.execute(sqlt("UPDATE creditos SET estado=:e WHERE id=:id"), {'e':est_sel.value,'id':credito_id})
                        db2.commit()
                        if est_sel.value == 'PAGADO' and not era_pagado:
                            _descontar_stock(cred.get('items_json','[]'))
                            ui.notify('Estado PAGADO — stock descontado del inventario ✓', type='positive')
                        else:
                            ui.notify('Estado actualizado ✓', type='positive')
                        dlg.close(); _render_tabla(tabla_ref, filtro)
                    finally:
                        db2.close()
                ui.button('Actualizar', icon='check', on_click=cambiar).props('outlined color=blue-7 dense')
                ui.button('Editar', icon='edit', on_click=lambda: [dlg.close(), _modal_editar(credito_id, tabla_ref, filtro)]).props('outlined color=orange-7 dense')
                ui.button('Registrar Abono', icon='payments', on_click=lambda: [dlg.close(), _modal_abono(credito_id, tabla_ref, filtro)]).classes('bg-green-700 text-white px-4 rounded-lg text-sm font-bold')
    dlg.open()

def _confirmar_eliminar(credito_id, tabla_ref, filtro):
    with ui.dialog() as dlg, ui.card().classes('p-6 max-w-sm'):
        ui.label('¿Eliminar crédito?').classes('text-lg font-bold text-gray-800 mb-2')
        ui.label('Se eliminarán también todos los abonos.').classes('text-sm text-gray-500 mb-4')
        with ui.row().classes('w-full justify-end gap-3'):
            ui.button('Cancelar', on_click=dlg.close).props('flat color=gray')
            def fn():
                from sqlalchemy import text
                db = get_db()
                try:
                    db.execute(text("DELETE FROM abonos_credito WHERE credito_id=:id"), {'id': credito_id})
                    db.execute(text("DELETE FROM creditos WHERE id=:id"), {'id': credito_id})
                    db.commit(); ui.notify('Eliminado', type='info'); dlg.close(); _render_tabla(tabla_ref, filtro)
                except Exception:
                    db.rollback(); ui.notify('Error', type='negative')
                finally:
                    db.close()
            ui.button('Eliminar', icon='delete', on_click=fn).props('color=red-7')
    dlg.open()

def crear_credito_desde_nota(nota_venta_id, cliente_nombre, telefono, descripcion, total, creado_por='Sistema'):
    _init_tablas()
    from sqlalchemy import text
    db = get_db()
    try:
        db.execute(text("INSERT INTO creditos (cliente_nombre,telefono,descripcion,total,pendiente,estado,nota,fecha_venta,creado_por) VALUES (:cn,:tel,:desc,:total,:total,'PENDIENTE',:nota,:fecha,:user)"),
            {'cn':cliente_nombre,'tel':telefono,'desc':descripcion,'total':total,'nota':f'Nota de Venta #{nota_venta_id}','fecha':datetime.now().isoformat(),'user':creado_por})
        db.commit(); return True
    except Exception:
        db.rollback(); print(traceback.format_exc()); return False
    finally:
        db.close()

def _modal_editar(credito_id, tabla_ref, filtro):
    """Modal para editar items de un crédito existente"""
    from sqlalchemy import text
    db = get_db()
    try:
        cred = db.execute(text("SELECT * FROM creditos WHERE id=:id"), {'id': credito_id}).fetchone()
        if not cred: ui.notify('No encontrado', type='warning'); return
        cred = dict(cred._mapping)
    finally:
        db.close()

    items_state = json.loads(cred.get('items_json','[]') or '[]')

    with ui.dialog() as dlg, ui.card().classes('w-full max-w-3xl p-0 overflow-hidden shadow-2xl').style('max-height:90vh;display:flex;flex-direction:column'):
        with ui.row().classes('w-full bg-[#e97316] px-8 py-5 items-center justify-between'):
            with ui.column().classes('gap-0'):
                ui.label(f'Editando: {cred["cliente_nombre"]}').classes('text-xl font-black text-white')
                ui.label('Agrega, quita o modifica productos y servicios').classes('text-xs text-orange-100')
            ui.button(icon='close', on_click=dlg.close).props('flat round color=white')

        with ui.scroll_area().style('height:75vh;width:100%'):
            with ui.column().classes('p-6 gap-4 w-full'):
                total_label = ui.label(f'TOTAL: S/ 0.00').classes('text-xl font-black text-gray-900 text-right w-full')

                def recalc():
                    t = sum(float(it.get('precio',0))*int(it.get('cantidad',1)) for it in items_state)
                    total_label.text = f'TOTAL: S/ {t:.2f}'

                items_container = ui.column().classes('w-full gap-2')

                def render_items():
                    items_container.clear()
                    with items_container:
                        if not items_state:
                            ui.label('Sin items — agrega abajo').classes('text-sm text-gray-300 italic py-2')
                        for i, item in enumerate(items_state):
                            bg = 'bg-orange-50' if item.get('tipo') == 'mano_obra' else 'bg-blue-50'
                            with ui.row().classes(f'w-full items-center gap-2 {bg} rounded-lg px-3 py-2'):
                                with ui.column().classes('flex-1 gap-0'):
                                    ui.label(item['nombre']).classes('text-sm font-bold text-gray-800')
                                    if item.get('tipo') == 'mano_obra':
                                        ui.label('Mano de obra').classes('text-xs text-orange-500 font-medium')
                                    else:
                                        ui.label(f'Stock: {item.get("stock_actual",0)}').classes('text-xs text-gray-400')
                                def mk_cant(idx):
                                    def h(e):
                                        try:
                                            items_state[idx]['cantidad'] = max(1,int(float(e.args or 1)))
                                            recalc()
                                        except: pass
                                    return h
                                def mk_precio(idx):
                                    def h(e):
                                        try:
                                            items_state[idx]['precio'] = max(0,float(e.args or 0))
                                            recalc()
                                        except: pass
                                    return h
                                cant = ui.number(value=item.get('cantidad',1), min=1, label='Cant').props('outlined dense').classes('w-20')
                                cant.on('update:model-value', mk_cant(i))
                                precio = ui.number(value=item.get('precio',0), min=0, step=0.5, prefix='S/', label='Precio').props('outlined dense').classes('w-28')
                                precio.on('update:model-value', mk_precio(i))
                                subtotal = float(item.get('precio',0))*int(item.get('cantidad',1))
                                ui.label(f'S/ {subtotal:.2f}').classes('w-20 text-right text-sm font-bold text-blue-700')
                                ui.button(icon='close', on_click=lambda idx=i: [items_state.pop(idx), render_items(), recalc()]).props('flat round dense color=red-4')
                    recalc()

                render_items()
                recalc()

                ui.separator()
                # Mano de obra
                ui.label('AGREGAR MANO DE OBRA').classes('text-xs font-black text-orange-400 tracking-widest')
                with ui.row().classes('w-full gap-2 items-center'):
                    mo_desc = ui.input('Descripción').props('outlined dense').classes('flex-1')
                    mo_precio = ui.number(value=0, min=0, step=5, prefix='S/', label='Precio').props('outlined dense').classes('w-28')
                    def agregar_mo():
                        desc = (mo_desc.value or '').strip()
                        precio = float(mo_precio.value or 0)
                        if not desc: ui.notify('Escribe descripción', type='warning'); return
                        if precio <= 0: ui.notify('Precio > 0', type='warning'); return
                        items_state.append({'item_id': None, 'nombre': f'🔧 {desc}', 'precio': precio, 'cantidad': 1, 'stock_actual': 0, 'tipo': 'mano_obra'})
                        mo_desc.value = ''; mo_precio.value = 0
                        render_items()
                    ui.button('+ Agregar', icon='build', on_click=agregar_mo).props('outlined color=orange-7 dense').classes('h-10')

                ui.separator()
                # Productos inventario
                ui.label('AGREGAR PRODUCTO DEL INVENTARIO').classes('text-xs font-black text-blue-400 tracking-widest')
                prod_map = {}
                with ui.row().classes('w-full gap-2 items-end'):
                    buscar_in = ui.input('Buscar producto...').props('outlined dense').classes('flex-1')
                    prod_sel = ui.select([], label='Selecciona producto', with_input=True, clearable=True).props('outlined dense').classes('flex-1')
                    def buscar(e=None):
                        texto = (buscar_in.value or '').strip()
                        if len(texto) < 2: ui.notify('Mínimo 2 caracteres', type='warning'); return
                        db2 = get_db()
                        try:
                            prods = db2.query(ItemInventario).filter(ItemInventario.nombre.ilike(f'%{texto}%')).limit(10).all()
                            if not prods: ui.notify('Sin resultados', type='warning'); return
                            prod_map.clear()
                            for p in prods:
                                k = f'{p.nombre} — S/{p.precio:.2f} (stock:{p.stock})'
                                prod_map[k] = {'item_id': p.codigo, 'nombre': p.nombre, 'precio': float(p.precio), 'stock': p.stock}
                            prod_sel.options = list(prod_map.keys())
                            prod_sel.value = None
                            prod_sel.update()
                            ui.notify(f'{len(prods)} encontrado(s)', type='positive')
                        finally:
                            db2.close()
                    buscar_in.on('keyup.enter', buscar)
                    def agregar_prod():
                        sel = prod_sel.value
                        if not sel: ui.notify('Selecciona producto', type='warning'); return
                        if sel not in prod_map: return
                        p = prod_map[sel]
                        items_state.append({'item_id': p['item_id'], 'nombre': p['nombre'], 'precio': p['precio'], 'cantidad': 1, 'stock_actual': p['stock']})
                        prod_sel.value = None
                        render_items()
                    ui.button('BUSCAR', icon='search', on_click=buscar).props('outlined color=blue-7 dense').classes('h-10')
                    ui.button('+ AGREGAR', icon='add', on_click=agregar_prod).props('unelevated color=blue-7 dense').classes('h-10')

                ui.separator()
                # Guardar
                async def guardar():
                    from sqlalchemy import text as sqlt
                    total = sum(float(it.get('precio',0))*int(it.get('cantidad',1)) for it in items_state)
                    abonos = _get_abonos(credito_id)
                    total_ab = sum(float(a['monto']) for a in abonos)
                    pendiente = max(0, round(total - total_ab, 2))
                    if pendiente <= 0: estado = 'PAGADO'
                    elif total_ab > 0: estado = 'PARCIAL'
                    else: estado = 'PENDIENTE'
                    db3 = get_db()
                    try:
                        db3.execute(sqlt("UPDATE creditos SET items_json=:ij, total=:t, pendiente=:p, estado=:e WHERE id=:id"),
                            {'ij': json.dumps(items_state, ensure_ascii=False), 't': total, 'p': pendiente, 'e': estado, 'id': credito_id})
                        db3.commit()
                        ui.notify('Crédito actualizado ✓', type='positive')
                        dlg.close()
                        _render_tabla(tabla_ref, filtro)
                    except Exception as ex:
                        ui.notify(f'Error: {ex}', type='negative')
                    finally:
                        db3.close()

                with ui.row().classes('w-full justify-end gap-3 pt-2'):
                    ui.button('Cancelar', on_click=dlg.close).props('outlined color=gray dense')
                    ui.button('Guardar cambios', icon='save', on_click=guardar).classes('btn-sandoval px-6')
    dlg.open()

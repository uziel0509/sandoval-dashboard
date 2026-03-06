"""
SANDOVAL Dashboard - Módulo de Facturas
Gestión de facturas de compra: mercadería (→ inventario) y gastos operacionales
Con OCR inteligente usando Groq Vision (análisis opcional, no bloquea la UI)
"""

import os
import json
import asyncio
from datetime import datetime
from nicegui import ui, events, app
from utils.models import get_db, ItemInventario
import theme

STATIC_FACTURAS = 'static/facturas'
os.makedirs(STATIC_FACTURAS, exist_ok=True)


# ─── Base de Datos ────────────────────────────────────────────────────────────

def _get_facturas_db():
    from sqlalchemy import text
    db = get_db()
    try:
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS facturas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tipo TEXT DEFAULT 'mercaderia',
                subtipo_gasto TEXT DEFAULT '',
                proveedor TEXT DEFAULT '',
                numero_factura TEXT DEFAULT '',
                fecha TEXT DEFAULT '',
                subtotal REAL DEFAULT 0,
                igv REAL DEFAULT 0,
                total REAL DEFAULT 0,
                imagen_path TEXT DEFAULT '',
                items_json TEXT DEFAULT '[]',
                estado TEXT DEFAULT 'procesada',
                notas TEXT DEFAULT '',
                fecha_registro TEXT DEFAULT '',
                agregado_inventario INTEGER DEFAULT 0
            )
        """))
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS proveedores_facturas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT UNIQUE,
                tipo TEXT DEFAULT 'gastos',
                ultima_fecha TEXT DEFAULT ''
            )
        """))
        db.commit()
    finally:
        db.close()

def _save_proveedor(nombre, tipo: str, ruc=''):
    nombre_str = str(nombre).strip() if nombre else ''
    if not nombre_str or nombre_str.lower() in ['desconocido', 's/n', 'none', 'null', '']:
        return
            
    from utils.models import get_db, Proveedor
    import hashlib
    
    db = get_db()
    try:
        nombre_clean = nombre_str.upper()
        ruc_clean = str(ruc).strip() if ruc else ""
        
        # Etiqueta visual para la tabla
        tipo_label = "📦 MERCADERÍA / REPUESTOS" if tipo.lower() == 'mercaderia' else "💸 GASTOS OPERACIONALES"
        
        # 1. Buscar si ya existe por RUC (Si nos dieron RUC)
        p = None
        if ruc_clean and len(ruc_clean) >= 8:
            p = db.query(Proveedor).filter_by(id=ruc_clean).first()
            
        # 2. Si no lo halló por RUC, intentar buscar por Nombre Exacto
        if not p:
            p = db.query(Proveedor).filter(Proveedor.nombre == nombre_clean).first()
            
        if not p:
            # Crear ID de RUC (Si no nos dio, inventamos uno temporal como PROV-ABC)
            fake_ruc = ruc_clean if (ruc_clean and len(ruc_clean) >= 8) else ("PROV-" + hashlib.md5(nombre_clean.encode()).hexdigest()[:6].upper())
            
            p = Proveedor(
                id=fake_ruc,
                nombre=nombre_clean,
                productos=tipo_label,
                tipo='Empresa' # Por defecto empresa
            )
            db.add(p)
        else:
            # Si ya existía, asgurarnos de que diga que vende (Mercadería o Gastos)
            prods = p.productos or ""
            if "GASTOS" not in prods and "MERCADERÍA" not in prods:
                p.productos = tipo_label
            elif tipo_label not in prods:
                p.productos = f"{prods} - {tipo_label}"
                
        db.commit()
    except Exception as e:
        import traceback
        print(f"ERROR en DB _save_proveedor: {e}")
        traceback.print_exc()
        try:
            db.rollback()
        except:
            pass
    finally:
        try:
            db.close()
        except:
            pass


def _save_factura(data: dict) -> int:
    from sqlalchemy import text
    db = get_db()
    try:
        db.execute(text("""
            INSERT INTO facturas (tipo, subtipo_gasto, proveedor, numero_factura, fecha,
                subtotal, igv, total, imagen_path, items_json, estado, notas,
                fecha_registro, agregado_inventario)
            VALUES (:tipo, :subtipo_gasto, :proveedor, :numero_factura, :fecha,
                :subtotal, :igv, :total, :imagen_path, :items_json, :estado, :notas,
                :fecha_registro, :agregado_inventario)
        """), {
            'tipo': data.get('tipo', 'mercaderia'),
            'subtipo_gasto': data.get('subtipo_gasto', ''),
            'proveedor': data.get('proveedor', ''),
            'numero_factura': data.get('numero_factura', ''),
            'fecha': data.get('fecha', datetime.now().strftime('%d/%m/%Y')),
            'subtotal': float(data.get('subtotal', 0) or 0),
            'igv': float(data.get('igv', 0) or 0),
            'total': float(data.get('total', 0) or 0),
            'imagen_path': data.get('imagen_path', ''),
            'items_json': json.dumps(data.get('items', []), ensure_ascii=False),
            'estado': 'procesada',
            'notas': data.get('notas', ''),
            'fecha_registro': datetime.now().isoformat(),
            'agregado_inventario': 1 if data.get('tipo') == 'mercaderia' else 0,
        })
        db.commit()
        
        # Guardar proveedor en su respectiva tabla automáticamente
        try:
            _save_proveedor(data.get('proveedor', ''), data.get('tipo', 'mercaderia'), data.get('ruc_proveedor', ''))
        except Exception as e:
            pass
            
        row = db.execute(text("SELECT last_insert_rowid()")).fetchone()
        return row[0] if row else 0
    finally:
        db.close()


def _get_all_facturas() -> list:
    from sqlalchemy import text
    db = get_db()
    try:
        rows = db.execute(text("""
            SELECT id, tipo, subtipo_gasto, proveedor, numero_factura, fecha,
                   total, estado, fecha_registro, imagen_path, items_json, notas
            FROM facturas 
            ORDER BY substr(fecha, 7, 4) DESC, substr(fecha, 4, 2) DESC, substr(fecha, 1, 2) DESC, id DESC
        """)).fetchall()
        return [dict(r._mapping) for r in rows]
    finally:
        db.close()


def _agregar_items_a_inventario(items: list):
    db = get_db()
    try:
        for item in items:
            nombre = item.get('nombre', '').strip()
            if not nombre:
                continue
            cantidad = int(item.get('cantidad', 1) or 1)
            costo = float(item.get('precio_unitario', 0) or 0)
            existente = db.query(ItemInventario).filter(
                ItemInventario.nombre.ilike(f'%{nombre[:20]}%')
            ).first()
            if existente:
                existente.stock += cantidad
                if costo > 0:
                    existente.costo = costo
            else:
                import random, string
                codigo = 'AUTO-' + ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
                db.add(ItemInventario(
                    codigo=codigo, nombre=nombre,
                    categoria='Repuesto', tipo='Repuesto',
                    costo=costo, precio=round(costo * 1.3, 2),
                    stock=cantidad, stock_minimo=2,
                ))
        db.commit()
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()


# ─── UI Principal ─────────────────────────────────────────────────────────────

def show_facturas(container):
    _get_facturas_db()
    with container:
        with ui.row().classes('w-full items-center justify-between mb-4 py-5 px-8 bg-white border border-gray-100 rounded-xl shadow-sm'):
            with ui.row().classes('items-center gap-4'):
                ui.icon('receipt', size='32px').classes('text-[#274495]')
                ui.label('GESTIÓN DE FACTURAS').classes('text-xl font-extrabold text-[#274495] tracking-tight')
            ui.button('+ Nueva Factura', on_click=lambda: _open_nueva_factura(list_container)).props(
                'unelevated rounded color=primary'
            ).classes('font-bold')

        _render_stats()
        list_container = ui.column().classes('w-full gap-3')
        _render_lista(list_container)


def _render_stats():
    facturas = _get_all_facturas()
    total_mercaderia = sum(f['total'] for f in facturas if f['tipo'] == 'mercaderia')
    total_gastos = sum(f['total'] for f in facturas if f['tipo'] == 'gasto')

    with ui.row().classes('w-full gap-4 mb-2'):
        for icon, label, valor, color in [
            ('receipt_long', 'Total Facturas', str(len(facturas)), '#274495'),
            ('inventory_2', 'Compras Mercadería', f'S/ {total_mercaderia:,.2f}', '#10b981'),
            ('payments', 'Gastos Operacionales', f'S/ {total_gastos:,.2f}', '#f59e0b'),
        ]:
            with ui.card().classes('flex-1 p-4 bg-white border border-gray-100 shadow-sm rounded-xl'):
                with ui.row().classes('items-center gap-3'):
                    ui.icon(icon, size='28px').style(f'color:{color}')
                    with ui.column().classes('gap-0'):
                        ui.label(valor).classes('text-xl font-black text-gray-900')
                        ui.label(label).classes('text-xs text-gray-400 font-medium')


def _render_lista(container):
    container.clear()
    facturas = _get_all_facturas()
    with container:
        if not facturas:
            with ui.column().classes('w-full items-center py-20 gap-4'):
                ui.icon('receipt_long', size='64px').classes('text-gray-200')
                ui.label('No hay facturas registradas').classes('text-gray-400 text-lg font-medium')
            return
        for f in facturas:
            _factura_card(f)


def _factura_card(f: dict):
    tipo = f['tipo']
    is_merc = tipo == 'mercaderia'
    color_border = '#86efac' if is_merc else '#fcd34d'
    color_icon = '#16a34a' if is_merc else '#d97706'
    icon = 'inventory_2' if is_merc else 'payments'
    tipo_label = '🔧 MERCADERÍA' if is_merc else '🏠 GASTO'
    try:
        items = json.loads(f['items_json']) if f['items_json'] else []
    except:
        items = []

    with ui.card().classes('w-full p-0 overflow-hidden shadow-sm hover:shadow-md transition-shadow').style(
        f'border:1.5px solid {color_border}; border-radius:16px;'
    ):
        with ui.row().classes('w-full items-center p-4 gap-4'):
            ui.icon(icon, size='28px').style(f'color:{color_icon}')
            with ui.column().classes('flex-1 gap-0'):
                with ui.row().classes('items-center gap-2'):
                    ui.label(f['proveedor'] or 'Sin proveedor').classes('font-bold text-gray-800')
                    ui.badge(tipo_label, color='green' if is_merc else 'amber').classes('text-[9px]')
                with ui.row().classes('gap-3'):
                    if f['numero_factura']:
                        ui.label(f"N° {f['numero_factura']}").classes('text-xs text-gray-400')
                    ui.label(f['fecha'] or '').classes('text-xs text-gray-400')
            ui.label(f"S/ {f['total']:,.2f}").classes('text-xl font-black text-gray-900')
            if f['imagen_path'] and os.path.exists(f['imagen_path']):
                ui.button(icon='image', on_click=lambda fp=f['imagen_path']: _ver_imagen(fp)).props('flat round color=blue-7 size=sm')
        if items:
            with ui.row().classes('w-full px-4 pb-3 gap-2 flex-wrap'):
                for item in items[:4]:
                    ui.badge(f"{item.get('nombre','')[:25]} ×{item.get('cantidad',1)}", color='grey-3').props('text-color=grey-8').classes('text-[9px]')


def _ver_imagen(filepath: str):
    with ui.dialog() as d, ui.card().classes('p-4 max-w-2xl w-full'):
        with ui.row().classes('w-full justify-between items-center mb-2'):
            ui.label('Factura').classes('font-bold text-gray-800')
            ui.button(icon='close', on_click=d.close).props('flat round')
        ui.image(filepath).classes('w-full rounded-xl')
    d.open()


# ─── Diálogo Nueva Factura (flujo simplificado) ────────────────────────────────

def _open_nueva_factura(list_container):
    """
    Flujo nuevo:
    1. El usuario sube la imagen → se guarda y se muestra
    2. El formulario aparece inmediatamente para que pueda llenar manualmente
    3. Botón "🤖 Analizar con IA" rellena los campos automáticamente (opcional)
    4. Botón "✅ Guardar Factura" siempre visible
    """
    state = {'tipo': 'mercaderia', 'items': [], 'imagen_path': None}

    with ui.dialog().props('maximized') as dlg:
        with ui.card().classes('w-full h-full max-w-2xl mx-auto p-0 rounded-none').style('max-height:100vh; overflow-y:auto'):

            # Header fijo
            with ui.element('div').classes('w-full p-5 text-white sticky top-0 z-10').style('background:linear-gradient(135deg,#274495,#1e3a8a)'):
                with ui.row().classes('items-center justify-between'):
                    with ui.row().classes('items-center gap-3'):
                        ui.icon('receipt', size='24px', color='white')
                        ui.label('NUEVA FACTURA').classes('text-lg font-black text-white')
                    ui.button(icon='close', on_click=dlg.close).props('flat round color=white')

            with ui.column().classes('w-full p-5 gap-5'):

                # ── 1. Tipo ──
                ui.label('1. TIPO DE FACTURA').classes('text-xs font-black text-blue-600 uppercase tracking-widest')
                tipo_row = ui.row().classes('w-full gap-3')

                def set_tipo(t):
                    state['tipo'] = t
                    tipo_row.clear()
                    with tipo_row:
                        _tipo_btn('🔧 MERCADERÍA', 'mercaderia', t, set_tipo, 'Va al inventario')
                        _tipo_btn('🏠 GASTO', 'gasto', t, set_tipo, 'Solo contabilidad')

                with tipo_row:
                    _tipo_btn('🔧 MERCADERÍA', 'mercaderia', 'mercaderia', set_tipo, 'Va al inventario')
                    _tipo_btn('🏠 GASTO', 'gasto', 'mercaderia', set_tipo, 'Solo contabilidad')

                ui.separator()

                # ── 2. Imagen ──
                ui.label('2. FOTO DE LA FACTURA').classes('text-xs font-black text-blue-600 uppercase tracking-widest')
                img_container = ui.column().classes('w-full items-center gap-2')

                with img_container:
                    ui.icon('add_photo_alternate', size='40px').classes('text-gray-300')
                    ui.label('Sube la imagen aquí').classes('text-sm text-gray-400')

                async def handle_upload_sync(e: events.UploadEventArguments):
                    try:
                        os.makedirs(STATIC_FACTURAS, exist_ok=True)
                        
                        # Extraer nombre compatible con NiceGUI < 3 y >= 3
                        file_name = getattr(e, 'name', None)
                        if not file_name and hasattr(e, 'file'):
                            file_name = getattr(e.file, 'name', 'imagen_subida.jpg')
                        file_name = file_name or 'imagen_subida.jpg'
                        
                        fname = f"factura_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file_name}"
                        fpath = os.path.join(STATIC_FACTURAS, fname)
                        
                        # Extraer contenido compatible con NiceGUI < 3 y >= 3
                        if hasattr(e, 'file'):
                            content = await e.file.read()
                        elif hasattr(e.content, 'read'):
                            content = e.content.read()
                        else:
                            content = e.content
                            
                        if isinstance(content, str):
                            content = content.encode('utf-8')

                        
                        with open(fpath, 'wb') as f:
                            f.write(content)
                            
                        # Guardar imagen y hacer update de state para acceso futuro
                        state['imagen_path'] = fpath
                        img_container.clear()
                        with img_container:
                            ui.image(fpath).classes('w-full max-h-40 object-contain rounded-xl border border-gray-200')
                            ui.label('✅ Imagen lista').classes('text-xs text-green-600 font-bold')
                        
                        import theme
                        theme.notify_success("Imagen cargada con éxito")
                    except Exception as ex:
                        import theme
                        theme.notify_warning(f'Error upload: {str(ex)}')
                        with img_container:
                            ui.label(f'⚠️ Error: {ex}').classes('text-xs text-red-500')

                ui.upload(
                    auto_upload=True, multiple=False,
                    on_upload=handle_upload_sync
                ).props('accept=image/* flat color=primary').classes('w-full')

                ui.separator()

                # ── 3. Formulario (siempre visible) ──
                ui.label('3. DATOS DE LA FACTURA').classes('text-xs font-black text-blue-600 uppercase tracking-widest')

                # Campos del formulario
                with ui.row().classes('w-full gap-3'):
                    inp_proveedor = ui.input('Proveedor / Tienda', placeholder='Ej: Repuestos Pérez SAC').props('outlined dense').classes('flex-[2]')
                    inp_ruc = ui.input('RUC/DNI', placeholder='Ej: 201234...').props('outlined dense').classes('flex-[1]')
                    inp_nro = ui.input('N° Factura', placeholder='F001-00123').props('outlined dense').classes('flex-[1]')

                with ui.row().classes('w-full gap-3'):
                    inp_fecha = ui.input('Fecha', value=datetime.now().strftime('%d/%m/%Y')).props('outlined dense').classes('flex-1')
                    inp_total = ui.input('Total (S/)', value='0.00', placeholder='0.00').props('outlined dense type=number').classes('flex-1')

                inp_notas = ui.input('Notas adicionales (opcional)').props('outlined dense').classes('w-full')

                # Botón analizar IA
                ia_status = ui.label('').classes('text-xs text-gray-400 text-center w-full')
                items_container = ui.column().classes('w-full gap-1')

                async def analizar_ia():
                    fpath = state.get('imagen_path')
                    if not fpath or not os.path.exists(fpath):
                        theme.notify_warning('Primero sube una imagen de la factura')
                        return
                    ia_status.set_text('🤖 Analizando con IA Groq Vision...')
                    try:
                        from utils.groq_service import analizar_factura_imagen
                        loop = asyncio.get_event_loop()
                        datos = await loop.run_in_executor(None, analizar_factura_imagen, fpath)

                        if datos and 'error' not in datos:
                            if datos.get('proveedor'):
                                inp_proveedor.value = datos['proveedor']
                            if datos.get('ruc_proveedor'):
                                inp_ruc.value = datos['ruc_proveedor']
                            if datos.get('numero_factura'):
                                inp_nro.value = datos['numero_factura']
                            if datos.get('fecha'):
                                inp_fecha.value = datos['fecha']
                            if datos.get('total'):
                                inp_total.value = str(datos['total'])
                            if datos.get('notas'):
                                inp_notas.value = datos['notas']

                            # Tipo detectado
                            tipo_det = datos.get('tipo_detectado', '')
                            if tipo_det in ('mercaderia', 'gasto'):
                                set_tipo(tipo_det)

                            # Mostrar items
                            state['items'] = datos.get('items', [])
                            items_container.clear()
                            if state['items']:
                                with items_container:
                                    ui.label(f"PRODUCTOS DETECTADOS ({len(state['items'])})").classes('text-xs font-black text-gray-400 uppercase tracking-widest')
                                    for item in state['items']:
                                        with ui.row().classes('w-full items-center gap-2 py-1 border-b border-gray-100'):
                                            ui.icon('check_circle', size='14px').classes('text-green-500')
                                            ui.label(item.get('nombre', '')).classes('flex-1 text-xs text-gray-700')
                                            ui.label(f"×{item.get('cantidad', 1)}").classes('text-xs text-gray-400')
                                            ui.label(f"S/{float(item.get('precio_unitario', 0)):,.2f}").classes('text-xs font-bold text-gray-800')
                            ia_status.set_text('✅ ¡Datos rellenados por la IA! Revisa y confirma.')
                        else:
                            err = datos.get('error', 'sin respuesta') if datos else 'sin respuesta'
                            ia_status.set_text(f'⚠️ IA no pudo leer ({err[:50]}). Rellena tú los datos.')
                    except Exception as ex:
                        ia_status.set_text(f'⚠️ Error IA: {str(ex)[:60]}')

                ui.button('🤖 Analizar imagen con IA (opcional)', on_click=analizar_ia).props(
                    'flat rounded color=blue-7 no-caps'
                ).classes('w-full text-sm font-bold')

                ui.separator()

                # ── 4. Botones acción ──
                with ui.row().classes('w-full gap-3'):
                    ui.button('Cancelar', on_click=dlg.close).props('flat rounded color=grey-6').classes('flex-1')

                    async def guardar():
                        proveedor = inp_proveedor.value.strip()
                        total_val = float(inp_total.value or 0)
                        fpath_final = state.get('imagen_path') or ''

                        if not proveedor:
                            theme.notify_warning('Escribe el nombre del proveedor')
                            return

                        data = {
                            'tipo': state['tipo'],
                            'proveedor': proveedor,
                            'ruc_proveedor': inp_ruc.value.strip(),
                            'numero_factura': inp_nro.value.strip(),
                            'fecha': inp_fecha.value.strip() or datetime.now().strftime('%d/%m/%Y'),
                            'total': total_val,
                            'subtotal': round(total_val / 1.18, 2),
                            'igv': round(total_val - total_val / 1.18, 2),
                            'notas': inp_notas.value.strip(),
                            'imagen_path': fpath_final,
                            'items': state['items'],
                        }

                        if state['tipo'] == 'mercaderia' and state['items']:
                            try:
                                _agregar_items_a_inventario(state['items'])
                                theme.notify_success(f"✅ {len(state['items'])} productos agregados al inventario")
                            except Exception as ex:
                                theme.notify_warning(f'Inventario: {str(ex)[:60]}')

                        _save_factura(data)
                        theme.notify_success(f'✅ Factura de {proveedor} guardada')
                        dlg.close()
                        _render_lista(list_container)

                    ui.button('✅ Guardar Factura', on_click=guardar).props(
                        'unelevated rounded color=primary'
                    ).classes('flex-1 font-bold')

    dlg.open()


def _tipo_btn(label: str, tipo: str, selected: str, on_click, subtitle: str):
    is_sel = tipo == selected
    bg = 'linear-gradient(135deg,#274495,#1e3a8a)' if is_sel else '#f8fafc'
    txt_color = 'white' if is_sel else '#374151'
    sub_color = '#a5b4fc' if is_sel else '#9ca3af'
    border = '#274495' if is_sel else '#e5e7eb'
    with ui.element('div').classes('flex-1 p-4 rounded-2xl cursor-pointer transition-all hover:shadow-md').style(
        f'background:{bg}; border:2px solid {border};'
    ).on('click', lambda t=tipo: on_click(t)):
        ui.label(label).style(f'font-size:13px; font-weight:800; color:{txt_color}')
        ui.label(subtitle).style(f'font-size:10px; color:{sub_color}; margin-top:3px')

"""
SANDOVAL Dashboard - Módulo de Facturas
Gestión de facturas de compra: mercadería (→ inventario) y gastos operacionales
Con OCR inteligente usando Groq Vision
"""

import os
import json
import shutil
from datetime import datetime
from nicegui import ui, events
from utils.models import get_db, ItemInventario, set_config, get_config
import theme


STATIC_FACTURAS = 'static/facturas'
os.makedirs(STATIC_FACTURAS, exist_ok=True)

CATEGORIAS_GASTO = [
    'Gasolina / Combustible', 'Medicinas / Farmacia',
    'Alimentación / Mercado', 'Servicios (agua, luz, internet)',
    'Herramientas / Equipos', 'Papelería / Oficina', 'Otros'
]


# ─── Modelo de Factura en DB ──────────────────────────────────────────────────

def _get_facturas_db():
    """Obtiene o inicializa la tabla de facturas"""
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
                estado TEXT DEFAULT 'pendiente',
                notas TEXT DEFAULT '',
                fecha_registro TEXT DEFAULT '',
                agregado_inventario INTEGER DEFAULT 0
            )
        """))
        db.commit()
    finally:
        db.close()


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
            FROM facturas ORDER BY id DESC
        """)).fetchall()
        return [dict(r._mapping) for r in rows]
    finally:
        db.close()


def _agregar_items_a_inventario(items: list):
    """Agrega o actualiza productos en el inventario"""
    db = get_db()
    try:
        for item in items:
            nombre = item.get('nombre', '').strip()
            if not nombre:
                continue
            cantidad = int(item.get('cantidad', 1) or 1)
            costo = float(item.get('precio_unitario', 0) or 0)
            
            # Buscar si ya existe (por nombre similar)
            existente = db.query(ItemInventario).filter(
                ItemInventario.nombre.ilike(f'%{nombre[:20]}%')
            ).first()
            
            if existente:
                existente.stock += cantidad
                if costo > 0:
                    existente.costo = costo
            else:
                # Generar código automático
                import random, string
                codigo = 'AUTO-' + ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
                nuevo = ItemInventario(
                    codigo=codigo, nombre=nombre,
                    categoria='Repuesto', tipo='Repuesto',
                    costo=costo, precio=costo * 1.3,
                    stock=cantidad, stock_minimo=2,
                )
                db.add(nuevo)
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
        # ── Header ──
        with ui.row().classes('w-full items-center justify-between mb-4 py-5 px-8 bg-white border border-gray-100 rounded-xl shadow-sm'):
            with ui.row().classes('items-center gap-4'):
                ui.icon('receipt', size='32px').classes('text-[#274495]')
                ui.label('GESTIÓN DE FACTURAS').classes('text-xl font-extrabold text-[#274495] tracking-tight')
            ui.button('+ Nueva Factura', on_click=lambda: _open_nueva_factura(list_container)).props(
                'unelevated rounded color=primary'
            ).classes('font-bold')

        # ── Estadísticas rápidas ──
        _render_stats()

        # ── Lista de facturas ──
        list_container = ui.column().classes('w-full gap-3')
        _render_lista(list_container)


def _render_stats():
    facturas = _get_all_facturas()
    total_mercaderia = sum(f['total'] for f in facturas if f['tipo'] == 'mercaderia')
    total_gastos = sum(f['total'] for f in facturas if f['tipo'] == 'gasto')
    total_facturas = len(facturas)

    with ui.row().classes('w-full gap-4 mb-2'):
        for icon, label, valor, color in [
            ('receipt_long', 'Total Facturas', str(total_facturas), '#274495'),
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
                ui.label('Sube tu primera factura con el botón "+ Nueva Factura"').classes('text-gray-300 text-sm')
            return

        for f in facturas:
            _factura_card(f, container)


def _factura_card(f: dict, list_container):
    tipo = f['tipo']
    is_merc = tipo == 'mercaderia'
    color_bg = '#f0fdf4' if is_merc else '#fffbeb'
    color_border = '#86efac' if is_merc else '#fcd34d'
    color_icon = '#16a34a' if is_merc else '#d97706'
    icon = 'inventory_2' if is_merc else 'payments'
    tipo_label = '🔧 MERCADERÍA' if is_merc else '🏠 GASTO OPERACIONAL'
    
    try:
        items = json.loads(f['items_json']) if f['items_json'] else []
    except:
        items = []

    with ui.card().classes('w-full p-0 overflow-hidden shadow-sm hover:shadow-md transition-shadow').style(
        f'border:1.5px solid {color_border}; border-radius:16px;'
    ):
        with ui.row().classes('w-full items-center p-4 gap-4'):
            # Ícono tipo
            with ui.element('div').classes('flex items-center justify-center w-12 h-12 rounded-xl').style(f'background:{color_bg}'):
                ui.icon(icon, size='24px').style(f'color:{color_icon}')
            
            # Info principal
            with ui.column().classes('flex-1 gap-0'):
                with ui.row().classes('items-center gap-2'):
                    ui.label(f['proveedor'] or 'Sin proveedor').classes('font-bold text-gray-800 text-base')
                    ui.badge(tipo_label, color='green' if is_merc else 'amber').classes('text-[9px]')
                with ui.row().classes('items-center gap-4'):
                    if f['numero_factura']:
                        ui.label(f"N° {f['numero_factura']}").classes('text-xs text-gray-400')
                    ui.label(f['fecha'] or '').classes('text-xs text-gray-400')
                    if not is_merc and f['subtipo_gasto']:
                        ui.label(f['subtipo_gasto']).classes('text-xs text-blue-400 font-medium')
            
            # Total
            ui.label(f"S/ {f['total']:,.2f}").classes('text-xl font-black text-gray-900')
            
            # Acciones
            with ui.row().classes('gap-1'):
                if f['imagen_path'] and os.path.exists(f['imagen_path']):
                    ui.button(icon='image', on_click=lambda fp=f['imagen_path']: _ver_imagen(fp)).props('flat round color=blue-7 size=sm')
                ui.button(icon='visibility', on_click=lambda fd=f, it=items: _ver_detalle(fd, it)).props('flat round color=primary size=sm')
        
        # Items preview
        if items:
            with ui.row().classes('w-full px-4 pb-3 gap-2 flex-wrap'):
                for item in items[:4]:
                    ui.badge(f"{item.get('nombre','')[:25]} ×{item.get('cantidad',1)}", color='grey-3').props('text-color=grey-8').classes('text-[9px]')
                if len(items) > 4:
                    ui.badge(f'+{len(items)-4} más', color='grey-2').props('text-color=grey-6').classes('text-[9px]')


def _ver_imagen(filepath: str):
    with ui.dialog() as d, ui.card().classes('p-4 max-w-2xl w-full'):
        with ui.row().classes('w-full justify-between items-center mb-2'):
            ui.label('Imagen de Factura').classes('font-bold text-gray-800')
            ui.button(icon='close', on_click=d.close).props('flat round')
        ui.image(filepath).classes('w-full rounded-xl')
    d.open()


def _ver_detalle(f: dict, items: list):
    with ui.dialog() as d, ui.card().classes('p-6 max-w-lg w-full gap-4'):
        with ui.row().classes('w-full justify-between items-center'):
            ui.label(f['proveedor'] or 'Factura').classes('text-lg font-black text-gray-900')
            ui.button(icon='close', on_click=d.close).props('flat round')
        
        for label, val in [
            ('Tipo', '🔧 Mercadería' if f['tipo'] == 'mercaderia' else '🏠 Gasto Operacional'),
            ('N° Factura', f['numero_factura'] or '-'),
            ('Fecha', f['fecha'] or '-'),
            ('Subtotal', f"S/ {f['subtotal']:,.2f}"),
            ('IGV', f"S/ {f['igv']:,.2f}"),
            ('Total', f"S/ {f['total']:,.2f}"),
        ]:
            with ui.row().classes('w-full justify-between py-1 border-b border-gray-100'):
                ui.label(label).classes('text-sm text-gray-400 font-medium')
                ui.label(str(val)).classes('text-sm font-bold text-gray-800')
        
        if items:
            ui.label('ITEMS').classes('text-xs font-black text-blue-600 mt-4 tracking-widest')
            for item in items:
                with ui.row().classes('w-full justify-between py-1'):
                    ui.label(f"{item.get('nombre','')} ×{item.get('cantidad',1)}").classes('text-sm text-gray-600 flex-1')
                    ui.label(f"S/ {float(item.get('total',0)):,.2f}").classes('text-sm font-bold text-gray-800')
    d.open()


# ─── Diálogo Nueva Factura ────────────────────────────────────────────────────

def _blank_factura() -> dict:
    """Devuelve una factura vacía para llenado manual"""
    return {
        'proveedor': '', 'numero_factura': '',
        'fecha': datetime.now().strftime('%d/%m/%Y'),
        'subtotal': 0, 'igv': 0, 'total': 0,
        'items': [], 'notas': '', 'tipo_detectado': '',
    }

def _open_nueva_factura(list_container):
    state = {
        'tipo': 'mercaderia',
        'imagen_path': None,
        'datos_ia': None,
        'procesando': False,
    }

    with ui.dialog() as dlg, ui.card().classes('w-full max-w-2xl p-0 overflow-hidden rounded-[24px]'):
        # Header
        with ui.element('div').classes('w-full p-6 text-white').style('background:linear-gradient(135deg,#274495,#1e3a8a)'):
            with ui.row().classes('items-center justify-between'):
                with ui.row().classes('items-center gap-3'):
                    ui.icon('receipt', size='28px', color='white')
                    ui.label('NUEVA FACTURA').classes('text-xl font-black text-white')
                ui.button(icon='close', on_click=dlg.close).props('flat round color=white')
        
        with ui.column().classes('w-full p-6 gap-6'):
            # ── Paso 1: Tipo de factura ──
            ui.label('1. ¿QUÉ TIPO DE FACTURA ES?').classes('text-xs font-black text-blue-600 uppercase tracking-widest')
            
            tipo_container = ui.row().classes('w-full gap-4')
            
            def set_tipo(t):
                state['tipo'] = t
                tipo_container.clear()
                with tipo_container:
                    _tipo_btn('🔧 COMPRA DE MERCADERÍA', 'mercaderia', t, set_tipo,
                              'Repuestos, aceites, filtros → Va al inventario')
                    _tipo_btn('🏠 GASTO OPERACIONAL', 'gasto', t, set_tipo,
                              'Gasolina, medicinas, servicios → Solo contabilidad')

            with tipo_container:
                _tipo_btn('🔧 COMPRA DE MERCADERÍA', 'mercaderia', 'mercaderia', set_tipo,
                          'Repuestos, aceites, filtros → Va al inventario')
                _tipo_btn('🏠 GASTO OPERACIONAL', 'gasto', 'mercaderia', set_tipo,
                          'Gasolina, medicinas, servicios → Solo contabilidad')

            ui.separator()

            # ── Paso 2: Subir imagen ──
            ui.label('2. SUBE LA FOTO DE LA FACTURA').classes('text-xs font-black text-blue-600 uppercase tracking-widest')
            
            preview_container = ui.column().classes('w-full items-center')
            status_label = ui.label('').classes('text-sm text-gray-500 text-center mt-2')
            
            with preview_container:
                upload_area = ui.element('div').classes(
                    'w-full border-2 border-dashed border-gray-200 rounded-2xl p-10 text-center bg-gray-50 cursor-pointer hover:bg-blue-50 hover:border-blue-300 transition-all'
                )
                with upload_area:
                    ui.icon('add_photo_alternate', size='48px').classes('text-gray-300')
                    ui.label('Toca para subir o tomar foto').classes('text-gray-400 font-medium mt-2')
                    ui.label('JPG, PNG — Máx. 10MB').classes('text-xs text-gray-300 mt-1')

            async def handle_upload(e: events.UploadEventArguments):
                state['procesando'] = True
                status_label.set_text('⏳ Subiendo imagen...')
                
                # Guardar imagen
                fname = f"factura_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{e.name}"
                fpath = os.path.join(STATIC_FACTURAS, fname)
                with open(fpath, 'wb') as f:
                    f.write(e.content.read())
                state['imagen_path'] = fpath
                
                # Mostrar preview
                preview_container.clear()
                with preview_container:
                    ui.image(fpath).classes('w-full max-h-48 object-contain rounded-xl border border-gray-200 shadow-sm')
                
                # Analizar con IA
                status_label.set_text('🤖 Analizando con IA Groq Vision...')
                try:
                    from utils.groq_service import analizar_factura_imagen
                    datos = analizar_factura_imagen(fpath)
                    
                    if 'error' in datos:
                        status_label.set_text(f'⚠️ IA no pudo leer la imagen. Rellena los datos tú mismo.')
                        datos = _blank_factura()
                    else:
                        tipo_detectado = datos.get('tipo_detectado', 'mercaderia')
                        if tipo_detectado in ('mercaderia', 'gasto'):
                            set_tipo(tipo_detectado)
                        status_label.set_text('✅ ¡Analizado! Revisa y confirma los datos.')
                except Exception as ex:
                    status_label.set_text(f'⚠️ Error IA ({str(ex)[:50]}). Rellena los datos tú mismo.')
                    datos = _blank_factura()
                
                state['datos_ia'] = datos
                _render_resultado_ia(datos, resultado_container, state)
                state['procesando'] = False

            ui.upload(
                label='', auto_upload=True, multiple=False,
                on_upload=handle_upload
            ).props('accept=image/* flat color=primary').classes('w-full')

            ui.separator()

            # ── Paso 3: Resultado IA (se llena dinámicamente) ──
            resultado_container = ui.column().classes('w-full gap-3')

            # ── Botones ──
            with ui.row().classes('w-full gap-3 pt-4 pb-2'):
                ui.button('Cancelar', on_click=dlg.close).props('flat rounded color=grey-6').classes('flex-1')
                
                async def confirmar_y_guardar():
                    if not state['datos_ia']:
                        theme.notify_warning('Primero sube una imagen para analizar o espera que termine el análisis')
                        return
                    
                    datos = state['datos_ia']
                    datos['tipo'] = state['tipo']
                    datos['imagen_path'] = state['imagen_path'] or ''
                    
                    # Si es mercadería, agregar al inventario
                    if state['tipo'] == 'mercaderia' and datos.get('items'):
                        _agregar_items_a_inventario(datos['items'])
                        theme.notify_success(f"✅ {len(datos['items'])} productos agregados al inventario")
                    
                    _save_factura(datos)
                    theme.notify_success(f'✅ Factura de {datos.get("proveedor","?")} guardada correctamente')
                    dlg.close()
                    _render_lista(list_container)
                
                ui.button('✅ Confirmar y Guardar', on_click=confirmar_y_guardar).props(
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
        ui.label(subtitle).style(f'font-size:10px; color:{sub_color}; margin-top:4px; line-height:1.3')


def _render_resultado_ia(datos: dict, container, state: dict):
    """Renderiza el resultado del análisis IA con campos editables"""
    container.clear()
    
    with container:
        ui.label('3. REVISA LOS DATOS DETECTADOS POR LA IA').classes('text-xs font-black text-green-600 uppercase tracking-widest')
        
        with ui.card().classes('w-full p-4 bg-green-50 border border-green-100 rounded-2xl gap-3'):
            # Datos principales
            with ui.row().classes('w-full gap-3'):
                proveedor_i = ui.input('Proveedor', value=datos.get('proveedor','')).props('outlined dense').classes('flex-1')
                nro_i = ui.input('N° Factura', value=datos.get('numero_factura','')).props('outlined dense').classes('flex-1')
            
            with ui.row().classes('w-full gap-3'):
                fecha_i = ui.input('Fecha', value=datos.get('fecha','')).props('outlined dense').classes('flex-1')
                total_i = ui.input('Total (S/)', value=str(datos.get('total',0) or 0)).props('outlined dense type=number').classes('flex-1')
            
            # Actualizar datos cuando cambien
            def update_datos():
                datos['proveedor'] = proveedor_i.value
                datos['numero_factura'] = nro_i.value
                datos['fecha'] = fecha_i.value
                datos['total'] = float(total_i.value or 0)
            
            proveedor_i.on('change', update_datos)
            nro_i.on('change', update_datos)
            fecha_i.on('change', update_datos)
            total_i.on('change', update_datos)
            
            # Items detectados
            items = datos.get('items', [])
            if items:
                ui.label(f'PRODUCTOS DETECTADOS ({len(items)} items)').classes('text-xs font-black text-gray-500 uppercase tracking-widest mt-2')
                for item in items:
                    with ui.row().classes('w-full items-center gap-2 py-1 border-b border-green-100'):
                        ui.icon('check_circle', size='16px').classes('text-green-500')
                        ui.label(item.get('nombre', '')).classes('flex-1 text-sm text-gray-700 font-medium')
                        ui.label(f"×{item.get('cantidad',1)}").classes('text-xs text-gray-400 w-8')
                        ui.label(f"S/ {float(item.get('precio_unitario',0)):,.2f}").classes('text-sm font-bold text-gray-800 w-20 text-right')
            
            # Nota de tipo detectado
            tipo_det = datos.get('tipo_detectado','')
            if tipo_det:
                tipo_msg = {'mercaderia': '🔧 IA detectó: Compra de mercadería para el taller',
                           'gasto': '🏠 IA detectó: Gasto operacional/personal',
                           'mixto': '⚠️ IA detectó contenido mixto — revisa el tipo arriba'}.get(tipo_det,'')
                if tipo_msg:
                    ui.label(tipo_msg).classes('text-xs text-blue-600 font-bold mt-1')
            
            if datos.get('notas'):
                ui.label(f'💬 {datos["notas"]}').classes('text-xs text-gray-400 italic')

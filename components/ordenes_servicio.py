"""
SANDOVAL Dashboard - Órdenes de Servicio
Flujo completo de 8 estados con SQLite + token de aprobación
"""

from nicegui import ui
from utils.models import get_db, Orden, Cliente, Vehiculo, ItemInventario, log_actividad, get_config
from utils import pdf_generator as pdf_gen
from datetime import datetime
import secrets
import os
import json
import theme

ESTADOS = list(theme.ESTADOS_CONFIG.keys())
TECNICOS_DEFAULT = ['Técnico 1', 'Técnico 2', 'Técnico 3']

def _get_tecnicos():
    try:
        from utils.models import ConfigSistema
        db = get_db()
        try:
            row = db.query(ConfigSistema).filter_by(clave='tecnicos').first()
            if row and row.valor:
                import json
                return json.loads(row.valor)
        finally:
            db.close()
    except Exception:
        pass
    return TECNICOS_DEFAULT


def show_ordenes(container):
    with container:
        state = {'filter_estado': None, 'search_query': ''}
        
        # Header Corporativo
        with ui.row().classes('w-full items-center justify-between mb-4 fade-in py-5 px-8 bg-white border border-gray-100 rounded-xl shadow-sm'):
            with ui.row().classes('items-center gap-4'):
                ui.icon('build_circle', size='32px').classes('text-[#274495]')
                ui.label('GESTIÓN DE ÓRDENES DE SERVICIO').classes('text-xl font-extrabold text-[#274495] tracking-tight')
            
            with ui.row().classes('gap-3'):
                ui.button('Importar Histórico (IA)', icon='auto_awesome', on_click=lambda: open_import_historico(cards_container, state, stats_container)).classes('bg-amber-600 hover:bg-amber-700 text-white font-bold px-4 rounded-lg shadow-sm h-11')
                ui.button('Nueva Orden', icon='add',
                    on_click=lambda: open_create_order_dialog(cards_container, state, stats_container)
                ).classes('btn-sandoval px-6 h-11')
        
        # Stats
        stats_container = ui.row().classes('w-full gap-3 mb-4 overflow-x-auto flex-nowrap pb-2 items-center')
        
        # Búsqueda
        with ui.row().classes('w-full gap-4 mb-6'):
            search_input = ui.input(placeholder='Buscar orden, cliente, placa...').props('outlined dense clearable bg-color=white').classes('flex-1')
            def do_search():
                state['search_query'] = search_input.value or ''
                refresh_orders(cards_container, state, stats_container)
            search_input.on('keydown.enter', lambda: do_search())
            ui.button('Buscar', icon='search', on_click=do_search).classes('btn-sandoval h-10 px-8').props('unelevated')
        
        cards_container = ui.column().classes('w-full gap-3')
        
        # Initial load (force stats refresh too)
        refresh_orders(cards_container, state, stats_container)

def refresh_stats(container, cards_container, state):
    if not container: return
    container.clear()
    
    db = get_db()
    try:
        from utils.models import Orden
        total = db.query(Orden).count()
        
        # Estilo de "Cuadro Azul" para el activo o hover
        card_style = 'min-w-[120px] p-3 cursor-pointer rounded-lg border transition-all shadow-sm'
        bg_normal = 'bg-white border-gray-200 hover:border-blue-500 hover:bg-blue-50'
        
        with container:
            with ui.card().classes(f'{card_style} {bg_normal}').on('click', lambda: (state.update({'filter_estado': None}), refresh_orders(cards_container, state, container))):
                ui.label('TOTAL').classes('text-[10px] font-bold text-gray-500 uppercase')
                ui.label(str(total)).classes('text-2xl font-bold text-[#154c79]')
            
            for est, cfg in theme.ESTADOS_CONFIG.items():
                count = db.query(Orden).filter_by(estado=est).count()
                color_text = cfg.get('hex', '#333')
                
                with ui.card().classes(f'{card_style} {bg_normal}').on('click', lambda e=est: (state.update({'filter_estado': e}), refresh_orders(cards_container, state, container))):
                        with ui.row().classes('items-center justify-between w-full'):
                            ui.label(est).classes(f'text-[10px] font-bold text-gray-600 uppercase')
                            # Dot de color
                            ui.element('div').classes(f'w-2 h-2 rounded-full bg-[{color_text}]')
                        ui.label(str(count)).classes(f'text-xl font-bold text-[{color_text}]')
    finally:
        db.close()


def refresh_orders(container, state, stats_container=None):
    if stats_container:
        refresh_stats(stats_container, container, state)
    
    container.clear()
    db = get_db()
    try:
        query = db.query(Orden)
        if state.get('filter_estado'):
            query = query.filter_by(estado=state['filter_estado'])
        if state.get('search_query'):
            q = f"%{state['search_query']}%"
            query = query.filter(
                (Orden.consecutivo.ilike(q)) | (Orden.motivo.ilike(q)) |
                (Orden.vehiculo_placa.ilike(q)) | (Orden.tecnico.ilike(q))
            )
        orders = query.order_by(Orden.fecha.desc()).all()
        clients = {c.id: c for c in db.query(Cliente).all()}
        vehicles = {v.placa: v for v in db.query(Vehiculo).all()}
        
        with container:
            if not orders:
                with ui.card().classes('w-full bg-white border border-gray-200 p-8 text-center shadow-sm'):
                    ui.icon('build', size='48px').classes('text-gray-400')
                    ui.label('No se encontraron órdenes').classes('text-gray-500 mt-2')
                return
            
            for order in orders:
                _render_order_card(order, clients, vehicles, container, state, stats_container)
    finally:
        db.close()


# ── Registrar endpoint FastAPI para importación histórica (solo una vez) ──────
_historico_route_registered = False

def _register_historico_api():
    global _historico_route_registered
    if _historico_route_registered:
        return
    _historico_route_registered = True
    
    from nicegui import app as _app
    from fastapi import UploadFile
    from fastapi.responses import JSONResponse
    
    @_app.post('/api/import-historico')
    async def _api_import_historico(file: UploadFile):
        """FastAPI endpoint: maneja subida de facturas históricas de forma confiable."""
        import os, traceback
        print(f"[HIST-API] Recibido: {file.filename}, content_type={file.content_type}")
        try:
            content = await file.read()  # FastAPI.read() siempre funciona
            print(f"[HIST-API] Leído: {len(content)} bytes")
            
            if not content:
                return JSONResponse({'ok': False, 'error': 'Archivo vacío recibido'})
            
            os.makedirs('/var/www/sandoval/static', exist_ok=True)
            ext = '.pdf' if (file.filename or '').lower().endswith('.pdf') else '.jpg'
            fname = f"hist_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}{ext}"
            fpath = f"/var/www/sandoval/static/{fname}"
            
            with open(fpath, 'wb') as fp:
                fp.write(content)
            print(f"[HIST-API] Guardado en: {fpath}")
            
            from utils.groq_service import analizar_factura_historica_imagen
            datos = analizar_factura_historica_imagen(fpath)
            print(f"[HIST-API] IA: {datos}")
            
            if not datos or 'error' in datos:
                return JSONResponse({'ok': False, 'error': f'Error IA: {datos.get("error") if datos else "sin respuesta"}'})
            
            placa = str(datos.get('placa', '')).upper().strip()
            if not placa or placa in ('NONE', 'NULL', ''):
                return JSONResponse({'ok': False, 'error': 'La IA no detectó placa en la factura. Asegúrate que figure en el PDF.'})
            
            db_h = get_db()
            try:
                vehiculo = db_h.query(Vehiculo).filter_by(placa=placa).first()
                if not vehiculo:
                    return JSONResponse({'ok': False, 'error': f'Placa "{placa}" no está registrada en el sistema'})
                
                cliente = db_h.query(Cliente).filter_by(id=vehiculo.cliente_id).first()
                if not cliente:
                    return JSONResponse({'ok': False, 'error': f'Vehículo {placa} no tiene cliente asignado'})
                
                td = datetime.now()
                cons = f"ODS-{td.strftime('%Y%m')}-HIST-{secrets.token_hex(2).upper()}"
                items = datos.get('items', [])
                for it in items:
                    if 'categoria' not in it: it['categoria'] = 'Repuesto Histórico'
                    if 'id' not in it: it['id'] = secrets.token_hex(4)
                total = sum(float(it.get('total', 0) or 0) for it in items)
                web = f"/static/{fname}"
                
                nueva = Orden(
                    consecutivo=cons,
                    fecha=str(datos.get('fecha', td.strftime('%Y-%m-%d %H:%M:%S'))),
                    cliente_id=cliente.id,
                    cliente_nombre=f"{cliente.nombre} {getattr(cliente,'apellidos','')}".strip(),
                    vehiculo_placa=vehiculo.placa,
                    tecnico='HISTÓRICO IA',
                    km=str(getattr(vehiculo, 'km', '0')),
                    motivo=f"Registro Histórico de Mantenimiento. Total: S/ {total:,.2f}",
                    estado='ARCHIVADO',
                    approval_status='aprobado',
                    fotos_evidencia=[{'path': web, 'fase': 'RECEPCIÓN'}, {'path': web, 'fase': 'DIAGNÓSTICO'}],
                    diagnostico="Mantenimiento culminado según comprobante histórico adjunto.",
                    items_cotizacion=items,
                    checklist_reparacion={
                        'quick_check': {}, 'findings': [],
                        'diagnostic_details': {'analysis': 'Histórico IA.', 'solution': 'Mantenimiento culminado.'}
                    },
                    historial=[{'fecha': td.strftime('%Y-%m-%d %H:%M'), 'accion': f'Importado IA — Placa: {placa}', 'usuario': 'Sistema IA'}]
                )
                db_h.add(nueva)
                db_h.commit()
                log_actividad(f'Histórico: {cons} — {placa}', 'ordenes')
                print(f"[HIST-API] ✅ Orden {cons} creada para {placa}")
                return JSONResponse({'ok': True, 'consecutivo': cons, 'placa': placa})
            finally:
                db_h.close()
        except Exception as err:
            traceback.print_exc()
            return JSONResponse({'ok': False, 'error': str(err)})


def open_import_historico(container, state, stats_container=None):
    _register_historico_api()  # Asegurar que el endpoint exista
    
    with ui.dialog() as dialog, ui.card().classes('w-full max-w-lg p-6 bg-white shadow-xl rounded-xl gap-4'):
        ui.icon('auto_awesome', size='3rem', color='amber-500').classes('mx-auto drop-shadow-sm')
        ui.label('MÁQUINA DEL TIEMPO (IA)').classes('text-xl font-bold text-center text-blue-900 w-full tracking-tight')
        ui.label('Selecciona la foto o PDF de una factura antigua. La IA crea la orden histórica automáticamente (sin descontar stock).').classes('text-xs text-center text-gray-500 font-medium leading-relaxed')
        
        status_label = ui.label('Selecciona un archivo para comenzar.').classes('text-sm font-bold text-center text-blue-600 w-full py-2 px-4 bg-blue-50 rounded-xl')
        
        # Input de archivo oculto (JS nativo - más confiable que NiceGUI upload)
        import random
        uid = random.randint(10000, 99999)
        ui.html(f'<input type="file" id="hist-picker-{uid}" accept=".pdf,.jpg,.jpeg,.png,image/*" style="display:none">')
        
        async def check_result():
            """Polling: verifica si el JS colocó un resultado en window._hist_result"""
            try:
                result = await ui.run_javascript(f'JSON.stringify(window._hist_result_{uid} || null)', timeout=2.0)
                if result and result != 'null':
                    import json as _j
                    r = _j.loads(result)
                    await ui.run_javascript(f'delete window._hist_result_{uid}')
                    check_timer.cancel()
                    if r.get('ok'):
                        cons = r.get('consecutivo', '')
                        placa = r.get('placa', '')
                        ui.notify(f'✅ ¡ÓRDEN HISTÓRICA CREADA! {cons} — Placa: {placa}', type='positive', position='top', timeout=8000)
                        dialog.close()
                        refresh_orders(container, state, stats_container)
                    else:
                        err = r.get('error', 'Error desconocido')
                        ui.notify(f'❌ {err}', type='negative', position='top', timeout=10000)
                        status_label.set_text(f'❌ {err}')
            except Exception:
                pass
        
        check_timer = ui.timer(1.5, check_result, active=False)
        
        async def pick_and_upload():
            check_timer.active = True
            status_label.set_text('⏳ Esperando archivo...')
            script = f"""
                const input = document.getElementById('hist-picker-{uid}');
                input.onchange = async (ev) => {{
                    const file = ev.target.files[0];
                    if (!file) return;
                    
                    const statusEl = document.getElementById('hist-status-{uid}');
                    if(statusEl) statusEl.textContent = '⏳ Subiendo ' + file.name + '... (espera ~15 seg)';
                    
                    const fd = new FormData();
                    fd.append('file', file);
                    
                    try {{
                        const resp = await fetch('/api/import-historico', {{method:'POST', body:fd}});
                        const r = await resp.json();
                        window._hist_result_{uid} = r;
                        if(statusEl) statusEl.textContent = r.ok 
                            ? '✅ Procesado: ' + (r.consecutivo || '') 
                            : '❌ ' + (r.error || 'Error');
                    }} catch(err) {{
                        window._hist_result_{uid} = {{ok: false, error: err.message}};
                        if(statusEl) statusEl.textContent = '❌ Error de red: ' + err.message;
                    }}
                }};
                input.click();
            """
            await ui.run_javascript(script)
        
        # Elemento con ID para que el JS lo actualice directamente
        ui.html(f'<div id="hist-status-{uid}" style="text-align:center;font-weight:bold;color:#1a3a6b;font-size:12px;padding:8px;">Selecciona un archivo para comenzar.</div>')
        
        ui.button('📁  SELECCIONAR FACTURA (PDF o Foto)', icon='upload_file', on_click=pick_and_upload
        ).classes('w-full bg-amber-600 hover:bg-amber-700 text-white font-bold py-4 rounded-xl shadow-lg text-sm tracking-wide')
        
        ui.button('✖ Cerrar', on_click=lambda: (check_timer.cancel() or True) and dialog.close()).props('flat color=grey-6').classes('w-full')
        
    dialog.open()




def regress_order(consecutivo, new_estado):
    db = get_db()
    try:
        o = db.query(Orden).filter_by(consecutivo=consecutivo).first()
        if o:
            if o.estado == 'ARCHIVADO':
                 # Si recuperamos de archivado, quizás necesitemos lógica especial, pero por ahora simple
                 pass
            old = o.estado
            o.estado = new_estado
            
            # Nota: Mantenemos los datos de diagnóstico y repuestos por si se desea corregir.
            # No limpiamos nada para evitar pérdida de trabajo del técnico.

            from utils.models import log_actividad
            log_actividad(f'Orden {consecutivo} retrocedida de {old} a {new_estado}', 'ordenes')
            db.commit()
            theme.notify_warning(f'Orden {consecutivo} retrocedida a {new_estado}')
    except Exception as e:
        db.rollback()
        theme.notify_error(f'Error al retroceder: {e}')
    finally:
        db.close()





def open_new_diagnostic_modal(consecutivo, container, state, stats_container=None):
    """
    Interfaz Completa de Diagnóstico (Light Mode / Form Based)
    """
    db = get_db()
    try:
        print(f"DEBUG: Opening Modal for Order {consecutivo}") 
        order = db.query(Orden).filter_by(consecutivo=consecutivo).first()
        if not order:
            theme.notify_error('Orden no encontrada')
            return

        client = db.query(Cliente).filter_by(id=order.cliente_id).first()
        vehicle = db.query(Vehiculo).filter_by(placa=order.vehiculo_placa).first()
        
        # Load existing data
        checklist_data = order.checklist_reparacion
        if not isinstance(checklist_data, dict):
            # Try to parse or default
            if isinstance(checklist_data, str):
                import json
                try: checklist_data = json.loads(checklist_data)
                except: checklist_data = {}
            else:
                checklist_data = {}
        
        # Initialize quick check with dict structure if possible, or migrate
        quick_check_raw = checklist_data.get('quick_check', {})
        quick_check = {}
        # Default items
        default_items = ['Luces', 'Neumáticos', 'Fluidos', 'Batería', 'Carrocería', 'Interior']
        for it in default_items:
            val = quick_check_raw.get(it, {'status': 'OK', 'note': ''})
            if isinstance(val, str): val = {'status': val, 'note': ''}
            quick_check[it] = val
            
        findings = checklist_data.get('findings', [])
        diag_struct = checklist_data.get('diagnostic_details', {})
        
        # State refs
        findings_ref = {'items': findings} # Mutable wrapper
        new_evidence_files = [] # New uploads
        
        # Styles matches Light Theme
        with ui.dialog() as dialog, ui.card().classes('w-full h-full max-w-none p-0 bg-gray-50'):
            
            # ─── HEADER ───
            with ui.row().classes('w-full items-center justify-between p-4 bg-white border-b border-gray-200 shadow-sm'):
                with ui.row().classes('items-center gap-4'):
                    with ui.column().classes('gap-0'):
                        ui.label('DIAGNÓSTICO TÉCNICO').classes('text-xl font-bold text-gray-800 tracking-wide')
                        ui.label(f'Orden {consecutivo}').classes('text-blue-600 font-bold text-sm')
                
                # Vehicle Info Bar
                with ui.row().classes('gap-8 items-center hidden md:flex bg-gray-50 px-4 py-2 rounded-lg border border-gray-100'):
                    def _info(icon, label, val):
                        with ui.row().classes('items-center gap-2'):
                            ui.icon(icon, size='xs').classes('text-gray-400')
                            with ui.column().classes('gap-0'):
                                ui.label(label).classes('text-[10px] text-gray-500 font-bold uppercase')
                                ui.label(val).classes('text-sm font-bold text-gray-800')
                    
                    if vehicle:
                        _info('directions_car', 'Vehículo', f"{vehicle.marca} {vehicle.modelo}")
                        _info('event', 'Año', vehicle.año)
                        _info('pin', 'Placa', vehicle.placa)
                        
                    with ui.row().classes('items-center gap-2 ml-4'):
                        ui.label('KM:').classes('text-gray-500 font-bold text-xs')
                        km_input = ui.input(value=order.km).props('outlined dense bg-color=white').classes('w-28')
                
                ui.button(icon='close', on_click=dialog.close).props('flat round color=grey-7')

            # ─── MAIN CONTENT ───
            with ui.scroll_area().classes('w-full flex-1 p-6'):
                with ui.row().classes('w-full gap-8'):
                    
                    # COL 1: Formulario Estructurado (Inputs)
                    with ui.column().classes('flex-1 gap-5 min-w-[400px]'):
                        
                        # A. Resumen Inicial
                        with ui.card().classes('w-full bg-white border border-gray-200 p-5 shadow-sm space-y-4'):
                            ui.label('INFORMACIÓN PRELIMINAR').classes('text-xs font-bold text-blue-600 mb-2 border-b border-blue-100 pb-1 w-full')
                            
                            # Grid principal para Sistemas y Códigos
                            with ui.column().classes('w-full gap-4'):
                                system_opts = ['Motor', 'Transmisión', 'Frenos', 'Suspensión/Dirección', 'Sistema Eléctrico', 'Carrocería', 'Mantenimiento General', 'Otro']
                                sys_val = diag_struct.get('system', ['Motor'])
                                if isinstance(sys_val, str): sys_val = [sys_val]
                                
                                ui.label('ÁREAS DE ATENCIÓN').classes('text-[10px] font-bold text-gray-500 tracking-widest uppercase mt-2')
                                d_system = ui.select(system_opts, value=sys_val, multiple=True).props('outlined dense use-chips options-dense bg-color=white label="Sistemas Afectados"').classes('w-full shadow-sm')
                                
                                def handle_scanner_up(e):
                                    import os
                                    from datetime import datetime
                                    try:
                                        content = e.content.read()
                                        folder = consecutivo.replace('#','').replace('/','_').strip()
                                        save_dir = f"static/scanner_reports/{folder}"
                                        os.makedirs(save_dir, exist_ok=True)
                                        f_name = f"scanner_{datetime.now().strftime('%H%M%S')}.pdf"
                                        f_path = os.path.join(save_dir, f_name)
                                        with open(f_path, 'wb') as f:
                                            f.write(content)
                                        diag_struct['scanner_path'] = f"/scanner_reports/{folder}/{f_name}"
                                        theme.notify_success('Reporte de escáner cargado')
                                    except Exception as err:
                                        theme.notify_error(f"Error al subir scanner: {err}")

                                with ui.row().classes('w-full items-center gap-2'):
                                    ui.icon('qr_code_scanner', size='sm', color='blue-6')
                                    ui.upload(on_upload=handle_scanner_up, label='Reporte de Escáner (PDF)').props('flat dense accept=.pdf').classes('flex-1 border-2 border-dotted border-blue-200 rounded-lg')
                                    if diag_struct.get('scanner_path'):
                                        ui.icon('check_circle', color='green-6').tooltip('Reporte cargado')
                            
                            ui.separator().classes('my-2 opacity-30')
                            d_motivo = ui.textarea(value=order.motivo, label='Motivo de Ingreso / Queja del Cliente').props('outlined dense rows=5 bg-color=white').classes('w-full')

                        # B. Desarrollo del Diagnóstico (Campos separados)
                        with ui.card().classes('w-full bg-white border border-gray-200 p-5 shadow-sm space-y-4'):
                            ui.label('ANÁLISIS TÉCNICO').classes('text-xs font-bold text-blue-600 mb-2 border-b border-blue-100 pb-1 w-full')
                            
                            d_pruebas = ui.textarea(value=diag_struct.get('tests', ''), label='Pruebas e Inspecciones Realizadas').props('outlined dense rows=7 placeholder="Ej: Escaneo de computadora, Prueba de ruta" bg-color=white').classes('w-full')
                            
                            d_analisis = ui.textarea(value=diag_struct.get('analysis', ''), label='Hallazgos / Causa Raíz').props('outlined dense rows=7 placeholder="Ej: Desgaste irregular en pastillas de freno" bg-color=white').classes('w-full')
                            
                            d_solucion = ui.textarea(value=diag_struct.get('solution', ''), label='Solución Técnica Recomendada').props('outlined dense rows=7 placeholder="Ej: Reemplazo de componentes y alineación" bg-color=white').classes('w-full')


                    # COL 2: Checklists y Evidencia
                    with ui.column().classes('w-[400px] gap-5'):
                        
                        # Quick Check Grid
                        with ui.card().classes('w-full bg-white border border-gray-200 p-5 shadow-sm'):
                            ui.label('INSPECCIÓN VISUAL RÁPIDA').classes('text-xs font-bold text-blue-600 mb-4 border-b border-blue-100 pb-1 w-full')
                            
                            scroll_check = ui.column().classes('w-full gap-2')
                            with scroll_check:
                                check_items = [
                                    ('Luces', 'lightbulb'), ('Neumáticos', 'tire_repair'), 
                                    ('Fluidos', 'water_drop'), ('Batería', 'battery_std'), 
                                    ('Carrocería', 'directions_car'), ('Interior', 'airline_seat_recline_normal'),
                                    ('Parabrisas Delantero', 'window'), ('Parabrisas Trasero', 'window')
                                ]
                            
                            def update_quick_note(name, e):
                                quick_check[name]['note'] = e.value

                            def set_check_status(name, status):
                                quick_check[name]['status'] = status
                                if status == 'OK': quick_check[name]['note'] = ''
                                refresh_checks_ui()

                            def refresh_checks_ui():
                                scroll_check.clear()
                                with scroll_check:
                                    check_items = [
                                        ('Luces', 'lightbulb'), ('Neumáticos', 'tire_repair'), 
                                        ('Fluidos', 'water_drop'), ('Batería', 'battery_std'), 
                                        ('Carrocería', 'directions_car'), ('Interior', 'airline_seat_recline_normal'),
                                        ('Parabrisas Delantero', 'window'), ('Parabrisas Trasero', 'window')
                                    ]
                                    
                                    for item, icon in check_items:
                                        data = quick_check.get(item, {'status':'OK', 'note':''})
                                        if isinstance(data, str): data = {'status': data, 'note': ''}
                                        
                                        is_ok = data.get('status') == 'OK'
                                        
                                        with ui.column().classes('w-full gap-1 p-2 border border-gray-100 rounded-lg hover:border-gray-300 transition-colors bg-gray-50/50'):
                                            with ui.row().classes('w-full items-center justify-between'):
                                                with ui.row().classes('items-center gap-2'):
                                                    ui.icon(icon, size='xs').classes('text-gray-500')
                                                    ui.label(item).classes('text-sm font-bold text-gray-700')
                                                
                                                with ui.row().classes('gap-1'):
                                                    ui.button('OK', on_click=lambda _, n=item: set_check_status(n, 'OK')).props(f'unelevated dense size=sm color={"green" if is_ok else "grey-3"} text-color={"white" if is_ok else "grey-7"}').classes('font-bold px-3 shadow-sm')
                                                    ui.button('REVISAR', on_click=lambda _, n=item: set_check_status(n, 'REVISAR')).props(f'unelevated dense size=sm color={"red" if not is_ok else "grey-3"} text-color={"white" if not is_ok else "grey-7"}').classes('font-bold px-3 shadow-sm')

                                            if not is_ok:
                                                ui.textarea(value=data.get('note', ''), on_change=lambda e, n=item: update_quick_note(n, e), placeholder='Describa la falla...').props('outlined dense text-color=red-9 bg-color=red-1 rows=2').classes('w-full text-xs animate-fade-in')

                            refresh_checks_ui()


                        # Evidence
                        with ui.card().classes('w-full bg-white border border-gray-200 p-5 shadow-sm'):
                            ui.label('EVIDENCIA FOTOGRÁFICA').classes('text-xs font-bold text-blue-600 mb-2 border-b border-blue-100 pb-1 w-full')
                            
                            ev_container = ui.row().classes('w-full gap-2 mt-2 flex-wrap')
                            
                            def refresh_evidence():
                                ev_container.clear()
                                with ev_container:
                                    # Filtrar evidencias de DIAGNÓSTICO (procedimiento robusto)
                                    existing = []
                                    for p in (order.fotos_evidencia or []):
                                        if isinstance(p, dict):
                                            fase = str(p.get('fase', '')).upper()
                                            if 'DIAG' in fase:
                                                existing.append(p)
                                        # Si es string, no es de diagnóstico a menos que el path lo diga
                                        elif isinstance(p, str) and 'DIAG' in p.upper():
                                            existing.append(p)
                                    
                                    if not existing and not new_evidence_files:
                                        ui.label('Sin fotos de diagnóstico').classes('text-gray-400 italic text-xs py-4 mx-auto')

                                    for p in existing:
                                        path = p.get('path') if isinstance(p, dict) else p
                                        with ui.card().classes('w-20 h-20 p-0 relative border border-gray-200 group overflow-hidden shadow-sm hover:shadow-md transition-shadow'):
                                            ui.image(path).classes('w-full h-full object-cover cursor-pointer').on('click', lambda p=path: ui.open(p, '_blank'))
                                            ui.button(icon='close', on_click=lambda p=path: remove_evidence(p)).props('flat dense color=red round size=xs').classes('absolute -top-1 -right-1 bg-white shadow-sm z-10')
                                    
                                    # New uploads placeholders (with preview!)
                                    import base64
                                    for name, content in new_evidence_files:
                                        try:
                                            b64 = base64.b64encode(content).decode('utf-8')
                                            src = f'data:image/jpeg;base64,{b64}'
                                            with ui.card().classes('w-20 h-20 p-0 relative border border-green-400 group overflow-hidden'):
                                                ui.image(src).classes('w-full h-full object-cover rounded')
                                                ui.button(icon='close', on_click=lambda n=name: remove_new_evidence(n)).props('flat dense color=red round size=xs').classes('absolute -top-1 -right-1 bg-white shadow-sm z-10')
                                        except:
                                            with ui.card().classes('w-20 h-20 bg-gray-100 flex items-center justify-center'):
                                                ui.icon('image', color='grey')

                            def remove_new_evidence(name):
                                nonlocal new_evidence_files
                                new_evidence_files = [f for f in new_evidence_files if f[0] != name]
                                refresh_evidence()

                            def remove_evidence(path):
                                current = list(order.fotos_evidencia or [])
                                # Eliminar por path sea string o dict
                                new_list = []
                                for itm in current:
                                    itm_path = itm.get('path') if isinstance(itm, dict) else itm
                                    if itm_path != path:
                                        new_list.append(itm)
                                
                                order.fotos_evidencia = new_list
                                from sqlalchemy.orm.attributes import flag_modified
                                flag_modified(order, "fotos_evidencia")
                                db.commit()
                                theme.notify_success('Foto eliminada')
                                refresh_evidence()
                            
                            refresh_evidence()
                            
                            async def handle_upload(e):
                                try:
                                    content = None
                                    name = None
                                    
                                    # Helper para obtener atributos de objeto o diccionario
                                    def _get(obj, attr):
                                        if isinstance(obj, dict): return obj.get(attr)
                                        return getattr(obj, attr, None)

                                    name = _get(e, 'name')
                                    
                                    # 1. Intentar desde 'content'
                                    f_obj = _get(e, 'content')
                                    if f_obj:
                                        if hasattr(f_obj, 'seek'): f_obj.seek(0)
                                        content = f_obj.read()
                                        if not name: name = _get(f_obj, 'name')
                                    
                                    # 2. Intentar desde 'file'
                                    if not content:
                                        f_obj = _get(e, 'file')
                                        if f_obj:
                                            if hasattr(f_obj, 'seek'): f_obj.seek(0)
                                            content = f_obj.read()
                                            if not name: name = _get(f_obj, 'name')
                                            
                                    # 3. Intentar desde 'files'
                                    if not content:
                                        files = _get(e, 'files')
                                        if files and len(files) > 0:
                                            f_obj = files[0]
                                            f_content = _get(f_obj, 'content') or f_obj
                                            if hasattr(f_content, 'read'):
                                                if hasattr(f_content, 'seek'): f_content.seek(0)
                                                content = f_content.read()
                                            else: content = f_content
                                            if not name: name = _get(f_obj, 'name')

                                    # 4. Esperar si es corrutina
                                    if hasattr(content, '__await__'):
                                        content = await content
                                    
                                    if content:
                                        final_name = name or f"evidencia_{datetime.now().strftime('%H%M%S')}.jpg"
                                        new_evidence_files.append((final_name, content))
                                        ui.notify(f'Cargada: {final_name}', type='positive')
                                        refresh_evidence()
                                    else:
                                        # Último recurso: debugging
                                        attrs = [a for a in dir(e) if not a.startswith('_')]
                                        theme.notify_error(f"Error: Estructura de archivo no reconocida. Atributos: {attrs}")
                                except Exception as err:
                                    theme.notify_error(f"Error crítico al subir: {str(err)}")
                                
                            ui.upload(on_upload=handle_upload, auto_upload=True).props('flat dense color=blue-7 accept="image/*" label="Agregar fotos"').classes('w-full border-2 border-dashed border-gray-300 rounded-lg p-2 hover:border-blue-400 transition-colors')


            # ─── FOOTER ───
            with ui.row().classes('w-full p-4 bg-gray-50 border-t border-gray-200 justify-end gap-3'):
                ui.button('CANCELAR', on_click=dialog.close).props('flat color=grey-7')
                
                def save_diagnosis(advance=False):
                    files_db = get_db()
                    try:
                        o = files_db.query(Orden).filter_by(consecutivo=consecutivo).first()
                        if not o:
                             theme.notify_error('Error: Orden no encontrada al guardar')
                             return

                        # 1. Save Files
                        if new_evidence_files:
                            from sqlalchemy.orm.attributes import flag_modified
                            # Use a safe folder name
                            folder_name = consecutivo.replace('#','').replace('/','_').strip()
                            save_dir = f"static/evidencia/{folder_name}"
                            os.makedirs(save_dir, exist_ok=True)
                            
                            current_pics = list(o.fotos_evidencia or [])
                            for fname, fcontent in new_evidence_files:
                                # Ensure unique filename
                                safe_fname = f"{datetime.now().strftime('%H%M%S')}_{fname}"
                                fpath = os.path.join(save_dir, safe_fname)
                                with open(fpath, 'wb') as f:
                                    f.write(fcontent)
                                current_pics.append({'path': f"/evidencia/{folder_name}/{safe_fname}", 'fase': 'DIAGNÓSTICO'})
                            
                            o.fotos_evidencia = current_pics
                            flag_modified(o, "fotos_evidencia")
                        
                        # 2. Update Order Fields
                        o.motivo = d_motivo.value
                        o.km = km_input.value
                        
                        # 3. Construct text
                        sys_list = d_system.value if isinstance(d_system.value, list) else [str(d_system.value)]
                        sys_str = ", ".join([str(s) for s in sys_list])
                        
                        summary_text = f"""SISTEMA: {sys_str} | CÓDIGOS: {diag_struct.get('codes', 'N/A')}\n
PRUEBAS REALIZADAS:
{d_pruebas.value}

HALLAZGOS / ANÁLISIS:
{d_analisis.value}

SOLUCIÓN RECOMENDADA:
{d_solucion.value}"""
                        o.diagnostico = summary_text
                        
                        # 4. Structured Data
                        full_struct = {
                            'quick_check': quick_check,
                            'findings': findings_ref['items'],
                            'diagnostic_details': {
                                'system': d_system.value,
                                'codes': diag_struct.get('codes', ''), # Keep codes in diag_struct for backward compatibility if needed
                                'scanner_path': diag_struct.get('scanner_path', ''),
                                'tests': d_pruebas.value,
                                'analysis': d_analisis.value,
                                'solution': d_solucion.value
                            }
                        }
                        o.checklist_reparacion = full_struct
                        from sqlalchemy.orm.attributes import flag_modified
                        flag_modified(o, "checklist_reparacion")
                        
                        # 5. State
                        if advance:
                            next_idx = min(ESTADOS.index('DIAGNÓSTICO') + 1, len(ESTADOS) - 1)
                            next_est = ESTADOS[next_idx]
                            o.estado = next_est
                            from utils.models import log_actividad
                            log_actividad(f'Diagnóstico finalizado {consecutivo} -> {next_est}', 'ordenes')
                        else:
                            from utils.models import log_actividad
                            log_actividad(f'Diagnóstico actualizado {consecutivo}', 'ordenes')
                        
                        files_db.commit()
                        theme.notify_success('Diagnóstico guardado correctamente')
                        dialog.close()
                        refresh_orders(container, state, stats_container)
                        
                    except Exception as e:
                        files_db.rollback()
                        import traceback
                        traceback.print_exc()
                        theme.notify_error(f"Error al guardar: {str(e)}")
                    finally:
                        files_db.close()

                ui.button('GUARDAR', on_click=lambda: save_diagnosis(False)).props('unelevated text-color=white').classes('bg-gray-600 font-bold px-4 shadow-sm hover:shadow-md')
                ui.button('GUARDAR Y FINALIZAR', icon='check_circle', on_click=lambda: save_diagnosis(True)).props('unelevated text-color=white').classes('bg-blue-600 font-bold px-6 shadow-sm hover:shadow-md')

        dialog.props('maximized transition-show=slide-up transition-hide=slide-down')
        dialog.open()
    except Exception as e:
        import traceback
        traceback.print_exc()
        theme.notify_error(f'Error al abrir diagnóstico: {str(e)}')
    finally:
        db.close()


def open_advance_diagnostic_dialog(consecutivo, container, state, stats_container=None):
    # Dialogo para Diagnóstico
    with ui.dialog() as dialog, ui.card().classes('w-full max-w-lg bg-white p-0 border border-gray-200 shadow-xl rounded-xl overflow-hidden'):
        # Header Corporativo
        with ui.row().classes('w-full justify-between items-center p-5 bg-[#274495]'):
            ui.label('Gestión de Diagnóstico').classes('text-lg font-bold text-white tracking-tight')
            ui.button(icon='close', on_click=dialog.close).props('flat round color=white size=sm')
            
        with ui.column().classes('w-full p-6 gap-6'):
            # Contenido principal
            # Check if diagnosis exists
            db = get_db()
            has_diag = False
            try:
                o_check = db.query(Orden).filter_by(consecutivo=consecutivo).first()
                if o_check and (o_check.checklist_reparacion or (o_check.diagnostico and len(o_check.diagnostico) > 10)):
                    has_diag = True
            finally:
                db.close()

            if has_diag:
                ui.label('El diagnóstico ya ha sido registrado. ¿Deseas finalizar esta etapa y pasar a Repuestos?').classes('text-gray-800 text-base font-medium leading-relaxed')
                
                def simple_advance():
                     db = get_db()
                     try:
                         o = db.query(Orden).filter_by(consecutivo=consecutivo).first()
                         if o:
                             # Advance to REPUESTOS
                             next_est = 'REPUESTOS'
                             o.estado = next_est
                             from utils.models import log_actividad
                             log_actividad(f'Orden {consecutivo} avanzada a {next_est}', 'ordenes')
                             db.commit()
                             theme.notify_success(f'Orden avanzada a {next_est}')
                             dialog.close()
                             refresh_orders(container, state, stats_container)
                     finally:
                         db.close()

                with ui.column().classes('w-full gap-3 mt-4'):
                    ui.button('AVANZAR A REPUESTOS', on_click=simple_advance).classes('w-full btn-sandoval h-12 text-sm')
                    ui.button('CANCELAR', on_click=dialog.close).props('unelevated color=grey-9 text-color=white').classes('w-full h-12 font-bold')

            else:
                ui.label('En esta fase tienes la opción de realizar el diagnóstico ¿Qué deseas hacer?').classes('text-gray-800 text-base font-medium leading-relaxed')

                def go_new_diag():
                    dialog.close()
                    open_new_diagnostic_modal(consecutivo, container, state, stats_container)

                def advance_no_diag():
                     db = get_db()
                     try:
                         o = db.query(Orden).filter_by(consecutivo=consecutivo).first()
                         if o:
                             next_idx = min(ESTADOS.index('DIAGNÓSTICO') + 1, len(ESTADOS) - 1)
                             next_est = ESTADOS[next_idx]
                             o.estado = next_est
                             from utils.models import log_actividad
                             log_actividad(f'Orden {consecutivo} avanzada a {next_est} sin diagnóstico explícito', 'ordenes')
                             db.commit()
                             theme.notify_success(f'Orden avanzada a {next_est}')
                             dialog.close()
                             refresh_orders(container, state, stats_container)
                     finally:
                         db.close()

                with ui.column().classes('w-full gap-3 mt-2'):
                    ui.button('REALIZAR DIAGNÓSTICO', icon='biotech', on_click=go_new_diag).classes('w-full btn-sandoval h-12 font-bold')
                    ui.button('AVANZAR SIN DIAGNÓSTICO', icon='skip_next', on_click=advance_no_diag).props('outline color=primary').classes('w-full h-12 font-bold')
                    ui.button('SALIR', on_click=dialog.close).props('flat color=grey-6').classes('w-full h-10 font-bold')
    
    dialog.open()


def open_parts_management_dialog(consecutivo, container, state, stats_container=None):
    """
    Módulo experto de Gestión de Repuestos y Mano de Obra (LIGHT CORPORATE)
    Permite: Búsqueda de inventario, Carga de mano de obra, Control de stock real,
    Deducción automática de inventario y Resumen de costos.
    """
    db = get_db()
    try:
        order = db.query(Orden).filter_by(consecutivo=consecutivo).first()
        if not order:
            theme.notify_error("Orden no encontrada")
            return
        
        current_items = list(order.items_cotizacion or [])
        for itm in current_items:
            if 'categoria' not in itm: itm['categoria'] = itm.get('tipo', 'Repuesto')
            if 'id' not in itm: itm['id'] = secrets.token_hex(4)
    finally:
        db.close()

    # --- DIÁLOGO PRINCIPAL (LIGHT THEME) ---
    with ui.dialog().props('maximized') as main_dialog, ui.card().classes('w-full h-full bg-[#f4f6f9] p-0 gap-0 border-none no-shadow flex-col no-wrap'):
        
        # Header Superior (Azul Corporativo)
        with ui.row().classes('w-full justify-between items-center p-5 bg-[#274495] shadow-lg z-10 flex-none'):
            with ui.row().classes('items-center gap-5'):
                ui.avatar(icon='inventory', color='white', text_color='blue-9').classes('shadow-md')
                with ui.column().classes('gap-0'):
                    ui.label('GESTIÓN DE REPUESTOS Y SERVICIOS').classes('text-white text-xl font-black tracking-tight')
                    ui.label(f'Orden de Servicio: {consecutivo}').classes('text-blue-100 text-[10px] font-bold tracking-widest')
            
            with ui.row().classes('gap-3'):
                ui.button('VALE DE SALIDA', icon='local_shipping').props('unelevated color=white text-color=primary size=sm').classes('font-bold')
                ui.button(icon='close', on_click=main_dialog.close).props('flat round color=white')

        # Contenedor Principal
        with ui.row().classes('w-full flex-1 gap-0 overflow-hidden min-h-0'):
            
            # --- COLUMNA IZQUIERDA: BÚSQUEDA Y CARGA (Azul pálido / Blanco) ---
            with ui.column().classes('w-[420px] h-full bg-white border-r border-gray-200 p-6 gap-6 overflow-y-auto shadow-sm flex-none'):
                
                # Card 1: Buscador de Inventario
                with ui.card().classes('w-full bg-gray-50 border border-gray-100 p-5 gap-4 shadow-sm'):
                    with ui.row().classes('w-full items-center justify-between'):
                        ui.label('BUSCADOR DE PIEZAS').classes('text-[#154c79] text-xs font-black tracking-widest')
                        ui.icon('search', color='primary')
                    
                    search_input = ui.input(placeholder='Buscar por código o nombre...').props('outlined dense bg-color=white').classes('w-full')
                    
                    results_container = ui.column().classes('w-full gap-2')
                    
                    def add_to_list(inv_item, is_labor=False):
                        if is_labor:
                            id_hex = secrets.token_hex(4)
                            current_items.append({
                                'id': id_hex, 'categoria': 'Servicio',
                                'nombre': inv_item['nombre'], 'referencia': 'MANO-DE-OBRA',
                                'cantidad': 1, 'precio_unitario': inv_item['precio'],
                                'total': inv_item['precio'], 'stock_sistema': 9999
                            })
                        else:
                            id_hex = secrets.token_hex(4)
                            current_items.append({
                                'id': id_hex, 'categoria': 'Repuesto',
                                'nombre': inv_item.nombre, 'referencia': inv_item.codigo,
                                'cantidad': 1, 'precio_unitario': inv_item.precio,
                                'total': inv_item.precio, 'stock_sistema': inv_item.stock
                            })
                        refresh_table()
                        ui.notify(f"Añadido: {inv_item['nombre'] if isinstance(inv_item, dict) else inv_item.nombre}", type='positive')

                    def perform_search():
                        results_container.clear()
                        term = search_input.value.strip()
                        if len(term) < 2: return
                        
                        sdb = get_db()
                        try:
                            items = sdb.query(ItemInventario).filter(
                                (ItemInventario.nombre.ilike(f'%{term}%')) | 
                                (ItemInventario.codigo.ilike(f'%{term}%'))
                            ).limit(5).all()
                            
                            with results_container:
                                for itm in items:
                                    stock_color = 'text-green-600' if itm.stock > 0 else 'text-red-600'
                                    with ui.row().classes('w-full items-center justify-between p-3 rounded-lg border border-gray-100 hover:bg-blue-50 cursor-pointer transition-all').on('click', lambda _, i=itm: add_to_list(i)):
                                        with ui.column().classes('gap-0'):
                                            ui.label(itm.nombre).classes('text-gray-900 text-sm font-bold')
                                            ui.label(f"SKU: {itm.codigo}").classes('text-gray-500 text-[10px]')
                                        with ui.column().classes('items-end gap-0'):
                                            ui.label(f"S/ {itm.precio:.2f}").classes('text-[#154c79] font-black')
                                            ui.label(f"Stock: {itm.stock}").classes(f'{stock_color} text-[10px] font-bold')
                                
                                if not items:
                                    ui.label('No hay coincidencias').classes('text-gray-400 text-xs italic py-2')
                        finally: sdb.close()
                    
                    search_input.on('update:model-value', perform_search)

                    # Botón (+) Quick Add
                    with ui.row().classes('w-full pt-1'):
                        def open_quick_add():
                            with ui.dialog() as quick_dialog, ui.card().classes('bg-white w-full max-w-sm p-6'):
                                ui.label('NUEVO REPUESTO AL INVENTARIO').classes('text-[#154c79] font-black mb-4')
                                q_sku = ui.input('Código / SKU').props('outlined dense').classes('w-full mb-3')
                                q_name = ui.input('Descripción de la pieza').props('outlined dense').classes('w-full mb-3')
                                with ui.row().classes('w-full gap-2 mb-3'):
                                    q_cost = ui.number('Costo', value=0).props('outlined dense prefix=S/').classes('flex-1')
                                    q_price = ui.number('Venta', value=0).props('outlined dense prefix=S/').classes('flex-1')
                                q_stock = ui.number('Stock Inicial', value=1).props('outlined dense').classes('w-full mb-4')
                                
                                def save_quick():
                                    if not q_sku.value or not q_name.value:
                                        theme.notify_error("Datos incompletos")
                                        return
                                    qdb = get_db()
                                    try:
                                        new_item = ItemInventario(
                                            codigo=q_sku.value, nombre=q_name.value,
                                            costo=q_cost.value, precio=q_price.value,
                                            stock=int(q_stock.value), tipo='Repuesto', categoria='General'
                                        )
                                        qdb.add(new_item)
                                        qdb.commit()
                                        theme.notify_success("Registrado y Agregado")
                                        add_to_list(new_item)
                                        quick_dialog.close()
                                    except Exception as e: theme.notify_error(f"Error: {e}")
                                    finally: qdb.close()

                                ui.button('REGISTRAR Y AÑADIR (+)', on_click=save_quick).classes('w-full btn-sandoval')
                            quick_dialog.open()

                        ui.button('¿PIEZA NO ENCONTRADA? REGISTRAR AQUÍ (+)', on_click=open_quick_add).props('flat dense size=sm').classes('text-blue-600 font-bold')

                # Card 2: Mano de Obra
                with ui.card().classes('w-full bg-blue-50 border border-blue-100 p-5 gap-4 shadow-sm'):
                    with ui.row().classes('w-full items-center justify-between'):
                        ui.label('MANO DE OBRA / TALLER').classes('text-blue-800 text-xs font-black tracking-widest')
                        ui.icon('build', color='blue-8')
                    
                    labor_service = ui.input(placeholder='Ej: Cambio de aceite, Rectificado...').props('outlined dense bg-color=white').classes('w-full')
                    with ui.row().classes('w-full gap-2'):
                        labor_price = ui.number(value=0, prefix='S/').props('outlined dense bg-color=white').classes('flex-1')
                        ui.button(icon='add', on_click=lambda: (add_to_list({'nombre': labor_service.value, 'precio': labor_price.value}, True), labor_service.set_value(''), labor_price.set_value(0))).props('unelevated color=blue-8').classes('h-10 px-4')

            # --- COLUMNA DERECHA: TABLA Y TOTALES (Blanco / Gris) ---
            with ui.column().classes('flex-1 h-full bg-[#f8f9fa] p-8 gap-6 overflow-y-auto'):
                
                # Header de Listado
                with ui.row().classes('w-full items-center justify-between mb-[-10px]'):
                    ui.label('LISTADO DE ELEMENTOS CARGADOS').classes('text-gray-500 text-xs font-black tracking-widest')
                    ui.badge(f'{len(current_items)} ítems', color='blue-2').classes('text-blue-800 font-bold')

                # Tabla con Scroll Independiente
                with ui.column().classes('w-full flex-1 min-h-0 min-w-0'):
                    with ui.card().classes('w-full bg-white border border-gray-200 p-0 shadow-sm rounded-xl flex-col no-wrap overflow-hidden h-full'):
                        # Cabecera Fija
                        with ui.row().classes('w-full bg-gray-50 py-3 px-6 items-center border-b border-gray-200 flex-none'):
                            for h, w in [('TIPO','12%'),('DESCRIPCIÓN','40%'),('CANT','12%'),('VALOR UNIT.','15%'),('TOTAL','15%')]:
                                ui.label(h).classes('text-gray-400 text-[10px] font-black').style(f'width: {w}')
                        
                        # Cuerpo Scrolleable
                        with ui.scroll_area().classes('w-full flex-1'):
                            table_rows = ui.column().classes('w-full gap-0')

                    def refresh_table():
                        table_rows.clear()
                        sub_rep, sub_mo = 0, 0
                        
                        with table_rows:
                            for idx, itm in enumerate(current_items):
                                is_service = itm.get('categoria') == 'Servicio'
                                icon_type = 'engineering' if is_service else 'settings'
                                icon_color = 'text-blue-800' if is_service else 'text-green-700'
                                
                                has_stock_error = not is_service and itm['cantidad'] > itm.get('stock_sistema', 0)
                                row_bg = 'bg-gray-50' if idx % 2 != 0 else 'bg-white'
                                if has_stock_error: row_bg = 'bg-red-50 border-l-4 border-red-500'

                                with ui.row().classes(f'w-full {row_bg} py-4 px-6 items-center border-b border-gray-100 hover:bg-gray-50 transition-colors'):
                                    # Tipo
                                    with ui.row().classes('items-center gap-2').style('width: 12%'):
                                        ui.icon(icon_type, size='18px').classes(icon_color)
                                        ui.label(itm['categoria'][:3].upper()).classes(f'{icon_color} text-[9px] font-bold')
                                    
                                    # Desc
                                    with ui.column().classes('gap-0').style('width: 40%'):
                                        ui.label(itm['nombre']).classes('text-gray-900 font-bold text-sm')
                                        ui.label(itm.get('referencia', '-')).classes('text-gray-400 text-[10px]')
                                    
                                    # Cantidad
                                    def upd_qty(e, item=itm):
                                        item['cantidad'] = int(e.value or 1)
                                        item['total'] = item['cantidad'] * item['precio_unitario']
                                        refresh_table()
                                    ui.number(value=itm['cantidad'], on_change=upd_qty).props('dense borderless').classes('text-center font-bold text-blue-700').style('width: 12%')
                                    
                                    # Precios
                                    ui.label(f"S/ {itm['precio_unitario']:.2f}").classes('text-gray-600 text-sm').style('width: 15%')
                                    ui.label(f"S/ {itm['total']:.2f}").classes('text-gray-900 font-black text-sm').style('width: 15%')
                                    
                                    # Accion
                                    ui.button(icon='close', on_click=lambda _, i=itm: (current_items.remove(i), refresh_table())).props('flat round color=red-4 size=sm').classes('ml-auto')

                                    if has_stock_error:
                                        with ui.row().classes('w-full px-6 mt-1 items-center gap-2'):
                                            ui.icon('warning', color='red-6', size='14px')
                                            ui.label(f"Stock insuficiente (Disponible: {itm.get('stock_sistema', 0)})").classes('text-red-600 text-[10px] font-bold')

                                if is_service: sub_mo += itm['total']
                                else: sub_rep += itm['total']
                        
                        update_summary(sub_rep, sub_mo)

                # Panel de Pie Fijo
                summary_container = ui.column().classes('w-full bg-white border border-gray-200 p-8 rounded-xl shadow-md mt-4 flex-none')
                
                def update_summary(rep, mo):
                    summary_container.clear()
                    total = rep + mo

                    with summary_container:
                        with ui.row().classes('w-full items-center'):
                            with ui.column().classes('flex-1 gap-2 border-r border-gray-100 pr-8'):
                                for l, v, clr in [('REPUESTOS Y PIEZAS', rep, 'text-gray-900'), ('MANO DE OBRA / SERVICIO', mo, 'text-blue-800')]:
                                    with ui.row().classes('w-full justify-between'):
                                        ui.label(l).classes('text-gray-400 text-[10px] font-black uppercase')
                                        ui.label(f"S/ {v:.2f}").classes(f'{clr} font-bold text-lg')

                            with ui.column().classes('items-end justify-center pl-8'):
                                ui.label('MONTO TOTAL NETO').classes('text-gray-400 text-xs font-black mb-1')
                                ui.label(f"S/ {total:.2f}").classes('text-[#154c79] text-6xl font-black')
                        
                        with ui.row().classes('w-full mt-8 gap-4 justify-end'):
                            def finalize():
                                if not current_items: return theme.notify_warning("Cargue al menos un ítem")
                                fdb = get_db()
                                try:
                                    o = fdb.query(Orden).filter_by(consecutivo=consecutivo).first()
                                    if o:
                                        o.items_cotizacion = current_items
                                        o.estado = 'APROBACIÓN'
                                        for itm in current_items: # Descontar stock
                                            if itm.get('categoria') == 'Repuesto':
                                                inv = fdb.query(ItemInventario).filter_by(codigo=itm['referencia']).first()
                                                if inv: inv.stock = max(0, inv.stock - itm['cantidad'])
                                        fdb.commit()
                                        theme.notify_success("Cotización guardada e Inventario actualizado")
                                        main_dialog.close()
                                        refresh_orders(container, state, stats_container)
                                except Exception as e: theme.notify_error(f"Error: {e}")
                                finally: fdb.close()

                            def save_progress():
                                if not current_items: return theme.notify_warning("No hay ítems para guardar")
                                sdb = get_db()
                                try:
                                    o = sdb.query(Orden).filter_by(consecutivo=consecutivo).first()
                                    if o:
                                        o.items_cotizacion = current_items
                                        sdb.commit()
                                        theme.notify_success("Progreso guardado (Estado mantenido en REPUESTOS)")
                                        main_dialog.close()
                                        refresh_orders(container, state, stats_container)
                                except Exception as e: theme.notify_error(f"Error: {e}")
                                finally: sdb.close()

                            ui.button('GUARDAR PROGRESO', icon='save', on_click=save_progress).props('outline color=primary').classes('px-8 h-12 font-bold')
                            ui.button('CONFIRMAR Y FINALIZAR', icon='check_circle', on_click=finalize).classes('px-8 h-12 btn-sandoval text-white')
                            ui.button('CANCELAR', on_click=main_dialog.close).props('flat color=grey-6').classes('h-12')

                refresh_table()

        main_dialog.open()


def open_advance_parts_dialog(consecutivo, container, state, stats_container=None):
    """Diálogo intermedio para la fase de REPUESTOS con lógica de confirmación"""
    db = get_db()
    has_items = False
    try:
        ord_ = db.query(Orden).filter_by(consecutivo=consecutivo).first()
        if ord_ and ord_.items_cotizacion and len(ord_.items_cotizacion) > 0:
            has_items = True
    finally:
        db.close()

    with ui.dialog() as dialog, ui.card().classes('w-full max-w-lg bg-white p-0 border border-gray-200 shadow-xl rounded-xl overflow-hidden'):
        # Header
        with ui.row().classes('w-full justify-between items-center p-4 bg-[#154c79]'):
            ui.label('Gestión de Repuestos y Servicios').classes('text-lg font-bold text-white')
            ui.button(icon='close', on_click=dialog.close).props('flat round color=white size=sm')
            
        with ui.column().classes('w-full p-6 gap-6'):
            if has_items:
                ui.label('La lista de repuestos y servicios ya ha sido registrada correctamente. ¿Deseas finalizar esta etapa y pasar a la fase de APROBACIÓN?').classes('text-gray-800 text-base font-medium leading-relaxed')
                
                def proceed():
                    advance_order(consecutivo, 'APROBACIÓN')
                    dialog.close()
                    refresh_orders(container, state, stats_container)
                
                def edit():
                    dialog.close()
                    open_parts_management_dialog(consecutivo, container, state, stats_container)

                with ui.column().classes('w-full gap-3 mt-2'):
                    ui.button('SÍ, AVANZAR A APROBACIÓN', icon='check_circle', on_click=proceed).classes('w-full btn-sandoval h-12 font-bold')
                    ui.button('MODIFICAR / EDITAR LISTA', icon='edit', on_click=edit).props('outline color=primary').classes('w-full h-12 font-bold')
            else:
                ui.label('Aún no has cargado repuestos o servicios a esta orden. ¿Qué deseas hacer?').classes('text-gray-800 text-base font-medium leading-relaxed')

                def include_prices():
                    dialog.close()
                    open_parts_management_dialog(consecutivo, container, state, stats_container)
                
                def advance_direct():
                    advance_order(consecutivo, 'APROBACIÓN')
                    dialog.close()
                    refresh_orders(container, state, stats_container)

                with ui.column().classes('w-full gap-3 mt-2'):
                    ui.button('CARGAR REPUESTOS / PRECIOS', icon='add_shopping_cart', on_click=include_prices).classes('w-full btn-sandoval h-12 font-bold')
                    ui.button('AVANZAR SIN PRECIOS', icon='fast_forward', on_click=advance_direct).props('flat color=grey-7').classes('w-full h-10 font-bold')
            
            ui.button('SALIR', on_click=dialog.close).props('flat color=grey-6').classes('w-full h-10')
    
    dialog.open()


def open_advance_approval_dialog(consecutivo, container, state, stats_container=None):
    """Diálogo intermedio para la fase de APROBACIÓN"""
    with ui.dialog() as dialog, ui.card().classes('w-full max-w-lg bg-white p-0 border border-gray-200 shadow-xl rounded-xl overflow-hidden'):
        # Header Corporativo
        with ui.row().classes('w-full justify-between items-center p-4 bg-[#154c79]'):
            ui.label('Gestión de Aprobación').classes('text-lg font-bold text-white')
            ui.button(icon='close', on_click=dialog.close).props('flat round color=white size=sm')
            
        with ui.column().classes('w-full p-6 gap-6'):
            ui.label('En esta fase puedes revisar los costos del servicio y enviar el presupuesto al cliente para su aprobación. ¿Qué deseas hacer?').classes('text-gray-800 text-base font-medium leading-relaxed')

            def review_and_send():
                dialog.close()
                open_order_detail(consecutivo, container, state)
            
            def advance_direct():
                # De APROBACIÓN a REPARACIÓN
                try:
                    advance_order(consecutivo, 'REPARACIÓN')
                    dialog.close()
                    refresh_orders(container, state, stats_container)
                except Exception as e:
                    theme.notify_error(f"Error al avanzar: {e}")

            # Helper functions to convert SQLAlchemy objects to dicts for PDF generation
            def _order_to_dict(order_obj):
                return {c.name: getattr(order_obj, c.name) for c in order_obj.__table__.columns} if order_obj else {}

            def _client_to_dict(client_obj):
                return {c.name: getattr(client_obj, c.name) for c in client_obj.__table__.columns} if client_obj else {}

            def _vehicle_to_dict(vehicle_obj):
                return {c.name: getattr(vehicle_obj, c.name) for c in vehicle_obj.__table__.columns} if vehicle_obj else {}

            def download_pdfs(ptype):
                # Helper to get dicts and call generate_pdf
                db_pdf = get_db()
                try:
                    o_row = db_pdf.query(Orden).filter_by(consecutivo=consecutivo).first()
                    c_row = db_pdf.query(Cliente).filter_by(id=o_row.cliente_id).first()
                    v_row = db_pdf.query(Vehiculo).filter_by(placa=o_row.vehiculo_placa).first()
                    generate_pdf(_order_to_dict(o_row), _client_to_dict(c_row), _vehicle_to_dict(v_row), ptype)
                finally:
                    db_pdf.close()

            with ui.column().classes('w-full gap-3 mt-2'):
                ui.button('REVISAR Y ENVIAR', icon='visibility', on_click=review_and_send).classes('w-full btn-sandoval h-12 font-bold')
                
                with ui.row().classes('w-full gap-2 mt-2'):
                    ui.button('PDF COTIZACIÓN', icon='request_quote', on_click=lambda: download_pdfs('cotizacion')).props('outline color=blue font-bold size=sm').classes('flex-1 h-10')
                    ui.button('PDF INGRESO', icon='description', on_click=lambda: download_pdfs('ingreso')).props('outline color=orange font-bold size=sm').classes('flex-1 h-10')

                ui.button('AVANZAR SIN ENVIAR PRESUPUESTO', icon='fast_forward', on_click=advance_direct).props('outline color=primary').classes('w-full h-12 font-bold')
                ui.button('SALIR', on_click=dialog.close).props('flat color=grey-6').classes('w-full h-10 font-bold')
    
    dialog.open()


def open_advance_repair_dialog(consecutivo, container, state, stats_container=None):
    """Diálogo intermedio para la fase de REPARACIÓN"""
    with ui.dialog() as dialog, ui.card().classes('w-full max-w-lg bg-white p-0 border border-gray-200 shadow-xl rounded-xl overflow-hidden'):
        # Header Corporativo
        with ui.row().classes('w-full justify-between items-center p-4 bg-[#154c79]'):
            ui.label('Avanzar Reparación').classes('text-lg font-bold text-white')
            ui.button(icon='close', on_click=dialog.close).props('flat round color=white size=sm')
            
        with ui.column().classes('w-full p-6 gap-6'):
            ui.label('Recuerda que tu cliente estará más satisfecho si completas la evidencia de reparación. ¿Qué deseas hacer?').classes('text-gray-800 text-base font-medium leading-relaxed')

            def include_evidence():
                dialog.close()
                open_advanced_repair_module(consecutivo, container, state, stats_container)
            
            def advance_direct():
                # De REPARACIÓN a CONTROL
                try:
                    advance_order(consecutivo, 'CONTROL')
                    dialog.close()
                    refresh_orders(container, state, stats_container)
                except Exception as e:
                    theme.notify_error(f"Error al avanzar: {e}")

            with ui.column().classes('w-full gap-3 mt-2'):
                ui.button('INCLUIR EVIDENCIA', icon='add_a_photo', on_click=include_evidence).classes('w-full btn-sandoval h-12 font-bold')
                ui.button('AVANZAR SIN EVIDENCIA', icon='fast_forward', on_click=advance_direct).props('outline color=primary').classes('w-full h-12 font-bold text-sm')
                ui.button('SALIR', on_click=dialog.close).props('flat color=grey-6').classes('w-full h-10 font-bold')
    
    dialog.open()



def open_archive_dialog(consecutivo: str, container, state, stats_container=None):
    """Diálogo de finalización/archivado con opciones de encuesta de satisfacción."""
    from utils.models import Orden, Cliente
    db = get_db()
    order = db.query(Orden).filter_by(consecutivo=consecutivo).first()
    client = db.query(Cliente).filter_by(id=order.cliente_id).first() if order and order.cliente_id else None
    db.close()
    
    with ui.dialog() as dlg, ui.card().style('width:460px; border-radius:20px; padding:0; overflow:hidden; box-shadow:0 20px 40px rgba(0,0,0,0.1);'):
        # Header Light
        with ui.element('div').style('background:linear-gradient(135deg,#f8fafc,#f1f5f9); padding:24px 30px; border-bottom:1px solid #e2e8f0;'):
            with ui.row().classes('w-full justify-between items-center'):
                with ui.row().classes('items-center gap-3'):
                    ui.icon('check_circle', size='md', color='green-6')
                    ui.label('Finalizar!').style('font-size:24px; font-weight:800; color:#1e293b; font-family:Inter,sans-serif;')
                ui.button(icon='close', on_click=dlg.close).props('flat round color=grey-5')

        with ui.column().classes('w-full p-8 gap-4'):
            ui.label('Esta orden de servicio se cerrará, ¿Cómo deseas enviar la encuesta de satisfacción?').style('font-size:15px; color:#475569; line-height:1.6; font-family:Inter,sans-serif;')

            def _btn_style(bg='#bef264', text='#166534'):
                return f'width:100%; height:50px; border-radius:12px; font-weight:700; font-size:12px; background:{bg}; color:{text}; letter-spacing:0.5px; transition:all 0.2s;'

            async def _do_archive(method=None):
                advance_order(consecutivo, 'ARCHIVADO')
                dlg.close()
                refresh_orders(container, state, stats_container)
                try:
                    theme.notify_success(f'✅ Orden {consecutivo} finalizada y archivada.')
                    if method:
                        theme.notify_info(f'Encuesta preparada vía {method}')
                except Exception:
                    pass  # El contexto UI ya fue destruido, no hay donde mostrar la notificación
                    
            def _open_wa_encuesta():
                if not client or not client.telefono:
                    theme.notify_warning('El cliente no tiene teléfono registrado.')
                    return
                
                # Obtener HOST dinámico
                import socket
                try: host = socket.gethostbyname(socket.gethostname())
                except: host = 'localhost'
                
                # Usar el token del reporte para la encuesta también
                token = order.report_token
                if not token: # Por si acaso no tiene token de reporte aún
                    import secrets
                    token = secrets.token_urlsafe(32)
                    db2 = get_db()
                    db2.execute(__import__('sqlalchemy').text("UPDATE ordenes SET report_token = :t WHERE consecutivo = :c"), {"t": token, "c": consecutivo})
                    db2.commit()
                    db2.close()

                url = f"http://{host}:8088/encuesta/{token}"
                phone = client.telefono.replace(' ','').replace('+','').replace('-','')
                
                msg = (
                    f"✅ *SERVICIO FINALIZADO*\n"
                    f"━━━━━━━━━━━━━━━━━━\n\n"
                    f"Hola *{client.nombre}*,\n\n"
                    f"Su vehículo ha sido entregado exitosamente. Nos encantaría que califique nuestra atención aquí:\n"
                    f"🔗 {url}\n\n"
                    f"¡Muchas gracias por confiar en SANDOVAL! ✨"
                )
                import urllib.parse
                link = f"https://wa.me/{phone}?text={urllib.parse.quote(msg)}"
                ui.run_javascript(f'window.open("{link}", "_blank")')
                _do_archive('WhatsApp')

            # Botones de Acción (Estilo Limón/Luz como pidió el usuario)
            ui.button('VÍA WHATSAPP', on_click=_open_wa_encuesta).style(_btn_style()).props('unelevated')
            ui.button('VÍA SMS', on_click=lambda: _do_archive('SMS')).style(_btn_style()).props('unelevated')
            ui.button('FINALIZAR SIN NOTIFICAR', on_click=lambda: _do_archive()).style(_btn_style()).props('unelevated')
            
            ui.button('VER ODS', on_click=lambda: (dlg.close(), open_order_detail(consecutivo, container, state))).style(_btn_style('#fef9c3', '#854d0e')).props('unelevated')
            
            ui.button('SALIR', on_click=dlg.close).props('flat').style('width:100%; color:#64748b; font-weight:700; margin-top:4px;')
        
    dlg.open()


def _render_order_card(order, clients, vehicles, container, state, stats_container=None):
    cur_estado = (order.estado or 'RECEPCIÓN').strip().upper()
    cfg = theme.ESTADOS_CONFIG.get(cur_estado, theme.ESTADOS_CONFIG.get('RECEPCIÓN'))
    client = clients.get(order.cliente_id)
    vehicle = vehicles.get(order.vehiculo_placa)
    
    with ui.card().classes('w-full bg-white border border-gray-200 hover:border-indigo-500 hover:shadow-md transition-all p-4 shadow-sm group'):
        with ui.row().classes('w-full items-center justify-between'):
            with ui.row().classes('items-center gap-4 flex-1'):
                # Icono de estado con fondo círculo
                with ui.avatar(color=cfg['color']+'-1', text_color=cfg['color']).classes('w-12 h-12'):
                    ui.icon(cfg['icon'], size='sm')

                with ui.column().classes('gap-1 flex-1'):
                    with ui.row().classes('items-center gap-2'):
                        ui.label(order.consecutivo).classes('text-indigo-900 font-bold text-lg cursor-pointer hover:underline underline-offset-4 decoration-indigo-300').on('click', lambda: open_order_detail(order.consecutivo, container, state))
                        ui.label(order.estado).classes(f'text-[10px] px-2 py-0.5 rounded-full bg-{cfg["color"]}-100 text-{cfg["color"]} font-bold uppercase tracking-wider')
                    
                    if client:
                        ui.label(f"{client.nombre} {client.apellidos}").classes('text-sm font-semibold text-gray-700')
                    
                    with ui.row().classes('items-center gap-3 text-gray-400 text-[11px]'):
                        if vehicle:
                             with ui.row().classes('items-center gap-1'):
                                 ui.icon('directions_car', size='xs')
                                 ui.label(vehicle.placa)
                        with ui.row().classes('items-center gap-1'):
                            ui.icon('calendar_month', size='xs')
                            ui.label(order.fecha[:10])
                        if order.tecnico:
                             ui.label(f"Técnico: {order.tecnico}").classes('text-indigo-600 text-xs font-medium')
                    
                    if order.motivo:
                        ui.label(order.motivo[:100] + ('...' if len(order.motivo or '') > 100 else '')).classes('text-gray-500 text-xs mt-1 italic')
            
            with ui.row().classes('gap-1'):
                # Vista Cliente (Ojo)
                has_diag = bool(order.checklist_reparacion or (order.diagnostico and len(order.diagnostico or '') > 10))
                if cur_estado == 'DIAGNÓSTICO' and not has_diag:
                    ui.button(icon='visibility').props('flat dense color=grey-4 size=sm disable').tooltip('Sin Diagnóstico')
                elif cur_estado == 'REPARACIÓN':
                    ui.button(icon='visibility', on_click=lambda o=order: open_repair_view_dialog(o.consecutivo)).props('flat dense color=cyan-7 size=sm').tooltip('Ver Informe Reparación')
                else:
                    ui.button(icon='visibility', on_click=lambda o=order: open_customer_preview(o.consecutivo)).props('flat dense color=cyan-7 size=sm').tooltip('Vista Cliente')
                
                # Editar (Lápiz)
                if cur_estado == 'DIAGNÓSTICO':
                    ui.button(icon='edit', on_click=lambda o=order: open_new_diagnostic_modal(o.consecutivo, container, state, stats_container)).props('flat dense color=amber-8 size=sm').tooltip('Editar Diagnóstico')
                elif cur_estado in ('REPUESTOS', 'APROBACIÓN'):
                    ui.button(icon='edit', on_click=lambda o=order: open_parts_management_dialog(o.consecutivo, container, state, stats_container)).props('flat dense color=amber-8 size=sm').tooltip('Editar Repuestos/Servicios')
                elif cur_estado == 'REPARACIÓN':
                    ui.button(icon='edit', on_click=lambda o=order: open_advanced_repair_module(o.consecutivo, container, state, stats_container)).props('flat dense color=amber-8 size=sm').tooltip('Editar Reparación')
                else:
                    ui.button(icon='edit', on_click=lambda o=order: open_edit_reception_dialog(o.consecutivo, container, state)).props('flat dense color=amber-8 size=sm').tooltip('Editar Recepción')
                
                # Gestión Interna (Llave/Settings)
                ui.button(icon='settings', on_click=lambda o=order: open_order_detail(o.consecutivo, container, state)).props('flat dense color=grey-7 size=sm').tooltip('Detalles')
                
                # Retroceder (Flecha Izquierda)
                try:
                    curr_idx = ESTADOS.index(cur_estado)
                except ValueError:
                    curr_idx = 0
                
                if curr_idx > 0:
                     prev_est = ESTADOS[curr_idx - 1]
                     ui.button(icon='arrow_back',
                         on_click=lambda o=order, pe=prev_est: (regress_order(o.consecutivo, pe), refresh_orders(container, state, stats_container))
                     ).props(f'flat dense color={cfg["color"]} size=sm').tooltip(f'Retroceder -> {prev_est}')

                if cur_estado != 'ARCHIVADO':
                    next_idx = min(curr_idx + 1, len(ESTADOS) - 1)
                    next_est = ESTADOS[next_idx]
                    
                    if cur_estado == 'RECEPCIÓN':
                         ui.button(icon='arrow_forward', 
                             on_click=lambda o=order: open_advance_reception_dialog(o.consecutivo, container, state, stats_container)
                         ).props(f'flat dense color={cfg["color"]} size=sm').tooltip(f'Avanzar -> {next_est}')
                    elif cur_estado == 'DIAGNÓSTICO':
                         ui.button(icon='arrow_forward', 
                             on_click=lambda o=order: open_advance_diagnostic_dialog(o.consecutivo, container, state, stats_container)
                         ).props(f'flat dense color={cfg["color"]} size=sm').tooltip(f'Avanzar -> {next_est}')
                    elif cur_estado == 'REPUESTOS':
                         ui.button(icon='arrow_forward', 
                             on_click=lambda o=order: open_advance_parts_dialog(o.consecutivo, container, state, stats_container)
                         ).props(f'flat dense color={cfg["color"]} size=sm').tooltip(f'Avanzar -> {next_est}')
                    elif cur_estado == 'APROBACIÓN':
                         ui.button(icon='arrow_forward', 
                             on_click=lambda o=order: open_advance_approval_dialog(o.consecutivo, container, state, stats_container)
                         ).props(f'flat dense color={cfg["color"]} size=sm').tooltip(f'Avanzar -> {next_est}')
                    elif cur_estado == 'REPARACIÓN':
                         ui.button(icon='arrow_forward', 
                             on_click=lambda o=order: open_advance_repair_dialog(o.consecutivo, container, state, stats_container)
                         ).props(f'flat dense color={cfg["color"]} size=sm').tooltip(f'Avanzar -> {next_est}')
                    elif cur_estado == 'CONTROL':
                         ui.button(icon='arrow_forward',
                             on_click=lambda o=order: open_quality_control_dialog(o.consecutivo, container, state, stats_container)
                         ).props(f'flat dense color={cfg["color"]} size=sm').tooltip('Control de Calidad → Entrega')
                    elif cur_estado == 'ENTREGA':
                         ui.button(icon='arrow_forward', 
                             on_click=lambda o=order: open_archive_dialog(o.consecutivo, container, state, stats_container)
                         ).props(f'flat dense color={cfg["color"]} size=sm').tooltip('Finalizar y Archivar')
                    else:
                        ui.button(icon='arrow_forward', 
                            on_click=lambda o=order, ne=next_est: (advance_order(o.consecutivo, ne), refresh_orders(container, state, stats_container))
                        ).props(f'flat dense color={cfg["color"]} size=sm').tooltip(f'Avanzar -> {next_est}')




def open_quality_control_dialog(consecutivo: str, container, state, stats_container=None):
    """Control de Calidad — UI premium light-theme, inspección final."""
    db = get_db()
    try:
        order   = db.query(Orden).filter_by(consecutivo=consecutivo).first()
        if not order: return
        client  = db.query(Cliente).filter_by(id=order.cliente_id).first()  if order.cliente_id   else None
        vehicle = db.query(Vehiculo).filter_by(placa=order.vehiculo_placa).first() if order.vehiculo_placa else None

        from sqlalchemy import text as sa_text
        raw_row = db.execute(
            sa_text("SELECT checklist_reparacion FROM ordenes WHERE consecutivo = :c"),
            {"c": consecutivo}
        ).fetchone()
        raw_chk = raw_row[0] if raw_row else None
        if isinstance(raw_chk, str):
            try:
                parsed = json.loads(raw_chk)
                saved_data = parsed if isinstance(parsed, dict) else {}
            except: saved_data = {}
        elif isinstance(raw_chk, dict):
            saved_data = dict(raw_chk)
        else:
            saved_data = {}
    finally:
        db.close()

    client_name  = (client.nombre + ' ' + (client.apellidos or '')).strip() if client else '—'
    vehicle_info = f"{vehicle.marca} {vehicle.modelo} {vehicle.año}" if vehicle else '—'
    vehicle_placa= vehicle.placa if vehicle else '—'
    technician   = order.tecnico or 'No asignado'
    diagnostico  = (order.diagnostico or '—')[:250]
    motivo       = (order.motivo or '—')[:150]

    # Logs de reparación para mostrar qué se hizo
    repair_logs  = saved_data.get('repair_logs', [])
    ev_cats      = saved_data.get('evidence_cats', {})
    total_fotos  = sum(len(v) for v in ev_cats.values())

    # ── Checklist agrupado ────────────────────────────────────────
    GROUPS = [
        {
            'title': '🔧 Verificación del trabajo realizado',
            'color': '#3b82f6',
            'bg':    '#eff6ff',
            'items': [
                ('repair_done',    'Reparación completada',      'Se realizó todo el trabajo indicado en la ODS'),
                ('parts_ok',       'Repuestos instalados',        'Todos los repuestos quedaron correctamente colocados'),
                ('no_leaks',       'Sin fugas ni escapes',        'Aceite, refrigerante, frenos, dirección hidráulica'),
                ('fluids_level',   'Niveles de fluidos',          'Aceite, refrigerante, limpiaparabrisas correctos'),
                ('engine_start',   'Motor arranca correctamente', 'Sin ruidos anormales al encender'),
                ('brakes_test',    'Prueba de frenos',            'Respuesta adecuada, pedal firme, sin ruidos'),
            ],
        },
        {
            'title': '🚗 Revisión estética y entrega',
            'color': '#10b981',
            'bg':    '#f0fdf4',
            'items': [
                ('bodywork_ok',    'Carrocería sin daños nuevos', 'Sin abolladuras o rayones causados durante el servicio'),
                ('interior_ok',    'Cabina limpia y en orden',    'Asientos, volante, tablero, alfombras limpias'),
                ('glass_ok',       'Vidrios y lunas',             'Sin fisuras, sin huellas de trabajo'),
                ('lights_ok',      'Alumbrado funcional',         'Faros, direccionales, luces traseras y tablero'),
                ('tires_ok',       'Neumáticos y presión',        'Presión correcta, sin pinchazos ni desgaste'),
                ('tools_removed',  'Herramientas retiradas',      'No queda ninguna herramienta dentro del vehículo'),
            ],
        },
        {
            'title': '📋 Documentación y entrega',
            'color': '#8b5cf6',
            'bg':    '#f5f3ff',
            'items': [
                ('evidence_ok',    'Evidencia fotográfica',       f'Fotos registradas en el sistema ({total_fotos} foto(s))'),
                ('order_signed',   'Orden de servicio firmada',   'Cliente firma conforme con el trabajo realizado'),
                ('warranty_given', 'Garantía entregada',          'Se explica al cliente el período de garantía'),
                ('payment_ok',     'Pago / factura',              'Pago procesado o crédito acordado correctamente'),
            ],
        },
    ]

    all_keys = [it[0] for g in GROUPS for it in g['items']]
    check_state = {k: {'status': None, 'note': ''} for k in all_keys}
    saved_qc = saved_data.get('quality_control', {})
    for k in check_state:
        if k in saved_qc:
            check_state[k] = dict(saved_qc[k])

    total_items = len(all_keys)

    # ── Función para generar/obtener el link de WhatsApp desde adentro ──
    async def _get_wa_link():
        import secrets, urllib.parse, socket, json
        db = get_db()
        # Generar o recuperar token
        row = db.execute(sa_text("SELECT report_token, cliente_id, vehiculo_placa FROM ordenes WHERE consecutivo = :c"), {"c": consecutivo}).fetchone()
        token = row[0] if row and row[0] else None
        if not token:
            token = secrets.token_urlsafe(32)
            db.execute(sa_text("UPDATE ordenes SET report_token = :t WHERE consecutivo = :c"), {"t": token, "c": consecutivo})
            db.commit()
        
        # Guardar estado actual antes de enviar para que el cliente vea lo último
        db.execute(sa_text("UPDATE ordenes SET checklist_reparacion = :v WHERE consecutivo = :c"), 
                   {"v": json.dumps({"quality_control": check_state}), "c": consecutivo})
        db.commit()

        # Datos cliente
        cli_name = "Cliente"
        cli_phone = ""
        if row and row[1]:
            cli = db.execute(sa_text("SELECT nombre, telefono FROM clientes WHERE id = :id"), {"id": row[1]}).fetchone()
            if cli:
                cli_name = cli[0]
                cli_phone = (cli[1] or '').replace(' ','').replace('+','').replace('-','')
        
        db.close()
        
        try: host = socket.gethostbyname(socket.gethostname())
        except: host = 'localhost'
        
        url = f"http://{host}:8088/reporte/{token}"
        msg = (
            f"✅ *REPORTE DE SERVICIO FINALIZADO*\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            f"Hola *{cli_name}*,\n\n"
            f"Su vehículo *{vehicle_placa}* ha sido inspeccionado.\n"
            f"Vea el detalle de Diagnóstico, Repuestos y Reparación aquí:\n"
            f"🔗 {url}\n\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"MECÁNICA Y REPUESTOS SANDOVAL ✨"
        )
        return f"https://wa.me/{cli_phone}?text={urllib.parse.quote(msg)}"

    async def _action_send_wa():
        link = await _get_wa_link()
        ui.run_javascript(f'window.open("{link}", "_blank")')
        theme.notify_success('Abriendo WhatsApp...')

    # ── Diálogo de ENVÍO (Pre-creado fuera de dlg para que persista al cerrar el anterior) ──
    send_url_ref   = ['']
    send_wa_ref    = ['']
    
    with ui.dialog() as send_dlg:
        with ui.card().style('width:500px;padding:0;overflow:hidden;border-radius:16px;box-shadow:0 20px 60px rgba(0,0,0,.2);'):
            with ui.element('div').style('background:linear-gradient(135deg,#059669,#10b981);padding:22px 26px;'):
                ui.icon('verified', color='white', size='md')
                ui.label('¡Control de Calidad Aprobado!').style('color:white;font-size:16px;font-weight:800;font-family:Inter,sans-serif;display:block;margin-top:6px;')
                ui.label('La orden avanzó a ENTREGA. Comparte el reporte con el cliente.').style('color:rgba(255,255,255,.8);font-size:11px;margin-top:3px;font-family:Inter,sans-serif;')

            with ui.column().style('padding:22px 26px;gap:14px;'):
                ui.label('🔗 Link del reporte de entrega').style('font-size:11px;font-weight:700;color:#64748b;font-family:Inter,sans-serif;')
                url_input = ui.input().props('readonly outlined dense').style('width:100%;font-size:11px;')

                def _copy_link():
                    url = send_url_ref[0]
                    ui.run_javascript(f'navigator.clipboard.writeText("{url}")')
                    theme.notify_success('¡Link copiado!')

                ui.button('📋 Copiar Link', on_click=_copy_link).props('unelevated').style('background:#e0f2fe;color:#0369a1;width:100%;border-radius:10px;font-weight:700;font-family:Inter,sans-serif;padding:11px;font-size:13px;')

                wa_btn = ui.button('📱 Enviar por WhatsApp').props('unelevated').style('background:#25D366;color:white;width:100%;border-radius:10px;font-weight:700;font-family:Inter,sans-serif;padding:12px;font-size:13px;')
                no_phone_lbl = ui.label('⚠ Sin teléfono — copia el link manualmente.').style('font-size:11px;color:#f59e0b;display:none;')

                def _open_wa():
                    link = send_wa_ref[0]
                    if link:
                        ui.run_javascript(f'window.open("{link}","_blank")')
                wa_btn.on('click', _open_wa)

                def _open_report():
                    url = send_url_ref[0]
                    ui.run_javascript(f'window.open("{url}","_blank")')

                ui.button('🖨️ Ver e Imprimir Reporte', on_click=_open_report).props('unelevated').style('background:#3b82f6;color:white;width:100%;border-radius:10px;font-weight:700;font-family:Inter,sans-serif;padding:12px;font-size:13px;')
                ui.button('Cerrar', on_click=send_dlg.close).props('flat').style('color:#64748b;font-family:Inter,sans-serif;width:100%;')

    with ui.dialog().props('maximized transition-show=slide-up transition-hide=slide-down') as dlg:
        ui.add_head_html(f'''<style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');
        .qcl-root {{ background:#f4f6f9; font-family:'Inter',sans-serif; height:100vh; display:flex; flex-direction:column; }}
        .qcl-topbar {{
            background:white; border-bottom:1px solid #e8edf2;
            padding:14px 28px; display:flex; align-items:center; justify-content:space-between;
            flex-shrink:0; box-shadow:0 1px 4px rgba(0,0,0,.06);
        }}
        .qcl-body {{ display:flex; flex:1; overflow:hidden; gap:0; }}

        /* Panel izquierdo */
        .qcl-left {{
            width:300px; min-width:270px; background:white;
            border-right:1px solid #e8edf2; overflow-y:auto;
            padding:24px 20px; flex-shrink:0;
        }}
        .qcl-section-hdr {{
            font-size:9px; font-weight:800; color:#94a3b8;
            text-transform:uppercase; letter-spacing:.14em;
            margin-bottom:12px; margin-top:20px; padding-bottom:6px;
            border-bottom:1px solid #f1f5f9;
        }}
        .qcl-section-hdr:first-child {{ margin-top:0; }}
        .qcl-info-card {{
            background:#f8fafc; border-radius:10px; padding:12px 14px;
            border:1px solid #e2e8f0; margin-bottom:8px;
        }}
        .qcl-info-label {{ font-size:10px; font-weight:700; color:#94a3b8; text-transform:uppercase; letter-spacing:.08em; }}
        .qcl-info-val   {{ font-size:13px; font-weight:600; color:#1e293b; margin-top:3px; line-height:1.4; }}
        .qcl-info-sub   {{ font-size:11px; color:#64748b; margin-top:2px; }}

        .qcl-log-item {{
            background:#f0fdf4; border:1px solid #bbf7d0; border-radius:8px;
            padding:8px 12px; margin-bottom:6px; font-size:11px; color:#166534;
            line-height:1.5;
        }}
        .qcl-stat-grid {{ display:grid; grid-template-columns:1fr 1fr; gap:8px; margin-bottom:16px; }}
        .qcl-stat-box {{
            background:#f8fafc; border:1px solid #e2e8f0; border-radius:10px;
            padding:12px; text-align:center;
        }}
        .qcl-stat-num {{ font-size:22px; font-weight:800; color:#1e293b; }}
        .qcl-stat-lbl {{ font-size:9px; font-weight:700; color:#94a3b8; text-transform:uppercase; letter-spacing:.08em; }}

        /* Barra de progreso */
        .qcl-prog-wrap {{ background:#f1f5f9; border-radius:8px; height:8px; overflow:hidden; margin:8px 0 4px; }}
        .qcl-prog-fill  {{ height:100%; border-radius:8px; background:linear-gradient(90deg,#3b82f6,#10b981); transition:width .35s; }}

        /* Panel derecho */
        .qcl-right {{ flex:1; overflow-y:auto; padding:24px 28px; }}
        .qcl-group-card {{
            background:white; border-radius:14px; margin-bottom:20px;
            border:1px solid #e8edf2; overflow:hidden;
            box-shadow:0 1px 4px rgba(0,0,0,.04);
        }}
        .qcl-group-hdr {{
            padding:14px 20px; font-size:13px; font-weight:700;
            display:flex; align-items:center; justify-content:space-between;
        }}
        .qcl-check-row {{
            display:flex; align-items:flex-start; gap:14px;
            padding:12px 20px; border-top:1px solid #f1f5f9;
            transition:background .15s;
        }}
        .qcl-check-row:hover {{ background:#fafbfd; }}
        .qcl-check-row.status-ok  {{ background:#f0fdf4 !important; }}
        .qcl-check-row.status-obs {{ background:#fffbeb !important; }}
        .qcl-check-row.status-fail{{ background:#fef2f2 !important; }}
        .qcl-check-text {{ flex:1; }}
        .qcl-check-label {{ font-size:12px; font-weight:600; color:#1e293b; }}
        .qcl-check-sub   {{ font-size:11px; color:#64748b; margin-top:2px; }}
        .qcl-btn-group   {{ display:flex; gap:6px; margin-top:8px; flex-wrap:wrap; }}
        .qcl-btn {{
            padding:4px 14px; border-radius:20px; font-size:10px; font-weight:700;
            cursor:pointer; border:1.5px solid #e2e8f0; color:#64748b;
            background:white; transition:all .15s; letter-spacing:.02em; user-select:none;
            font-family:'Inter',sans-serif;
        }}
        .qcl-btn:hover {{ border-color:#94a3b8; color:#1e293b; }}
        .qcl-btn.ok   {{ background:#dcfce7; border-color:#86efac; color:#15803d; }}
        .qcl-btn.obs  {{ background:#fef9c3; border-color:#fde047; color:#854d0e; }}
        .qcl-btn.fail {{ background:#fee2e2; border-color:#fca5a5; color:#b91c1c; }}
        .qcl-note {{
            margin-top:6px; width:100%; border:1px solid #e2e8f0; border-radius:8px;
            padding:6px 10px; font-size:11px; font-family:'Inter',sans-serif;
            color:#374151; outline:none; transition:border .15s; background:#fff;
        }}
        .qcl-note:focus {{ border-color:#3b82f6; box-shadow:0 0 0 2px rgba(59,130,246,.1); }}

        /* Footer */
        .qcl-footer {{
            background:white; border-top:1px solid #e8edf2; padding:14px 28px;
            display:flex; align-items:center; justify-content:space-between; flex-shrink:0;
        }}
        .qcl-btn-cancel {{
            padding:10px 28px; border-radius:10px; font-size:13px; font-weight:600;
            background:white; border:1.5px solid #e2e8f0; color:#64748b; cursor:pointer;
            font-family:'Inter',sans-serif; transition:all .15s;
        }}
        .qcl-btn-cancel:hover {{ border-color:#94a3b8; color:#1e293b; }}
        .qcl-btn-approve {{
            padding:10px 32px; border-radius:10px; font-size:13px; font-weight:700;
            background:linear-gradient(135deg,#1d4ed8,#3b82f6); color:white; border:none;
            cursor:pointer; font-family:'Inter',sans-serif;
            box-shadow:0 4px 14px rgba(59,130,246,.35); transition:all .2s; letter-spacing:.02em;
        }}
        .qcl-btn-approve:hover {{ box-shadow:0 6px 20px rgba(59,130,246,.5); transform:translateY(-1px); }}
        </style>''')

        with ui.element('div').classes('qcl-root'):

            # ── TOP BAR ──────────────────────────────────────────────
            with ui.element('div').classes('qcl-topbar'):
                with ui.row().classes('items-center gap-3'):
                    ui.icon('verified_user', size='sm').style('color:#3b82f6;')
                    with ui.column().classes('gap-0'):
                        ui.label('Control de Calidad').style('font-size:15px;font-weight:800;color:#1e293b;')
                        ui.label(f'Orden {consecutivo}  ·  {vehicle_placa}').style('font-size:11px;color:#64748b;')
                with ui.row().classes('items-center gap-3'):
                    # BOTÓN DE WHATSAPP DIRECTO EN EL TOPBAR
                    ui.button('📱 Enviar WhatsApp', on_click=_action_send_wa).props('unelevated').style('background:#25D366;color:white;border-radius:8px;font-weight:700;font-size:12px;padding:6px 14px;')
                    
                    # Progreso global en el header
                    progress_label = ui.label('0 / 16 verificados').style('font-size:12px;font-weight:600;color:#64748b;')
                    ui.button(icon='close', on_click=dlg.close).props('flat round size=sm color=grey-6')

            # ── BARRA PROGRESO TOP ────────────────────────────────────
            with ui.element('div').style('background:#f1f5f9;height:4px;flex-shrink:0;'):
                progress_bar = ui.element('div').style('height:100%;background:linear-gradient(90deg,#3b82f6,#10b981);width:0%;transition:width .35s;')

            # ── BODY ─────────────────────────────────────────────────
            with ui.element('div').classes('qcl-body'):

                # ── PANEL IZQUIERDO ───────────────────────────────────
                with ui.element('div').classes('qcl-left'):
                    # Stats rápidas
                    done_init = sum(1 for v in check_state.values() if v['status'] is not None)
                    with ui.element('div').classes('qcl-stat-grid'):
                        with ui.element('div').classes('qcl-stat-box'):
                            ui.label(str(total_items)).classes('qcl-stat-num').style('color:#3b82f6;')
                            ui.label('Ítems totales').classes('qcl-stat-lbl')
                        with ui.element('div').classes('qcl-stat-box'):
                            ui.label(str(total_fotos)).classes('qcl-stat-num').style('color:#10b981;')
                            ui.label('Fotos evidencia').classes('qcl-stat-lbl')

                    # Datos del servicio
                    ui.label('Datos del servicio').classes('qcl-section-hdr')
                    for lbl, val in [
                        ('Cliente',    client_name),
                        ('Vehículo',   vehicle_info),
                        ('Placa',      vehicle_placa),
                        ('Técnico',    technician),
                        ('Ingreso',    order.fecha[:10] if order.fecha else '—'),
                        ('Km entrada', str(order.km or '—')),
                    ]:
                        with ui.element('div').classes('qcl-info-card'):
                            ui.label(lbl).classes('qcl-info-label')
                            ui.label(val).classes('qcl-info-val')

                    # Motivo de ingreso
                    ui.label('Motivo de ingreso').classes('qcl-section-hdr')
                    with ui.element('div').classes('qcl-info-card'):
                        ui.label(motivo).classes('qcl-info-val')

                    # Trabajo realizado (logs de falla)
                    ui.label(f'Trabajo realizado ({len(repair_logs)} falla(s))').classes('qcl-section-hdr')
                    if repair_logs:
                        for i, log in enumerate(repair_logs):
                            with ui.element('div').classes('qcl-log-item'):
                                ui.label(f"#{i+1} {log.get('falla','—')}").style('font-weight:700;')
                                if log.get('solucion'):
                                    ui.label(f"↳ {log['solucion']}").style('color:#166534;opacity:.8;')
                    else:
                        ui.label('Sin bitácora de fallas registrada').style('font-size:11px;color:#94a3b8;')

                # ── PANEL DERECHO: CHECKLIST ──────────────────────────
                with ui.element('div').classes('qcl-right'):

                    def _update_progress():
                        done = sum(1 for v in check_state.values() if v['status'] is not None)
                        pct  = int(done / total_items * 100)
                        progress_bar.style(f'height:100%;background:linear-gradient(90deg,#3b82f6,#10b981);width:{pct}%;transition:width .35s;')
                        progress_label.set_text(f'{done} / {total_items} verificados')

                    note_inputs = {}  # key → ui.input element

                    for gidx, group in enumerate(GROUPS):
                        gcolor  = group['color']
                        gbg     = group['bg']
                        g_items = group['items']

                        with ui.element('div').classes('qcl-group-card'):
                            # Header del grupo
                            with ui.element('div').classes('qcl-group-hdr').style(f'background:{gbg};border-bottom:1px solid #e8edf2;'):
                                ui.label(group['title']).style(f'color:{gcolor};font-size:13px;font-weight:700;')
                                g_done_lbl = ui.label(f'0/{len(g_items)}').style(f'font-size:11px;font-weight:700;color:{gcolor};background:white;padding:2px 10px;border-radius:20px;border:1.5px solid {gcolor}20;')

                            for (key, label, sublabel) in g_items:
                                cur = check_state[key]
                                row_cls = ''
                                if cur['status'] == 'ok':   row_cls = 'status-ok'
                                elif cur['status'] == 'obs': row_cls = 'status-obs'
                                elif cur['status'] == 'fail':row_cls = 'status-fail'

                                with ui.element('div').classes(f'qcl-check-row {row_cls}') as row_div:
                                    # Ícono de estado
                                    status_icon = ui.icon(
                                        'check_circle' if cur['status']=='ok' else
                                        'warning'      if cur['status']=='obs' else
                                        'cancel'       if cur['status']=='fail' else
                                        'radio_button_unchecked',
                                        size='xs'
                                    ).style(
                                        'color:#16a34a;' if cur['status']=='ok' else
                                        'color:#ca8a04;' if cur['status']=='obs' else
                                        'color:#dc2626;' if cur['status']=='fail' else
                                        'color:#cbd5e1;'
                                    )

                                    with ui.column().classes('qcl-check-text gap-0'):
                                        ui.label(label).classes('qcl-check-label')
                                        ui.label(sublabel).classes('qcl-check-sub')

                                        # Botones de estado
                                        ok_cls   = 'ok'   if cur['status']=='ok'   else ''
                                        obs_cls  = 'obs'  if cur['status']=='obs'  else ''
                                        fail_cls = 'fail' if cur['status']=='fail' else ''

                                        with ui.element('div').classes('qcl-btn-group'):
                                            btn_ok   = ui.label('✓ Conforme').classes(f'qcl-btn {ok_cls}')
                                            btn_obs  = ui.label('⚠ Con observación').classes(f'qcl-btn {obs_cls}')
                                            btn_fail = ui.label('✗ No conforme').classes(f'qcl-btn {fail_cls}')

                                        # Campo de nota
                                        note_input = ui.input(
                                            placeholder='Detalle la observación...',
                                            value=cur.get('note','')
                                        ).style(
                                            f'width:100%;margin-top:6px;font-size:11px;'
                                            f'{"display:block" if cur["status"] in ("obs","fail") else "display:none"}'
                                        ).props('dense outlined')
                                        note_inputs[key] = note_input

                                def _make_setter(k, stt, r_div, s_icon, b_ok, b_obs, b_fail, n_inp, g_lbl, gcolr, g_itms):
                                    def _set():
                                        check_state[k]['status'] = stt
                                        # Actualizar clases botones
                                        b_ok .classes(replace='qcl-btn ok'   if stt=='ok'   else 'qcl-btn', remove='ok obs fail')
                                        b_obs.classes(replace='qcl-btn obs'  if stt=='obs'  else 'qcl-btn', remove='ok obs fail')
                                        b_fail.classes(replace='qcl-btn fail'if stt=='fail' else 'qcl-btn', remove='ok obs fail')
                                        # Ícono
                                        ico_name  = 'check_circle' if stt=='ok' else 'warning' if stt=='obs' else 'cancel'
                                        ico_color = 'color:#16a34a;' if stt=='ok' else 'color:#ca8a04;' if stt=='obs' else 'color:#dc2626;'
                                        s_icon._props['name'] = ico_name
                                        s_icon.style(ico_color)
                                        s_icon.update()
                                        # Row color
                                        row_new = 'status-ok' if stt=='ok' else 'status-obs' if stt=='obs' else 'status-fail'
                                        r_div._classes = [c for c in r_div._classes if not c.startswith('status-')] + [row_new]
                                        r_div.update()
                                        # Mostrar/ocultar nota
                                        n_inp.style('width:100%;margin-top:6px;font-size:11px;display:block;' if stt in ('obs','fail') else 'width:100%;margin-top:6px;font-size:11px;display:none;')
                                        # Progreso del grupo
                                        g_done = sum(1 for gk in [it[0] for it in g_itms] if check_state[gk]['status'] is not None)
                                        g_lbl.set_text(f'{g_done}/{len(g_itms)}')
                                        if g_done == len(g_itms):
                                            g_lbl.style(f'font-size:11px;font-weight:700;color:white;background:{gcolr};padding:2px 10px;border-radius:20px;border:none;')
                                        else:
                                            g_lbl.style(f'font-size:11px;font-weight:700;color:{gcolr};background:white;padding:2px 10px;border-radius:20px;border:1.5px solid {gcolr}20;')
                                        _update_progress()
                                    return _set

                                setter_ok   = _make_setter(key,'ok',  row_div,status_icon,btn_ok,btn_obs,btn_fail,note_input,g_done_lbl,gcolor,g_items)
                                setter_obs  = _make_setter(key,'obs', row_div,status_icon,btn_ok,btn_obs,btn_fail,note_input,g_done_lbl,gcolor,g_items)
                                setter_fail = _make_setter(key,'fail',row_div,status_icon,btn_ok,btn_obs,btn_fail,note_input,g_done_lbl,gcolor,g_items)
                                btn_ok  .on('click', setter_ok)
                                btn_obs .on('click', setter_obs)
                                btn_fail.on('click', setter_fail)

            # ── FOOTER ───────────────────────────────────────────────
            with ui.element('div').classes('qcl-footer'):
                done_count = sum(1 for v in check_state.values() if v['status'] is not None)
                footer_info = ui.label(
                    f'✅ Todo verificado — listo para entrega' if done_count==total_items else
                    f'⚠ Faltan {total_items-done_count} ítem(s) por verificar'
                ).style('font-size:12px;color:#64748b;')

                with ui.row().classes('gap-3'):
                    ui.label('Cancelar').classes('qcl-btn-cancel').on('click', dlg.close)
                    
                    # BOTÓN DE WHATSAPP DIRECTO EN EL FOOTER
                    ui.button('📱 Enviar Reporte WhatsApp', on_click=_action_send_wa).props('outline color=green-7').style('border-radius:10px;font-weight:700;padding:0 20px;')

                    async def _finalize():
                        # Guardar notas actuales
                        for k, ni in note_inputs.items():
                            check_state[k]['note'] = ni.value or ''

                        pending = [
                            label
                            for g in GROUPS
                            for (key, label, _) in g['items']
                            if check_state[key]['status'] is None
                        ]
                        if pending:
                            theme.notify_warning(f'Faltan {len(pending)} ítem(s): {", ".join(pending[:2])}{"…" if len(pending)>2 else ""}')
                            return

                        failed = [
                            label
                            for g in GROUPS
                            for (key, label, _) in g['items']
                            if check_state[key]['status'] == 'fail'
                        ]
                        if failed:
                            theme.notify_warning(f'{len(failed)} ítem(s) marcados como No conforme. Corrígelos antes de enviar a Entrega.')
                            return

                        try:
                            import secrets as _sec, urllib.parse as _ul, socket as _sk, json as _json
                            db2 = get_db()
                            from sqlalchemy import text as sa_text

                            # 1. Guardar el checklist de calidad
                            row_raw = db2.execute(sa_text("SELECT checklist_reparacion FROM ordenes WHERE consecutivo = :c"), {"c": consecutivo}).fetchone()
                            current_data = {}
                            if row_raw and row_raw[0]:
                                try:
                                    current_data = _json.loads(row_raw[0]) if isinstance(row_raw[0], str) else dict(row_raw[0])
                                except: current_data = {}

                            current_data['quality_control'] = check_state
                            
                            # 2. Generar o actualizar token
                            rpt_token = _sec.token_urlsafe(32)

                            db2.execute(
                                sa_text("UPDATE ordenes SET checklist_reparacion = :v, report_token = :t WHERE consecutivo = :c"),
                                {"v": _json.dumps(current_data), "t": rpt_token, "c": consecutivo}
                            )
                            db2.commit()
                            db2.close()
                        except Exception as ex:
                            print(f'[ERROR] QC Finalize DB: {ex}')

                        # Avanzar orden a Entrega
                        advance_order(consecutivo, 'ENTREGA')
                        dlg.close()
                        refresh_orders(container, state, stats_container)
                        theme.notify_success('✅ ¡Listo! Orden enviada a Entrega.')

                        # ── Construir mensaje de WhatsApp ──
                        try:
                            import socket
                            host = socket.gethostbyname(socket.gethostname())
                        except: host = 'localhost'
                        
                        report_url = f"http://{host}:8088/reporte/{rpt_token}"
                        wa_msg = (
                            f"✅ *REPORTE DE SERVICIO FINALIZADO*\n"
                            f"━━━━━━━━━━━━━━━━━━\n\n"
                            f"Hola *{cli_name}*,\n\n"
                            f"Su vehículo con placa *{v_placa}* ha pasado el control de calidad.\n\n"
                            f"Aquí puede ver el reporte completo (Diagnóstico, Repuestos, Reparación y Fotos):\n"
                            f"🔗 {report_url}\n\n"
                            f"━━━━━━━━━━━━━━━━━━\n"
                            f"MECÁNICA Y REPUESTOS SANDOVAL ✨"
                        )
                        import urllib.parse
                        wa_link = f"https://wa.me/{cli_phone}?text={urllib.parse.quote(wa_msg)}" if cli_phone else ''

                        # Rellenar y abrir el diálogo de envío
                        send_url_ref[0] = report_url
                        send_wa_ref[0] = wa_link
                        url_input.set_value(report_url)
                        
                        if wa_link:
                            wa_btn.style('display:block;')
                            no_phone_lbl.style('display:none;')
                        else:
                            wa_btn.style('display:none;')
                            no_phone_lbl.style('display:block;')

                        ui.timer(0.5, send_dlg.open, once=True)
                        theme.notify_success('✅ ¡Listo! Orden enviada a Entrega')


                    ui.label('✓ Aprobar y enviar a Entrega').classes('qcl-btn-approve').on('click', _finalize)

        # Actualizar progreso inicial si hay datos guardados
        if done_count := sum(1 for v in check_state.values() if v['status'] is not None):
            pct = int(done_count / total_items * 100)
            progress_bar.style(f'height:100%;background:linear-gradient(90deg,#3b82f6,#10b981);width:{pct}%;transition:width .35s;')
            progress_label.set_text(f'{done_count} / {total_items} verificados')

    dlg.open()



def open_repair_view_dialog(consecutivo: str):
    """Informe tipo PDF/reporte de la reparación — solo lectura, bien organizado."""
    db = get_db()
    try:
        order  = db.query(Orden).filter_by(consecutivo=consecutivo).first()
        if not order: return
        client  = db.query(Cliente).filter_by(id=order.cliente_id).first() if order.cliente_id else None
        vehicle = db.query(Vehiculo).filter_by(placa=order.vehiculo_placa).first() if order.vehiculo_placa else None

        from sqlalchemy import text as sa_text
        raw_row = db.execute(
            sa_text("SELECT checklist_reparacion FROM ordenes WHERE consecutivo = :c"),
            {"c": consecutivo}
        ).fetchone()
        raw_chk = raw_row[0] if raw_row else None
        if isinstance(raw_chk, str):
            try: data = json.loads(raw_chk)
            except: data = {}
        elif isinstance(raw_chk, dict):
            data = dict(raw_chk)
        else:
            data = {}
    finally:
        db.close()

    ev_cats   = data.get('evidence_cats', {})
    logs      = data.get('repair_logs', [])

    CATS_INFO = {
        'recepcion':  {'label': 'Recepción',     'icon': '📥', 'color': '#3b82f6'},
        'desarmado':  {'label': 'Desarmado',      'icon': '🔧', 'color': '#f59e0b'},
        'dañadas':    {'label': 'Pieza Dañada',   'icon': '🔴', 'color': '#ef4444'},
        'reparacion': {'label': 'Reparación',     'icon': '✅', 'color': '#10b981'},
    }

    with ui.dialog().props('maximized transition-show=slide-up transition-hide=slide-down') as dlg:
        ui.add_head_html('''<style>
        .rv-root { background:#f4f6f9; font-family:"Inter",sans-serif; }
        .rv-page { background:white; max-width:900px; margin:0 auto;
                   box-shadow:0 4px 24px rgba(0,0,0,.10); border-radius:16px;
                   overflow:hidden; }
        .rv-header { background:linear-gradient(135deg,#1e40af,#3b82f6);
                     padding:32px 40px; color:white; }
        .rv-section { padding:28px 40px; border-bottom:1px solid #f1f3f7; }
        .rv-section-title { font-size:11px; font-weight:800; color:#6b7280;
                            text-transform:uppercase; letter-spacing:.12em;
                            margin-bottom:16px; }
        .rv-info-grid { display:grid; grid-template-columns:1fr 1fr 1fr;
                        gap:16px; }
        .rv-info-box { background:#f8fafc; border-radius:12px; padding:14px 18px;
                       border:1px solid #e8edf2; }
        .rv-info-label { font-size:10px; font-weight:700; color:#94a3b8;
                         text-transform:uppercase; letter-spacing:.08em; }
        .rv-info-val { font-size:14px; font-weight:600; color:#1e293b; margin-top:4px; }
        .rv-cat-block { margin-bottom:24px; }
        .rv-cat-header { display:flex; align-items:center; gap:10px;
                         margin-bottom:12px; }
        .rv-cat-title { font-size:13px; font-weight:700; }
        .rv-photo-grid { display:grid; grid-template-columns:repeat(4,1fr); gap:10px; }
        .rv-photo { width:100%; aspect-ratio:1; object-fit:cover;
                    border-radius:10px; border:2px solid #e8edf2; }
        .rv-log-row { background:#f8fafc; border-radius:10px; padding:14px 18px;
                      margin-bottom:10px; border-left:4px solid #3b82f6; }
        .rv-log-title { font-size:12px; font-weight:700; color:#1e293b; margin-bottom:6px; }
        .rv-log-item { font-size:11px; color:#6b7280; margin:2px 0; }
        .rv-empty { text-align:center; padding:20px; color:#9ca3af; font-size:12px; }
        @media print {
            .rv-topbar { display:none !important; }
            .rv-page { box-shadow:none; border-radius:0; max-width:100%; }
            .rv-root { background:white; }
        }
        </style>''')

        with ui.column().classes('w-full h-full rv-root gap-0 overflow-auto'):
            # Top bar
            with ui.row().classes('rv-topbar w-full items-center justify-between px-6 py-3 bg-white border-b border-gray-100 sticky top-0 z-10'):
                with ui.row().classes('items-center gap-3'):
                    ui.icon('description', color='blue-7', size='sm')
                    ui.label('Informe de Reparación').classes('font-bold text-gray-700 text-sm')
                    ui.badge('Solo lectura', color='grey-5').classes('text-white text-xs')
                with ui.row().classes('gap-2'):
                    ui.button('Imprimir', icon='print', on_click=lambda: ui.run_javascript('window.print()')).props('outline color=blue-6 size=sm')
                    ui.button(icon='close', on_click=dlg.close).props('flat round color=grey-6 size=sm')

            # Página principal tipo PDF
            with ui.column().classes('w-full p-6 gap-0'):
                with ui.element('div').classes('rv-page'):

                    # ── ENCABEZADO ────────────────────────────────
                    with ui.element('div').classes('rv-header'):
                        with ui.row().classes('items-start justify-between'):
                            with ui.column().classes('gap-1'):
                                ui.label('INFORME DE REPARACIÓN').style('font-size:11px;font-weight:800;letter-spacing:.12em;opacity:.7;')
                                ui.label(consecutivo).style('font-size:26px;font-weight:800;letter-spacing:-.5px;')
                                ui.label(f"Fecha: {order.fecha[:10]}  ·  Técnico: {order.tecnico or 'No asignado'}").style('font-size:13px;opacity:.8;margin-top:6px;')
                            with ui.column().classes('items-end gap-1'):
                                ui.label(f"Estado: {order.estado}").style('font-size:12px;background:rgba(255,255,255,.2);padding:6px 14px;border-radius:20px;font-weight:700;')
                                ui.label(f"Tipo: {order.tipo}").style('font-size:11px;opacity:.7;')

                    # ── DATOS DEL VEHÍCULO Y CLIENTE ──────────────
                    with ui.element('div').classes('rv-section'):
                        ui.label('Datos del servicio').classes('rv-section-title')
                        with ui.element('div').classes('rv-info-grid'):
                            for label, value in [
                                ('Cliente',    (client.nombre + ' ' + (client.apellidos or '')) if client else '—'),
                                ('Vehículo',   f"{vehicle.marca} {vehicle.modelo} {vehicle.año}" if vehicle else '—'),
                                ('Placa',      vehicle.placa if vehicle else '—'),
                                ('Km entrada', order.km or '—'),
                                ('Motivo',     (order.motivo or '—')[:60]),
                                ('Diagnóstico', (order.diagnostico or '—')[:60]),
                            ]:
                                with ui.element('div').classes('rv-info-box'):
                                    ui.label(label).classes('rv-info-label')
                                    ui.label(value).classes('rv-info-val')

                    # ── EVIDENCIA FOTOGRÁFICA ──────────────────────
                    with ui.element('div').classes('rv-section'):
                        ui.label('Evidencia fotográfica').classes('rv-section-title')
                        any_photos = False
                        for ck, ci in CATS_INFO.items():
                            photos = ev_cats.get(ck, [])
                            if not photos:
                                continue
                            any_photos = True
                            with ui.element('div').classes('rv-cat-block'):
                                with ui.element('div').classes('rv-cat-header'):
                                    ui.label(ci['icon']).style('font-size:18px;')
                                    ui.label(f"{ci['label']}  ({len(photos)} foto{'s' if len(photos)!=1 else ''})").classes('rv-cat-title').style(f'color:{ci["color"]};')
                                with ui.element('div').classes('rv-photo-grid'):
                                    for ph in photos:
                                        p_path = ph.get('path') if isinstance(ph, dict) else ph
                                        ui.image(p_path).classes('rv-photo')
                        if not any_photos:
                            with ui.element('div').classes('rv-empty'):
                                ui.icon('photo_library', size='32px', color='grey-3')
                                ui.label('Sin evidencia fotográfica registrada').classes('text-xs text-gray-400 mt-1')

                    # ── BITÁCORA DE FALLAS ──────────────────────────
                    with ui.element('div').classes('rv-section'):
                        ui.label('Bitácora de fallas').classes('rv-section-title')
                        if logs:
                            for i, log in enumerate(logs):
                                with ui.element('div').classes('rv-log-row'):
                                    ui.label(f"Falla #{i+1}: {log.get('falla') or '(sin descripción)'}").classes('rv-log-title')
                                    if log.get('causa'):     ui.label(f"• Causa: {log['causa']}").classes('rv-log-item')
                                    if log.get('solucion'): ui.label(f"• Solución: {log['solucion']}").classes('rv-log-item')
                                    if log.get('repuestos'):ui.label(f"• Repuestos: {log['repuestos']}").classes('rv-log-item')
                        else:
                            with ui.element('div').classes('rv-empty'):
                                ui.icon('assignment', size='32px', color='grey-3')
                                ui.label('Sin fallas registradas en bitácora').classes('text-xs text-gray-400 mt-1')

                    # ── OBSERVACIONES ───────────────────────────────
                    if data.get('observaciones'):
                        with ui.element('div').classes('rv-section'):
                            ui.label('Observaciones al cliente').classes('rv-section-title')
                            ui.label(data['observaciones']).style('font-size:13px;color:#374151;line-height:1.6;')

                    # ── PIE ─────────────────────────────────────────
                    with ui.element('div').style('padding:20px 40px;text-align:center;background:#f8fafc;'):
                        ui.label('MECÁNICA Y REPUESTOS SANDOVAL EIRL').style('font-size:10px;font-weight:700;color:#94a3b8;letter-spacing:.1em;')
                        ui.label(f'Documento generado el {datetime.now().strftime("%d/%m/%Y %H:%M")}').style('font-size:10px;color:#94a3b8;')

    dlg.open()


def open_advanced_repair_module(consecutivo, container, state, stats_container=None):
    """
    Módulo de Evidencia y Reparación - Diseño Premium
    UX/UI Senior - Automotive ERP Edition
    """
    from sqlalchemy.orm.attributes import flag_modified
    db = get_db()
    try:
        order = db.query(Orden).filter_by(consecutivo=consecutivo).first()
        if not order: return
        client = db.query(Cliente).filter_by(id=order.cliente_id).first()
        vehicle = db.query(Vehiculo).filter_by(placa=order.vehiculo_placa).first()

        # Leer checklist con raw SQL para evitar cache ORM (expire_on_commit=False)
        from sqlalchemy import text as sa_text
        raw_row = db.execute(
            sa_text("SELECT checklist_reparacion FROM ordenes WHERE consecutivo = :c"),
            {"c": consecutivo}
        ).fetchone()
        raw_chk = raw_row[0] if raw_row else None
        if isinstance(raw_chk, str):
            try: data = json.loads(raw_chk)
            except: data = {}
        elif isinstance(raw_chk, dict):
            data = dict(raw_chk)
        else:
            data = {}

        repair_logs = data.get('repair_logs', [])
        _raw_ev = data.get('evidence_cats', {})
        evidence_categories = {
            'recepcion':  list(_raw_ev.get('recepcion',  [])),
            'desarmado':  list(_raw_ev.get('desarmado',  [])),
            'dañadas':    list(_raw_ev.get('dañadas',    [])),
            'reparacion': list(_raw_ev.get('reparacion', [])),
        }
        is_mantenimiento = data.get('is_mantenimiento', order.tipo == 'Express')

    finally:
        db.close()

    # ─── CSS PREMIUM DEFINITIVO ───
    ui.add_head_html('''
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;900&display=swap');

            .ev-root {
                background: #f0f2f5 !important;
                font-family: "Inter", sans-serif !important;
            }
            .ev-topbar {
                background: white;
                border-bottom: 1px solid #e5e7eb;
                padding: 16px 32px;
            }
            .ev-sidebar {
                background: white;
                border-right: 1px solid #e9ecef;
                min-width: 300px;
                max-width: 300px;
            }
            .ev-card {
                background: white;
                border-radius: 20px;
                border: 1px solid #e9ecef;
                box-shadow: 0 1px 3px rgba(0,0,0,0.05);
                overflow: hidden;
            }
            .ev-section-title {
                font-size: 10px;
                font-weight: 700;
                color: #9ca3af;
                text-transform: uppercase;
                letter-spacing: 0.12em;
                margin-bottom: 14px;
            }
            .ev-info-row {
                display: flex;
                align-items: center;
                justify-content: space-between;
                padding: 10px 14px;
                background: #f9fafb;
                border-radius: 12px;
                margin-bottom: 8px;
            }
            .ev-info-label { font-size: 11px; font-weight: 600; color: #6b7280; }
            .ev-info-value { font-size: 12px; font-weight: 700; color: #111827; }

            .ev-cat-tab {
                flex: 1;
                padding: 10px 6px;
                border-radius: 12px;
                text-align: center;
                cursor: pointer;
                transition: all 0.2s;
                border: 2px solid transparent;
                user-select: none;
            }
            .ev-cat-tab:hover { background: #f3f4f6; }
            .ev-cat-tab.active { background: #eff6ff; border-color: #3b82f6; }
            .ev-cat-tab .tab-label {
                font-size: 9px; font-weight: 700; color: #374151;
                text-transform: uppercase; letter-spacing: 0.05em;
                display: block; margin-top: 4px;
            }
            .ev-cat-tab.active .tab-label { color: #2563eb; }

            .ev-drop-zone {
                border: 2px dashed #d1d5db;
                border-radius: 16px;
                padding: 28px;
                text-align: center;
                background: #fafafa;
                transition: all 0.25s;
            }
            .ev-drop-zone:hover { border-color: #3b82f6; background: #eff6ff; }

            .ev-thumb {
                border-radius: 14px;
                overflow: hidden;
                position: relative;
                aspect-ratio: 1;
                background: #f3f4f6;
                box-shadow: 0 2px 8px rgba(0,0,0,0.08);
                transition: transform 0.2s, box-shadow 0.2s;
            }
            .ev-thumb:hover { transform: scale(1.04); box-shadow: 0 8px 24px rgba(0,0,0,0.15); }
            .ev-thumb .ev-del {
                position: absolute; top: 6px; right: 6px;
                background: rgba(0,0,0,0.55); border-radius: 50%;
                width: 26px; height: 26px;
                display: flex; align-items: center; justify-content: center;
                opacity: 0; transition: opacity 0.2s; cursor: pointer;
            }
            .ev-thumb:hover .ev-del { opacity: 1; }
            .ev-thumb .ev-num {
                position: absolute; bottom: 0; left: 0; right: 0;
                background: linear-gradient(to top, rgba(0,0,0,0.55), transparent);
                color: white; font-size: 9px; font-weight: 700;
                padding: 14px 8px 6px; text-transform: uppercase; letter-spacing: 0.07em;
            }

            .falla-item {
                background: #f9fafb; border: 1px solid #e5e7eb;
                border-radius: 16px; padding: 14px 16px;
                transition: all 0.2s; margin-bottom: 10px;
            }
            .falla-item:hover { border-color: #3b82f6; background: white; box-shadow: 0 4px 20px rgba(59,130,246,0.06); }
            .falla-field {
                display: flex; align-items: center; gap: 8px;
                background: white; border: 1px solid #e9ecef;
                border-radius: 10px; padding: 6px 10px; margin-top: 6px;
            }
            .falla-field:focus-within { border-color: #3b82f6; }

            .ev-badge-num {
                width: 24px; height: 24px; border-radius: 50%;
                background: #dbeafe; color: #1d4ed8;
                font-size: 11px; font-weight: 800;
                display: flex; align-items: center; justify-content: center;
                flex-shrink: 0;
            }
            .ev-btn { border-radius: 12px !important; font-weight: 600 !important; height: 46px !important; }
        </style>
    ''')

    active_cat = {'key': 'recepcion'}
    CATS = {
        'recepcion':  {'label': 'Recepción',     'icon': 'car_repair',      'color': 'blue'},
        'desarmado':  {'label': 'Desarmado',      'icon': 'handyman',         'color': 'amber'},
        'dañadas':    {'label': 'Pieza Dañada',   'icon': 'broken_image',     'color': 'red'},
        'reparacion': {'label': 'Reparación',     'icon': 'build_circle',     'color': 'green'},
    }

    with ui.dialog().props('maximized transition-show=slide-up transition-hide=slide-down') as dialog:
        with ui.column().classes('w-full h-full ev-root gap-0'):

            # ── TOP BAR ─────────────────────
            with ui.row().classes('ev-topbar w-full items-center justify-between'):
                with ui.row().classes('items-center gap-4'):
                    with ui.avatar(color='blue-7', text_color='white').classes('w-11 h-11'):
                        ui.icon('build_circle', size='sm')
                    with ui.column().classes('gap-0'):
                        ui.label('SANDOVAL PERFORMANCE WORKSHOP').classes('text-[9px] font-black text-blue-600 tracking-[0.2em]')
                        ui.label(f'Módulo de Reparación · {consecutivo}').classes('text-lg font-bold text-gray-900')
                with ui.row().classes('gap-3 items-center'):
                    client_name = (client.nombre + ' ' + (client.apellidos or '')) if client else '—'
                    plate_val   = vehicle.placa if vehicle else '---'
                    ui.label(client_name).classes('text-sm font-semibold text-gray-400 mr-2')
                    ui.badge(plate_val, color='blue-1').classes('text-blue-700 font-bold text-xs px-3 py-1')
                    ui.separator().props('vertical').classes('mx-2 h-6')
                    ui.button(icon='close', on_click=dialog.close).props('flat round color=grey-7')

            # ── CUERPO PRINCIPAL: 3 COLUMNAS REALES ───────────────────────────
            with ui.row().classes('w-full flex-1 overflow-hidden gap-0'):

                # ══ SIDEBAR IZQUIERDO — Datos del vehículo ══════════════
                with ui.scroll_area().classes('ev-sidebar h-full'):
                    with ui.column().classes('w-full p-6 gap-5'):

                        with ui.column().classes('w-full gap-2'):
                            ui.label('Datos del servicio').classes('ev-section-title')

                            def _irow(lbl, val, icn):
                                with ui.element('div').classes('ev-info-row'):
                                    with ui.row().classes('items-center gap-2'):
                                        ui.icon(icn, size='16px', color='blue-4')
                                        ui.label(lbl).classes('ev-info-label')
                                    ui.label(str(val) if val else '—').classes('ev-info-value')

                            _irow('Cliente',  client.nombre if client else '—', 'person')
                            _irow('Vehículo', f"{vehicle.marca} {vehicle.modelo}" if vehicle else '—', 'directions_car')
                            _irow('Placa',    vehicle.placa if vehicle else '—', 'tag')
                            _irow('Tipo',     order.tipo or 'Regular', 'category')

                        ui.separator().classes('opacity-30')

                        with ui.column().classes('w-full gap-2'):
                            ui.label('Tipo de trabajo').classes('ev-section-title')
                            with ui.row().classes('w-full bg-gray-100 p-1 rounded-xl'):
                                mode_switch = ui.toggle(
                                    {True: 'Mantenimiento', False: 'Reparación'},
                                    value=is_mantenimiento
                                ).props('color=blue-6 dense unelevated').classes('w-full text-xs font-bold')

                        ui.separator().classes('opacity-30')

                        with ui.column().classes('w-full gap-3'):
                            ui.label('Motivo de ingreso').classes('ev-section-title')
                            ui.textarea(value=order.motivo or '').props('readonly outlined dense rows=4').classes('w-full text-xs')
                            ui.label('Diagnóstico técnico').classes('ev-section-title mt-2')
                            ui.textarea(value=order.diagnostico or '').props('readonly outlined dense rows=4').classes('w-full text-xs')

                # ══ PANEL CENTRAL — Evidencia fotográfica ══════════════
                with ui.scroll_area().classes('flex-1 h-full'):
                    with ui.column().classes('w-full h-full p-6 gap-5'):

                        # Tarjeta de evidencia por categorías
                        with ui.element('div').classes('ev-card p-6'):
                            ui.label('Evidencia fotográfica por categoría').classes('ev-section-title')

                            tab_row   = ui.row().classes('w-full gap-3')
                            gallery_col = ui.column().classes('w-full mt-4 gap-4')


                            # evidence_categories ya viene inicializado desde DB (línea ~1108)
                            # Es el dict compartido entre todos los closures de este diálogo.

                            def render_tabs():
                                tab_row.clear()
                                for cat_key, cat_info in CATS.items():
                                    count = len(evidence_categories.get(cat_key, []))
                                    is_active = active_cat['key'] == cat_key
                                    ac = 'active' if is_active else ''
                                    with tab_row:
                                        with ui.element('div').classes(f'ev-cat-tab {ac}').on('click', lambda k=cat_key: _switch(k)):
                                            ui.icon(cat_info['icon'], size='sm',
                                                    color=f'{cat_info["color"]}-6' if is_active else 'grey-5')
                                            ui.label(cat_info['label']).classes('tab-label')
                                            if count > 0:
                                                ui.badge(str(count), color=f'{cat_info["color"]}-6').classes('mt-1 text-white')

                            def _switch(key):
                                active_cat['key'] = key
                                render_tabs()
                                render_gallery()

                            def render_gallery():
                                gallery_col.clear()
                                cat_key = active_cat['key']
                                files = list(evidence_categories.get(cat_key, []))

                                with gallery_col:
                                    # DEBUG VISIBLE: muestra el estado actual
                                    ui.label(f'[{cat_key}]: {len(files)} foto(s) | total cats: {list(evidence_categories.keys())}'
                                             ).classes('text-[9px] text-gray-300 font-mono')

                                    with ui.element('div').classes('ev-drop-zone'):
                                        ui.icon('add_photo_alternate', size='42px', color='blue-4')
                                        ui.label(f'Subir fotos — {CATS[cat_key]["label"]}').classes('text-sm font-semibold text-gray-500 mt-2 block')
                                        ui.label('JPG · PNG · MP4  |  Subida automática').classes('text-xs text-gray-400 mb-3 block')

                                        async def _handle_upload(e, ck=cat_key):
                                            import os
                                            from datetime import datetime
                                            # NiceGUI 3.x: el archivo viene en e.file
                                            file_obj  = e.file
                                            file_name = file_obj.name
                                            folder = f"static/evidencia/{consecutivo.replace('#','')}/{ck}"
                                            os.makedirs(folder, exist_ok=True)
                                            ts = datetime.now().strftime('%H%M%S%f')[:12]
                                            safe_name = f"{ck.upper()}_{ts}_{file_name.replace(' ','_')}"
                                            save_path = os.path.join(folder, safe_name)
                                            try:
                                                # Guardar archivo (read() es coroutine en NiceGUI 3.x)
                                                content = await file_obj.read()
                                                with open(save_path, 'wb') as f:
                                                    f.write(content)

                                                path = f"/evidencia/{consecutivo.replace('#','')}/{ck}/{safe_name}"

                                                # 1. Actualizar en memoria PRIMERO
                                                if ck not in evidence_categories:
                                                    evidence_categories[ck] = []
                                                evidence_categories[ck].append(path)

                                                # 2. Persistir en BD con raw SQL
                                                try:
                                                    db_u = get_db()
                                                    from sqlalchemy import text as sa_text
                                                    row = db_u.execute(
                                                        sa_text("SELECT checklist_reparacion, fotos_evidencia FROM ordenes WHERE consecutivo = :c"),
                                                        {"c": consecutivo}
                                                    ).fetchone()
                                                    raw_val = row[0] if row else None
                                                    if isinstance(raw_val, str):
                                                        try: d = json.loads(raw_val)
                                                        except: d = {}
                                                    elif isinstance(raw_val, dict):
                                                        d = dict(raw_val)
                                                    else:
                                                        d = {}
                                                    if 'evidence_cats' not in d:
                                                        d['evidence_cats'] = {}
                                                    if ck not in d['evidence_cats']:
                                                        d['evidence_cats'][ck] = []
                                                    d['evidence_cats'][ck].append(path)
                                                    
                                                    # Sincronizar con fotos_evidencia
                                                    try:
                                                        raw_f = row[1] if row and len(row) > 1 else None
                                                        if isinstance(raw_f, str): f_list = json.loads(raw_f)
                                                        else: f_list = list(raw_f or [])
                                                    except: f_list = []
                                                    f_list.append({'path': path, 'fase': 'REPARACIÓN'})

                                                    db_u.execute(
                                                        sa_text("UPDATE ordenes SET checklist_reparacion = :v, fotos_evidencia = :f WHERE consecutivo = :c"),
                                                        {"v": json.dumps(d), "f": json.dumps(f_list), "c": consecutivo}
                                                    )
                                                    db_u.commit()
                                                    db_u.close()
                                                except Exception as db_ex:
                                                    print(f'[WARN] BD no actualizada: {db_ex}')

                                                theme.notify_success(f'✅ {file_name} guardada en "{CATS[ck]["label"]}"')
                                                render_tabs()
                                                render_gallery()

                                            except Exception as ex:
                                                import traceback
                                                print(f'[ERROR] upload: {traceback.format_exc()}')
                                                theme.notify_error(f'Error al subir: {ex}')


                                        ui.upload(
                                            on_upload=_handle_upload,
                                            auto_upload=True,
                                            label='Seleccionar archivos',
                                            multiple=True
                                        ).props('color=blue-6 flat').classes('mt-2')

                                    # Galería de miniaturas
                                    if files:
                                        ui.label(f'{len(files)} imagen(es) en esta categoría').classes('text-xs font-semibold text-gray-400')
                                        with ui.grid(columns=5).classes('w-full gap-4'):
                                            for idx_f, f_path in enumerate(list(files)):
                                                with ui.element('div').classes('ev-thumb'):
                                                    ui.image(f_path).classes('w-full h-full object-cover')
                                                    with ui.element('div').classes('ev-num'):
                                                        ui.label(f'#{idx_f + 1}')

                                                    async def _del(fp=f_path, ck=cat_key):
                                                        # Eliminar en memoria PRIMERO
                                                        if ck in evidence_categories and fp in evidence_categories[ck]:
                                                            evidence_categories[ck].remove(fp)
                                                        # Persistir en BD
                                                        try:
                                                            db_d = get_db()
                                                            from sqlalchemy import text as sa_text
                                                            row = db_d.execute(
                                                                sa_text("SELECT checklist_reparacion FROM ordenes WHERE consecutivo = :c"),
                                                                {"c": consecutivo}
                                                            ).fetchone()
                                                            raw_val = row[0] if row else None
                                                            if isinstance(raw_val, str):
                                                                try: d = json.loads(raw_val)
                                                                except: d = {}
                                                            elif isinstance(raw_val, dict):
                                                                d = dict(raw_val)
                                                            else:
                                                                d = {}
                                                            cats = d.get('evidence_cats', {})
                                                            cats[ck] = [x for x in cats.get(ck, []) if x != fp]
                                                            d['evidence_cats'] = cats
                                                            db_d.execute(
                                                                sa_text("UPDATE ordenes SET checklist_reparacion = :v WHERE consecutivo = :c"),
                                                                {"v": json.dumps(d), "c": consecutivo}
                                                            )
                                                            db_d.commit()
                                                            db_d.close()
                                                        except Exception as ex:
                                                            print(f'[WARN] _del BD: {ex}')
                                                        render_tabs()
                                                        render_gallery()

                                                    with ui.element('div').classes('ev-del').on('click', _del):
                                                        ui.icon('close', size='14px', color='white')
                                    else:
                                        with ui.column().classes('w-full items-center py-8'):
                                            ui.icon('photo_library', size='48px', color='grey-3')
                                            ui.label('Sin fotos en esta categoría aún').classes('text-sm text-gray-400 mt-2')

                            render_tabs()
                            render_gallery()

                # ══ SIDEBAR DERECHO — Bitácora y observaciones ══════════
                with ui.scroll_area().classes('ev-sidebar h-full border-l border-gray-100'):
                    with ui.column().classes('w-full p-6 gap-5'):

                        # Observaciones para el cliente
                        with ui.column().classes('w-full gap-2'):
                            ui.label('Observaciones al cliente').classes('ev-section-title')
                            ui.textarea(
                                placeholder='Trabajo realizado, recomendaciones, observaciones finales…'
                            ).props('outlined dense rows=5').classes('w-full text-xs')

                        ui.separator().classes('opacity-30')

                        # Bitácora de fallas
                        with ui.column().classes('w-full gap-2'):
                            with ui.row().classes('w-full items-center justify-between'):
                                ui.label('Bitácora de fallas').classes('ev-section-title m-0')

                                def add_falla():
                                    repair_logs.append({'falla': '', 'causa': '', 'solucion': '', 'repuestos': ''})
                                    render_logs()

                                ui.button(icon='add', on_click=add_falla).props('flat round color=blue-6 size=xs').tooltip('Agregar falla')

                            logs_container = ui.column().classes('w-full gap-0')

                            def render_logs():
                                logs_container.clear()
                                if not repair_logs:
                                    with logs_container:
                                        with ui.column().classes('w-full items-center py-6 gap-2'):
                                            ui.icon('assignment', size='36px', color='grey-3')
                                            ui.label('Sin fallas registradas').classes('text-xs text-gray-400 text-center')
                                            ui.label('Presiona + para agregar').classes('text-[10px] text-gray-300')
                                    return
                                for i, log in enumerate(repair_logs):
                                    with logs_container:
                                        with ui.column().classes('falla-item'):
                                            with ui.row().classes('w-full items-center gap-2 mb-1'):
                                                with ui.element('div').classes('ev-badge-num'):
                                                    ui.label(str(i + 1))
                                                ui.input(
                                                    value=log.get('falla', ''),
                                                    placeholder='Nombre de la falla…',
                                                    on_change=lambda ev, idx=i: repair_logs[idx].update({'falla': ev.value})
                                                ).props('borderless dense').classes('flex-1 text-sm font-semibold text-gray-800')
                                                ui.button(icon='close',
                                                    on_click=lambda idx=i: (repair_logs.pop(idx), render_logs())
                                                ).props('flat round color=red-4 size=xs')

                                            for icn, ph, key in [
                                                ('search',        'Causa raíz…',         'causa'),
                                                ('auto_fix_high', 'Solución aplicada…',  'solucion'),
                                                ('inventory_2',   'Repuestos/insumos…',  'repuestos'),
                                            ]:
                                                with ui.element('div').classes('falla-field'):
                                                    ui.icon(icn, size='14px', color='grey-5')
                                                    ui.input(
                                                        value=log.get(key, ''),
                                                        placeholder=ph,
                                                        on_change=lambda ev, idx=i, k=key: repair_logs[idx].update({k: ev.value})
                                                    ).props('borderless dense').classes('flex-1 text-xs')

                            render_logs()


            # ── FOOTER ───────────────────────────────────────────────
            with ui.row().classes('w-full items-center justify-center gap-5 px-8 py-5 bg-white border-t border-gray-200'):
                ui.button('Cancelar', icon='close', on_click=dialog.close).props('outline').classes('ev-btn px-8 text-sm text-gray-600')

                def _save():
                    db_s = get_db()
                    try:
                        o_s = db_s.query(Orden).filter_by(consecutivo=consecutivo).first()
                        # Leer estado actual de BD con raw SQL para no perder evidence_cats
                        from sqlalchemy import text as sa_text
                        row = db_s.execute(
                            sa_text("SELECT checklist_reparacion FROM ordenes WHERE consecutivo = :c"),
                            {"c": consecutivo}
                        ).fetchone()
                        raw_val = row[0] if row else None
                        if isinstance(raw_val, str):
                            try: d = json.loads(raw_val)
                            except: d = {}
                        elif isinstance(raw_val, dict):
                            d = dict(raw_val)
                        else:
                            d = {}
                        # Actualizar sólo los campos de este módulo, preservando evidence_cats
                        d['repair_logs']      = repair_logs
                        d['is_mantenimiento'] = mode_switch.value
                        # Sincronizar evidence_categories en memoria → BD
                        d['evidence_cats']    = evidence_categories
                        db_s.execute(
                            sa_text("UPDATE ordenes SET checklist_reparacion = :v WHERE consecutivo = :c"),
                            {"v": json.dumps(d), "c": consecutivo}
                        )
                        db_s.commit()
                        theme.notify_success('Progreso guardado correctamente')
                    except Exception as ex:
                        print(f'[ERROR] _save: {ex}')
                        theme.notify_error(f'Error al guardar: {ex}')
                    finally:
                        db_s.close()

                ui.button('Guardar avances', icon='save', on_click=_save).props('unelevated color=blue-6').classes('ev-btn px-8 text-sm')

                def _finish():
                    _save()
                    advance_order(consecutivo, 'CONTROL')
                    dialog.close()
                    refresh_orders(container, state, stats_container)

                ui.button('Finalizar y enviar a Control', icon='check_circle', on_click=_finish).props('unelevated color=green-7').classes('ev-btn px-10 text-sm')

        dialog.open()


def open_order_detail(consecutivo, container, state):
    db = get_db()
    try:
        order = db.query(Orden).filter_by(consecutivo=consecutivo).first()
        if not order:
            theme.notify_error('Orden no encontrada')
            return
        
        client = db.query(Cliente).filter_by(id=order.cliente_id).first() if order.cliente_id else None
        vehicle = db.query(Vehiculo).filter_by(placa=order.vehiculo_placa).first() if order.vehiculo_placa else None
        inv_items = db.query(ItemInventario).all()
        
        # Convert to dicts to use outside session
        o = _order_to_dict(order)
        c = _client_to_dict(client)
        v = _vehicle_to_dict(vehicle)
        inv = [{'codigo': i.codigo, 'nombre': i.nombre, 'precio': i.precio} for i in inv_items]
    finally:
        db.close()
    
    estado = o['estado']
    cfg = theme.ESTADOS_CONFIG.get(estado, {'icon': 'build', 'color': 'grey-6'})
    
    with ui.dialog() as dialog, ui.card().classes('w-full max-w-6xl bg-slate-50 p-0 border-none shadow-2xl overflow-hidden'):
        # --- HEADER PREMIUM ---
        with ui.row().classes('w-full items-center justify-between p-6 bg-slate-900 border-b-4 border-indigo-500'):
            with ui.row().classes('items-center gap-4'):
                ui.icon(cfg['icon'], size='40px').classes('text-indigo-400')
                with ui.column().classes('gap-0'):
                    ui.label('DETALLE DE ORDEN DE SERVICIO').classes('text-white text-[10px] font-bold tracking-widest uppercase')
                    ui.label(consecutivo).classes('text-3xl font-black text-white italic text-nowrap')
            
            with ui.row().classes('items-center gap-3'):
                ui.badge(estado, color=cfg['color']).classes('px-4 py-2 text-sm font-bold shadow-sm rounded-full')
                ui.button(icon='close', on_click=dialog.close).props('flat round color=white size=sm').classes('hover:bg-white/10')

        with ui.scroll_area().classes('w-full p-6').style('height: 80vh'):
            # --- SECCIÓN 1: CABECERA TÉCNICA (CLIENTE Y VEHÍCULO) ---
            with ui.row().classes('w-full gap-6 mb-8'):
                with ui.card().classes('flex-1 bg-white border border-slate-200 p-5 shadow-sm rounded-2xl'):
                    with ui.row().classes('items-center gap-2 mb-3'):
                        ui.icon('person', color='indigo-7').classes('text-lg')
                        ui.label('CLIENTE').classes('text-slate-400 text-[10px] font-bold tracking-wider')
                    if c:
                        ui.label(f"{c['nombre']} {c.get('apellidos', '')}").classes('text-lg font-bold text-slate-800')
                        ui.label(f"Tel: {c.get('telefono', '-') or '-'}").classes('text-slate-600 text-sm')
                
                with ui.card().classes('flex-1 bg-white border border-slate-200 p-5 shadow-sm rounded-2xl'):
                    with ui.row().classes('items-center gap-2 mb-3'):
                        ui.icon('directions_car', color='indigo-7').classes('text-lg')
                        ui.label('VEHÍCULO').classes('text-slate-400 text-[10px] font-bold tracking-wider')
                    if v:
                        ui.label(f"{v.get('marca', '')} {v.get('modelo', '')}").classes('text-lg font-bold text-slate-800')
                        ui.label(f"Placa: {v.get('placa', '')} | KM: {o.get('km', '-')}").classes('text-slate-600 text-sm font-mono')

            # --- SECCIÓN 2: FLUJO DE TRABAJO (FASE POR CUADRO) ---
            ui.label('FLUJO DE TRABAJO POR FASES').classes('text-xs font-bold text-slate-400 tracking-[0.2em] mb-4 ml-2 uppercase')
            
            with ui.column().classes('w-full gap-4'):
                order_states = list(theme.ESTADOS_CONFIG.keys())
                try: current_state_idx = order_states.index(estado)
                except: current_state_idx = 0
                
                for idx, (est_name, est_cfg) in enumerate(theme.ESTADOS_CONFIG.items()):
                    is_current = est_name == estado
                    is_past = idx < current_state_idx
                    
                    card_status_cls = 'border-indigo-500 shadow-md ring-2 ring-indigo-50 ring-offset-2' if is_current else (
                        'border-emerald-200 opacity-90' if is_past else 'border-slate-100 opacity-60'
                    )
                    
                    with ui.card().classes(f'w-full bg-white border {card_status_cls} rounded-2xl overflow-hidden transition-all'):
                        with ui.expansion('', icon=est_cfg['icon']).classes('w-full').props('expand-icon-class=text-slate-400') as exp:
                            with exp.add_slot('header'):
                                with ui.row().classes('items-center justify-between w-full py-2 pr-4'):
                                    with ui.row().classes('items-center gap-4'):
                                        with ui.avatar(color=est_cfg['color']+'-1', text_color=est_cfg['color']).classes('w-10 h-10'):
                                            ui.icon(est_cfg['icon'], size='xs')
                                        with ui.column().classes('gap-0'):
                                            ui.label(est_name).classes('font-black text-slate-800 tracking-tight')
                                            status_label = 'EN PROCESO' if is_current else ('COMPLETADO' if is_past else 'PENDIENTE')
                                            status_color = 'indigo-600' if is_current else ('emerald-600' if is_past else 'slate-400')
                                            ui.label(status_label).classes(f'text-[9px] font-black text-{status_color} tracking-widest')
                                    if is_past or is_current:
                                        ui.icon('check_circle', color='emerald-500') if is_past else ui.icon('pending', color='indigo-500')

                            with ui.column().classes('w-full p-4 gap-4 bg-slate-50/30'):
                                # Phase-based filtering robusto
                                phase_pics = []
                                if o.get('fotos_evidencia'):
                                    def norm(t): return str(t or '').upper().replace('Á','A').replace('É','E').replace('Í','I').replace('Ó','O').replace('Ú','U').strip()
                                    target_p = norm(est_name)
                                    for p in o['fotos_evidencia']:
                                        p_fase = ''
                                        p_path = ''
                                        if isinstance(p, dict):
                                            p_path = p.get('path', '')
                                            p_fase = norm(p.get('fase', 'RECEPCIÓN'))
                                        else:
                                            p_path = p
                                            if 'DIAG' in p_path.upper(): p_fase = 'DIAGNOSTICO'
                                            elif 'REP' in p_path.upper(): p_fase = 'REPARACION'
                                            else: p_fase = 'RECEPCION'
                                        if p_fase == target_p:
                                            phase_pics.append(p_path)

                                if est_name.upper() == 'RECEPCIÓN':
                                    with ui.row().classes('w-full gap-4'):
                                        with ui.column().classes('flex-1'):
                                            ui.label('MOTIVO').classes('text-[9px] font-bold text-slate-400')
                                            ui.label(o.get('motivo', 'No especificado')).classes('text-sm text-slate-700 font-medium')
                                        with ui.column().classes('flex-1'):
                                            ui.label('OBSERVACIONES').classes('text-[9px] font-bold text-slate-400')
                                            ui.label(o.get('observaciones', '-')).classes('text-sm text-slate-700')
                                elif est_name.upper() == 'DIAGNÓSTICO':
                                    if o.get('diagnostico'):
                                        ui.label('DIAGNÓSTICO TÉCNICO').classes('text-[9px] font-bold text-slate-400')
                                        ui.markdown(o['diagnostico']).classes('text-sm text-slate-700 bg-white p-3 rounded-lg border border-slate-100')
                                elif est_name.upper() in ('REPUESTOS', 'APROBACIÓN'):
                                    items_list = o.get('items_cotizacion') or []
                                    if items_list:
                                        for itm in items_list:
                                            with ui.row().classes('w-full justify-between text-xs py-1 border-b'):
                                                ui.label(f"• {itm.get('nombre')} x{itm.get('cantidad', 1)}")
                                                ui.label(f"S/ {itm.get('total', 0):.2f}")
                                elif est_name.upper() == 'REPARACIÓN':
                                    if o.get('checklist_reparacion'): ui.label('Reparación finalizada.').classes('text-sm text-emerald-700')

                                if phase_pics:
                                    ui.label('EVIDENCIAS').classes('text-[9px] font-bold text-indigo-400 mt-2')
                                    with ui.row().classes('w-full gap-2 flex-wrap'):
                                        for path in phase_pics:
                                            ui.image(path).classes('w-20 h-20 border rounded-lg cursor-pointer').on('click', lambda l=path: ui.run_javascript(f'window.open("{l}", "_blank")'))

                                if is_current:
                                    with ui.row().classes('w-full justify-end mt-2'):
                                        if est_name.upper() == 'DIAGNÓSTICO':
                                            ui.button('EDITAR', icon='edit', on_click=lambda: (dialog.close(), open_new_diagnostic_modal(consecutivo, container, state))).props('unelevated color=amber-8 size=sm')
                                        elif est_name.upper() == 'REPARACIÓN':
                                            ui.button('EDITAR', icon='edit', on_click=lambda: (dialog.close(), open_advanced_repair_module(consecutivo, container, state))).props('unelevated color=amber-8 size=sm')
                                        else:
                                            ui.button('EDITAR', icon='edit', on_click=lambda: (dialog.close(), open_edit_reception_dialog(consecutivo, container, state))).props('unelevated color=amber-8 size=sm')
                            if is_current: exp.value = True

            # --- DOCUMENTOS ---
            with ui.row().classes('w-full justify-between mt-8 pt-4 border-t'):
                with ui.row().classes('gap-2'):
                    ui.button('PDF Ingreso', icon='picture_as_pdf', on_click=lambda: generate_pdf(o, c, v, 'ingreso')).props('outline size=sm')
                    ui.button('Enviar link', icon='send', on_click=lambda: send_approval_link(consecutivo)).props('outline color=cyan size=sm')
                
                if estado != 'ARCHIVADO':
                    next_idx = min(order_states.index(estado) + 1, len(order_states) - 1)
                    next_est = order_states[next_idx]
                    ui.button(f'AVANZAR -> {next_est}', icon='arrow_forward',
                        on_click=lambda n=next_est: (advance_order(consecutivo, n), dialog.close(), refresh_orders(container, state))
                    ).classes('btn-sandoval')
    dialog.open()


def open_create_order_dialog(container, state, stats_container=None):
    # Importar aquí para evitar referencias circulares
    from components.clientes import open_client_dialog
    from components.vehiculos import open_vehicle_dialog
    
    db = get_db()
    try:
        clients = db.query(Cliente).all()
        client_opts = {c.id: f"{c.nombre} {c.apellidos}".strip() for c in clients}
        vehicles = db.query(Vehiculo).all()
        vehicle_opts = {v.placa: f"{v.marca} {v.modelo} - {v.placa}" for v in vehicles}
    finally:
        db.close()
    
    tecnicos = _get_tecnicos()
    now = datetime.now()
    new_id = f"#ODS-{now.strftime('%Y%m%d')}-{now.strftime('%H%M')}"
    
    with ui.dialog() as dialog, ui.card().classes('w-full max-w-6xl bg-white p-0 border border-gray-200 shadow-xl'):
        # Header
        with ui.row().classes('w-full justify-between items-center p-4 border-b border-gray-200'):
            with ui.row().classes('items-center gap-2'):
                ui.label('Nueva Orden de Servicio').classes('text-xl font-bold text-gray-800')
                ui.label(new_id).classes('text-lime-700 font-mono font-bold text-lg')
            ui.button(icon='close', on_click=dialog.close).props('flat round color=grey-8')
            
        with ui.row().classes('w-full p-6 gap-6'):
            # Columna Izquierda: Datos Principales
            with ui.column().classes('flex-1 gap-4'):
                ui.label('Datos del Servicio').classes('text-gray-800 font-bold mb-2')
                
                # Tipo de Orden
                with ui.row().classes('w-full justify-between items-center bg-gray-50 p-3 rounded border border-gray-200'):
                    ui.label('Tipo de Orden').classes('text-gray-600')
                    tipo = ui.toggle(['Express', 'Estándar'], value='Express').props('color=lime-13 toggle-color=black text-color=black')
                
                # Cliente
                ui.label('Cliente *').classes('text-gray-600 text-xs mb-[-5px]')
                with ui.row().classes('w-full gap-2 items-center'):
                    cliente_sel = ui.select(client_opts, with_input=True, label='SELECCIONA CLIENTE').props('outlined dense use-input bg-color=white').classes('flex-1')
                    
                    def on_client_created(new_id):
                        db = get_db()
                        try:
                            c = db.query(Cliente).filter_by(id=new_id).first()
                            if c:
                                new_opts = client_opts.copy()
                                new_opts[c.id] = f"{c.nombre} {c.apellidos}".strip()
                                cliente_sel.options = new_opts
                                cliente_sel.value = c.id
                                cliente_sel.update()
                        finally:
                            db.close()

                    def open_new_client():
                        open_client_dialog(None, None, on_success=on_client_created)

                    ui.button(icon='add', on_click=open_new_client).props('unelevated color=lime-13 text-color=black round dense')

                # Vehículo
                ui.label('Vehículo *').classes('text-gray-600 text-xs mb-[-5px]')
                with ui.row().classes('w-full gap-2 items-center'):
                    vehiculo_sel = ui.select(vehicle_opts, with_input=True, label='SELECCIONA VEHÍCULO').props('outlined dense use-input bg-color=white').classes('flex-1')
                    
                    def on_vehicle_created(new_placa):
                        db = get_db()
                        try:
                            v = db.query(Vehiculo).filter_by(placa=new_placa).first()
                            if v:
                                new_opts = vehicle_opts.copy()
                                new_opts[v.placa] = f"{v.marca} {v.modelo} - {v.placa}"
                                vehiculo_sel.options = new_opts
                                vehiculo_sel.value = v.placa
                                vehiculo_sel.update()
                                # Si el vehículo tiene dueño y no hay cliente seleccionado, seleccionarlo
                                if v.cliente_id and not cliente_sel.value:
                                    cliente_sel.value = v.cliente_id
                        finally:
                            db.close()
                            
                    def open_new_vehicle():
                        open_vehicle_dialog(None, None, on_success=on_vehicle_created)

                    ui.button(icon='add', on_click=open_new_vehicle).props('unelevated color=lime-13 text-color=black round dense')

                # Técnico
                ui.label('Técnico responsable').classes('text-gray-600 text-xs mb-[-5px]')
                tecnico_sel = ui.select(tecnicos, value=tecnicos[0] if tecnicos else '', label='SELECCIONA').props('outlined dense bg-color=white').classes('w-full')
                
                # Datos extra vehículo
                with ui.row().classes('w-full gap-4'):
                    km_input = ui.input('Kilometraje').props('outlined dense type=number bg-color=white').classes('flex-1')
                    combustible_input = ui.select(['Reserva', '1/4', '1/2', '3/4', 'Full'],  label='Nivel Combustible').props('outlined dense bg-color=white').classes('flex-1')

            # Columna Derecha: Detalles
            with ui.column().classes('flex-1 gap-4'):
                ui.label('Diagnóstico e Ingreso').classes('text-gray-800 font-bold mb-2')
                
                # Diagnóstico Requerido
                with ui.card().classes('w-full bg-gray-50 border border-gray-200 p-4 shadow-sm'):
                    with ui.row().classes('w-full justify-between items-center'):
                        with ui.column().classes('gap-0'):
                            ui.label('¿El vehículo requiere diagnóstico inicial?').classes('text-gray-900 font-medium')
                            ui.label('Se requiere un diagnóstico para identificar la causa de falla.').classes('text-gray-500 text-xs')
                        diag_check = ui.switch('').props('color=lime-13').classes('mr-2')
                        diag_check.value = True # Default
                
                # Motivo
                ui.label('Motivo de ingreso *').classes('text-lime-700 text-xs font-bold mb-[-5px]')
                motivo_input = ui.textarea(placeholder='Describe aquí un motivo de ingreso').props('outlined dense rows=3 bg-color=white').classes('w-full rounded-lg')


            # Sección inferior: Evidencia de ingreso
            with ui.column().classes('w-full max-w-full mt-4 p-4 bg-gray-50 border border-gray-200 rounded shadow-sm'):
                ui.label('Evidencia de ingreso').classes('text-gray-900 font-bold mb-2')
                ui.label('Carga aquí la evidencia de ingreso (Max 10 fotos en formato JPG, PNG, JPEG, JFIF):').classes('text-gray-500 text-xs mb-1')
                
                uploaded_files = [] # Tuples (name, content)
                
                # Contenedor para previsualización de imágenes
                preview_container = ui.row().classes('w-full gap-2 mt-3 flex-wrap')

                with ui.row().classes('w-full gap-0 no-wrap items-center'):
                    # Input readonly simulando file picker
                    file_names_input = ui.input(placeholder='Seleccionar archivos').props('outlined dense readonly bg-color=white input-style="color: #444"').classes('flex-1 mr-2')
                    
                    # Uploader oculto
                    async def handle_upload(e):
                        try:
                            content = None
                            name = None

                            # Helper para leer contenido de forma segura (sync o async)
                            async def read_safe(obj):
                                # Si no tiene read, devolver el objeto tal cual (asumiendo que es bytes o string)
                                if not hasattr(obj, 'read'):
                                    return obj
                                # Si tiene read, llamar
                                val = obj.read()
                                # Si es awaitable (coroutine), esperar
                                if hasattr(val, '__await__'):
                                    return await val
                                return val

                            # Intentar obtener contenido y nombre de cualquier lugar posible
                            if hasattr(e, 'content'):
                                content = await read_safe(e.content)
                                # Intentar sacar nombre de e.content o e.name
                                name = getattr(e, 'name', getattr(e.content, 'name', None))
                            elif hasattr(e, 'files') and e.files:
                                f = e.files[0]
                                if hasattr(f, 'content'):
                                    content = await read_safe(f.content)
                                elif hasattr(f, 'read'):
                                    content = await read_safe(f)
                                name = getattr(f, 'name', getattr(e, 'name', None))
                            elif hasattr(e, 'file'):
                                # Posible alias
                                f = e.file
                                content = await read_safe(f)
                                name = getattr(f, 'name', getattr(e, 'name', None))
                            
                            # Fallback si no hay nombre
                            if not name:
                                # Tratar de buscar en cualquier atributo 'name'
                                name = getattr(e, 'name', None)

                            if not name:
                                name = f"imagen_{len(uploaded_files)+1}.jpg"
                            
                            if content is None:
                                attrs = [a for a in dir(e) if not a.startswith('_')]
                                raise Exception(f"Estructura desconocida. Atributos: {attrs}")

                            uploaded_files.append((name, content))
                            current_names = [f[0] for f in uploaded_files]
                            file_names_input.value = ", ".join(current_names)
                            ui.notify(f'Archivo cargado: {name}', type='positive')
                            
                            # Mostrar previsualización
                            import base64
                            try:
                                # Asegurar bytes
                                if isinstance(content, str):
                                    content = content.encode('utf-8') # Solo si fuera string accidentalmente
                                
                                # Verificar que tenemos algo
                                if not content:
                                    raise ValueError("Contenido vacío")

                                b64 = base64.b64encode(content).decode('utf-8')
                                mime = 'image/png' if name.lower().endswith('.png') else 'image/jpeg'
                                src = f'data:{mime};base64,{b64}'
                                
                                with preview_container:
                                    with ui.card().classes('w-24 h-24 p-0 relative group border border-gray-400'):
                                        ui.image(src).classes('w-full h-full object-cover rounded')
                                        ui.label(name).classes('absolute bottom-0 w-full bg-black/50 text-white text-[8px] truncate px-1')
                                        ui.icon('check_circle', size='xs').classes('absolute top-1 right-1 text-green-400')
                                
                                print(f"Preview generated for {name}, size: {len(content)} bytes")

                            except Exception as img_err:
                                print(f"Error preview: {img_err}")
                                ui.notify(f'Error visualizando {name}: {str(img_err)}', type='warning', multi_line=True, close_button=True)

                        except Exception as ex:
                            # Mostrar error detallado en UI para debug rápido
                            ui.notify(f'Error al cargar: {str(ex)}', type='negative', multi_line=True, close_button=True)
                            print(f"UPLOAD ERROR: {ex}")
                        
                    # Uploader invisible pero presente en el DOM (width/height 0, opacity 0)
                    uploader = ui.upload(on_upload=handle_upload, auto_upload=True, multiple=True, max_file_size=10_000_000).props('accept="image/*" flat dense').classes('absolute w-0 h-0 opacity-0 overflow-hidden m-0 p-0')
                    
                    # Botón visible que activa el uploader
                    ui.button('EXAMINAR ...', icon='folder_open', on_click=lambda: uploader.run_method('pickFiles')).props('unelevated color=lime-13 text-color=black font-bold icon-right').classes('h-10 ml-0')

        # Footer Actions
        with ui.row().classes('w-full justify-end gap-3 p-4 border-t border-gray-200'):
            ui.button('Cancelar', on_click=dialog.close).props('flat color=grey-8')
            
            def crear():
                if not cliente_sel.value or not motivo_input.value:
                    theme.notify_error('Cliente y motivo son obligatorios')
                    return
                
                cdb = get_db()
                try:
                    # Guardar evidencia si existe
                    evidencia_paths = []
                    if uploaded_files:
                        import os
                        # Directorio para la orden
                        base_dir = "static/evidencia"
                        os.makedirs(base_dir, exist_ok=True)
                        order_dir = os.path.join(base_dir, new_id.replace("#", "").replace("/", "_"))
                        os.makedirs(order_dir, exist_ok=True)
                        
                        for name, content in uploaded_files:
                            file_path = os.path.join(order_dir, name)
                            with open(file_path, 'wb') as f:
                                f.write(content)
                            # Guardar ruta relativa para acceso web e incluir la fase para separación
                            rel_path = f"/evidencia/{new_id.replace('#', '').replace('/', '_')}/{name}"
                            evidencia_paths.append({'path': rel_path, 'fase': 'RECEPCIÓN'})

                    new_order = Orden(
                        consecutivo=new_id,
                        fecha=now.strftime('%Y-%m-%d %H:%M'),
                        cliente_id=cliente_sel.value,
                        vehiculo_placa=vehiculo_sel.value or '',
                        motivo=(motivo_input.value or '').strip(),
                        estado='RECEPCIÓN',
                        tecnico=tecnico_sel.value or '',
                        km=(km_input.value or '').strip(),
                        tipo=tipo.value,
                        diagnostico_requerido=diag_check.value,
                        fotos_evidencia=evidencia_paths,
                        # Guardamos info extra en observaciones si no hay campo específico modelado aun
                        observaciones=f"Combustible: {combustible_input.value or '-'}",
                        items_cotizacion=[],
                        historial=[{
                            'fecha': now.strftime('%Y-%m-%d %H:%M'),
                            'accion': 'Orden creada',
                            'usuario': 'Admin', # TODO: Usar usuario real
                        }],
                        approval_token=secrets.token_urlsafe(32),
                    )
                    cdb.add(new_order)
                    cdb.commit()
                    log_actividad(f'Orden creada: {new_id}', 'ordenes')
                    theme.notify_success(f'Orden {new_id} creada')
                    dialog.close()
                    refresh_orders(container, state, stats_container)
                except Exception as e:
                    cdb.rollback()
                    theme.notify_error(f'Error: {str(e)}')
                finally:
                    cdb.close()
            
            ui.button('GUARDAR', icon='check_circle', on_click=crear).props('unelevated color=lime-13 text-color=black font-bold')
    dialog.open()


def advance_order(consecutivo, new_estado):
    db = get_db()
    try:
        order = db.query(Orden).filter_by(consecutivo=consecutivo).first()
        if order:
            old = order.estado
            order.estado = new_estado
            hist = list(order.historial or [])
            hist.append({
                'fecha': datetime.now().strftime('%Y-%m-%d %H:%M'),
                'accion': f'Estado: {old} -> {new_estado}',
                'usuario': 'Admin',
            })
            order.historial = hist
            db.commit()
            log_actividad(f'{consecutivo}: {old} -> {new_estado}', 'ordenes')
            theme.notify_success(f'{consecutivo} -> {new_estado}')
    except Exception as e:
        db.rollback()
        theme.notify_error(f'Error: {str(e)}')
    finally:
        db.close()


def send_approval_link(consecutivo):
    """Muestra diálogo con opciones de envío: WhatsApp, Email, Copiar link"""
    from utils.notifications import generate_approval_message
    
    msg_data = generate_approval_message(consecutivo)
    if 'error' in msg_data:
        theme.notify_error(msg_data['error'])
        return
    
    with ui.dialog() as dialog, ui.card().classes('w-full max-w-lg bg-white p-6 shadow-xl border border-gray-200'):
        ui.label('Enviar Link de Aprobación').classes('text-2xl font-bold text-gray-800 mb-4')
        ui.label(f'Orden: {consecutivo}').classes('text-gray-600 mb-2')
        
        if msg_data.get('total', 0) > 0:
            ui.label(f'Total: S/ {msg_data["total"]:.2f}').classes('text-lime-700 font-bold mb-4')
        
        # Link
        with ui.card().classes('bg-gray-50 border border-gray-200 p-3 w-full mb-3 shadow-sm'):
            ui.label('Link de aprobación:').classes('text-xs text-gray-500 font-bold')
            ui.label(msg_data['link']).classes('text-cyan-600 text-sm break-all')
        
        with ui.row().classes('w-full gap-2 flex-wrap'):
            # Copiar link
            ui.button('Copiar Link', icon='content_copy', on_click=lambda: (
                ui.run_javascript(f'navigator.clipboard.writeText("{msg_data["link"]}")'),
                theme.notify_success('Link copiado al portapapeles')
            )).props('color=cyan-6')
            
            # WhatsApp
            if msg_data.get('whatsapp_link'):
                ui.button('WhatsApp', icon='chat', on_click=lambda: (
                    ui.run_javascript(f'window.open("{msg_data["whatsapp_link"]}", "_blank")'),
                )).props('color=green-6')
            else:
                with ui.row().classes('items-center gap-1'):
                    ui.button('WhatsApp', icon='chat').props('color=green-6 disable')
                    ui.label('(sin teléfono)').classes('text-gray-500 text-xs')
            
            # Email
            if msg_data.get('client_email'):
                email = msg_data['client_email']
                subject = msg_data['email_subject']
                body = msg_data['email_body'].replace('\n', '%0A')
                mailto = f"mailto:{email}?subject={subject}&body={body}"
                ui.button('Email', icon='email', on_click=lambda: (
                    ui.run_javascript(f'window.open("{mailto}")'),
                )).props('color=blue-6')
            else:
                ui.button('Email', icon='email').props('color=blue-6 disable')
        
        # Previsualización WhatsApp
        with ui.expansion('Ver mensaje WhatsApp', icon='visibility').classes('w-full mt-3'):
            ui.label(msg_data['whatsapp_msg']).classes('text-gray-800 text-sm whitespace-pre-wrap font-mono bg-gray-50 border border-gray-200 p-3 rounded')
        
        ui.button('Cerrar', on_click=dialog.close).props('flat color=grey-8').classes('mt-4')
    
    dialog.open()


def generate_pdf(order_dict, client_dict, vehicle_dict, pdf_type):
    from utils import pdf_generator as pg
    try:
        os.makedirs('pdfs', exist_ok=True)
        timestamp = datetime.now().strftime('%H%M%S')
        filename = f"pdfs/{order_dict['consecutivo'].replace('#', '')}_{pdf_type}_{timestamp}.pdf"
        
        # Llamar al generador centralizado
        pg.generate_pdf(order_dict, client_dict, vehicle_dict, pdf_type, filename)
        
        # 1. Fuerza la descarga en el navegador
        ui.download(filename)
        
        # 2. Apertura automática en Windows (Nivel Profesional: El archivo se abre solo)
        try:
            os.startfile(os.path.abspath(filename))
        except Exception as e:
            print(f"No se pudo abrir automáticamente: {e}")

        theme.notify_success(f'PDF Generado: {filename}')
    except Exception as e:
        theme.notify_error(f'Error generando PDF: {str(e)}')


def open_advance_reception_dialog(consecutivo, container, state, stats_container=None):
    with ui.dialog() as dialog, ui.card().classes('w-full max-w-md bg-white p-0 border border-gray-200 shadow-xl rounded-xl overflow-hidden'):
        # Header Corporativo
        with ui.row().classes('w-full justify-between items-center p-4 bg-[#154c79]'):
            ui.label('Avanzar').classes('text-xl font-bold text-white')
            ui.button(icon='close', on_click=dialog.close).props('flat round color=grey-4 size=sm')
            
        with ui.column().classes('w-full p-6 gap-6'):
            ui.label('El vehículo ingresará a tu taller, tu cliente debe aprobar el estado en el que ingresa. ¿Cómo deseas solicitar su aprobación?').classes('text-gray-800 text-base font-medium leading-relaxed')
            
            with ui.column().classes('w-full gap-3'):
                # 1. WhatsApp
                def send_whatsapp():
                    from utils.notifications import generate_approval_message
                    msg_data = generate_approval_message(consecutivo)
                    # Solo abrimos WhatsApp, NO avanzamos estado (el cliente debe aprobar)
                    if msg_data.get('whatsapp_link'):
                         ui.run_javascript(f'window.open("{msg_data["whatsapp_link"]}", "_blank")')
                         theme.notify_success('Enlace generado y WhatsApp abierto. Esperando aprobación del cliente.')
                    else:
                        theme.notify_warning('Sin teléfono para WhatsApp.')
                    dialog.close()
                
                ui.button('VÍA WHATSAPP', on_click=send_whatsapp).props('unelevated').classes('w-full bg-[#4dd0e1] text-black font-bold h-12 text-sm hover:shadow-md transition-all')

                # 2. SMS (Placeholder)
                def send_sms():
                     # Simular envío
                     theme.notify_info('Opción SMS en desarrollo. No se avanzó el estado.')
                     dialog.close()
                ui.button('VÍA SMS', on_click=send_sms).props('unelevated').classes('w-full bg-[#4dd0e1] text-black font-bold h-12 text-sm hover:shadow-md transition-all')
                
                # 3. Verbalmente Aprobado
                def verbal_approve():
                    # Advance logic (Directo porque es verbal)
                    advance_order(consecutivo, 'DIAGNÓSTICO')
                    refresh_orders(container, state, stats_container)
                    theme.notify_success('Aprobación verbal registrada. Orden avanzada.')
                    dialog.close()
                    
                ui.button('VERBALMENTE APROBADO', on_click=verbal_approve).props('unelevated').classes('w-full bg-[#4dd0e1] text-black font-bold h-12 text-sm hover:shadow-md transition-all')
                
                # 4. Salir
                ui.button('SALIR', on_click=dialog.close).props('unelevated color=grey-9 text-color=white').classes('w-full h-12 font-bold')

    dialog.open()


def _order_to_dict(o):
    return {
        'consecutivo': o.consecutivo, 'fecha': o.fecha, 'cliente_id': o.cliente_id,
        'vehiculo_placa': o.vehiculo_placa, 'motivo': o.motivo, 'diagnostico': o.diagnostico,
        'estado': o.estado, 'tecnico': o.tecnico, 'km': o.km, 'tipo': o.tipo,
        'observaciones': o.observaciones, 'diagnostico_requerido': o.diagnostico_requerido,
        'items_cotizacion': o.items_cotizacion, 'historial': o.historial,
        'checklist_reparacion': o.checklist_reparacion, 'fotos_evidencia': o.fotos_evidencia,
        'approval_token': o.approval_token, 'approval_status': o.approval_status,
        'approval_date': o.approval_date,
    }

def _client_to_dict(c):
    if not c: return {}
    return {'id': c.id, 'nombre': c.nombre, 'apellidos': c.apellidos, 'email': c.email,
        'telefono': c.telefono, 'direccion': c.direccion}

def _vehicle_to_dict(v):
    if not v: return {}
    return {'placa': v.placa, 'marca': v.marca, 'modelo': v.modelo, 'año': v.año,
        'color': v.color, 'vin': v.vin}

def open_customer_preview(consecutivo):
    """Muestra previsualización de lo que ve el cliente con diseño Premium"""
    db = get_db()
    try:
        order = db.query(Orden).filter_by(consecutivo=consecutivo).first()
        if not order:
            theme.notify_error('Orden no encontrada')
            return
        
        client = db.query(Cliente).filter_by(id=order.cliente_id).first()
        vehicle = db.query(Vehiculo).filter_by(placa=order.vehiculo_placa).first()
        
        # Parse structured data
        checklist_data = order.checklist_reparacion
        if not isinstance(checklist_data, dict):
            if isinstance(checklist_data, str):
                import json
                try: checklist_data = json.loads(checklist_data)
                except: checklist_data = {}
            else: checklist_data = {}
        
        quick_check = checklist_data.get('quick_check', {})
        diag_details = checklist_data.get('diagnostic_details', {})
        
        with ui.dialog() as dialog, ui.card().classes('w-full max-w-5xl bg-slate-50 p-0 border-none shadow-2xl overflow-hidden'):
            # ─── HEADER PREMIUM ───
            with ui.row().classes('w-full items-center justify-between p-6 bg-slate-900 border-b-4 border-lime-400'):
                with ui.row().classes('items-center gap-4'):
                    ui.icon('verified', size='40px').classes('text-lime-400')
                    with ui.column().classes('gap-0'):
                        ui.label('REPORTE TÉCNICO OFICIAL').classes('text-white text-xs font-bold tracking-widest')
                        ui.label(f'ORDEN {consecutivo}').classes('text-3xl font-black text-white italic')
                
                with ui.column().classes('items-end gap-0'):
                    ui.button(icon='close', on_click=dialog.close).props('flat round color=white size=sm').classes('hover:bg-white/10')
                    ui.label(order.fecha).classes('text-slate-400 text-[10px] font-mono mt-1')

            with ui.scroll_area().classes('w-full p-6').style('height: 85vh'):
                
                # SECTION 1: RESUMEN Y ESTADO
                with ui.row().classes('w-full gap-6 mb-8'):
                    # Estado Card
                    with ui.card().classes('flex-1 bg-white border border-slate-200 p-6 shadow-sm rounded-2xl relative overflow-hidden'):
                        ui.element('div').classes('absolute top-0 right-0 w-32 h-32 bg-lime-100/50 rounded-full -mr-16 -mt-16')
                        ui.label('ESTADO ACTUAL').classes('text-slate-400 text-[10px] font-bold tracking-wider mb-1')
                        ui.label(order.estado).classes('text-2xl font-black text-slate-800 uppercase')
                        with ui.row().classes('items-center gap-2 mt-4'):
                            ui.icon('person', size='xs').classes('text-lime-600')
                            ui.label(f"Técnico: {order.tecnico or 'Asignando...'}").classes('text-slate-600 text-sm font-medium')
                    
                    # Vehículo Card
                    with ui.card().classes('flex-1 bg-white border border-slate-200 p-6 shadow-sm rounded-2xl'):
                        ui.label('VEHÍCULO REGISTRADO').classes('text-slate-400 text-[10px] font-bold tracking-wider mb-1')
                        if vehicle:
                            ui.label(f"{vehicle.marca} {vehicle.modelo}").classes('text-xl font-bold text-slate-800')
                            with ui.row().classes('items-center gap-4 mt-3'):
                                with ui.row().classes('items-center gap-1'):
                                    ui.icon('pin', size='xs').classes('text-slate-400')
                                    ui.label(vehicle.placa).classes('text-slate-900 font-mono font-bold bg-slate-100 px-2 py-1 rounded text-sm')
                                with ui.row().classes('items-center gap-1'):
                                    ui.icon('speed', size='xs').classes('text-slate-400')
                                    ui.label(f"{order.km or '-'} KM").classes('text-slate-900 font-bold text-sm')
                        else:
                            ui.label('Sin vehículo asociado').classes('text-slate-500 italic')

                # SECTION 2: INSPECCIÓN VISUAL (QUICK CHECK)
                if quick_check:
                    ui.label('INSPECCIÓN PREVENTIVA').classes('text-xs font-bold text-slate-400 tracking-[0.2em] mb-4 ml-2')
                    with ui.row().classes('w-full gap-3 mb-8 flex-wrap'):
                        check_icons = {
                            'Luces': 'lightbulb', 'Neumáticos': 'tire_repair', 
                            'Fluidos': 'water_drop', 'Batería': 'battery_std', 
                            'Carrocería': 'directions_car', 'Interior': 'airline_seat_recline_normal'
                        }
                        for item, data in quick_check.items():
                            if isinstance(data, str): data = {'status': data, 'note': ''}
                            is_ok = data.get('status') == 'OK'
                            
                            with ui.card().classes(f'min-w-[150px] flex-1 p-4 border border-slate-200 rounded-xl transition-all {"bg-green-50/50" if is_ok else "bg-amber-50 border-amber-200"}'):
                                with ui.row().classes('w-full items-center justify-between'):
                                    ui.icon(check_icons.get(item, 'check_circle'), size='sm').classes('text-slate-400' if is_ok else 'text-amber-600')
                                    ui.icon('check_circle' if is_ok else 'error', size='xs').classes('text-green-500' if is_ok else 'text-amber-600')
                                
                                ui.label(item).classes('text-xs font-bold text-slate-700 mt-2')
                                if not is_ok:
                                    ui.label(data.get('note') or 'REVISIÓN REQUERIDA').classes('text-[10px] text-amber-800 line-clamp-2 mt-1 italic leading-tight')
                                else:
                                    ui.label('SISTEMA OK').classes('text-[9px] text-green-700 font-bold mt-1 tracking-wider')

                # SECTION 3: DIAGNÓSTICO DETALLADO
                ui.label('ANÁLISIS TÉCNICO Y HALLAZGOS').classes('text-xs font-bold text-slate-400 tracking-[0.2em] mb-4 ml-2')
                with ui.card().classes('w-full bg-white border border-slate-200 rounded-3xl p-8 mb-8 text-slate-900 relative shadow-sm'):
                    
                    if diag_details:
                        # Usar datos estructurados para diseño más limpio
                        with ui.column().classes('w-full gap-8'):
                            # Célula de sistemas
                            with ui.column().classes('gap-2'):
                                ui.label('SISTEMAS AFECTADOS').classes('text-lime-700 text-[10px] font-bold tracking-widest')
                                systems = diag_details.get('system', [])
                                if isinstance(systems, str): systems = [systems]
                                with ui.row().classes('gap-2'):
                                    for s in systems:
                                        ui.label(s).classes('bg-slate-100 px-4 py-1 rounded-full text-xs font-bold border border-slate-200 text-slate-800')
                            
                            def _diag_box(title, content):
                                if not content: return
                                with ui.column().classes('w-full gap-2 mt-4 ml-2'):
                                    ui.label(title).classes('text-lime-700 text-[10px] font-bold tracking-widest')
                                    ui.label(content).classes('text-sm text-slate-700 leading-relaxed font-medium')

                            _diag_box('PRUEBAS REALIZADAS', diag_details.get('tests'))
                            _diag_box('CÓDIGOS DETECTADOS', diag_details.get('codes'))
                            _diag_box('DIAGNÓSTICO TÉCNICO', diag_details.get('analysis'))
                            _diag_box('SOLUCIÓN RECOMENDADA', diag_details.get('solution'))
                        
                    elif order.diagnostico:
                        # Fallback a texto plano si no hay estructura
                        ui.markdown(order.diagnostico.replace('\n', '  \n')).classes('text-sm leading-relaxed text-slate-700')
                    else:
                        ui.label('El diagnóstico aún no ha sido finalizado por el técnico.').classes('text-slate-400 italic text-sm')

                # SECTION 4: EVIDENCIA FOTOGRÁFICA (FILTRADA POR FASE ACTUAL)
                cur_fase = (order.estado or 'RECEPCIÓN').strip().upper()
                if order.fotos_evidencia and isinstance(order.fotos_evidencia, list):
                    # Filtrar evidencias que correspondan a la fase actual
                    def norm(t): return str(t or '').upper().replace('Á','A').replace('É','E').replace('Í','I').replace('Ó','O').replace('Ú','U').strip()
                    cur_fase_norm = norm(order.estado or 'RECEPCIÓN')
                    
                    fase_pics = []
                    for p in order.fotos_evidencia:
                        p_fase = ''
                        p_path = ''
                        if isinstance(p, dict):
                            p_path = p.get('path', '')
                            p_fase = norm(p.get('fase', 'RECEPCIÓN'))
                        else:
                            p_path = p
                            if 'DIAG' in p_path.upper(): p_fase = 'DIAGNOSTICO'
                            elif 'REP' in p_path.upper(): p_fase = 'REPARACION'
                            else: p_fase = 'RECEPCION'
                        
                        if p_fase == cur_fase_norm:
                            fase_pics.append(p_path)
                    
                    if fase_pics:
                        ui.label(f'EVIDENCIA FOTOGRÁFICA - {cur_fase}').classes('text-xs font-bold text-slate-400 tracking-[0.2em] mb-4 ml-2')
                        with ui.row().classes('w-full gap-4 mb-4 flex-wrap'):
                            for p in fase_pics:
                                pic_path = p.get('path') if isinstance(p, dict) else p
                                with ui.card().classes('w-48 h-48 p-0 relative border border-slate-200 group rounded-xl overflow-hidden shadow-sm hover:shadow-md transition-shadow'):
                                    ui.image(pic_path).classes('w-full h-full object-cover')
                                    with ui.row().classes('absolute inset-0 bg-slate-900/40 opacity-0 group-hover:opacity-100 transition-opacity items-center justify-center'):
                                        ui.button(icon='zoom_in', on_click=lambda l=pic_path: ui.run_javascript(f'window.open("{l}", "_blank")')).props('flat round color=white size=sm')

                # SECTION 5: PRESUPUESTO Y SERVICIOS (ULTRA PROFESSIONAL)
                items = order.items_cotizacion or []
                if items:
                    ui.label('RESUMEN DE INVERSIONES').classes('text-xs font-bold text-slate-400 tracking-[0.2em] mb-4 mt-8 ml-2')
                    with ui.card().classes('w-full bg-white border-none shadow-xl rounded-2xl overflow-hidden p-0 mb-8'):
                        # Header de la cotización
                        with ui.row().classes('w-full bg-slate-900 p-6 items-center justify-between'):
                            with ui.column().classes('gap-0'):
                                ui.label('MECÁNICA Y REPUESTOS SANDOVAL EIRL').classes('text-lime-400 text-[10px] font-black tracking-widest')
                                ui.label('DETALLE TÉCNICO ECONÓMICO').classes('text-white text-lg font-bold')
                            ui.icon('receipt_long', size='32px').classes('text-slate-400')
                        
                        # Tabla
                        with ui.column().classes('w-full p-0'):
                            # Encabezado
                            with ui.row().classes('w-full bg-slate-50 border-b border-slate-100 py-3 px-6 flex-nowrap'):
                                ui.label('CANT').classes('text-slate-400 text-[10px] font-black').style('width: 10%')
                                ui.label('DESCRIPCIÓN').classes('text-slate-400 text-[10px] font-black').style('width: 60%')
                                ui.label('P. UNIT.').classes('text-slate-400 text-[10px] font-black text-right').style('width: 15%')
                                ui.label('TOTAL').classes('text-slate-400 text-[10px] font-black text-right').style('width: 15%')
                            
                            subtotal = 0
                            for idx, itm in enumerate(items):
                                bg_row = 'bg-white' if idx % 2 == 0 else 'bg-slate-50/50'
                                val_unit = float(itm.get('precio_unitario', 0))
                                total_itm = float(itm.get('total', 0))
                                subtotal += total_itm
                                
                                with ui.row().classes(f'w-full {bg_row} py-4 px-6 items-center border-b border-slate-50 hover:bg-slate-100/50 transition-colors flex-nowrap'):
                                    ui.label(str(itm.get('cantidad', 1))).classes('text-slate-500 font-bold text-sm').style('width: 10%')
                                    with ui.column().classes('gap-0').style('width: 60%'):
                                        ui.label(itm.get('nombre', 'Item sin nombre')).classes('text-slate-800 font-bold text-sm truncate')
                                        ui.label(itm.get('categoria', 'Repuesto').upper()).classes('text-slate-400 text-[9px] font-bold')
                                    ui.label(f"S/ {val_unit:.2f}").classes('text-slate-500 text-sm text-right').style('width: 15%')
                                    ui.label(f"S/ {total_itm:.2f}").classes('text-slate-900 font-black text-sm text-right').style('width: 15%')
                            
                            # Totales
                            with ui.row().classes('w-full p-8 bg-slate-100 items-center justify-between'):
                                with ui.column().classes('gap-1'):
                                    ui.label('MÉTODO DE PAGO:').classes('text-slate-400 text-[10px] font-bold')
                                    with ui.row().classes('items-center gap-2'):
                                        ui.icon('account_balance', size='xs').classes('text-slate-400')
                                        ui.label('Transferencia / Yape / Plin').classes('text-slate-600 text-[10px] font-medium')
                                
                                with ui.column().classes('items-end'):
                                    ui.label('TOTAL A INVERTIR').classes('text-slate-500 text-xs font-black tracking-widest mb-1')
                                    ui.label(f"S/ {subtotal:.2f}").classes('text-slate-900 text-6xl font-black drop-shadow-sm')
                                    ui.label('* Precios finales incluyen impuestos').classes('text-slate-400 text-[9px] italic')

        dialog.open()
    finally:
        db.close()


def open_edit_reception_dialog(consecutivo, container, state):
    """Edita datos iniciales de recepción con manejo de errores robusto"""
    try:
        db = get_db()
        try:
            order = db.query(Orden).filter_by(consecutivo=consecutivo).first()
            if not order: 
                theme.notify_error('Orden no encontrada')
                return
            
            new_reception_files = [] # Para nuevas fotos durante edición
            
            # Datos actuales para prellenar
            curr_motivo = order.motivo
            curr_km = order.km
            curr_tecnico = order.tecnico
            curr_diag_req = order.diagnostico_requerido
            curr_tipo = order.tipo
            curr_obs = order.observaciones
            
            combustible_val = 'Reserva'
            if 'Combustible: ' in (curr_obs or ''):
                parts = curr_obs.split('Combustible: ')
                if len(parts) > 1:
                    combustible_val = parts[1].split('\n')[0].strip()
        finally:
            db.close()

        tecnicos = _get_tecnicos()
        if curr_tecnico and curr_tecnico not in tecnicos:
            tecnicos.append(curr_tecnico)
        
        tipo_opts = ['Express', 'Estándar']
        if curr_tipo and curr_tipo not in tipo_opts:
            tipo_opts.append(curr_tipo)
            
        comb_opts = ['Reserva', '1/4', '1/2', '3/4', 'Full']
        if combustible_val and combustible_val not in comb_opts:
            comb_opts.append(combustible_val)

        with ui.dialog() as dialog, ui.card().classes('w-full max-w-4xl bg-white p-0 border border-gray-200 shadow-xl'):
            with ui.row().classes('w-full items-center justify-between p-4 border-b border-gray-200'):
                ui.label(f'Editar Recepción - {consecutivo}').classes('text-xl font-bold text-gray-800')
                ui.button(icon='close', on_click=dialog.close).props('flat round color=grey-8')
            
            with ui.scroll_area().classes('w-full').style('height: 65vh'):
                with ui.row().classes('w-full p-6 gap-6'):
                    with ui.column().classes('flex-1 gap-4'):
                        tipo_input = ui.toggle(tipo_opts, value=curr_tipo).props('color=lime-13 toggle-color=black text-color=black')
                        tecnico_input = ui.select(tecnicos, value=curr_tecnico, label='Técnico').props('outlined dense bg-color=white').classes('w-full')
                        with ui.row().classes('w-full gap-4'):
                            km_input = ui.input('Kilometraje', value=curr_km).props('outlined dense bg-color=white').classes('flex-1')
                            comb_input = ui.select(comb_opts, value=combustible_val, label='Nivel Combustible').props('outlined dense bg-color=white').classes('flex-1')
                
                    with ui.column().classes('flex-1 gap-4'):
                        ui.label('GESTIÓN DE FOTOS (RECEPCIÓN)').classes('text-xs font-bold text-blue-600 border-b w-full pb-1')
                        edit_ev_cont = ui.row().classes('w-full gap-2 flex-wrap min-h-[50px]')
                        
                        def refresh_edit_photos():
                            edit_ev_cont.clear()
                            try:
                                db_p = get_db()
                                try:
                                    o_p = db_p.query(Orden).filter_by(consecutivo=consecutivo).first()
                                    if o_p:
                                        # Solo mostramos fotos de la fase RECEPCIÓN para editar aquí
                                        current_pics = []
                                        for p in list(o_p.fotos_evidencia or []):
                                            if isinstance(p, dict):
                                                if p.get('fase', 'RECEPCIÓN').strip().upper() == 'RECEPCIÓN':
                                                    current_pics.append(p)
                                            else:
                                                current_pics.append(p)

                                        with edit_ev_cont:
                                            for p in current_pics:
                                                pic_path = p.get('path') if isinstance(p, dict) else p
                                                with ui.card().classes('w-16 h-16 p-0 relative'):
                                                    ui.image(pic_path).classes('w-full h-full object-cover rounded')
                                                    ui.button(icon='close', on_click=lambda item=p: remove_existent_photo(item)).props('flat dense color=red round size=xs shadow-sm').classes('absolute -top-1 -right-1 bg-white z-10')
                                finally:
                                    db_p.close()
                            except Exception as ex:
                                print(f"Error refresh_edit_photos: {ex}")

                        def remove_existent_photo(path):
                            db_r = get_db()
                            try:
                                o_r = db_r.query(Orden).filter_by(consecutivo=consecutivo).first()
                                if o_r:
                                    cur = list(o_r.fotos_evidencia or [])
                                    if path in cur:
                                        cur.remove(path)
                                        o_r.fotos_evidencia = cur
                                        from sqlalchemy.orm.attributes import flag_modified
                                        flag_modified(o_r, "fotos_evidencia")
                                        db_r.commit()
                                        refresh_edit_photos()
                            finally: db_r.close()

                        async def handle_edit_up(e):
                            try:
                                content = None
                                name = getattr(e, 'name', None)
                                f_obj = getattr(e, 'content', getattr(e, 'file', None))
                                if f_obj:
                                    if hasattr(f_obj, 'seek'): f_obj.seek(0)
                                    content = f_obj.read()
                                    if hasattr(content, '__await__'): content = await content
                                    if not name: name = getattr(f_obj, 'name', None)
                                
                                if content:
                                    final_name = name or "foto.jpg"
                                    new_reception_files.append((final_name, content))
                                    ui.notify(f'Añadida: {final_name}', type='positive')
                                    # Simular visualización de la nueva foto
                                    with edit_ev_cont:
                                        ui.icon('image', size='lg', color='blue-2').classes('w-16 h-16 border rounded')
                                else:
                                    theme.notify_error("Error al leer imagen")
                            except Exception as err:
                                theme.notify_error(f"Error: {str(err)}")

                        ui.upload(on_upload=handle_edit_up, auto_upload=True).props('flat dense color=blue-7 accept="image/*" label="Añadir fotos de recepción"').classes('w-full border border-dashed border-gray-300 rounded p-1')
                        refresh_edit_photos()

                        with ui.row().classes('w-full justify-between items-center mt-2'):
                            ui.label('¿Requiere diagnóstico?').classes('text-gray-800')
                            diag_check = ui.switch(value=curr_diag_req).props('color=lime-13')
                        
                        motivo_input = ui.textarea('Motivo de ingreso', value=curr_motivo).props('outlined dense rows=3 bg-color=white').classes('w-full')

            with ui.row().classes('w-full justify-end gap-3 p-4 border-t border-gray-200'):
                ui.button('Cancelar', on_click=dialog.close).props('flat color=grey-8')
                
                def save_changes():
                    ddb = get_db()
                    try:
                        o = ddb.query(Orden).filter_by(consecutivo=consecutivo).first()
                        if o:
                            o.tipo = tipo_input.value
                            o.tecnico = tecnico_input.value
                            o.km = km_input.value
                            o.motivo = motivo_input.value
                            o.diagnostico_requerido = diag_check.value
                            o.observaciones = f"Combustible: {comb_input.value}"
                            
                            if new_reception_files:
                                folder_name = consecutivo.replace('#','').replace('/','_').strip()
                                s_dir = f"static/evidencia/{folder_name}"
                                os.makedirs(s_dir, exist_ok=True)
                                curr_p = list(o.fotos_evidencia or [])
                                for fn, fc in new_reception_files:
                                    sfname = f"REV_{datetime.now().strftime('%H%M%S')}_{fn}"
                                    f_path = os.path.join(s_dir, sfname)
                                    with open(f_path, 'wb') as f:
                                        f.write(fc)
                                    curr_p.append({'path': f"/evidencia/{folder_name}/{sfname}", 'fase': 'RECEPCIÓN'})
                                o.fotos_evidencia = curr_p
                                from sqlalchemy.orm.attributes import flag_modified
                                flag_modified(o, "fotos_evidencia")

                            ddb.commit()
                            theme.notify_success('Recepción actualizada')
                            dialog.close()
                            refresh_orders(container, state)
                    except Exception as e:
                        ddb.rollback()
                        theme.notify_error(f'Error al guardar: {e}')
                    finally:
                        ddb.close()

                ui.button('Guardar Cambios', icon='save', on_click=save_changes).props('unelevated color=lime-13 text-color=black')
            
        dialog.open()
    except Exception as outer_ex:
        theme.notify_error(f"Error crítico al abrir edición: {outer_ex}")
        print(f"CRITICAL ERROR open_edit_reception_dialog: {outer_ex}")

"""
SANDOVAL Dashboard - Asistente IA del Taller
Chat inteligente con Groq para análisis del negocio.
Historial persistente en app.storage.user (sobrevive navegación).
Completamente separado del bot universitario Jarvis.
"""

from nicegui import ui, app
from datetime import datetime
import theme

STORAGE_KEY_HISTORY = 'sandoval_ia_history'    # lista de {role, content, time}
STORAGE_KEY_GROQ    = 'sandoval_ia_groq_msgs'  # lista de {role, content}


def _load_history() -> list:
    return app.storage.user.get(STORAGE_KEY_HISTORY, [])

def _save_history(history: list):
    app.storage.user[STORAGE_KEY_HISTORY] = history[-60:]  # máx 60 mensajes guardados

def _load_groq() -> list:
    return app.storage.user.get(STORAGE_KEY_GROQ, [])

def _save_groq(msgs: list):
    app.storage.user[STORAGE_KEY_GROQ] = msgs[-40:]  # máx 40 para la API


def show_asistente(container):
    """Panel principal del Asistente IA Sandoval con historial persistente."""

    # Cargar historial de la sesión
    chat_history  = _load_history()
    groq_messages = _load_groq()

    with container:
        # ── Header ──
        with ui.row().classes('w-full items-center justify-between mb-4 py-5 px-8 bg-white border border-gray-100 rounded-xl shadow-sm'):
            with ui.row().classes('items-center gap-4'):
                with ui.element('div').classes('w-10 h-10 rounded-xl flex items-center justify-center').style('background:linear-gradient(135deg,#274495,#1e3a8a)'):
                    ui.icon('smart_toy', size='22px', color='white')
                with ui.column().classes('gap-0'):
                    ui.label('ASISTENTE IA SANDOVAL').classes('text-xl font-extrabold text-[#274495] tracking-tight')
                    ui.label('Powered by Groq · llama-3.3-70b-versatile').classes('text-[10px] text-gray-400 font-medium')
            with ui.row().classes('items-center gap-2'):
                ui.badge('EN LÍNEA', color='green').classes('text-[9px] font-black')
                if chat_history:
                    ui.label(f'{len(chat_history)} mensajes').classes('text-[10px] text-gray-400')
                ui.button(icon='refresh', on_click=lambda: _reset_chat(chat_container, chat_history, groq_messages)).props('flat round color=grey-6 size=sm').tooltip('Limpiar conversación')

        # ── Layout principal ──
        with ui.row().classes('w-full gap-4 h-full'):

            # ── Panel izquierdo: Atajos ──
            with ui.card().classes('w-64 p-4 bg-white border border-gray-100 shadow-sm rounded-2xl self-start'):
                ui.label('PREGUNTAS RÁPIDAS').classes('text-[10px] font-black text-blue-600 uppercase tracking-widest mb-3')
                sugerencias = [
                    ('📊', '¿Cómo va el taller hoy?'),
                    ('⚠️', '¿Qué órdenes están retrasadas?'),
                    ('📦', '¿Qué productos necesito pedir?'),
                    ('💰', '¿Cuánto he ganado este mes?'),
                    ('🔧', '¿Cuántas órdenes activas hay?'),
                    ('📈', '¿Cómo mejorar la rentabilidad?'),
                ]
                sugerencia_container = ui.column().classes('w-full gap-1')

            # ── Panel derecho: Chat ──
            with ui.column().classes('flex-1 gap-3'):

                # Área de chat
                chat_container = ui.column().classes(
                    'w-full bg-gray-50 rounded-2xl border border-gray-100 overflow-y-auto gap-0'
                ).style('min-height:420px; max-height:520px; padding:16px;')

                # ── Renderizar historial guardado ──
                with chat_container:
                    if chat_history:
                        # Restaurar conversación previa
                        for msg in chat_history:
                            _render_bubble(msg['role'], msg['content'], msg.get('time', ''))
                    else:
                        _mensaje_bienvenida()

                # ── Input de mensaje ──
                with ui.row().classes('w-full gap-3 items-center'):
                    msg_input = ui.input(
                        placeholder='Escribe tu pregunta o sube una factura...'
                    ).props('outlined rounded dense').classes('flex-1').style('font-size:14px')

                    # Botón subir imagen (factura)
                    async def handle_img_upload(e):
                        import os, asyncio
                        
                        file_name = getattr(e, 'name', None)
                        if not file_name and hasattr(e, 'file'):
                            file_name = getattr(e.file, 'name', 'imagen_subida.jpg')
                        file_name = file_name or 'imagen_subida.jpg'
                        
                        fname = f'ia_img_{datetime.now().strftime("%Y%m%d_%H%M%S")}_{file_name}'
                        fpath = os.path.join('static/facturas', fname)
                        os.makedirs('static/facturas', exist_ok=True)
                        
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

                        _append_message(chat_container, chat_history, groq_messages, 'user', f'📸 [Imagen subida: {file_name}]')
                        typing = _add_typing_indicator(chat_container)

                        try:
                            from utils.groq_service import analizar_factura_imagen
                            # Ejecutar en hilo separado para no bloquear la UI
                            loop = asyncio.get_event_loop()
                            datos = await loop.run_in_executor(None, analizar_factura_imagen, fpath)
                            if 'error' in datos:
                                resp = f"⚠️ No pude leer la imagen: {datos['error']}"
                            else:
                                proveedor = datos.get('proveedor', 'desconocido')
                                total = datos.get('total', 0)
                                items = datos.get('items', [])
                                tipo = datos.get('tipo_detectado', 'mercaderia')
                                items_txt = "\n".join([f"  • {it.get('nombre','')} ×{it.get('cantidad',1)} @ S/. {it.get('precio_unitario',0):.2f}" for it in items[:10]])
                                tipo_msg = "🔧 Parece una compra de mercadería para el taller." if tipo == 'mercaderia' else "🏠 Parece un gasto operacional."
                                resp = f"📋 Análisis de Factura completado\n\nProveedor: {proveedor}\nTotal: S/ {total:,.2f}\n{tipo_msg}\n\nProductos detectados ({len(items)}):\n{items_txt}\n\n¿Deseas registrarla en Facturas para {'agregar al inventario' if tipo == 'mercaderia' else 'registrar como gasto'}?"
                        except Exception as ex:
                            resp = f"⚠️ Error analizando imagen: {str(ex)[:100]}"

                        chat_container.remove(typing)
                        _append_message(chat_container, chat_history, groq_messages, 'assistant', resp)


                    ui.upload(auto_upload=True, multiple=False, on_upload=handle_img_upload).props(
                        'flat round color=blue-7 icon=add_photo_alternate accept=image/*'
                    ).classes('shrink-0')

                    async def send_message():
                        msg = msg_input.value.strip()
                        if not msg:
                            return
                        msg_input.value = ''
                        _append_message(chat_container, chat_history, groq_messages, 'user', msg)
                        typing = _add_typing_indicator(chat_container)

                        try:
                            from utils.groq_service import chat_con_asistente, get_context_data
                            ctx = get_context_data()
                            respuesta = chat_con_asistente(groq_messages.copy(), ctx)
                        except Exception as ex:
                            respuesta = f"⚠️ Error conectando con Groq: {str(ex)[:120]}\n\nVerifica la API Key en Configuración → IA Sandoval."

                        chat_container.remove(typing)
                        _append_message(chat_container, chat_history, groq_messages, 'assistant', respuesta)
                        ui.run_javascript('var el = document.querySelector(".overflow-y-auto"); if(el) el.scrollTop = el.scrollHeight;')

                    msg_input.on('keydown.enter', send_message)
                    ui.button(icon='send', on_click=send_message).props(
                        'unelevated round color=primary'
                    ).classes('shrink-0')

                # Botones de sugerencias
                with sugerencia_container:
                    for emoji, texto in sugerencias:
                        async def ask_sugerencia(t=texto):
                            msg_input.value = t
                            await send_message()
                        ui.button(
                            f'{emoji} {texto}', on_click=ask_sugerencia
                        ).props('flat no-caps align=left').classes(
                            'w-full text-left text-xs text-gray-600 hover:bg-blue-50 rounded-xl px-3 py-2'
                        ).style('font-size:11px; min-height:32px')

        ui.label('🔒 Las conversaciones son privadas y no se comparten con el bot universitario Jarvis.').classes(
            'text-[10px] text-gray-300 text-center w-full mt-2'
        )

        # Scroll al final al cargar si hay historial
        if chat_history:
            ui.run_javascript('setTimeout(()=>{ var el = document.querySelector(".overflow-y-auto"); if(el) el.scrollTop = el.scrollHeight; }, 300);')


def _append_message(container, history: list, groq_msgs: list, role: str, content: str):
    """Agrega un mensaje, lo renderiza y lo persiste en session storage."""
    hora = datetime.now().strftime('%H:%M')
    history.append({'role': role, 'content': content, 'time': hora})
    groq_msgs.append({'role': role, 'content': content})
    # Persistir en sesión
    _save_history(history)
    _save_groq(groq_msgs)
    # Renderizar
    with container:
        _render_bubble(role, content, hora)


def _render_bubble(role: str, content: str, hora: str = ''):
    """Renderiza una burbuja de chat (sin modificar el historial)."""
    is_user = role == 'user'
    if not hora:
        hora = datetime.now().strftime('%H:%M')

    with ui.element('div').classes(f'flex gap-3 mb-3 {"flex-row-reverse" if is_user else ""}'):
        avatar_bg = 'linear-gradient(135deg,#10b981,#059669)' if is_user else 'linear-gradient(135deg,#274495,#1e3a8a)'
        icon_name = 'person' if is_user else 'smart_toy'
        with ui.element('div').classes('w-8 h-8 rounded-xl flex items-center justify-center shrink-0').style(f'background:{avatar_bg}'):
            ui.icon(icon_name, size='16px', color='white')

        bubble_bg = 'linear-gradient(135deg,#274495,#1e3a8a)' if is_user else '#ffffff'
        txt_color = 'white' if is_user else '#1e293b'
        shadow = '' if is_user else 'box-shadow:0 2px 8px rgba(0,0,0,0.08)'
        radius = 'border-radius:18px 18px 18px 4px' if not is_user else 'border-radius:18px 18px 4px 18px'

        with ui.column().classes('gap-1').style('max-width:80%'):
            with ui.element('div').classes('rounded-2xl px-4 py-3').style(f'background:{bubble_bg}; {shadow}; {radius}'):
                ui.label(content).style(
                    f'color:{txt_color}; font-size:13px; line-height:1.6; white-space:pre-wrap; word-break:break-word'
                )
            ui.label(hora).classes(f'text-[10px] text-gray-400 {"text-right" if is_user else ""}')


def _mensaje_bienvenida():
    with ui.element('div').classes('flex gap-3 p-3 rounded-2xl mb-2').style('background:linear-gradient(135deg,#eff6ff,#dbeafe)'):
        with ui.element('div').classes('w-9 h-9 rounded-xl flex items-center justify-center shrink-0').style('background:linear-gradient(135deg,#274495,#1e3a8a)'):
            ui.icon('smart_toy', size='18px', color='white')
        with ui.column().classes('flex-1 gap-1'):
            ui.label('Asistente Sandoval').classes('text-xs font-black text-blue-700')
            ui.label(
                '¡Hola! Soy el Asistente IA de Mecánica Sandoval. 🔧\n\n'
                'Puedo ayudarte con:\n'
                '• Analizar el estado actual del taller\n'
                '• Revisar órdenes, clientes y stock\n'
                '• Historial completo: ingresos, repuestos, tendencias\n'
                '• Leer y procesar fotos de facturas 📸\n\n'
                '¿Qué necesitas saber hoy?'
            ).classes('text-sm text-blue-800 whitespace-pre-line leading-relaxed')
            ui.label(datetime.now().strftime('%H:%M')).classes('text-[10px] text-blue-400')


def _add_typing_indicator(container):
    with container:
        with ui.element('div').classes('flex gap-3 mb-3') as typing_el:
            with ui.element('div').classes('w-8 h-8 rounded-xl flex items-center justify-center').style('background:linear-gradient(135deg,#274495,#1e3a8a)'):
                ui.icon('smart_toy', size='16px', color='white')
            with ui.element('div').classes('rounded-2xl px-4 py-3 bg-white').style('box-shadow:0 2px 8px rgba(0,0,0,0.08)'):
                with ui.row().classes('gap-1 items-center'):
                    for i in range(3):
                        ui.element('div').classes('w-2 h-2 rounded-full bg-blue-400').style(
                            f'animation:bounce 1s infinite {i*0.2}s'
                        )
            ui.add_head_html('<style>@keyframes bounce{0%,100%{transform:translateY(0)}50%{transform:translateY(-4px)}}</style>')
        return typing_el


def _reset_chat(container, history: list, groq_messages: list):
    """Limpia el chat y la sesión persistida."""
    history.clear()
    groq_messages.clear()
    # Limpiar del storage
    app.storage.user.pop(STORAGE_KEY_HISTORY, None)
    app.storage.user.pop(STORAGE_KEY_GROQ, None)
    container.clear()
    with container:
        _mensaje_bienvenida()
    theme.notify_info('Conversación borrada')

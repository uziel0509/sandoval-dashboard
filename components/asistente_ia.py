"""
SANDOVAL Dashboard - Asistente IA del Taller
Chat inteligente con Groq para análisis del negocio
Completamente separado del bot universitario Jarvis
"""

from nicegui import ui
from datetime import datetime
import theme


def show_asistente(container):
    """Panel principal del Asistente IA Sandoval"""
    
    # Estado interno del chat
    chat_history = []  # lista de {'role','content','time'}
    groq_messages = []  # mensajes para enviar a Groq API
    
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
                ui.button(icon='refresh', on_click=lambda: _reset_chat(chat_container, chat_history, groq_messages)).props('flat round color=grey-6 size=sm')

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
                
                def make_ask_fn(txt, chat_c, hist, groq_h, inp, send_fn):
                    async def ask():
                        inp.value = txt
                        await send_fn()
                    return ask
                
                # Los botones de sugerencias se crearán después de definir el input
                sugerencia_container = ui.column().classes('w-full gap-1')
            
            # ── Panel derecho: Chat ──
            with ui.column().classes('flex-1 gap-3'):
                
                # Área de chat
                chat_container = ui.column().classes(
                    'w-full bg-gray-50 rounded-2xl border border-gray-100 overflow-y-auto gap-0'
                ).style('min-height:420px; max-height:520px; padding:16px;')
                
                with chat_container:
                    _mensaje_bienvenida()
                
                # ── Input de mensaje ──
                with ui.row().classes('w-full gap-3 items-center'):
                    msg_input = ui.input(
                        placeholder='Escribe tu pregunta o sube una factura...'
                    ).props('outlined rounded dense').classes('flex-1').style('font-size:14px')
                    
                    # Botón subir imagen (factura)
                    async def handle_img_upload(e):
                        import os
                        fname = f'ia_img_{datetime.now().strftime("%Y%m%d_%H%M%S")}_{e.name}'
                        fpath = os.path.join('static/facturas', fname)
                        os.makedirs('static/facturas', exist_ok=True)
                        with open(fpath, 'wb') as f:
                            f.write(e.content.read())
                        
                        # Agregar imagen al chat
                        _add_message(chat_container, chat_history, 'user', f'📸 [Imagen subida: {e.name}]', imagen_path=fpath)
                        _add_message(chat_container, chat_history, 'assistant', '⏳ Analizando la imagen con Groq Vision...')
                        
                        try:
                            from utils.groq_service import analizar_factura_imagen
                            datos = analizar_factura_imagen(fpath)
                            
                            if 'error' in datos:
                                resp = f"⚠️ No pude leer la imagen: {datos['error']}"
                            else:
                                proveedor = datos.get('proveedor', 'desconocido')
                                total = datos.get('total', 0)
                                items = datos.get('items', [])
                                tipo = datos.get('tipo_detectado', 'mercaderia')
                                
                                items_txt = "\n".join([f"  • {it.get('nombre','')} ×{it.get('cantidad',1)} @ S/. {it.get('precio_unitario',0):.2f}" for it in items[:10]])
                                tipo_msg = "🔧 Parece una **compra de mercadería** para el taller." if tipo == 'mercaderia' else "🏠 Parece un **gasto operacional**."
                                
                                resp = f"""📋 **Análisis de Factura completado**

**Proveedor:** {proveedor}
**Total:** S/ {total:,.2f}
{tipo_msg}

**Productos detectados ({len(items)}):**
{items_txt}

¿Deseas que guarde esta factura en el sistema? Ve a la sección **Facturas** para registrarla y {("agregar los productos al inventario automáticamente" if tipo == "mercaderia" else "registrarla como gasto")}."""
                        except Exception as ex:
                            resp = f"⚠️ Error analizando imagen: {str(ex)[:100]}"
                        
                        # Reemplazar el mensaje de "analizando"
                        chat_history.pop()  # quitar el "analizando"
                        _add_message(chat_container, chat_history, 'assistant', resp)
                    
                    ui.upload(auto_upload=True, multiple=False, on_upload=handle_img_upload).props(
                        'flat round color=blue-7 icon=add_photo_alternate accept=image/*'
                    ).classes('shrink-0')
                    
                    async def send_message():
                        msg = msg_input.value.strip()
                        if not msg:
                            return
                        
                        msg_input.value = ''
                        _add_message(chat_container, chat_history, 'user', msg)
                        groq_messages.append({'role': 'user', 'content': msg})
                        
                        # Indicador de typing
                        typing_msg = _add_typing_indicator(chat_container)
                        
                        try:
                            from utils.groq_service import chat_con_asistente, get_context_data
                            ctx = get_context_data()
                            respuesta = chat_con_asistente(groq_messages.copy(), ctx)
                            groq_messages.append({'role': 'assistant', 'content': respuesta})
                        except Exception as ex:
                            respuesta = f"⚠️ Error conectando con Groq: {str(ex)[:120]}\n\nVerifica que la API Key esté configurada en **Configuración → IA Sandoval**."
                        
                        # Remover indicador typing y agregar respuesta
                        chat_container.remove(typing_msg)
                        _add_message(chat_container, chat_history, 'assistant', respuesta)
                        
                        # Scroll al final
                        ui.run_javascript('var el = document.querySelector(".overflow-y-auto"); if(el) el.scrollTop = el.scrollHeight;')
                    
                    msg_input.on('keydown.enter', send_message)
                    ui.button(icon='send', on_click=send_message).props(
                        'unelevated round color=primary'
                    ).classes('shrink-0')
                
                # Agregar botones de sugerencias ahora que tenemos send_message
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
        
        # ── Nota de privacidad ──
        ui.label('🔒 Las conversaciones son privadas y no se comparten con el bot universitario Jarvis.').classes(
            'text-[10px] text-gray-300 text-center w-full mt-2'
        )


def _mensaje_bienvenida():
    """Mensaje inicial del asistente"""
    with ui.element('div').classes('flex gap-3 p-3 rounded-2xl mb-2').style('background:linear-gradient(135deg,#eff6ff,#dbeafe)'):
        with ui.element('div').classes('w-9 h-9 rounded-xl flex items-center justify-center shrink-0').style('background:linear-gradient(135deg,#274495,#1e3a8a)'):
            ui.icon('smart_toy', size='18px', color='white')
        with ui.column().classes('flex-1 gap-1'):
            ui.label('Asistente Sandoval').classes('text-xs font-black text-blue-700')
            ui.label(
                '¡Hola! Soy el Asistente IA de Mecánica Sandoval. 🔧\n\n'
                'Puedo ayudarte con:\n'
                '• Analizar el estado actual del taller\n'
                '• Revisar órdenes y clientes\n'
                '• Identificar stock crítico\n'
                '• Leer y procesar fotos de facturas 📸\n\n'
                '¿Qué necesitas saber hoy?'
            ).classes('text-sm text-blue-800 whitespace-pre-line leading-relaxed')
            ui.label(datetime.now().strftime('%H:%M')).classes('text-[10px] text-blue-400')


def _add_message(container, history: list, role: str, content: str, imagen_path: str = None):
    """Agrega un mensaje al chat"""
    is_user = role == 'user'
    hora = datetime.now().strftime('%H:%M')
    history.append({'role': role, 'content': content, 'time': hora})
    
    with container:
        with ui.element('div').classes(f'flex gap-3 mb-3 {"flex-row-reverse" if is_user else ""}'):
            # Avatar
            avatar_bg = 'linear-gradient(135deg,#274495,#1e3a8a)' if not is_user else 'linear-gradient(135deg,#10b981,#059669)'
            icon_name = 'smart_toy' if not is_user else 'person'
            with ui.element('div').classes('w-8 h-8 rounded-xl flex items-center justify-center shrink-0').style(f'background:{avatar_bg}'):
                ui.icon(icon_name, size='16px', color='white')
            
            # Burbuja de mensaje
            bubble_bg = '#ffffff' if not is_user else 'linear-gradient(135deg,#274495,#1e3a8a)'
            txt_color = '#1e293b' if not is_user else 'white'
            shadow = 'box-shadow:0 2px 8px rgba(0,0,0,0.08)' if not is_user else ''
            max_w = 'max-width:80%'
            
            with ui.column().classes('gap-1').style(max_w):
                with ui.element('div').classes('rounded-2xl px-4 py-3').style(
                    f'background:{bubble_bg}; {shadow}; {"border-radius:18px 18px 4px 18px" if not is_user else "border-radius:18px 18px 18px 4px"}'
                ):
                    if imagen_path:
                        ui.image(imagen_path).classes('w-48 h-32 object-cover rounded-xl mb-2')
                    ui.label(content).style(
                        f'color:{txt_color}; font-size:13px; line-height:1.6; white-space:pre-wrap; word-break:break-word'
                    )
                ui.label(hora).classes(f'text-[10px] text-gray-400 {"text-right" if is_user else ""}')


def _add_typing_indicator(container):
    """Agrega indicador de typing animado"""
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
    """Reinicia el chat"""
    history.clear()
    groq_messages.clear()
    container.clear()
    with container:
        _mensaje_bienvenida()
    theme.notify_info('Chat reiniciado')

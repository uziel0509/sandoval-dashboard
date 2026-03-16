"""
SANDOVAL Dashboard - Telegram Assistant Bot
"""
import os
import json
import logging
import asyncio
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from dotenv import load_dotenv
import sys

# Agregar la ruta base para poder importar utils y components
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.models import get_db, ItemInventario, Vehiculo, Cliente, Orden
from components.facturas import _save_factura, _agregar_items_a_inventario
from utils.groq_service import get_groq_client, FACTURA_PROMPT, get_context_data, analizar_intencion_cotizacion

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")

ALLOWED_USERS = [int(x.strip()) for x in os.getenv("ALLOWED_USERS", "").split(",") if x.strip()]

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if ALLOWED_USERS and user_id not in ALLOWED_USERS:
        await update.message.reply_text(f"🛑 Acceso denegado. Tu ID es: {user_id}. No estás en la lista blanca del Taller Sandoval.")
        return
        
    await update.message.reply_text(
        f"👋 ¡Hola! Soy el Asistente del Taller Sandoval.\n\n"
        f"🔑 Tu ID secreto de Telegram es: `{user_id}`\n(Pásamelo para blindar el bot a tu cuenta).\n\n"
        f"Puedes:\n"
        f"1️⃣ Preguntarme sobre el taller (inventario, repuestos, clientes).\n"
        f"2️⃣ Enviarme una foto de una factura para subirla al sistema web.\n"
        f"3️⃣ Enviarme una **NOTA DE VOZ** si no puedes escribir."
    )

async def _process_bot_message(user_text: str, update: Update, context: ContextTypes.DEFAULT_TYPE, processing_msg):
    try:
        # Analizar intención de cotización
        intencion = analizar_intencion_cotizacion(user_text)
        if intencion.get('is_cotizacion'):
            placa = str(intencion.get('placa', '')).upper()
            
            # Buscar dueño si la placa existe
            db = get_db()
            try:
                vehiculo = db.query(Vehiculo).filter_by(placa=placa).first()
                if vehiculo and vehiculo.cliente_id:
                    cliente = db.query(Cliente).filter_by(id=vehiculo.cliente_id).first()
                    if cliente:
                        # Auto-completar
                        intencion['cliente_nombre'] = f"{cliente.nombre} {cliente.apellidos or ''}".strip()
                        if not intencion.get('telefono') or intencion.get('telefono') == "":
                            intencion['telefono'] = cliente.telefono
            finally:
                db.close()
                
            # Guardamos la data
            context.user_data['pending_cotizacion'] = intencion
            
            # Calcula el total iterando los items
            total = sum(float(i.get('precio', 0)) * int(i.get('cantidad', 1)) for i in intencion.get('items', []))
            
            items_str = "\n".join([f"  - {i.get('nombre')} x{i.get('cantidad', 1)}: S/ {float(i.get('precio', 0))*int(i.get('cantidad', 1)):.2f}" for i in intencion.get('items', [])])
            if not items_str: items_str = "  (Ningún ítem detectado o con precio válido)"
            
            msg = (
                f"📝 **Cotización Generada por IA**\n\n"
                f"🚗 *Placa:* {intencion.get('placa', '')}\n"
                f"👤 *Cliente:* {intencion.get('cliente_nombre', '')}\n"
                f"📱 *Teléfono:* {intencion.get('telefono', '')}\n"
                f"🛣️ *Kilometraje:* {intencion.get('kilometraje', '')} km\n\n"
                f"**Servicios y Repuestos Detectados:**\n"
                f"{items_str}\n\n"
                f"💰 **Total Estimado:** S/ {total:.2f}\n\n"
                f"¿Es correcta esta cotización y deseas crearla oficialmente?"
            )
            
            keyboard = [
                [InlineKeyboardButton("✅ Confirmar, Crear y Generar PDF", callback_data='save_cotizacion')],
                [InlineKeyboardButton("❌ Cancelar", callback_data='cancel_cotizacion')]
            ]
            await processing_msg.edit_text(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
            return

        # ── DIRRETRICES ESTRICTAS DE SEGURIDAD Y CONTEXTO ──
        system_prompt = """
        Eres el asistente exclusivo del Taller Sandoval. Tu única función es ayudar con temas 
        relacionados a mecánica automotriz, inventario de repuestos, gestión de clientes, gastos 
        del taller y operaciones diarias. 
        
        REGLA DE ORO: Si el usuario te pregunta sobre la universidad, tareas académicas, historia, 
        matemáticas, o CUALQUIER TEMA que no tenga que ver directa y exclusivamente con el taller, 
        debes NEGARTÉ a responder cortésmente y recordarle que eres un asistente de taller automotriz.
        Responde de forma concisa, profesional y yendo directo al grano.
        """
        context_data = get_context_data()
        full_prompt = f"{system_prompt}\n\nCONTEXTO DEL TALLER:\n{context_data}"
        
        client = get_groq_client()
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": full_prompt},
                {"role": "user", "content": user_text}
            ],
            max_tokens=1000,
            temperature=0.3
        )
        reply = response.choices[0].message.content
        await processing_msg.edit_text(reply)
        
    except Exception as e:
        logger.error(f"Error AI: {e}", exc_info=True)
        await processing_msg.edit_text("❌ Hubo un error procesando el mensaje mediante IA.")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if ALLOWED_USERS and user_id not in ALLOWED_USERS:
        return
        
    user_text = update.message.text
    processing_msg = await update.message.reply_text("⏳ Consultando la base de datos del taller...")
    await _process_bot_message(user_text, update, context, processing_msg)

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if ALLOWED_USERS and user_id not in ALLOWED_USERS:
        return
        
    # Agarrar la versión de mayor resolución de la foto
    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    
    # Validar carpetas
    os.makedirs('static/facturas', exist_ok=True)
    fname = f"tg_img_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file.file_id}.jpg"
    fpath = os.path.join('static/facturas', fname)
    
    # Descargar la imagen de los servidores de Telegram a nuestro servidor
    await file.download_to_drive(fpath)
    context.user_data['last_invoice_path'] = fpath
    
    # Menú de botones
    keyboard = [
        [
            InlineKeyboardButton("🛒 Mercadería (Al Inventario)", callback_data='tipo_mercaderia'),
            InlineKeyboardButton("💸 Gasto (Contabilidad)", callback_data='tipo_gasto')
        ],
        [InlineKeyboardButton("❌ Cancelar", callback_data='cancelar_factura')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "📸 Factura recibida con éxito.\n*¿Qué tipo de registro es este?*", 
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if ALLOWED_USERS and user_id not in ALLOWED_USERS:
        return
        
    data = query.data
    
    if data == 'cancelar_factura' or data == 'discard_factura':
        context.user_data.pop('pending_factura', None)
        await query.edit_message_text("❌ Subida de recibo cancelada.")
        return
        
    if data == 'save_factura':
        factura_data = context.user_data.get('pending_factura')
        if not factura_data:
            await query.edit_message_text("⚠️ Sesión expirada. Vuelve a subir la foto.")
            return
            
        try:
            # Inyectar silenciosamente a SQLite de la página web
            factura_id = _save_factura(factura_data)
            
            # Si es mercadería, añadir también al stock disponible internamente
            if factura_data['tipo'] == 'mercaderia' and factura_data.get('items'):
                _agregar_items_a_inventario(factura_data['items'])
                
            res_msg = (
                f"✅ **¡Factura Registrada Exitosamente!**\n\n"
                f"🏢 *Proveedor:* {factura_data['proveedor']}\n"
                f"📄 *Nº Factura:* {factura_data['numero_factura']}\n"
                f"💰 *Total:* S/ {factura_data['total']}\n"
                f"📦 *Items detectados:* {len(factura_data['items'])}\n"
                f"📌 *Clasificación:* {factura_data['tipo'].upper()}\n\n"
                f"*(Ya está disponible en la página web)*"
            )
            await query.edit_message_text(res_msg, parse_mode='Markdown')
            context.user_data.pop('pending_factura', None)
        except Exception as e:
            logger.error(f"Error guardando factura telegram: {e}")
            await query.edit_message_text(f"❌ Falló el guardado. Error técnico: {str(e)}")
        return
        
    if data == 'cancel_cotizacion':
        context.user_data.pop('pending_cotizacion', None)
        await query.edit_message_text("❌ Cotización cancelada / descartada.")
        return
        
    if data == 'save_cotizacion':
        c_data = context.user_data.get('pending_cotizacion')
        if not c_data:
            await query.edit_message_text("⚠️ Sesión expirada. Vuelve a intentarlo.")
            return
            
        try:
            res_msg, pdf_path = _crear_cotizacion_desde_bot(c_data)
            await query.edit_message_text(res_msg, parse_mode='Markdown')
            
            # Enviar el Documento por Telegram
            if pdf_path and os.path.exists(pdf_path):
                with open(pdf_path, 'rb') as doc:
                    await context.bot.send_document(
                        chat_id=user_id, 
                        document=doc, 
                        filename=os.path.basename(pdf_path),
                        caption="📄 PDF listo para reenviar al cliente."
                    )
            context.user_data.pop('pending_cotizacion', None)
        except Exception as e:
            logger.error(f"Error creando cotización TG: {e}", exc_info=True)
            await query.edit_message_text(f"❌ Error interno al generar la cotización: {str(e)}")
        return
        
    fpath = context.user_data.get('last_invoice_path')
    if not fpath or not os.path.exists(fpath):
        await query.edit_message_text("⚠️ No se encontró la imagen en memoria. Vuelve a subirla.")
        return
        
    tipo = "mercaderia" if data == 'tipo_mercaderia' else "gasto"
    await query.edit_message_text(f"🤖 Analizando la imagen como *{tipo.upper()}* usando Llama-4 Vision... Espera un momento.", parse_mode="Markdown")
    
    try:
        client = get_groq_client()
        import base64
        with open(fpath, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode("utf-8")
            
        # Pasar por el OCR del LLM
        response = client.chat.completions.create(
            model="llama-3.2-90b-vision-preview",
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": FACTURA_PROMPT},
                    {"type": "image_url", "image_url": {
                        "url": f"data:image/jpeg;base64,{img_b64}"
                    }}
                ]
            }],
            max_tokens=2000,
            temperature=0.1,
        )
        
        raw = response.choices[0].message.content.strip()
        raw = raw.replace("```json", "").replace("```", "").strip()
        datos = json.loads(raw)
        
        # Estructurar la Data Final
        factura_data = {
            'tipo': tipo,
            'subtipo_gasto': '',
            'proveedor': datos.get('proveedor', 'Desconocido'),
            'ruc_proveedor': datos.get('ruc_proveedor', ''),
            'numero_factura': datos.get('numero_factura', 'S/N'),
            'fecha': datos.get('fecha', datetime.now().strftime('%d/%m/%Y')),
            'subtotal': datos.get('subtotal', 0),
            'igv': datos.get('igv', 0),
            'total': datos.get('total', 0),
            'imagen_path': f"{fpath}",
            'items': datos.get('items', []),
            'notas': 'Subida vía Telegram Bot Sandoval'
        }
        
        # Guardar temporalmente para confirmación
        context.user_data['pending_factura'] = factura_data
        
        # Generar mensaje de confirmación
        items_str = "\n".join([f"   - {i.get('cantidad', 1)}x {i.get('nombre', '...')[:25]} (S/ {i.get('total', 0)})" for i in factura_data['items'][:5]])
        if len(factura_data['items']) > 5:
            items_str += f"\n   ... y {len(factura_data['items']) - 5} ítems más"
            
        from components.facturas import _check_duplicate_factura
        is_duplicate = _check_duplicate_factura(factura_data['proveedor'], factura_data['numero_factura'])
        
        duplicate_warning = "⚠️ *¡ATENCIÓN: EL SISTEMA DETECTA QUE ESTA FACTURA YA FUE REGISTRADA ANTES!*\n\n" if is_duplicate else ""
        
        preview_msg = (
            f"{duplicate_warning}"
            f"🔍 **Vista Previa de la Factura ({tipo.upper()})**\n\n"
            f"🏢 *Proveedor:* {factura_data['proveedor']}\n"
            f"📄 *Nº Factura:* {factura_data['numero_factura']}\n"
            f"📅 *Fecha:* {factura_data['fecha']}\n"
            f"� *Subtotal:* S/ {factura_data['subtotal']}\n"
            f"� *IGV:* S/ {factura_data['igv']}\n"
            f"💰 *Total:* S/ {factura_data['total']}\n\n"
            f"� *Ítems detectados:*\n{items_str if items_str else '   (Ninguno o no legibles)'}\n\n"
            f"¿Los datos son correctos?"
        )
        
        keyboard = []
        if not is_duplicate:
            keyboard.append([InlineKeyboardButton("✅ Confirmar y Guardar", callback_data='save_factura')])
        else:
            keyboard.append([InlineKeyboardButton("⚠️ Guardar Doble de todas formas", callback_data='save_factura')])
        
        keyboard.append([InlineKeyboardButton("❌ Rechazar", callback_data='discard_factura')])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(preview_msg, reply_markup=reply_markup, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Error procesando factura telegram: {e}")
        await query.edit_message_text(f"❌ Falló la visión artificial. Error técnico: {str(e)}")

def _crear_cotizacion_desde_bot(data: dict):
    from sqlalchemy import text
    from utils.pdf_generator import generate_cotizacion
    from utils.models import Actividad
    db = get_db()
    try:
        # 1. Cliente
        cliente_id = None
        if data.get('cliente_nombre'):
            c = db.query(Cliente).filter(Cliente.nombre.like(f"%{data['cliente_nombre']}%")).first()
            if not c:
                c = Cliente(nombre=data['cliente_nombre'], telefono=data.get('telefono', ''), email="", tipo='Persona')
                db.add(c)
                db.commit()
                db.refresh(c)
            cliente_id = c.id
            
        # 2. Vehiculo
        placa = (data.get('placa') or '').upper().replace('-', '')
        if placa:
            v = db.query(Vehiculo).filter_by(placa=placa).first()
            if not v:
                v = Vehiculo(placa=placa, cliente_id=cliente_id, marca='Por Definir', modelo='-')
                db.add(v)
                db.commit()
            elif v and not v.cliente_id and cliente_id:
                v.cliente_id = cliente_id
                db.commit()
                
        # 3. Consecutivo
        res = db.execute(text("SELECT consecutivo FROM ordenes ORDER BY consecutivo DESC LIMIT 1")).fetchone()
        if res and res[0] and res[0].startswith('OS-'):
            ult = int(res[0].split('-')[1])
            consecutivo = f"OS-{ult+1:05d}"
        else:
            consecutivo = "OS-00001"
            
        # Procesar items para que todos aseguren precio/totales
        items_procesados = []
        for i in data.get('items', []):
            cant = int(i.get('cantidad', 1))
            precio = float(i.get('precio', 0))
            items_procesados.append({
                "nombre": i.get('nombre', 'Item sin nombre'),
                "cantidad": cant,
                "precio_unitario": precio,
                "total": cant * precio,
                "categoria": i.get('tipo', 'repuesto')
            })
            
        # 4. Creación
        orden = Orden(
            consecutivo=consecutivo,
            fecha=datetime.now().strftime('%Y-%m-%d %H:%M'),
            cliente_id=cliente_id,
            vehiculo_placa=placa if placa else None,
            motivo='Cotización Inteligente vía Telegram',
            estado='COTIZACIÓN',
            items_cotizacion=json.dumps(items_procesados),
            km=data.get('kilometraje', '')
        )
        db.add(orden)
        db.add(Actividad(accion=f"Cotización {consecutivo} creada vía Telegram Bot", modulo="ordenes"))
        db.commit()
        
        # 5. PDF
        pdf_path = generate_cotizacion(consecutivo)
        return f"✅ *Cotización {consecutivo} Generada Exitosamente* y guardada en tu sistema web.", pdf_path
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if ALLOWED_USERS and user_id not in ALLOWED_USERS:
        return
        
    processing_msg = await update.message.reply_text("🎙️ Escuchando audio...")
    
    try:
        # Descargar el audio de Telegram
        voice = update.message.voice or update.message.audio
        file = await context.bot.get_file(voice.file_id)
        
        os.makedirs('static/audios', exist_ok=True)
        fname = f"tg_audio_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file.file_id}.ogg"
        fpath = os.path.join('static/audios', fname)
        await file.download_to_drive(fpath)
        
        # Procesar con Groq Whisper
        client = get_groq_client()
        with open(fpath, "rb") as file_to_transcribe:
            transcription = client.audio.transcriptions.create(
                file=(fpath, file_to_transcribe.read()),
                model="whisper-large-v3",
                prompt="El usuario habla sobre mecánica automotriz, clientes, repuestos e inventario.",
                response_format="json",
                language="es",
            )
            
        user_text = transcription.text.strip()
        if not user_text:
            await processing_msg.edit_text("❌ No se pudo entender el audio o está vacío.")
            return

        await processing_msg.edit_text(f"🗣️ *Escuché:* _{user_text}_\n\n⏳ Analizando...", parse_mode="Markdown")
        await _process_bot_message(user_text, update, context, processing_msg)
        
    except Exception as e:
        logger.error(f"Error AI Audio: {e}")
        await processing_msg.edit_text("❌ Hubo un error entendiendo tu nota de voz.")

def run_telegram_bot():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice))
    app.add_handler(CallbackQueryHandler(button_callback))
    
    logger.info("🤖 Motores del Bot de Telegram Iniciados...")
    app.run_polling()

if __name__ == '__main__':
    run_telegram_bot()

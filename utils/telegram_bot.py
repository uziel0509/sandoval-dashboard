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

from utils.models import get_db, ItemInventario
from components.facturas import _save_factura, _agregar_items_a_inventario
from utils.groq_service import get_groq_client, FACTURA_PROMPT, get_context_data

load_dotenv()

TELEGRAM_TOKEN = "8680913184:AAHMAU3GaUwXZLgxnIniR7GTAtXlRulSp9E"

# Aquí pondremos los IDs de ustedes dos para que nadie más pueda usarlo.
# Por ahora está vacío para que cuando le escribas tu primer "Hola", te diga tu ID
# y luego me lo pasas para agregarlo a esta lista fuerte de seguridad.
ALLOWED_USERS = []

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
        f"2️⃣ Enviarme una foto de una factura para subirla al sistema web."
    )

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if ALLOWED_USERS and user_id not in ALLOWED_USERS:
        return
        
    user_text = update.message.text
    
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
    
    # Obtenemos la información de tu base de datos (inventario, órdenes, clientes)
    context_data = get_context_data()
    full_prompt = f"{system_prompt}\n\nCONTEXTO DEL TALLER:\n{context_data}"
    
    processing_msg = await update.message.reply_text("⏳ Consultando la base de datos del taller...")
    
    try:
        client = get_groq_client()
        response = client.chat.completions.create(
            model="meta-llama/llama-4-scout-17b-16e-instruct", # Modelo inteligente de Groq
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
        logger.error(f"Error AI: {e}")
        await processing_msg.edit_text("❌ Hubo un error de conexión con el cerebro del taller.")

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
    
    if data == 'cancelar_factura':
        await query.edit_message_text("❌ Subida de recibo cancelada.")
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
            model="meta-llama/llama-4-scout-17b-16e-instruct",
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
            'numero_factura': datos.get('numero_factura', 'S/N'),
            'fecha': datos.get('fecha', datetime.now().strftime('%d/%m/%Y')),
            'subtotal': datos.get('subtotal', 0),
            'igv': datos.get('igv', 0),
            'total': datos.get('total', 0),
            'imagen_path': f"{fpath}",
            'items': datos.get('items', []),
            'notas': 'Subida vía Telegram Bot Sandoval'
        }
        
        # Inyectar silenciosamente a SQLite de la página web
        factura_id = _save_factura(factura_data)
        
        # Si es mercadería, añadir también al stock disponible internamente
        if tipo == 'mercaderia' and datos.get('items'):
            _agregar_items_a_inventario(datos['items'])
            
        res_msg = (
            f"✅ **¡Factura Registrada Exitosamente!**\n\n"
            f"🏢 *Proveedor:* {factura_data['proveedor']}\n"
            f"📄 *Nº Factura:* {factura_data['numero_factura']}\n"
            f"💰 *Total:* S/ {factura_data['total']}\n"
            f"📦 *Items detectados:* {len(factura_data['items'])}\n"
            f"📌 *Clasificación:* {tipo.upper()}\n\n"
            f"*(Ya está disponible en la página web)*"
        )
        await query.edit_message_text(res_msg, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Error procesando factura telegram: {e}")
        await query.edit_message_text(f"❌ Falló la visión artificial. Error técnico: {str(e)}")

def run_telegram_bot():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(CallbackQueryHandler(button_callback))
    
    logger.info("🤖 Motores del Bot de Telegram Iniciados...")
    app.run_polling()

if __name__ == '__main__':
    run_telegram_bot()

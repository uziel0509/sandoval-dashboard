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
from utils.agent import run_agent
from utils.groq_service import get_groq_client, FACTURA_PROMPT, get_context_data, analizar_intencion_cotizacion, analizar_edicion_cotizacion, analizar_intencion_credito

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

# ═══════════════════════════════════════════════════════════════════
#  CRÉDITOS / FIADO - Funciones auxiliares del bot
# ═══════════════════════════════════════════════════════════════════

def _buscar_creditos_por_nombre(nombre: str) -> list:
    """Busca créditos activos por nombre de cliente"""
    from sqlalchemy import text
    db = get_db()
    try:
        rows = db.execute(text("""
            SELECT * FROM creditos
            WHERE LOWER(cliente_nombre) LIKE :nombre
            AND estado IN ('PENDIENTE', 'PARCIAL', 'VENCIDO')
            ORDER BY fecha_venta DESC
        """), {'nombre': f'%{nombre.lower()}%'}).fetchall()
        return [dict(r._mapping) for r in rows]
    except Exception:
        return []
    finally:
        db.close()


def _get_todos_creditos_pendientes() -> list:
    """Obtiene todos los créditos pendientes"""
    from sqlalchemy import text
    db = get_db()
    try:
        rows = db.execute(text("""
            SELECT * FROM creditos
            WHERE estado IN ('PENDIENTE', 'PARCIAL', 'VENCIDO')
            ORDER BY fecha_venta DESC LIMIT 20
        """)).fetchall()
        return [dict(r._mapping) for r in rows]
    except Exception:
        return []
    finally:
        db.close()


def _registrar_abono_bot(credito_id: int, monto: float, nota: str) -> bool:
    """Registra un abono y actualiza el estado del crédito"""
    from sqlalchemy import text
    from datetime import date
    db = get_db()
    try:
        db.execute(text("""
            INSERT INTO abonos_credito (credito_id, monto, nota, fecha)
            VALUES (:cid, :monto, :nota, :fecha)
        """), {'cid': credito_id, 'monto': monto, 'nota': nota, 'fecha': datetime.now().isoformat()})
        db.commit()
        # Recalcular estado
        cred = db.execute(text("SELECT * FROM creditos WHERE id=:id"), {'id': credito_id}).fetchone()
        if cred:
            cred = dict(cred._mapping)
            ab = db.execute(text("SELECT COALESCE(SUM(monto),0) as t FROM abonos_credito WHERE credito_id=:cid"), {'cid': credito_id}).fetchone()
            total_ab = float(ab._mapping['t'])
            pendiente = round(float(cred['total']) - total_ab, 2)
            vencido = cred.get('fecha_amortizacion','') and cred.get('fecha_amortizacion','') < date.today().isoformat()
            if pendiente <= 0: estado = 'PAGADO'
            elif vencido: estado = 'VENCIDO'
            elif total_ab > 0: estado = 'PARCIAL'
            else: estado = 'PENDIENTE'
            db.execute(text("UPDATE creditos SET pendiente=:p, estado=:e WHERE id=:id"),
                {'p': max(pendiente, 0), 'e': estado, 'id': credito_id})
            db.commit()
        return True
    except Exception as e:
        db.rollback()
        logger.error(f"Error registrar_abono_bot: {e}")
        return False
    finally:
        db.close()


def _crear_credito_bot(data: dict) -> bool:
    """Crea un crédito desde el bot"""
    from sqlalchemy import text
    db = get_db()
    try:
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS creditos (
                id INTEGER PRIMARY KEY AUTOINCREMENT, cliente_nombre TEXT NOT NULL,
                telefono TEXT DEFAULT '', descripcion TEXT DEFAULT '',
                items_json TEXT DEFAULT '[]', total REAL DEFAULT 0,
                pendiente REAL DEFAULT 0, estado TEXT DEFAULT 'PENDIENTE',
                nota TEXT DEFAULT '', fecha_venta TEXT DEFAULT '',
                fecha_amortizacion TEXT DEFAULT '', creado_por TEXT DEFAULT '')
        """))
        import json as _json
        items = data.get('items', [])
        desc  = data.get('descripcion', '')
        if not desc and items:
            desc = ', '.join(f"{it.get('cantidad',1)}x {it['nombre']} S/{float(it.get('precio',0)):.2f}" for it in items)
        db.execute(text("""
            INSERT INTO creditos
            (cliente_nombre, telefono, descripcion, items_json, total, pendiente, estado, nota, fecha_venta, creado_por)
            VALUES (:cn, :tel, :desc, :items, :total, :total, 'PENDIENTE', :nota, :fecha, 'Bot Telegram')
        """), {
            'cn':    data.get('cliente_nombre', ''),
            'tel':   data.get('telefono', ''),
            'desc':  desc,
            'items': _json.dumps(items),
            'total': float(data.get('total', 0)),
            'nota':  data.get('nota', ''),
            'fecha': datetime.now().isoformat()
        })
        db.commit()
        return True
    except Exception as e:
        db.rollback()
        logger.error(f"Error crear_credito_bot: {e}")
        return False
    finally:
        db.close()


def _formato_credito(c: dict) -> str:
    """Formatea un crédito para mostrar en Telegram"""
    estado_emoji = {'PENDIENTE': '🟡', 'PARCIAL': '🔵', 'PAGADO': '✅', 'VENCIDO': '🔴'}.get(c.get('estado',''), '⚪')
    return (
        f"{estado_emoji} *{c.get('cliente_nombre','—')}*\n"
        f"   📱 {c.get('telefono','—')}\n"
        f"   💰 Total: S/ {float(c.get('total',0)):.2f} | Pendiente: *S/ {float(c.get('pendiente',0)):.2f}*\n"
        f"   📦 {str(c.get('descripcion',''))[:60]}\n"
        f"   🆔 ID: `{c.get('id')}`"
    )


async def _handle_credito_intent(intencion: dict, update: Update, context: ContextTypes.DEFAULT_TYPE, processing_msg):
    """Maneja todas las intenciones relacionadas con créditos desde el bot"""

    tipo = intencion.get('intencion', 'ninguna')

    # ── VER CRÉDITOS PENDIENTES ──────────────────────────────────────────
    if tipo == 'ver_creditos':
        creditos = _get_todos_creditos_pendientes()
        if not creditos:
            await processing_msg.edit_text("✅ No hay créditos pendientes registrados.")
            return True
        texto = "📋 *Créditos Pendientes*\n\n"
        for c in creditos[:10]:
            texto += _formato_credito(c) + "\n\n"
        texto += f"_Total: {len(creditos)} crédito(s) activo(s)_"
        await processing_msg.edit_text(texto, parse_mode='Markdown')
        return True

    # ── CREAR CRÉDITO ────────────────────────────────────────────────────
    if tipo == 'crear_credito':
        nombre = intencion.get('cliente_nombre', '').strip()
        items  = intencion.get('items', [])
        desc   = intencion.get('descripcion', '').strip()

        if not nombre:
            await processing_msg.edit_text(
                "⚠️ No pude detectar el nombre del cliente.\n\n"
                "Dime así: *'Pedro Quispe se llevó 2 filtros a 25 soles cada uno, al fiado'*",
                parse_mode='Markdown')
            return True

        # Si hay items con precio, calcular total desde items
        if items:
            for it in items:
                # Si no tiene precio, buscar en inventario
                if float(it.get('precio', 0)) == 0:
                    try:
                        from utils.models import ItemInventario
                        db2 = get_db()
                        try:
                            prod = db2.query(ItemInventario).filter(
                                ItemInventario.nombre.ilike(f"%{it['nombre']}%")
                            ).first()
                            if prod:
                                it['precio'] = float(prod.precio)
                                it['item_id'] = prod.codigo
                        finally:
                            db2.close()
                    except Exception:
                        pass
            total = sum(float(it.get('precio',0)) * int(it.get('cantidad',1)) for it in items)
            intencion['total'] = total
            intencion['items'] = items
        else:
            total = float(intencion.get('total', 0))

        if total <= 0 and not items:
            await processing_msg.edit_text(
                "⚠️ No detecté el monto ni los productos.\n\n"
                "Dime así: *'Mario Flores se llevó 2 filtros a 25 soles y 1 bujía a 15 soles, al fiado'*",
                parse_mode='Markdown')
            return True

        # Construir mensaje con detalle de items y precios
        items_txt = ""
        if items:
            for it in items:
                precio = float(it.get('precio', 0))
                cant   = int(it.get('cantidad', 1))
                subtot = precio * cant
                precio_txt = f"S/ {precio:.2f} c/u" if precio > 0 else "*(precio pendiente)*"
                items_txt += f"  • {cant}x {it['nombre']} — {precio_txt} = S/ {subtot:.2f}\n"
        else:
            items_txt = f"  • {desc or 'Sin detalle'}\n"

        context.user_data['pending_credito'] = intencion
        msg = (
            f"💳 *Nuevo Crédito / Fiado*\n\n"
            f"👤 *Cliente:* {nombre}\n"
            f"📱 *Teléfono:* {intencion.get('telefono','—') or '—'}\n\n"
            f"📦 *Productos:*\n{items_txt}\n"
            f"💰 *Total: S/ {total:.2f}*\n"
            f"📝 *Nota:* {intencion.get('nota','—') or '—'}\n\n"
            f"¿Confirmas registrar este crédito?\n"
            f"_Si algún precio está mal, cancela y dicta de nuevo con el precio correcto_"
        )
        keyboard = [
            [InlineKeyboardButton("✅ Confirmar Crédito", callback_data='confirmar_credito')],
            [InlineKeyboardButton("❌ Cancelar", callback_data='cancelar_credito')]
        ]
        await processing_msg.edit_text(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        return True

    # ── REGISTRAR ABONO ──────────────────────────────────────────────────
    if tipo == 'registrar_abono':
        nombre = intencion.get('cliente_nombre', '').strip()
        monto = float(intencion.get('monto', 0))

        if not nombre or monto <= 0:
            await processing_msg.edit_text(
                "⚠️ No pude detectar bien el abono.\n\n"
                "Dime así: *'Mario Flores abonó 40 soles, pagó con yape'*",
                parse_mode='Markdown')
            return True

        creditos = _buscar_creditos_por_nombre(nombre)

        if not creditos:
            await processing_msg.edit_text(
                f"❌ No encontré créditos activos para *{nombre}*.\n\n"
                f"Verifica el nombre o consulta con: _'ver créditos pendientes'_",
                parse_mode='Markdown')
            return True

        if len(creditos) == 1:
            # Solo uno — confirmar directo
            c = creditos[0]
            context.user_data['pending_abono'] = {
                'credito_id': c['id'],
                'monto': monto,
                'nota': intencion.get('metodo_pago', '') or intencion.get('nota', ''),
                'cliente': c['cliente_nombre'],
                'pendiente_actual': float(c['pendiente'])
            }
            msg = (
                f"💰 *Registrar Abono*\n\n"
                f"👤 *Cliente:* {c['cliente_nombre']}\n"
                f"📱 *Tel:* {c.get('telefono','—')}\n"
                f"💸 *Pendiente actual:* S/ {float(c['pendiente']):.2f}\n"
                f"✅ *Abono a registrar:* S/ {monto:.2f}\n"
                f"💳 *Método:* {intencion.get('metodo_pago','—') or '—'}\n"
                f"📊 *Nuevo pendiente:* S/ {max(0, float(c['pendiente'])-monto):.2f}\n\n"
                f"¿Confirmas el abono?"
            )
            keyboard = [
                [InlineKeyboardButton("✅ Confirmar Abono", callback_data='confirmar_abono')],
                [InlineKeyboardButton("❌ Cancelar", callback_data='cancelar_abono')]
            ]
            await processing_msg.edit_text(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        else:
            # Varios clientes con ese nombre — mostrar lista para elegir
            context.user_data['abono_pendiente_datos'] = {'monto': monto, 'intencion': intencion}
            texto = f"🔍 Encontré *{len(creditos)}* créditos para *{nombre}*.\nElige cuál:\n\n"
            keyboard = []
            for c in creditos[:5]:
                texto += f"🆔 `{c['id']}` — {c['cliente_nombre']} | Debe: S/ {float(c['pendiente']):.2f}\n"
                keyboard.append([InlineKeyboardButton(
                    f"#{c['id']} {c['cliente_nombre']} — S/ {float(c['pendiente']):.2f}",
                    callback_data=f"sel_credito_{c['id']}"
                )])
            keyboard.append([InlineKeyboardButton("❌ Cancelar", callback_data='cancelar_abono')])
            await processing_msg.edit_text(texto, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        return True

    return False


async def _handle_credito_callbacks(data: str, query, context) -> bool:
    """Maneja los callbacks de créditos en button_callback"""

    # ── CONFIRMAR CRÉDITO ────────────────────────────────────────────
    if data == 'confirmar_credito':
        cred_data = context.user_data.pop('pending_credito', None)
        if not cred_data:
            await query.edit_message_text("⚠️ Sesión expirada. Vuelve a dictar el crédito.")
            return True
        ok = _crear_credito_bot(cred_data)
        if ok:
            await query.edit_message_text(
                f"✅ *Crédito registrado correctamente*\n\n"
                f"👤 {cred_data.get('cliente_nombre')}\n"
                f"💰 S/ {float(cred_data.get('total',0)):.2f} pendiente\n\n"
                f"_Puedes ver todos los créditos en el dashboard o preguntando 'créditos pendientes'_",
                parse_mode='Markdown')
        else:
            await query.edit_message_text("❌ Error al guardar el crédito. Intenta de nuevo.")
        return True

    # ── CANCELAR CRÉDITO ─────────────────────────────────────────────
    if data == 'cancelar_credito':
        context.user_data.pop('pending_credito', None)
        await query.edit_message_text("❌ Crédito cancelado.")
        return True

    # ── CONFIRMAR ABONO ──────────────────────────────────────────────
    if data == 'confirmar_abono':
        abono = context.user_data.pop('pending_abono', None)
        if not abono:
            await query.edit_message_text("⚠️ Sesión expirada. Vuelve a registrar el abono.")
            return True
        nota = abono.get('nota', '') or ''
        ok = _registrar_abono_bot(abono['credito_id'], abono['monto'], nota)
        if ok:
            nuevo_pendiente = max(0, abono['pendiente_actual'] - abono['monto'])
            estado_msg = "✅ *¡Crédito PAGADO completamente!*" if nuevo_pendiente <= 0 else f"📊 Nuevo pendiente: *S/ {nuevo_pendiente:.2f}*"
            await query.edit_message_text(
                f"✅ *Abono registrado*\n\n"
                f"👤 {abono['cliente']}\n"
                f"💰 Abono: S/ {abono['monto']:.2f}\n"
                f"💳 Método: {nota or '—'}\n"
                f"{estado_msg}",
                parse_mode='Markdown')
        else:
            await query.edit_message_text("❌ Error al registrar el abono. Intenta de nuevo.")
        return True

    # ── CANCELAR ABONO ───────────────────────────────────────────────
    if data == 'cancelar_abono':
        context.user_data.pop('pending_abono', None)
        context.user_data.pop('abono_pendiente_datos', None)
        await query.edit_message_text("❌ Abono cancelado.")
        return True

    # ── SELECCIONAR CRÉDITO cuando hay varios con mismo nombre ────────
    if data.startswith('sel_credito_'):
        credito_id = int(data.replace('sel_credito_', ''))
        datos = context.user_data.pop('abono_pendiente_datos', None)
        if not datos:
            await query.edit_message_text("⚠️ Sesión expirada.")
            return True
        from sqlalchemy import text as sqlt
        db = get_db()
        try:
            cred = db.execute(sqlt("SELECT * FROM creditos WHERE id=:id"), {'id': credito_id}).fetchone()
            if not cred:
                await query.edit_message_text("❌ Crédito no encontrado.")
                return True
            cred = dict(cred._mapping)
        finally:
            db.close()
        monto = float(datos['monto'])
        intencion = datos['intencion']
        context.user_data['pending_abono'] = {
            'credito_id': credito_id,
            'monto': monto,
            'nota': intencion.get('metodo_pago','') or intencion.get('nota',''),
            'cliente': cred['cliente_nombre'],
            'pendiente_actual': float(cred['pendiente'])
        }
        msg = (
            f"💰 *Confirmar Abono*\n\n"
            f"👤 *Cliente:* {cred['cliente_nombre']}\n"
            f"💸 *Pendiente actual:* S/ {float(cred['pendiente']):.2f}\n"
            f"✅ *Abono:* S/ {monto:.2f}\n"
            f"💳 *Método:* {intencion.get('metodo_pago','—') or '—'}\n"
            f"📊 *Nuevo pendiente:* S/ {max(0, float(cred['pendiente'])-monto):.2f}\n\n"
            f"¿Confirmas?"
        )
        keyboard = [
            [InlineKeyboardButton("✅ Confirmar Abono", callback_data='confirmar_abono')],
            [InlineKeyboardButton("❌ Cancelar", callback_data='cancelar_abono')]
        ]
        await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        return True

    return False


async def _process_bot_message(user_text: str, update, context, processing_msg, foto_path=None):
    try:
        historial = context.user_data.get('agent_historial', [])
        respuesta = await run_agent(user_text, foto_path=foto_path, historial=historial)
        historial.append({'role': 'user', 'content': user_text})
        historial.append({'role': 'assistant', 'content': respuesta})
        context.user_data['agent_historial'] = historial[-20:]

        # Detectar si la respuesta incluye un PDF para enviar
        import json as _json, os as _os
        pdf_enviado = False
        try:
            # El agente puede devolver JSON con pdf_path
            if '"pdf_path"' in respuesta:
                data = _json.loads(respuesta)
                pdf_path = data.get('pdf_path')
                if pdf_path and _os.path.exists(pdf_path):
                    numero = data.get('numero', '')
                    cliente = data.get('cliente', '')
                    caption = f"📄 PDF {numero} - {cliente}"
                    await context.bot.send_document(
                        chat_id=update.effective_chat.id,
                        document=open(pdf_path, 'rb'),
                        filename=_os.path.basename(pdf_path),
                        caption=caption
                    )
                    try: await processing_msg.delete()
                    except: pass
                    pdf_enviado = True
                elif data.get('error'):
                    await processing_msg.edit_text(f"❌ {data['error']}")
                    pdf_enviado = True
        except Exception:
            pass

        if not pdf_enviado:
            if len(respuesta) > 4000:
                for i in range(0, len(respuesta), 4000):
                    await update.message.reply_text(respuesta[i:i+4000])
                try: await processing_msg.delete()
                except: pass
            else:
                await processing_msg.edit_text(respuesta)
    except Exception as e:
        logger.error(f'Error agente: {e}', exc_info=True)
        try: await processing_msg.edit_text(f'Error: {str(e)[:200]}')
        except: pass

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

    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    caption = (update.message.caption or '').strip().lower()

    # Descargar foto
    os.makedirs('/var/www/sandoval/static/evidencia/temp', exist_ok=True)
    fname = f"tg_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file.file_id}.jpg"

    # Decidir si es EVIDENCIA DE ORDEN o FACTURA
    palabras_orden = ['orden', 'os-', 'evidencia', 'foto', 'placa', 'vehiculo',
                      'vehículo', 'trabajo', 'reparacion', 'reparación', 'entrega',
                      'listo', 'terminado', 'avanzar', 'fase', 'subir']
    es_evidencia = any(p in caption for p in palabras_orden)

    # Si tiene caption con placa (formato ABC-123 o ABC123)
    import re
    tiene_placa = bool(re.search(r'[A-Za-z]{3}[-\s]?\d{3,4}', caption))
    if tiene_placa:
        es_evidencia = True

    if es_evidencia:
        # Guardar en carpeta de evidencias
        fpath = f'/var/www/sandoval/static/evidencia/temp/{fname}'
        await file.download_to_drive(fpath)
        context.user_data['last_photo_path'] = fpath

        # Pasar al agente con el caption como texto
        processing_msg = await update.message.reply_text('⏳ Procesando foto...')
        user_text = update.message.caption or 'El usuario mandó una foto de evidencia de una orden.'
        await _process_bot_message(user_text, update, context, processing_msg, foto_path=fpath)
    else:
        # Sin caption claro: preguntar qué es la foto
        # Guardar en temp primero
        os.makedirs('/var/www/sandoval/static/evidencia/temp', exist_ok=True)
        fpath_temp = f'/var/www/sandoval/static/evidencia/temp/{fname}'
        await file.download_to_drive(fpath_temp)
        context.user_data['last_photo_path'] = fpath_temp
        context.user_data['last_invoice_path'] = fpath_temp

        keyboard = [
            [
                InlineKeyboardButton("📋 Evidencia de Orden", callback_data='foto_evidencia'),
                InlineKeyboardButton("🛒 Factura Mercadería", callback_data='tipo_mercaderia'),
            ],
            [
                InlineKeyboardButton("💸 Gasto/Factura", callback_data='tipo_gasto'),
                InlineKeyboardButton("❌ Cancelar", callback_data='cancelar_factura'),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "📸 Foto recibida. *¿Qué es esta foto?*\n\n"
            "💡 Tip: Si mandas la foto con el caption de la placa o número de orden, el bot la procesa automáticamente.",
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

    # ── Créditos / Fiado ──
    credito_handled = await _handle_credito_callbacks(data, query, context)
    if credito_handled:
        return

    # ── Cotización: cancelar ──
    if data == 'cancelar_cotizacion':
        context.user_data.pop('pending_cotizacion', None)
        context.user_data.pop('cotizacion_activa', None)
        await query.edit_message_text("❌ Cotización cancelada / descartada.")
        return

    # ── Cotización: confirmar cambios de edición (re-confirmar) ──
    if data == 'confirmar_cotizacion':
        cot_data = context.user_data.get('pending_cotizacion')
        if not cot_data:
            await query.edit_message_text("⚠️ Sesión expirada. Vuelve a dictar la cotización.")
            return
        # Continuar al bloque confirmar_cotizacion_ok
        data = 'confirmar_cotizacion_ok'

    if data == 'confirmar_cotizacion_ok':
        cot_data = context.user_data.get('pending_cotizacion')
        if not cot_data:
            await query.edit_message_text("⚠️ Sesión expirada. Vuelve a dictar la cotización.")
            return
        try:
            res_msg, pdf_path = _crear_cotizacion_desde_bot(cot_data)
            context.user_data.pop('pending_cotizacion', None)
            if pdf_path and os.path.exists(pdf_path):
                await context.bot.send_document(
                    chat_id=update.effective_chat.id,
                    document=open(pdf_path, 'rb'),
                    caption=res_msg,
                    parse_mode='Markdown'
                )
                await query.edit_message_text("📄 PDF listo para reenviar al cliente.")
            else:
                await query.edit_message_text(res_msg, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Error creando cotización TG: {e}", exc_info=True)
            await query.edit_message_text(f"❌ Error interno al generar la cotización: {str(e)}")
        return

    if data == 'foto_evidencia':
        fpath = context.user_data.get('last_photo_path')
        if not fpath:
            await query.edit_message_text("⚠️ Foto no encontrada. Vuelve a enviarla.")
            return
        await query.edit_message_text("⏳ Procesando foto como evidencia de orden...")
        await _process_bot_message(
            "El usuario mandó una foto de evidencia de una orden o vehículo. Busca la orden activa más reciente y sube esta foto como evidencia.",
            update, context, query.message, foto_path=fpath
        )
        return

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
    from utils.models import Cotizacion, CotizacionItem, log_actividad
    db = get_db()
    try:
        # Buscar cliente SOLO por placa, nunca crear cliente nuevo
        cliente_id = None
        nombre_cotizacion = data.get('cliente_nombre', 'Cliente sin registrar')
        placa_busqueda = (data.get('placa') or '').upper().replace('-', '').replace(' ', '')
        if placa_busqueda:
            v_existente = db.query(Vehiculo).filter_by(placa=placa_busqueda).first()
            if v_existente and v_existente.cliente_id:
                cliente_id = v_existente.cliente_id
                c = db.query(Cliente).filter_by(id=cliente_id).first()
                if c:
                    nombre_cotizacion = f"{c.nombre} {c.apellidos or ''}".strip()

        # Generar número de cotización
        hoy = datetime.now().strftime('%Y%m')
        count = db.query(Cotizacion).filter(Cotizacion.numero.like(f'COT-{hoy}%')).count()
        numero = f'COT-{hoy}-{count + 1:04d}'

        # Calcular total
        items = data.get('items', [])
        total = sum(int(i.get('cantidad',1)) * float(i.get('precio',0)) for i in items)

        # Crear cotización en tabla Cotizacion (NO en Orden)
        cot = Cotizacion(
            numero=numero,
            nombre_cliente=nombre_cotizacion,
            cliente_id=cliente_id,
            nota=f"Placa: {placa_busqueda}" if placa_busqueda else '',
            total=total,
            estado='PENDIENTE',
            creado_por='Jarvis (Telegram)',
        )
        db.add(cot)
        db.flush()

        for i in items:
            qty = int(i.get('cantidad', 1))
            price = float(i.get('precio', 0))
            db.add(CotizacionItem(
                cotizacion_id=cot.id,
                descripcion=i.get('nombre', ''),
                tipo=i.get('tipo', 'repuesto'),
                cantidad=qty,
                precio_unitario=price,
                subtotal=qty * price,
            ))

        db.commit()
        log_actividad(f'Cotización {numero} creada vía Telegram', 'cotizaciones', f'Cliente: {nombre_cotizacion}')

        # Generar PDF
        import os
        os.makedirs('/var/www/sandoval/pdfs', exist_ok=True)
        pdf_path = None
        try:
            from utils.pdf_cotizacion import generar_pdf_cotizacion
            pdf_path = generar_pdf_cotizacion(cot.id)
        except Exception as e:
            print(f"[BOT] Error PDF: {e}")

        return f"✅ *Cotización {numero}* creada\n👤 Cliente: {nombre_cotizacion}\n💰 Total: S/ {total:.2f}\n📋 Ya aparece en el dashboard.", pdf_path

    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()

def _crear_cotizacion_desde_bot_OLD(data: dict):
    # Versión legacy - NO usar
    from sqlalchemy import text
    from utils.pdf_generator import generate_cotizacion
    from utils.models import Actividad
    db = get_db()
    try:
        cliente_id = None
        nombre_cotizacion = data.get('cliente_nombre', 'Cliente sin registrar')
        placa_busqueda = (data.get('placa') or '').upper().replace('-', '').replace(' ', '')
        if placa_busqueda:
            v_existente = db.query(Vehiculo).filter_by(placa=placa_busqueda).first()
            if v_existente and v_existente.cliente_id:
                cliente_id = v_existente.cliente_id
                c = db.query(Cliente).filter_by(id=cliente_id).first()
                if c:
                    nombre_cotizacion = f"{c.nombre} {c.apellidos or ''}".strip()
        # Si no encontró por placa, usar el nombre que dio sin crear nada en DB
            
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
        # Generar PDF con los argumentos correctos
        order_dict = {
            'consecutivo': consecutivo,
            'km': data.get('kilometraje', ''),
            'motivo': 'Cotización vía Telegram',
        }
        client_dict = {
            'nombre': nombre_cotizacion,
            'apellidos': '',
            'id': str(cliente_id) if cliente_id else '',
            'telefono': data.get('telefono', ''),
        }
        vehicle_dict = {
            'placa': placa if placa else '',
            'marca': '',
            'modelo': '',
        }
        import os
        os.makedirs('/var/www/sandoval/pdfs', exist_ok=True)
        pdf_path = f'/var/www/sandoval/pdfs/{consecutivo}.pdf'
        generate_cotizacion(order_dict, client_dict, vehicle_dict, items_procesados, pdf_path)
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

async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja videos enviados al bot - los trata como evidencia de órdenes"""
    user_id = update.effective_user.id
    if ALLOWED_USERS and user_id not in ALLOWED_USERS:
        return

    # Obtener el video (puede ser video normal o video_note = circulito)
    video = update.message.video or update.message.video_note
    if not video:
        return

    caption = (update.message.caption or '').strip()
    processing_msg = await update.message.reply_text('⏳ Procesando video...')

    try:
        file = await context.bot.get_file(video.file_id)
        os.makedirs('/var/www/sandoval/static/evidencia/temp', exist_ok=True)
        fname = f"tg_video_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{video.file_id}.mp4"
        fpath = f'/var/www/sandoval/static/evidencia/temp/{fname}'
        await file.download_to_drive(fpath)
        context.user_data['last_photo_path'] = fpath

        user_text = caption or 'El usuario mandó un video de evidencia de una orden o vehículo.'
        await _process_bot_message(user_text, update, context, processing_msg, foto_path=fpath)

    except Exception as e:
        logger.error(f"Error handle_video: {e}", exc_info=True)
        await processing_msg.edit_text(f"❌ Error procesando el video: {e}")


def run_telegram_bot():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.VIDEO | filters.VIDEO_NOTE, handle_video))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice))
    app.add_handler(CallbackQueryHandler(button_callback))
    
    logger.info("🤖 Motores del Bot de Telegram Iniciados...")
    app.run_polling()

if __name__ == '__main__':
    run_telegram_bot()

"""
SANDOVAL - Agente IA Autónomo
Detecta la intención del mensaje y ejecuta la acción correspondiente
en el sistema sin necesidad de programar cada caso manualmente.

Flujo:
  handle_text → run_agent → detectar_intencion → ejecutar_accion
                                ↓ (si no reconoce)
                           chat_con_asistente (responde con datos reales del taller)
"""
import logging
import json
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# ── Prompt maestro de detección de intenciones ──────────────────────────────
_INTENT_PROMPT = """Eres el cerebro del bot del Taller Mecánico Sandoval (Perú).
Analiza el mensaje y devuelve ÚNICAMENTE un JSON válido con la intención detectada.

INTENCIONES:

"cotizacion" — crear presupuesto/cotización
  Señales: "cotización", "presupuesto", "cuánto cuesta", "hazme una coti", placa + trabajos/repuestos
  JSON: {"intencion":"cotizacion","placa":"ABC-123","cliente_nombre":"","telefono":"","kilometraje":"","items":[{"nombre":"","cantidad":1,"precio":0,"tipo":"repuesto"}]}

"ganancia" — consultar cuánto se ganó
  Señales: "cuánto gané", "ganancia", "ingresos de hoy/ayer/semana/mes", "cuánto hice"
  JSON: {"intencion":"ganancia","periodo":"hoy|ayer|semana|mes"}

"stock" — consultar existencias de producto
  Señales: "hay", "tengo", "stock de", "cuántos [producto]", nombre de repuesto
  JSON: {"intencion":"stock","producto":"nombre del producto a buscar"}

"estado_orden" — ver estado de órdenes
  Señales: "orden", "cómo va", "estado de", "órdenes activas", placa o número OS-XXXXX
  JSON: {"intencion":"estado_orden","referencia":"placa o número, vacío=todas activas"}

"crear_orden" — registrar nueva orden de trabajo
  Señales: "nueva orden", "ingresa orden", "registra", cliente + placa + trabajo
  JSON: {"intencion":"crear_orden","cliente_nombre":"","placa":"","motivo":"","descripcion":""}

"chat" — pregunta general, análisis, estadísticas, cualquier otra cosa
  JSON: {"intencion":"chat"}

IMPORTANTE: Si no estás seguro, usa "chat". Responde SOLO con el JSON."""


async def run_agent(user_text: str, foto_path: str = None, historial: list = None) -> str:
    """
    Punto de entrada del agente autónomo.
    Detecta la intención y ejecuta la acción directamente.
    Retorna str (texto para Telegram) o JSON str con {"pdf_path": ..., ...} para PDFs.

    Los créditos/fiado NO pasan por aquí — se manejan antes en handle_text
    porque necesitan botones de confirmación (acceso a update/context de Telegram).
    """
    from utils.groq_service import get_groq_client, get_context_data, chat_con_asistente

    historial = historial or []

    # ── Foto: responde con contexto del taller ───────────────────────────────
    if foto_path:
        ctx = get_context_data()
        prompt = (
            f"El usuario mandó una foto de evidencia. Caption: '{user_text}'. "
            f"Analiza en el contexto del taller y responde qué hacer con ella."
        )
        mensajes = historial[-6:] + [{"role": "user", "content": prompt}]
        return chat_con_asistente(mensajes, ctx)

    # ── Detectar intención ───────────────────────────────────────────────────
    try:
        client = get_groq_client()
        resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": _INTENT_PROMPT + "\n\nMensaje: " + user_text}],
            response_format={"type": "json_object"},
            max_tokens=400,
            temperature=0.1,
        )
        intent = json.loads(resp.choices[0].message.content.strip())
    except Exception as e:
        logger.error(f"[AGENT] Error intent detection: {e}")
        intent = {"intencion": "chat"}

    intencion = intent.get("intencion", "chat")
    logger.info(f"[AGENT] intent={intencion} | '{user_text[:60]}'")

    # ── Routing ──────────────────────────────────────────────────────────────
    try:
        if intencion == "cotizacion":
            return _handle_cotizacion(intent)

        elif intencion == "ganancia":
            return _handle_ganancia(intent.get("periodo", "hoy"))

        elif intencion == "stock":
            return _handle_stock(intent.get("producto", ""))

        elif intencion == "estado_orden":
            return _handle_estado_orden(intent.get("referencia", ""))

        elif intencion == "crear_orden":
            return _handle_crear_orden(intent)

        else:  # chat — respuesta inteligente con datos reales del taller
            ctx = get_context_data()
            mensajes = historial[-10:] + [{"role": "user", "content": user_text}]
            return chat_con_asistente(mensajes, ctx)

    except Exception as e:
        logger.error(f"[AGENT] Error en {intencion}: {e}", exc_info=True)
        # Fallback: siempre responder algo útil
        try:
            from utils.groq_service import get_context_data, chat_con_asistente
            ctx = get_context_data()
            mensajes = historial[-6:] + [{"role": "user", "content": user_text}]
            return chat_con_asistente(mensajes, ctx)
        except Exception:
            return "❌ Error interno. Intenta de nuevo en un momento."


# ── Handlers específicos ─────────────────────────────────────────────────────

def _handle_cotizacion(intent: dict) -> str:
    """Crea cotización directamente y retorna JSON con pdf_path o mensaje de error."""
    items = intent.get("items", [])
    if not items:
        return (
            "⚠️ No detecté los servicios o repuestos a cotizar.\n\n"
            "Dime así: *'cotización para placa ABC-123, cambio aceite 80 soles y filtro 25 soles'*"
        )

    # Completar precios desde inventario si están en 0
    from utils.models import get_db, ItemInventario
    db = get_db()
    try:
        for it in items:
            if float(it.get("precio", 0)) == 0 and it.get("nombre"):
                prod = db.query(ItemInventario).filter(
                    ItemInventario.nombre.ilike(f"%{it['nombre']}%")
                ).first()
                if prod:
                    it["precio"] = float(prod.precio)
    finally:
        db.close()

    try:
        from utils.telegram_bot import _crear_cotizacion_desde_bot
        msg, pdf_path = _crear_cotizacion_desde_bot(intent)
        if pdf_path:
            import os
            if os.path.exists(pdf_path):
                return json.dumps({
                    "pdf_path": pdf_path,
                    "numero": "COT",
                    "cliente": intent.get("cliente_nombre", "Cliente"),
                })
        return msg
    except Exception as e:
        logger.error(f"[AGENT] cotizacion error: {e}", exc_info=True)
        return f"❌ Error creando cotización: {e}"


def _handle_ganancia(periodo: str) -> str:
    """Calcula y formatea ganancias del período solicitado."""
    from utils.models import get_db, Orden, ItemInventario, NotaVenta
    import json as _j

    now = datetime.now()
    fin = None

    if periodo == "hoy":
        inicio = now.replace(hour=0, minute=0, second=0, microsecond=0)
        label = "HOY"
    elif periodo == "ayer":
        ayer = now - timedelta(days=1)
        inicio = ayer.replace(hour=0, minute=0, second=0, microsecond=0)
        fin = now.replace(hour=0, minute=0, second=0, microsecond=0)
        label = "AYER"
    elif periodo == "semana":
        inicio = now - timedelta(days=7)
        label = "ÚLTIMOS 7 DÍAS"
    else:  # mes
        inicio = now - timedelta(days=30)
        label = "ÚLTIMOS 30 DÍAS"

    def _pf(f):
        f = (f or "").strip()[:10]
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d"):
            try:
                return datetime.strptime(f, fmt)
            except Exception:
                pass
        return None

    db = get_db()
    try:
        costos_map = {it.codigo: float(it.costo or 0) for it in db.query(ItemInventario).all()}
        gan_rep = 0.0
        gan_mo = 0.0
        n_ordenes = 0

        for o in db.query(Orden).all():
            fd = _pf(o.fecha)
            if not fd or fd < inicio:
                continue
            if fin and fd >= fin:
                continue
            n_ordenes += 1
            items = o.items_cotizacion or []
            if isinstance(items, str):
                try: items = _j.loads(items)
                except: items = []
            for it in (items if isinstance(items, list) else []):
                precio_u = float(it.get("precio_unitario", 0) or 0)
                cant = float(it.get("cantidad", 1) or 1)
                total = precio_u * cant
                cat = (it.get("categoria") or "").lower()
                ref = (it.get("referencia") or it.get("ref") or "").strip()
                nombre = (it.get("nombre") or "").lower()
                es_mo = cat in ("servicio", "mano de obra") or ref == "MANO-DE-OBRA" or "mano" in nombre
                if es_mo:
                    gan_mo += total
                else:
                    gan_rep += total - (costos_map.get(ref, 0) * cant if ref else 0)

        for n in db.query(NotaVenta).filter_by(estado="pagada").all():
            if not n.fecha:
                continue
            try:
                nf = n.fecha if hasattr(n.fecha, "strftime") else _pf(str(n.fecha)[:10])
                if not nf or nf < inicio:
                    continue
                if fin and nf >= fin:
                    continue
            except Exception:
                continue
            items_n = n.items or []
            if isinstance(items_n, str):
                try: items_n = _j.loads(items_n)
                except: items_n = []
            for it in (items_n if isinstance(items_n, list) else []):
                precio_u = float(it.get("precio", 0) or 0)
                cant = float(it.get("cantidad", 1) or 1)
                total = precio_u * cant
                ref = (it.get("codigo") or "").strip()
                gan_rep += total - (costos_map.get(ref, 0) * cant if ref else 0)

        gan_total = gan_rep + gan_mo
        emoji = "📈" if gan_total > 0 else "📉"
        return (
            f"{emoji} *Ganancia {label}*\n\n"
            f"🔧 Repuestos:    *S/ {gan_rep:,.2f}*\n"
            f"⚙️ Mano de obra: *S/ {gan_mo:,.2f}*\n"
            f"──────────────────\n"
            f"💰 *NETA TOTAL: S/ {gan_total:,.2f}*\n\n"
            f"_({n_ordenes} orden(es) en el periodo)_"
        )
    except Exception as e:
        logger.error(f"[AGENT] ganancia error: {e}", exc_info=True)
        return f"❌ Error calculando ganancia: {e}"
    finally:
        db.close()


def _handle_stock(producto: str) -> str:
    """Busca stock de un producto. Sin producto → muestra stock crítico."""
    from utils.models import get_db, ItemInventario
    db = get_db()
    try:
        if not producto:
            criticos = db.query(ItemInventario).filter(
                ItemInventario.stock <= ItemInventario.stock_minimo
            ).all()
            if not criticos:
                return "✅ Todo el inventario está sobre el mínimo."
            txt = "⚠️ *Stock Crítico:*\n\n"
            for i in criticos[:10]:
                txt += f"• {i.nombre}: *{i.stock}* uds (mín: {i.stock_minimo})\n"
            return txt

        items = db.query(ItemInventario).filter(
            ItemInventario.nombre.ilike(f"%{producto}%")
        ).all()
        if not items:
            return f"❌ No encontré *{producto}* en el inventario."
        if len(items) == 1:
            i = items[0]
            estado = "✅" if i.stock > i.stock_minimo else "⚠️"
            return (
                f"{estado} *{i.nombre}*\n"
                f"📦 Stock: *{i.stock}* uds\n"
                f"💰 Precio venta: S/ {i.precio:.2f}\n"
                f"🔖 Código: {i.codigo or '—'}"
            )
        txt = f"🔍 *{len(items)}* productos encontrados:\n\n"
        for i in items[:8]:
            estado = "✅" if i.stock > i.stock_minimo else "⚠️"
            txt += f"{estado} {i.nombre} — *{i.stock}* uds @ S/{i.precio:.2f}\n"
        return txt
    finally:
        db.close()


def _handle_estado_orden(referencia: str) -> str:
    """Busca estado de órdenes por placa/número o lista todas las activas."""
    from utils.models import get_db, Orden, Cliente
    db = get_db()
    try:
        if referencia:
            ref_clean = referencia.upper().replace("-", "").replace(" ", "")
            ordenes = db.query(Orden).filter(
                (Orden.consecutivo.ilike(f"%{referencia}%")) |
                (Orden.vehiculo_placa.ilike(f"%{ref_clean}%"))
            ).order_by(Orden.fecha.desc()).limit(5).all()
        else:
            ordenes = db.query(Orden).filter(
                Orden.estado.notin_(["ARCHIVADO"])
            ).order_by(Orden.fecha.desc()).limit(10).all()

        if not ordenes:
            return (
                f"❌ No encontré órdenes para *{referencia}*."
                if referencia else
                "ℹ️ No hay órdenes activas en este momento."
            )

        estado_emoji = {
            "COTIZACIÓN": "📝", "APROBACIÓN": "⏳", "REPUESTOS": "🔧",
            "EN PROCESO": "⚙️", "ENTREGA": "🚗", "ARCHIVADO": "✅",
        }
        txt = f"📋 *{'Resultado' if referencia else 'Órdenes Activas'}:*\n\n"
        for o in ordenes:
            cliente_nombre = ""
            if o.cliente_id:
                cl = db.query(Cliente).filter_by(id=o.cliente_id).first()
                if cl:
                    cliente_nombre = f"{cl.nombre} {cl.apellidos or ''}".strip()
            em = estado_emoji.get(o.estado, "🔵")
            txt += (
                f"{em} *{o.consecutivo}* — {o.estado}\n"
                f"   🚗 {o.vehiculo_placa or '—'} | 👤 {cliente_nombre or '—'}\n"
                f"   📅 {str(o.fecha or '')[:10]} | {(o.motivo or '')[:40]}\n\n"
            )
        return txt
    finally:
        db.close()


def _handle_crear_orden(intent: dict) -> str:
    """Crea una nueva orden de servicio desde los datos del intent."""
    from utils.models import get_db, Orden, Cliente, Vehiculo
    from sqlalchemy import text as sqlt

    cliente_nombre = (intent.get("cliente_nombre") or "").strip()
    placa = (intent.get("placa") or "").upper().replace("-", "").replace(" ", "")
    motivo = (intent.get("motivo") or intent.get("descripcion") or "Sin especificar").strip()

    if not placa and not cliente_nombre:
        return "⚠️ Para crear una orden necesito al menos la *placa del vehículo* o el *nombre del cliente*."

    db = get_db()
    try:
        cliente_id = None
        if cliente_nombre:
            parts = cliente_nombre.split()
            cl = db.query(Cliente).filter(
                Cliente.nombre.ilike(f"%{parts[0]}%")
            ).first()
            if cl:
                cliente_id = cl.id

        if placa and not cliente_id:
            v = db.query(Vehiculo).filter_by(placa=placa).first()
            if v and v.cliente_id:
                cliente_id = v.cliente_id

        # Generar consecutivo
        res = db.execute(sqlt("SELECT consecutivo FROM ordenes ORDER BY id DESC LIMIT 1")).fetchone()
        if res and res[0] and res[0].startswith("OS-"):
            try:
                ult = int(res[0].split("-")[1])
                consecutivo = f"OS-{ult + 1:05d}"
            except Exception:
                consecutivo = f"OS-{datetime.now().strftime('%Y%m%d%H%M')}"
        else:
            consecutivo = "OS-00001"

        orden = Orden(
            consecutivo=consecutivo,
            fecha=datetime.now().strftime("%Y-%m-%d"),
            cliente_id=cliente_id,
            vehiculo_placa=placa or None,
            motivo=motivo,
            estado="EN PROCESO",
            items_cotizacion="[]",
        )
        db.add(orden)
        db.commit()

        return (
            f"✅ *Orden creada: {consecutivo}*\n\n"
            f"👤 Cliente: {cliente_nombre or '—'}\n"
            f"🚗 Placa: {placa or '—'}\n"
            f"🔧 Motivo: {motivo}\n"
            f"📊 Estado: EN PROCESO\n\n"
            f"_Ya aparece en el dashboard. Agrega el presupuesto desde el panel web._"
        )
    except Exception as e:
        db.rollback()
        logger.error(f"[AGENT] crear_orden error: {e}", exc_info=True)
        return f"❌ Error creando la orden: {e}"
    finally:
        db.close()

"""
SANDOVAL - Agente IA Autónomo v2 — Tool Calling Architecture
═══════════════════════════════════════════════════════════════
Cómo funciona:
  1. El usuario manda un mensaje al bot
  2. run_agent() lee el TOOLS_REGISTRY dinámicamente
  3. Le pasa TODAS las herramientas disponibles a Groq como JSON schema
  4. Groq decide cuál herramienta invocar y con qué parámetros
  5. El agente ejecuta esa herramienta

Para agregar una nueva función al bot:
  - Agrega una entrada en TOOLS_REGISTRY con name, description, parameters, handler
  - NADA MÁS. El bot lo detecta solo en el siguiente mensaje.

Las secciones del sidebar se inyectan automáticamente en el system prompt
para que el bot sepa exactamente qué módulos existen en el sistema.
"""
import logging
import json
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════════
# TOOLS REGISTRY — Aquí se registran TODAS las capacidades del bot.
# Para agregar una nueva: añade un dict con name, description, parameters, handler.
# El bot la detecta automáticamente sin tocar nada más.
# ═══════════════════════════════════════════════════════════════════════════════

def _get_tools_registry():
    """
    Retorna la lista de herramientas disponibles.
    Se llama en cada mensaje para que sea siempre actualizada.
    """
    return [
        {
            "name": "crear_nota_venta",
            "description": (
                "Crea una nota de venta directa en el módulo 'Notas de Venta' del sistema. "
                "Úsalo cuando el usuario quiera registrar una venta, nota de venta, venta directa, "
                "o vender productos/mano de obra a un cliente. "
                "Estado final: pagada. Descuenta stock automáticamente."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "cliente_nombre": {"type": "string", "description": "Nombre del cliente, vacío si es venta de mostrador"},
                    "items": {
                        "type": "array",
                        "description": "Lista de productos o servicios vendidos",
                        "items": {
                            "type": "object",
                            "properties": {
                                "nombre":   {"type": "string"},
                                "cantidad": {"type": "number"},
                                "precio":   {"type": "number", "description": "Precio unitario en soles"},
                                "tipo":     {"type": "string", "enum": ["repuesto", "mano_obra"]}
                            },
                            "required": ["nombre", "cantidad"]
                        }
                    }
                },
                "required": ["items"]
            },
            "handler": _tool_crear_nota_venta,
        },
        {
            "name": "crear_cotizacion",
            "description": (
                "Crea un presupuesto o cotización en el módulo 'Cotizaciones'. "
                "Úsalo cuando el usuario quiera hacer un presupuesto, cotización, o calcular cuánto costaría "
                "un trabajo para un vehículo. Genera PDF automáticamente."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "placa":          {"type": "string", "description": "Placa del vehículo"},
                    "cliente_nombre": {"type": "string"},
                    "telefono":       {"type": "string"},
                    "kilometraje":    {"type": "string"},
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "nombre":   {"type": "string"},
                                "cantidad": {"type": "number"},
                                "precio":   {"type": "number"},
                                "tipo":     {"type": "string", "enum": ["repuesto", "servicio", "mano_obra"]}
                            },
                            "required": ["nombre"]
                        }
                    }
                },
                "required": ["items"]
            },
            "handler": _tool_crear_cotizacion,
        },
        {
            "name": "crear_orden_servicio",
            "description": (
                "Crea una nueva orden de servicio en el módulo 'Órdenes de Servicio'. "
                "Úsalo cuando el usuario quiera registrar que un vehículo entró al taller, "
                "crear una orden, o registrar un trabajo a realizar."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "cliente_nombre": {"type": "string"},
                    "placa":          {"type": "string"},
                    "motivo":         {"type": "string", "description": "Motivo o descripción del trabajo"}
                },
                "required": []
            },
            "handler": _tool_crear_orden,
        },
        {
            "name": "crear_credito",
            "description": (
                "Registra una venta al crédito / fiado en el módulo 'Créditos / Fiado'. "
                "Úsalo cuando el usuario diga que alguien se llevó algo al fiado, al crédito, "
                "anotarlo, o que alguien debe dinero."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "cliente_nombre": {"type": "string"},
                    "telefono":       {"type": "string"},
                    "total":          {"type": "number"},
                    "nota":           {"type": "string"},
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "nombre":   {"type": "string"},
                                "cantidad": {"type": "number"},
                                "precio":   {"type": "number"}
                            }
                        }
                    }
                },
                "required": ["cliente_nombre"]
            },
            "handler": _tool_crear_credito,
        },
        {
            "name": "registrar_abono",
            "description": (
                "Registra un abono o pago parcial a un crédito existente. "
                "Úsalo cuando alguien abonó, pagó, canceló o entregó dinero para su deuda."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "cliente_nombre": {"type": "string"},
                    "monto":          {"type": "number"},
                    "metodo_pago":    {"type": "string", "description": "efectivo, yape, plin, transferencia"}
                },
                "required": ["cliente_nombre", "monto"]
            },
            "handler": _tool_registrar_abono,
        },
        {
            "name": "crear_cita",
            "description": (
                "Agenda una cita en el módulo 'Citas / Agenda'. "
                "Úsalo cuando el usuario quiera agendar, reservar o programar una cita para un cliente."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "cliente_nombre": {"type": "string"},
                    "fecha":          {"type": "string", "description": "Fecha en formato YYYY-MM-DD"},
                    "hora":           {"type": "string", "description": "Hora en formato HH:MM"},
                    "motivo":         {"type": "string"},
                    "placa":          {"type": "string"}
                },
                "required": ["cliente_nombre", "fecha"]
            },
            "handler": _tool_crear_cita,
        },
        {
            "name": "consultar_ganancia",
            "description": (
                "Consulta las ganancias del taller del período indicado (hoy, ayer, semana, mes). "
                "Muestra ganancia de repuestos, mano de obra y total neto."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "periodo": {"type": "string", "enum": ["hoy", "ayer", "semana", "mes"]}
                },
                "required": ["periodo"]
            },
            "handler": _tool_consultar_ganancia,
        },
        {
            "name": "consultar_top_repuestos",
            "description": (
                "Muestra qué repuestos o servicios se vendieron más, cuáles tuvieron mayor demanda, "
                "cuáles generaron más ingresos, o el ranking de productos más vendidos. "
                "Úsalo cuando pregunten: 'qué repuesto se vendió más', 'cuáles fueron los más demandados', "
                "'top productos', 'qué se vende más', 'qué repuesto salió más esta semana/mes'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "periodo": {
                        "type": "string",
                        "enum": ["semana", "mes", "año", "todo"],
                        "description": "Período a analizar. Por defecto 'mes'."
                    },
                    "top_n": {
                        "type": "integer",
                        "description": "Cuántos productos mostrar, por defecto 10"
                    }
                },
                "required": []
            },
            "handler": _tool_top_repuestos,
        },
        {
            "name": "consultar_stock",
            "description": (
                "Consulta cuántas unidades hay en stock de un producto del inventario. "
                "Úsalo cuando pregunten cuánto hay, si queda stock, o ver productos en stock crítico. "
                "NO usar para saber qué se vendió más — para eso usa consultar_top_repuestos."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "producto": {"type": "string", "description": "Nombre o código del producto, vacío para ver stock crítico"}
                },
                "required": []
            },
            "handler": _tool_consultar_stock,
        },
        {
            "name": "consultar_ordenes",
            "description": (
                "Consulta el estado de órdenes de servicio activas o busca por placa/número. "
                "Úsalo para ver cómo va un trabajo, qué órdenes están activas, o buscar una orden."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "referencia": {"type": "string", "description": "Placa o número de orden (OS-XXXXX), vacío = todas las activas"}
                },
                "required": []
            },
            "handler": _tool_consultar_ordenes,
        },
        {
            "name": "ver_creditos_pendientes",
            "description": (
                "Muestra los créditos/fiados pendientes de cobro. "
                "Úsalo cuando pregunten quién debe, los créditos activos o deudas pendientes."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "nombre_filtro": {"type": "string", "description": "Filtrar por nombre de cliente, vacío = todos"}
                },
                "required": []
            },
            "handler": _tool_ver_creditos,
        },
    ]


def _build_groq_tools(registry: list) -> list:
    """Convierte el registry al formato de tools que acepta la API de Groq."""
    return [
        {
            "type": "function",
            "function": {
                "name":        t["name"],
                "description": t["description"],
                "parameters":  t["parameters"],
            }
        }
        for t in registry
    ]


def _get_sidebar_sections() -> str:
    """Lee las secciones del sidebar dinámicamente para incluirlas en el prompt."""
    try:
        # Importar la configuración del sidebar para leer las secciones actuales
        import importlib.util, os
        sidebar_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'components', 'sidebar.py')
        spec = importlib.util.spec_from_file_location("sidebar", sidebar_path)
        mod  = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        # Extraer la lista de items del sidebar parseando el archivo
    except Exception:
        pass

    # Fallback: lista fija leída del sidebar (siempre actualizada manualmente aquí si cambia)
    secciones = [
        "dashboard", "ordenes de servicio", "cotizaciones", "clientes", "vehiculos",
        "proveedores", "inventario", "notas de venta", "facturas", "creditos / fiado",
        "citas / agenda", "reportes", "rentabilidad", "ia sandoval", "usuarios", "configuracion"
    ]
    return ", ".join(secciones)


# ═══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

async def run_agent(user_text: str, foto_path: str = None, historial: list = None) -> str:
    """
    Punto de entrada del agente autónomo.
    Usa Tool Calling de Groq — la IA elige la herramienta correcta automáticamente.
    """
    from utils.groq_service import get_groq_client, get_context_data, chat_con_asistente

    historial = historial or []

    # Foto: delegar al asistente con contexto
    if foto_path:
        ctx = get_context_data()
        prompt = f"El usuario mandó una foto. Caption: '{user_text}'. Responde en el contexto del taller."
        mensajes = historial[-6:] + [{"role": "user", "content": prompt}]
        return chat_con_asistente(mensajes, ctx)

    registry = _get_tools_registry()
    groq_tools = _build_groq_tools(registry)
    handler_map = {t["name"]: t["handler"] for t in registry}

    sections_str = _get_sidebar_sections()

    system_prompt = (
        "Eres el asistente autónomo del Taller Mecánico Sandoval (Perú).\n"
        f"El sistema tiene estos módulos: {sections_str}.\n"
        "Cuando el usuario pida hacer algo que corresponde a una herramienta, llámala directamente.\n"
        "Si el usuario hace una pregunta general sobre el taller (estadísticas, análisis, datos), "
        "NO uses herramienta — responde con tu conocimiento del contexto.\n"
        "Responde siempre en español."
    )

    try:
        client = get_groq_client()
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system_prompt},
                *historial[-8:],
                {"role": "user", "content": user_text},
            ],
            tools=groq_tools,
            tool_choice="auto",
            max_tokens=1000,
            temperature=0.1,
        )

        msg = response.choices[0].message

        # ── La IA eligió una herramienta ─────────────────────────────────────
        if msg.tool_calls:
            tool_call = msg.tool_calls[0]
            tool_name = tool_call.function.name
            try:
                args = json.loads(tool_call.function.arguments)
            except Exception:
                args = {}

            logger.info(f"[AGENT] tool={tool_name} args={json.dumps(args, ensure_ascii=False)[:120]}")

            handler = handler_map.get(tool_name)
            if handler:
                try:
                    return handler(args)
                except Exception as e:
                    logger.error(f"[AGENT] handler {tool_name} error: {e}", exc_info=True)
                    return f"❌ Error ejecutando '{tool_name}': {e}"
            else:
                return f"⚠️ Herramienta '{tool_name}' no encontrada en el registry."

        # ── La IA respondió en texto (pregunta general) ───────────────────────
        if msg.content:
            return msg.content.strip()

        # Fallback con contexto completo del taller
        ctx = get_context_data()
        mensajes = historial[-8:] + [{"role": "user", "content": user_text}]
        return chat_con_asistente(mensajes, ctx)

    except Exception as e:
        logger.error(f"[AGENT] run_agent error: {e}", exc_info=True)
        # Fallback
        try:
            from utils.groq_service import get_context_data, chat_con_asistente
            ctx = get_context_data()
            return chat_con_asistente(historial[-6:] + [{"role": "user", "content": user_text}], ctx)
        except Exception:
            return "❌ Error interno. Intenta de nuevo."


# ═══════════════════════════════════════════════════════════════════════════════
# TOOL HANDLERS — Cada función ejecuta una acción real en la base de datos.
# Para agregar un nuevo handler: defínelo aquí y regístralo en TOOLS_REGISTRY.
# ═══════════════════════════════════════════════════════════════════════════════

def _tool_crear_nota_venta(args: dict) -> str:
    items_raw = args.get("items", [])
    if not items_raw:
        return "⚠️ No detecté productos para la nota de venta. Dime los productos y precios."

    from utils.models import get_db, NotaVenta, ItemInventario, Cliente
    from sqlalchemy import text as sqlt

    db = get_db()
    try:
        items_procesados = []
        for it in items_raw:
            nombre   = (it.get("nombre") or "").strip()
            cant     = float(it.get("cantidad", 1) or 1)
            precio   = float(it.get("precio", 0) or 0)
            tipo     = (it.get("tipo") or "repuesto").lower()
            codigo   = ""

            if precio == 0 and nombre and tipo != "mano_obra":
                prod = db.query(ItemInventario).filter(
                    ItemInventario.nombre.ilike(f"%{nombre}%")
                ).first()
                if prod:
                    precio = float(prod.precio)
                    nombre = prod.nombre
                    codigo = prod.codigo or ""

            items_procesados.append({
                "codigo":    codigo,
                "nombre":    nombre or "Sin nombre",
                "cantidad":  cant,
                "precio":    precio,
                "subtotal":  round(precio * cant, 2),
                "categoria": "Mano de obra" if tipo == "mano_obra" else "Repuesto",
            })

        subtotal = round(sum(i["subtotal"] for i in items_procesados), 2)

        res = db.execute(sqlt("SELECT numero FROM notas_venta ORDER BY id DESC LIMIT 1")).fetchone()
        if res and res[0] and res[0].startswith("NV-"):
            try:
                numero = f"NV-{int(res[0].split('-')[1]) + 1:05d}"
            except Exception:
                numero = f"NV-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        else:
            numero = "NV-00001"

        cliente_id     = None
        cliente_nombre = (args.get("cliente_nombre") or "Mostrador").strip()
        if cliente_nombre and cliente_nombre.lower() not in ("mostrador", ""):
            parts = cliente_nombre.split()
            cl = db.query(Cliente).filter(Cliente.nombre.ilike(f"%{parts[0]}%")).first()
            if cl:
                cliente_id     = str(cl.id)
                cliente_nombre = f"{cl.nombre} {cl.apellidos or ''}".strip()

        db.add(NotaVenta(
            numero=numero, cliente_id=cliente_id, cliente_nombre=cliente_nombre,
            subtotal=subtotal, igv=0, total=subtotal,
            estado="pagada", notas="Creada vía Telegram Bot", items=items_procesados,
        ))

        for it in items_procesados:
            if it.get("codigo"):
                inv = db.query(ItemInventario).filter_by(codigo=it["codigo"]).first()
                if inv:
                    inv.stock = max(0, inv.stock - int(it["cantidad"]))

        db.commit()

        items_txt = "\n".join(
            f"  • {it['cantidad']}x {it['nombre']} — S/ {it['precio']:.2f} = S/ {it['subtotal']:.2f}"
            for it in items_procesados
        )
        return (
            f"✅ *Nota de Venta {numero} creada*\n\n"
            f"👤 Cliente: {cliente_nombre}\n\n"
            f"📦 *Productos:*\n{items_txt}\n\n"
            f"💰 *Total: S/ {subtotal:.2f}*\n"
            f"_Ya aparece en el módulo Notas de Venta._"
        )
    except Exception as e:
        db.rollback()
        logger.error(f"[AGENT] crear_nota_venta: {e}", exc_info=True)
        return f"❌ Error creando nota de venta: {e}"
    finally:
        db.close()


def _tool_crear_cotizacion(args: dict) -> str:
    if not args.get("items"):
        return "⚠️ No detecté ítems para la cotización. Dime los servicios o repuestos con sus precios."
    try:
        from utils.telegram_bot import _crear_cotizacion_desde_bot
        msg, pdf_path = _crear_cotizacion_desde_bot(args)
        if pdf_path:
            import os
            if os.path.exists(pdf_path):
                return json.dumps({
                    "pdf_path": pdf_path,
                    "numero":   "COT",
                    "cliente":  args.get("cliente_nombre", "Cliente"),
                })
        return msg
    except Exception as e:
        logger.error(f"[AGENT] crear_cotizacion: {e}", exc_info=True)
        return f"❌ Error creando cotización: {e}"


def _tool_crear_orden(args: dict) -> str:
    from utils.models import get_db, Orden, Cliente, Vehiculo
    from sqlalchemy import text as sqlt

    cliente_nombre = (args.get("cliente_nombre") or "").strip()
    placa  = (args.get("placa") or "").upper().replace("-", "").replace(" ", "")
    motivo = (args.get("motivo") or "Sin especificar").strip()

    if not placa and not cliente_nombre:
        return "⚠️ Necesito al menos la *placa del vehículo* o el *nombre del cliente* para crear la orden."

    db = get_db()
    try:
        cliente_id = None
        if cliente_nombre:
            parts = cliente_nombre.split()
            cl = db.query(Cliente).filter(Cliente.nombre.ilike(f"%{parts[0]}%")).first()
            if cl:
                cliente_id = cl.id
        if placa and not cliente_id:
            v = db.query(Vehiculo).filter_by(placa=placa).first()
            if v and v.cliente_id:
                cliente_id = v.cliente_id

        res = db.execute(sqlt("SELECT consecutivo FROM ordenes ORDER BY id DESC LIMIT 1")).fetchone()
        if res and res[0] and res[0].startswith("OS-"):
            try:
                consecutivo = f"OS-{int(res[0].split('-')[1]) + 1:05d}"
            except Exception:
                consecutivo = f"OS-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        else:
            consecutivo = "OS-00001"

        db.add(Orden(
            consecutivo=consecutivo, fecha=datetime.now().strftime("%Y-%m-%d"),
            cliente_id=cliente_id, vehiculo_placa=placa or None,
            motivo=motivo, estado="EN PROCESO", items_cotizacion="[]",
        ))
        db.commit()
        return (
            f"✅ *Orden {consecutivo} creada*\n\n"
            f"👤 Cliente: {cliente_nombre or '—'}\n"
            f"🚗 Placa: {placa or '—'}\n"
            f"🔧 Motivo: {motivo}\n"
            f"_Agrega el presupuesto desde el panel web._"
        )
    except Exception as e:
        db.rollback()
        logger.error(f"[AGENT] crear_orden: {e}", exc_info=True)
        return f"❌ Error creando orden: {e}"
    finally:
        db.close()


def _tool_crear_credito(args: dict) -> str:
    """Crea un crédito/fiado directamente. Confirmación ya fue implícita en el chat."""
    try:
        from utils.telegram_bot import _crear_credito_bot
        ok = _crear_credito_bot(args)
        if ok:
            nombre = args.get("cliente_nombre", "—")
            total  = float(args.get("total", 0))
            items  = args.get("items", [])
            if not total and items:
                total = sum(float(i.get("precio", 0)) * float(i.get("cantidad", 1)) for i in items)
            return (
                f"✅ *Crédito registrado*\n\n"
                f"👤 {nombre}\n"
                f"💰 Total pendiente: *S/ {total:.2f}*\n"
                f"_Ya aparece en Créditos / Fiado._"
            )
        return "❌ Error guardando el crédito. Intenta de nuevo."
    except Exception as e:
        logger.error(f"[AGENT] crear_credito: {e}", exc_info=True)
        return f"❌ Error: {e}"


def _tool_registrar_abono(args: dict) -> str:
    nombre = (args.get("cliente_nombre") or "").strip()
    monto  = float(args.get("monto", 0) or 0)
    if not nombre or monto <= 0:
        return "⚠️ Necesito el nombre del cliente y el monto del abono."

    try:
        from utils.telegram_bot import _buscar_creditos_por_nombre, _registrar_abono_bot
        creditos = _buscar_creditos_por_nombre(nombre)
        if not creditos:
            return f"❌ No encontré créditos activos para *{nombre}*."

        # Tomar el más reciente
        c   = creditos[0]
        ok  = _registrar_abono_bot(c["id"], monto, args.get("metodo_pago", "") or "")
        if ok:
            nuevo_pendiente = max(0, float(c["pendiente"]) - monto)
            estado_msg = "✅ *¡Crédito cancelado completamente!*" if nuevo_pendiente <= 0 else f"📊 Nuevo pendiente: *S/ {nuevo_pendiente:.2f}*"
            return (
                f"✅ *Abono registrado*\n\n"
                f"👤 {c['cliente_nombre']}\n"
                f"💰 Abono: S/ {monto:.2f}\n"
                f"💳 Método: {args.get('metodo_pago', '—') or '—'}\n"
                f"{estado_msg}"
            )
        return "❌ Error registrando el abono."
    except Exception as e:
        logger.error(f"[AGENT] registrar_abono: {e}", exc_info=True)
        return f"❌ Error: {e}"


def _tool_crear_cita(args: dict) -> str:
    from utils.models import get_db, Cliente
    from sqlalchemy import text as sqlt

    cliente_nombre = (args.get("cliente_nombre") or "").strip()
    fecha  = (args.get("fecha") or datetime.now().strftime("%Y-%m-%d"))
    hora   = (args.get("hora") or "09:00")
    motivo = (args.get("motivo") or "Sin especificar")
    placa  = (args.get("placa") or "").upper().replace("-", "")

    db = get_db()
    try:
        cliente_id = None
        if cliente_nombre:
            parts = cliente_nombre.split()
            cl = db.query(Cliente).filter(Cliente.nombre.ilike(f"%{parts[0]}%")).first()
            if cl:
                cliente_id = cl.id

        db.execute(sqlt("""
            INSERT INTO citas (cliente_id, cliente_nombre, fecha, hora, motivo, placa, estado, creado_por)
            VALUES (:cid, :cn, :fecha, :hora, :motivo, :placa, 'pendiente', 'Bot Telegram')
        """), {
            "cid": cliente_id, "cn": cliente_nombre,
            "fecha": fecha, "hora": hora,
            "motivo": motivo, "placa": placa or None,
        })
        db.commit()
        return (
            f"✅ *Cita agendada*\n\n"
            f"👤 Cliente: {cliente_nombre}\n"
            f"📅 Fecha: {fecha} a las {hora}\n"
            f"🔧 Motivo: {motivo}\n"
            f"🚗 Placa: {placa or '—'}\n"
            f"_Ya aparece en Citas / Agenda._"
        )
    except Exception as e:
        db.rollback()
        logger.error(f"[AGENT] crear_cita: {e}", exc_info=True)
        return f"❌ Error agendando cita: {e}"
    finally:
        db.close()


def _tool_consultar_ganancia(args: dict) -> str:
    periodo = (args.get("periodo") or "hoy").lower()
    from utils.models import get_db, Orden, ItemInventario, NotaVenta
    import json as _j

    now = datetime.now()
    fin = None
    if periodo == "hoy":
        inicio = now.replace(hour=0, minute=0, second=0, microsecond=0)
        label  = "HOY"
    elif periodo == "ayer":
        ayer   = now - timedelta(days=1)
        inicio = ayer.replace(hour=0, minute=0, second=0, microsecond=0)
        fin    = now.replace(hour=0, minute=0, second=0, microsecond=0)
        label  = "AYER"
    elif periodo == "semana":
        inicio = now - timedelta(days=7)
        label  = "ÚLTIMOS 7 DÍAS"
    else:
        inicio = now - timedelta(days=30)
        label  = "ÚLTIMOS 30 DÍAS"

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
        gan_mo  = 0.0
        n_ord   = 0

        for o in db.query(Orden).all():
            fd = _pf(o.fecha)
            if not fd or fd < inicio or (fin and fd >= fin):
                continue
            n_ord += 1
            items = o.items_cotizacion or []
            if isinstance(items, str):
                try: items = _j.loads(items)
                except: items = []
            for it in (items if isinstance(items, list) else []):
                precio_u = float(it.get("precio_unitario", 0) or 0)
                cant     = float(it.get("cantidad", 1) or 1)
                total    = precio_u * cant
                cat      = (it.get("categoria") or "").lower()
                ref      = (it.get("referencia") or it.get("ref") or "").strip()
                nombre   = (it.get("nombre") or "").lower()
                es_mo    = cat in ("servicio", "mano de obra") or ref == "MANO-DE-OBRA" or "mano" in nombre
                if es_mo:
                    gan_mo  += total
                else:
                    gan_rep += total - (costos_map.get(ref, 0) * cant if ref else 0)

        for n in db.query(NotaVenta).filter_by(estado="pagada").all():
            if not n.fecha:
                continue
            try:
                nf = n.fecha if hasattr(n.fecha, "strftime") else _pf(str(n.fecha)[:10])
                if not nf or nf < inicio or (fin and nf >= fin):
                    continue
            except Exception:
                continue
            items_n = n.items or []
            if isinstance(items_n, str):
                try: items_n = _j.loads(items_n)
                except: items_n = []
            for it in (items_n if isinstance(items_n, list) else []):
                precio_u = float(it.get("precio", 0) or 0)
                cant     = float(it.get("cantidad", 1) or 1)
                total    = precio_u * cant
                ref      = (it.get("codigo") or "").strip()
                gan_rep += total - (costos_map.get(ref, 0) * cant if ref else 0)

        gan_total = gan_rep + gan_mo
        emoji = "📈" if gan_total > 0 else "📉"
        return (
            f"{emoji} *Ganancia {label}*\n\n"
            f"🔧 Repuestos:    *S/ {gan_rep:,.2f}*\n"
            f"⚙️ Mano de obra: *S/ {gan_mo:,.2f}*\n"
            f"──────────────────\n"
            f"💰 *NETA TOTAL: S/ {gan_total:,.2f}*\n\n"
            f"_({n_ord} orden(es) en el periodo)_"
        )
    except Exception as e:
        logger.error(f"[AGENT] consultar_ganancia: {e}", exc_info=True)
        return f"❌ Error calculando ganancia: {e}"
    finally:
        db.close()


def _tool_consultar_stock(args: dict) -> str:
    producto = (args.get("producto") or "").strip()
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
        txt = f"🔍 *{len(items)}* productos:\n\n"
        for i in items[:8]:
            estado = "✅" if i.stock > i.stock_minimo else "⚠️"
            txt += f"{estado} {i.nombre} — *{i.stock}* uds @ S/{i.precio:.2f}\n"
        return txt
    finally:
        db.close()


def _tool_consultar_ordenes(args: dict) -> str:
    referencia = (args.get("referencia") or "").strip()
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
                f"❌ No encontré órdenes para *{referencia}*." if referencia
                else "ℹ️ No hay órdenes activas en este momento."
            )

        emojis = {
            "COTIZACIÓN": "📝", "APROBACIÓN": "⏳", "REPUESTOS": "🔧",
            "EN PROCESO": "⚙️", "ENTREGA": "🚗", "ARCHIVADO": "✅",
        }
        txt = f"📋 *{'Resultado' if referencia else 'Órdenes Activas'}:*\n\n"
        for o in ordenes:
            nombre_cl = ""
            if o.cliente_id:
                cl = db.query(Cliente).filter_by(id=o.cliente_id).first()
                if cl:
                    nombre_cl = f"{cl.nombre} {cl.apellidos or ''}".strip()
            em = emojis.get(o.estado, "🔵")
            txt += (
                f"{em} *{o.consecutivo}* — {o.estado}\n"
                f"   🚗 {o.vehiculo_placa or '—'} | 👤 {nombre_cl or '—'}\n"
                f"   📅 {str(o.fecha or '')[:10]} | {(o.motivo or '')[:40]}\n\n"
            )
        return txt
    finally:
        db.close()


def _tool_top_repuestos(args: dict) -> str:
    """Ranking de repuestos/servicios más vendidos por cantidad e ingresos."""
    periodo = (args.get("periodo") or "mes").lower()
    top_n   = int(args.get("top_n") or 10)

    from utils.models import get_db, Orden, NotaVenta
    import json as _j

    now = datetime.now()
    if periodo == "semana":
        inicio = now - timedelta(days=7)
        label  = "esta semana (7 días)"
    elif periodo == "año":
        inicio = now - timedelta(days=365)
        label  = "este año"
    elif periodo == "todo":
        inicio = datetime(2000, 1, 1)
        label  = "histórico total"
    else:
        inicio = now - timedelta(days=30)
        label  = "este mes (30 días)"

    def _pf(f):
        f = (f or "").strip()[:10]
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d"):
            try:
                return datetime.strptime(f, fmt)
            except Exception:
                pass
        return None

    # agg[nombre] = {cantidad, ingresos, es_mo}
    agg = {}

    db = get_db()
    try:
        # ── Órdenes de servicio ──
        for o in db.query(Orden).all():
            fd = _pf(o.fecha)
            if not fd or fd < inicio:
                continue
            items = o.items_cotizacion or []
            if isinstance(items, str):
                try: items = _j.loads(items)
                except: items = []
            for it in (items if isinstance(items, list) else []):
                nombre = (it.get("nombre") or "").strip()
                if not nombre:
                    continue
                cant   = float(it.get("cantidad", 1) or 1)
                precio = float(it.get("precio_unitario", 0) or 0)
                cat    = (it.get("categoria") or "").lower()
                ref    = (it.get("referencia") or it.get("ref") or "").strip()
                es_mo  = cat in ("servicio", "mano de obra") or ref == "MANO-DE-OBRA" or "mano" in nombre.lower()
                key    = nombre[:50]
                if key not in agg:
                    agg[key] = {"nombre": key, "cantidad": 0, "ingresos": 0.0, "es_mo": es_mo}
                agg[key]["cantidad"] += cant
                agg[key]["ingresos"] += precio * cant

        # ── Notas de venta ──
        for n in db.query(NotaVenta).filter_by(estado="pagada").all():
            if not n.fecha:
                continue
            try:
                nf = n.fecha if hasattr(n.fecha, "strftime") else _pf(str(n.fecha)[:10])
                if not nf or nf < inicio:
                    continue
            except Exception:
                continue
            items_n = n.items or []
            if isinstance(items_n, str):
                try: items_n = _j.loads(items_n)
                except: items_n = []
            for it in (items_n if isinstance(items_n, list) else []):
                nombre = (it.get("nombre") or "").strip()
                if not nombre:
                    continue
                cant   = float(it.get("cantidad", 1) or 1)
                precio = float(it.get("precio", 0) or 0)
                key    = nombre[:50]
                es_mo  = (it.get("categoria") or "").lower() == "mano de obra"
                if key not in agg:
                    agg[key] = {"nombre": key, "cantidad": 0, "ingresos": 0.0, "es_mo": es_mo}
                agg[key]["cantidad"] += cant
                agg[key]["ingresos"] += precio * cant

        if not agg:
            return f"ℹ️ Sin ventas registradas para el período ({label})."

        # Ordenar por cantidad vendida
        ranking = sorted(agg.values(), key=lambda x: x["cantidad"], reverse=True)[:top_n]

        # Separar repuestos y mano de obra
        repuestos = [r for r in ranking if not r["es_mo"]]
        mo        = [r for r in ranking if r["es_mo"]]

        txt = f"🏆 *Top repuestos más vendidos — {label}*\n\n"

        if repuestos:
            txt += "🔧 *Repuestos / Productos:*\n"
            for i, r in enumerate(repuestos[:8], 1):
                txt += f"  {i}. {r['nombre']} — *{int(r['cantidad'])} uds* · S/ {r['ingresos']:,.2f}\n"

        if mo:
            txt += "\n⚙️ *Servicios / Mano de obra:*\n"
            for i, r in enumerate(mo[:5], 1):
                txt += f"  {i}. {r['nombre']} — *{int(r['cantidad'])} veces* · S/ {r['ingresos']:,.2f}\n"

        return txt

    except Exception as e:
        logger.error(f"[AGENT] top_repuestos: {e}", exc_info=True)
        return f"❌ Error consultando top repuestos: {e}"
    finally:
        db.close()


def _tool_ver_creditos(args: dict) -> str:
    nombre_filtro = (args.get("nombre_filtro") or "").strip()
    try:
        from utils.telegram_bot import _buscar_creditos_por_nombre, _get_todos_creditos_pendientes, _formato_credito
        if nombre_filtro:
            creditos = _buscar_creditos_por_nombre(nombre_filtro)
        else:
            creditos = _get_todos_creditos_pendientes()

        if not creditos:
            return "✅ No hay créditos pendientes."

        texto = f"📋 *Créditos Pendientes* ({len(creditos)})\n\n"
        for c in creditos[:10]:
            texto += _formato_credito(c) + "\n\n"
        return texto
    except Exception as e:
        logger.error(f"[AGENT] ver_creditos: {e}", exc_info=True)
        return f"❌ Error consultando créditos: {e}"

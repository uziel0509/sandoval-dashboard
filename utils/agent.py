"""
SANDOVAL - Agente IA Autónomo v3
══════════════════════════════════════════════════════════════
Arquitectura completa:

  1. MEMORIA PERSISTENTE    — historial guardado en SQLite por usuario
  2. RAG CORRECCIONES       — aprende de errores del pasado
  3. CONTEXT DATA SIEMPRE   — datos reales del taller en el prompt
  4. SQL LIBRE              — consulta cualquier cosa con SELECT
  5. REACT LOOP 3 PASOS     — si falla, razona y reintenta
  6. CONFIRMACIONES         — acciones destructivas piden OK primero
  7. AMBIGÜEDAD             — pregunta cuando no está claro
  8. HERRAMIENTAS COMPLETAS — nota venta, cotización, orden, cita,
                              crédito, abono, estado orden, buscar
                              contacto, buscar PDF, top repuestos,
                              stock, ganancia, órdenes

Para agregar una función nueva:
  - Añade un dict en _get_tools_registry()
  - Escribe el handler _tool_XXX(args)
  - Nada más. El bot lo detecta solo.
"""
import logging
import json
import re
import os
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

MODEL          = "llama-3.3-70b-versatile"
MAX_REACT_STEPS = 3
HISTORIAL_MAX   = 20
BASE_DIR        = os.path.dirname(os.path.dirname(__file__))

# ══════════════════════════════════════════════════════════════
# MEMORIA PERSISTENTE
# ══════════════════════════════════════════════════════════════

def cargar_historial(user_id: int) -> list:
    """Carga el historial de conversación desde SQLite."""
    try:
        from utils.models import get_db, AgentMemoria
        db = get_db()
        try:
            m = db.query(AgentMemoria).filter_by(telegram_user_id=user_id).first()
            if m and m.historial_json:
                return json.loads(m.historial_json)
        finally:
            db.close()
    except Exception as e:
        logger.error(f"[MEM] cargar_historial: {e}")
    return []


def guardar_historial(user_id: int, historial: list):
    """Persiste el historial de conversación en SQLite."""
    try:
        from utils.models import get_db, AgentMemoria
        db = get_db()
        try:
            recortado = historial[-HISTORIAL_MAX:]
            m = db.query(AgentMemoria).filter_by(telegram_user_id=user_id).first()
            if m:
                m.historial_json = json.dumps(recortado, ensure_ascii=False)
                m.updated_at     = datetime.now()
            else:
                db.add(AgentMemoria(
                    telegram_user_id=user_id,
                    historial_json=json.dumps(recortado, ensure_ascii=False),
                    updated_at=datetime.now()
                ))
            db.commit()
        finally:
            db.close()
    except Exception as e:
        logger.error(f"[MEM] guardar_historial: {e}")


# ══════════════════════════════════════════════════════════════
# RAG — APRENDER DE ERRORES
# ══════════════════════════════════════════════════════════════

_STOP_WORDS = {'el', 'la', 'los', 'las', 'un', 'una', 'de', 'en', 'y', 'a',
               'que', 'se', 'es', 'me', 'mi', 'no', 'si', 'por', 'con', 'al',
               'del', 'lo', 'le', 'su', 'más', 'ya', 'te', 'fue', 'hay', 'para'}

def _keywords(texto: str) -> str:
    """Extrae palabras clave (sin stopwords, min 3 chars)."""
    words = re.findall(r'\b[a-záéíóúüñ]{3,}\b', texto.lower())
    return ' '.join(w for w in words if w not in _STOP_WORDS)


def registrar_correccion(mensaje_original: str, respuesta_jarvis: str, correccion_usuario: str):
    """Guarda una corrección del usuario para que Jarvis aprenda."""
    try:
        from utils.models import get_db, AgentCorreccion
        db = get_db()
        try:
            kw = _keywords(mensaje_original + ' ' + correccion_usuario)
            db.add(AgentCorreccion(
                mensaje_original   = mensaje_original[:500],
                respuesta_jarvis   = respuesta_jarvis[:500],
                correccion_usuario = correccion_usuario[:500],
                keywords           = kw[:300],
                fecha              = datetime.now()
            ))
            db.commit()
            logger.info(f"[RAG] Corrección guardada. Keywords: {kw[:80]}")
        finally:
            db.close()
    except Exception as e:
        logger.error(f"[RAG] registrar_correccion: {e}")


def buscar_correcciones_relevantes(mensaje: str) -> str:
    """
    Busca correcciones pasadas relevantes para inyectar en el prompt.
    Retorna string vacío si no hay coincidencias.
    """
    try:
        from utils.models import get_db, AgentCorreccion
        db = get_db()
        try:
            todas = db.query(AgentCorreccion).order_by(AgentCorreccion.fecha.desc()).limit(100).all()
            if not todas:
                return ""

            words_query = set(_keywords(mensaje).split())
            if not words_query:
                return ""

            scored = []
            for c in todas:
                words_stored = set((c.keywords or '').split())
                score = len(words_query & words_stored)
                if score > 0:
                    scored.append((score, c))

            if not scored:
                return ""

            scored.sort(key=lambda x: x[0], reverse=True)
            top3 = scored[:3]

            lineas = ["📚 Aprende de estos errores pasados (aplícalos si el caso es similar):"]
            for _, c in top3:
                lineas.append(
                    f'  • Cuando dijeron: "{c.mensaje_original[:80]}"\n'
                    f'    Respondiste: "{c.respuesta_jarvis[:80]}"\n'
                    f'    La respuesta correcta era: "{c.correccion_usuario[:120]}"'
                )
            return '\n'.join(lineas)
        finally:
            db.close()
    except Exception as e:
        logger.error(f"[RAG] buscar_correcciones: {e}")
        return ""


def es_correccion(texto: str) -> bool:
    """Detecta si el usuario está corrigiendo a Jarvis."""
    patrones = [
        r'^no[,\s]', r'te equivocaste', r'está mal', r'eso está mal',
        r'no era eso', r'no es eso', r'incorrecto', r'error[,\s]',
        r'no eso', r'mal respondiste', r'no te pedi', r'no pedí eso',
        r'no es lo que', r'corrígete', r'equivocado', r'no entendiste'
    ]
    t = texto.lower().strip()
    return any(re.search(p, t) for p in patrones)


# ══════════════════════════════════════════════════════════════
# TOOLS REGISTRY
# ══════════════════════════════════════════════════════════════

def _get_tools_registry():
    return [
        # ── CONSULTAS ──────────────────────────────────────────────────
        {
            "name": "consultar_db",
            "description": (
                "Ejecuta una consulta SQL SELECT en la base de datos del taller para responder "
                "CUALQUIER pregunta analítica: clientes frecuentes, órdenes por período, "
                "productos más vendidos, proveedores, créditos vencidos, comparaciones, rankings, etc. "
                "Tablas disponibles: ordenes, clientes, vehiculos, items_inventario, notas_venta, "
                "creditos, abonos_credito, citas, facturas, cotizaciones, proveedores. "
                "USA ESTA HERRAMIENTA cuando no haya una herramienta específica para la pregunta."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "sql": {
                        "type": "string",
                        "description": "Consulta SELECT válida en SQLite. Solo SELECT, sin modificaciones."
                    },
                    "descripcion": {
                        "type": "string",
                        "description": "Qué busca esta consulta (para el log)"
                    }
                },
                "required": ["sql"]
            },
            "handler": _tool_consultar_db,
        },
        {
            "name": "consultar_ganancia",
            "description": (
                "Ganancia neta del taller: repuestos + mano de obra. "
                "Úsalo para: cuánto gané hoy/ayer/semana/mes."
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
                "Ranking de repuestos y servicios más vendidos por cantidad. "
                "Úsalo para: qué se vendió más, cuáles tuvieron mayor demanda, top productos."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "periodo": {"type": "string", "enum": ["semana", "mes", "año", "todo"]},
                    "top_n":   {"type": "integer"}
                },
                "required": []
            },
            "handler": _tool_top_repuestos,
        },
        {
            "name": "consultar_stock",
            "description": (
                "Cuántas unidades hay en inventario de un producto específico, "
                "o ver todos los productos en stock crítico (bajo mínimo). "
                "NO usar para saber qué se vendió más — para eso usa consultar_top_repuestos."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "producto": {"type": "string", "description": "Nombre del producto, vacío = stock crítico"}
                },
                "required": []
            },
            "handler": _tool_consultar_stock,
        },
        {
            "name": "consultar_ordenes",
            "description": (
                "Estado de órdenes de servicio. Busca por placa o número de orden. "
                "Sin referencia muestra todas las activas."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "referencia": {"type": "string", "description": "Placa o OS-XXXXX, vacío = todas activas"}
                },
                "required": []
            },
            "handler": _tool_consultar_ordenes,
        },
        {
            "name": "buscar_contacto",
            "description": (
                "Busca datos de contacto de un cliente o proveedor: "
                "teléfono, email, dirección, RUC. "
                "Úsalo cuando pregunten por datos de contacto de alguien."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "nombre":  {"type": "string"},
                    "tipo":    {"type": "string", "enum": ["cliente", "proveedor", "cualquiera"]}
                },
                "required": ["nombre"]
            },
            "handler": _tool_buscar_contacto,
        },
        {
            "name": "ver_creditos_pendientes",
            "description": "Créditos/fiados pendientes de cobro. Filtrable por cliente.",
            "parameters": {
                "type": "object",
                "properties": {
                    "nombre_filtro": {"type": "string"}
                },
                "required": []
            },
            "handler": _tool_ver_creditos,
        },
        {
            "name": "buscar_pdf",
            "description": (
                "Busca y envía un PDF existente: cotización, orden de servicio, factura. "
                "Úsalo cuando pidan 'mándame el PDF de...', 'el presupuesto de...', etc."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "referencia": {"type": "string", "description": "Número de cotización, OS, o nombre de cliente"}
                },
                "required": ["referencia"]
            },
            "handler": _tool_buscar_pdf,
        },

        # ── ACCIONES (con confirmación) ─────────────────────────────────
        {
            "name": "crear_nota_venta",
            "description": (
                "Crea una nota de venta directa. Úsalo para: registrar venta, nota de venta, "
                "vender productos o mano de obra a un cliente. Estado: pagada."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "cliente_nombre": {"type": "string"},
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "nombre":   {"type": "string"},
                                "cantidad": {"type": "number"},
                                "precio":   {"type": "number"},
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
                "Crea presupuesto/cotización con PDF. Úsalo para: cotización, presupuesto, "
                "cuánto costaría un trabajo."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "placa":          {"type": "string"},
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
                                "tipo":     {"type": "string"}
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
                "Crea una nueva orden de servicio. Úsalo para: registrar entrada de vehículo "
                "al taller, nueva orden, registrar trabajo."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "cliente_nombre": {"type": "string"},
                    "placa":          {"type": "string"},
                    "motivo":         {"type": "string"}
                },
                "required": []
            },
            "handler": _tool_crear_orden,
        },
        {
            "name": "cambiar_estado_orden",
            "description": (
                "Cambia el estado de una orden de servicio. "
                "Estados: COTIZACIÓN, APROBACIÓN, REPUESTOS, EN PROCESO, ENTREGA, ARCHIVADO. "
                "Úsalo para: marcar como lista, cambiar a entrega, archivar orden."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "referencia":   {"type": "string", "description": "Número de orden OS-XXXXX o placa"},
                    "nuevo_estado": {"type": "string", "enum": ["APROBACIÓN","REPUESTOS","EN PROCESO","ENTREGA","ARCHIVADO"]}
                },
                "required": ["referencia", "nuevo_estado"]
            },
            "handler": _tool_cambiar_estado_orden,
        },
        {
            "name": "crear_credito",
            "description": (
                "Registra venta al crédito/fiado. Úsalo cuando alguien se lleve algo al fiado, "
                "al crédito, anotarlo, o deba dinero."
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
                "Registra abono/pago a un crédito. Úsalo cuando alguien abonó, pagó, "
                "canceló o entregó dinero para su deuda."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "cliente_nombre": {"type": "string"},
                    "monto":          {"type": "number"},
                    "metodo_pago":    {"type": "string"}
                },
                "required": ["cliente_nombre", "monto"]
            },
            "handler": _tool_registrar_abono,
        },
        {
            "name": "crear_cita",
            "description": "Agenda cita en el módulo Citas/Agenda.",
            "parameters": {
                "type": "object",
                "properties": {
                    "cliente_nombre": {"type": "string"},
                    "fecha":          {"type": "string", "description": "YYYY-MM-DD"},
                    "hora":           {"type": "string", "description": "HH:MM"},
                    "motivo":         {"type": "string"},
                    "placa":          {"type": "string"}
                },
                "required": ["cliente_nombre", "fecha"]
            },
            "handler": _tool_crear_cita,
        },
    ]


def _build_groq_tools(registry: list) -> list:
    return [
        {"type": "function", "function": {
            "name":        t["name"],
            "description": t["description"],
            "parameters":  t["parameters"],
        }}
        for t in registry
    ]


# ══════════════════════════════════════════════════════════════
# ENTRY POINT — ReAct loop
# ══════════════════════════════════════════════════════════════

async def run_agent(user_text: str, foto_path: str = None,
                    historial: list = None, user_id: int = None) -> str:
    """
    Agente autónomo con ReAct loop de 3 pasos.
    Carga y guarda historial persistente si se provee user_id.
    """
    from utils.groq_service import get_groq_client, get_context_data, chat_con_asistente

    # ── Memoria persistente ──────────────────────────────────────────
    if user_id:
        historial = cargar_historial(user_id)
    else:
        historial = historial or []

    # ── Foto ─────────────────────────────────────────────────────────
    if foto_path:
        ctx = get_context_data()
        prompt = f"El usuario mandó una foto. Caption: '{user_text}'. Responde en el contexto del taller."
        mensajes = historial[-6:] + [{"role": "user", "content": prompt}]
        respuesta = chat_con_asistente(mensajes, ctx)
        _actualizar_historial(user_id, historial, user_text, respuesta)
        return respuesta

    registry    = _get_tools_registry()
    groq_tools  = _build_groq_tools(registry)
    handler_map = {t["name"]: t["handler"] for t in registry}

    # ── Context data siempre disponible ──────────────────────────────
    try:
        ctx = get_context_data()
    except Exception:
        ctx = {}

    # ── RAG: correcciones pasadas relevantes ─────────────────────────
    rag_hint = buscar_correcciones_relevantes(user_text)

    # ── System prompt con datos reales del taller ────────────────────
    from utils.groq_service import _get_system_prompt
    system_base = _get_system_prompt(ctx)

    system_prompt = (
        system_base + "\n\n"
        "MÓDULOS DEL SISTEMA: dashboard, órdenes de servicio, cotizaciones, "
        "clientes, vehículos, proveedores, inventario, notas de venta, facturas, "
        "créditos/fiado, citas/agenda, reportes, rentabilidad.\n\n"
        "REGLAS DE HERRAMIENTAS:\n"
        "- Si el usuario pregunta algo analítico o de datos → usa consultar_db con SQL\n"
        "- Si pide crear/registrar algo → usa la herramienta específica\n"
        "- Si la pregunta es ambigua y podrías equivocarte → PREGUNTA antes de actuar\n"
        "- Si hay duda sobre a qué cliente/orden se refiere → PREGUNTA cuál\n"
        + (f"\n{rag_hint}" if rag_hint else "")
    )

    # ── Construir mensajes ────────────────────────────────────────────
    messages = [
        {"role": "system", "content": system_prompt},
        *historial[-8:],
        {"role": "user", "content": user_text},
    ]

    respuesta_final = None

    try:
        client = get_groq_client()

        # ── ReAct loop (máximo MAX_REACT_STEPS iteraciones) ──────────
        for step in range(MAX_REACT_STEPS):
            response = client.chat.completions.create(
                model=MODEL,
                messages=messages,
                tools=groq_tools,
                tool_choice="auto",
                max_tokens=1200,
                temperature=0.1,
            )

            msg = response.choices[0].message

            # ── Sin tool call → respuesta directa o pregunta aclaratoria
            if not msg.tool_calls:
                respuesta_final = (msg.content or "").strip()
                break

            # ── Con tool call ──────────────────────────────────────────
            tool_call = msg.tool_calls[0]
            tool_name = tool_call.function.name
            try:
                args = json.loads(tool_call.function.arguments)
            except Exception:
                args = {}

            logger.info(f"[AGENT] step={step+1} tool={tool_name} args={str(args)[:100]}")

            handler = handler_map.get(tool_name)
            if not handler:
                respuesta_final = f"⚠️ Herramienta '{tool_name}' no disponible."
                break

            resultado = handler(args)

            # ── Si necesita confirmación → parar y devolver al bot ────
            if isinstance(resultado, dict) and resultado.get("__confirm__"):
                respuesta_final = json.dumps(resultado)
                break

            # ── Si es PDF → parar y devolver al bot ──────────────────
            if isinstance(resultado, str) and '"pdf_path"' in resultado:
                respuesta_final = resultado
                break

            # ── Agregar resultado al contexto para siguiente paso ─────
            # Formato correcto para Groq: assistant con tool_calls + tool result
            messages.append({
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [{
                    "id":       tool_call.id,
                    "type":     "function",
                    "function": {
                        "name":      tool_name,
                        "arguments": tool_call.function.arguments,
                    }
                }]
            })
            messages.append({
                "role":         "tool",
                "tool_call_id": tool_call.id,
                "content":      str(resultado),
            })

            # Si es el último paso, pedir al LLM que formule la respuesta final
            if step == MAX_REACT_STEPS - 1:
                messages.append({
                    "role":    "user",
                    "content": "Resume los resultados anteriores en una respuesta clara y directa."
                })

        # Si llegamos aquí sin respuesta_final, pedir resumen
        if not respuesta_final:
            final_resp = client.chat.completions.create(
                model=MODEL, messages=messages, max_tokens=800, temperature=0.2
            )
            respuesta_final = (final_resp.choices[0].message.content or "").strip()

    except Exception as e:
        logger.error(f"[AGENT] run_agent error: {e}", exc_info=True)
        try:
            respuesta_final = chat_con_asistente(
                historial[-6:] + [{"role": "user", "content": user_text}], ctx
            )
        except Exception:
            respuesta_final = "❌ Error interno. Intenta de nuevo."

    if not respuesta_final:
        respuesta_final = "No pude procesar esa solicitud. ¿Puedes reformularla?"

    # ── Actualizar historial ─────────────────────────────────────────
    _actualizar_historial(user_id, historial, user_text, respuesta_final)
    return respuesta_final


def _actualizar_historial(user_id, historial, user_text, respuesta):
    """Agrega turno al historial y persiste."""
    # No guardar JSON de confirmación en el historial visible
    texto_guardado = respuesta
    if isinstance(respuesta, str) and respuesta.startswith('{"__confirm__"'):
        texto_guardado = "[Acción pendiente de confirmación]"

    historial.append({"role": "user",      "content": user_text})
    historial.append({"role": "assistant", "content": texto_guardado})

    if user_id:
        guardar_historial(user_id, historial)


def ejecutar_accion_confirmada(tool_name: str, args: dict) -> str:
    """Ejecuta una acción que fue previamente confirmada por el usuario."""
    registry    = _get_tools_registry()
    handler_map = {t["name"]: t["handler"] for t in registry}
    # Marcar como confirmado para que los handlers no pidan confirmación de nuevo
    args["__ya_confirmado__"] = True
    handler = handler_map.get(tool_name)
    if not handler:
        return f"⚠️ Herramienta '{tool_name}' no encontrada."
    try:
        return handler(args)
    except Exception as e:
        logger.error(f"[AGENT] accion_confirmada {tool_name}: {e}", exc_info=True)
        return f"❌ Error ejecutando acción: {e}"


# ══════════════════════════════════════════════════════════════
# TOOL HANDLERS
# ══════════════════════════════════════════════════════════════

def _tool_consultar_db(args: dict) -> str:
    """Ejecuta SQL SELECT de solo lectura. La IA genera el query."""
    sql = (args.get("sql") or "").strip()
    desc = args.get("descripcion", "consulta")

    if not sql:
        return "⚠️ No recibí una consulta SQL."

    # Seguridad: solo SELECT
    sql_upper = sql.upper().lstrip()
    if not sql_upper.startswith("SELECT"):
        return "❌ Solo se permiten consultas SELECT."
    for kw in ["DROP", "DELETE", "UPDATE", "INSERT", "ALTER", "CREATE", "ATTACH"]:
        if kw in sql_upper:
            return f"❌ Operación '{kw}' no permitida."

    # Agregar LIMIT si no tiene
    if "LIMIT" not in sql_upper:
        sql = sql.rstrip(";") + " LIMIT 30"

    try:
        from utils.models import get_db
        from sqlalchemy import text as _sa_text
        _db = get_db()
        try:
            _result = _db.execute(_sa_text(sql))
            cols = list(_result.keys())
            rows = _result.fetchall()
        finally:
            _db.close()

        if not rows:
            return f"ℹ️ La consulta '{desc}' no devolvió resultados."

        # Formatear resultado
        lineas = [" | ".join(str(r[i]) for i in range(len(cols))) for r in rows[:20]]
        encabezado = " | ".join(cols)
        return f"📊 *{desc}* ({len(rows)} filas)\n```\n{encabezado}\n{'─'*40}\n" + "\n".join(lineas) + "\n```"

    except Exception as e:
        logger.error(f"[DB] consultar_db: {e} | SQL: {sql[:100]}")
        return f"❌ Error en consulta: {e}"


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
            try: return datetime.strptime(f, fmt)
            except: pass
        return None

    db = get_db()
    try:
        costos_map = {it.codigo: float(it.costo or 0) for it in db.query(ItemInventario).all()}
        gan_rep = 0.0; gan_mo = 0.0; n_ord = 0

        for o in db.query(Orden).all():
            fd = _pf(o.fecha)
            if not fd or fd < inicio or (fin and fd >= fin): continue
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
                if es_mo: gan_mo  += total
                else:     gan_rep += total - (costos_map.get(ref, 0) * cant if ref else 0)

        for n in db.query(NotaVenta).filter_by(estado="pagada").all():
            if not n.fecha: continue
            try:
                nf = n.fecha if hasattr(n.fecha, "strftime") else _pf(str(n.fecha)[:10])
                if not nf or nf < inicio or (fin and nf >= fin): continue
            except: continue
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
        return (
            f"{'📈' if gan_total > 0 else '📉'} *Ganancia {label}*\n\n"
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


def _tool_top_repuestos(args: dict) -> str:
    periodo = (args.get("periodo") or "mes").lower()
    top_n   = int(args.get("top_n") or 10)
    from utils.models import get_db, Orden, NotaVenta
    import json as _j

    now = datetime.now()
    if periodo == "semana":   inicio = now - timedelta(days=7);   label = "esta semana"
    elif periodo == "año":    inicio = now - timedelta(days=365); label = "este año"
    elif periodo == "todo":   inicio = datetime(2000, 1, 1);      label = "histórico"
    else:                     inicio = now - timedelta(days=30);  label = "este mes"

    def _pf(f):
        f = (f or "").strip()[:10]
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d"):
            try: return datetime.strptime(f, fmt)
            except: pass
        return None

    agg = {}
    db = get_db()
    try:
        for o in db.query(Orden).all():
            fd = _pf(o.fecha)
            if not fd or fd < inicio: continue
            items = o.items_cotizacion or []
            if isinstance(items, str):
                try: items = _j.loads(items)
                except: items = []
            for it in (items if isinstance(items, list) else []):
                nombre = (it.get("nombre") or "").strip()
                if not nombre: continue
                cant   = float(it.get("cantidad", 1) or 1)
                precio = float(it.get("precio_unitario", 0) or 0)
                cat    = (it.get("categoria") or "").lower()
                ref    = (it.get("referencia") or it.get("ref") or "").strip()
                es_mo  = cat in ("servicio", "mano de obra") or ref == "MANO-DE-OBRA" or "mano" in nombre.lower()
                key    = nombre[:50]
                if key not in agg: agg[key] = {"nombre": key, "cantidad": 0, "ingresos": 0.0, "es_mo": es_mo}
                agg[key]["cantidad"] += cant
                agg[key]["ingresos"] += precio * cant

        for n in db.query(NotaVenta).filter_by(estado="pagada").all():
            if not n.fecha: continue
            try:
                nf = n.fecha if hasattr(n.fecha, "strftime") else _pf(str(n.fecha)[:10])
                if not nf or nf < inicio: continue
            except: continue
            items_n = n.items or []
            if isinstance(items_n, str):
                try: items_n = _j.loads(items_n)
                except: items_n = []
            for it in (items_n if isinstance(items_n, list) else []):
                nombre = (it.get("nombre") or "").strip()
                if not nombre: continue
                cant   = float(it.get("cantidad", 1) or 1)
                precio = float(it.get("precio", 0) or 0)
                es_mo  = (it.get("categoria") or "").lower() == "mano de obra"
                key    = nombre[:50]
                if key not in agg: agg[key] = {"nombre": key, "cantidad": 0, "ingresos": 0.0, "es_mo": es_mo}
                agg[key]["cantidad"] += cant
                agg[key]["ingresos"] += precio * cant

        if not agg:
            return f"ℹ️ Sin ventas registradas ({label})."

        ranking   = sorted(agg.values(), key=lambda x: x["cantidad"], reverse=True)[:top_n]
        repuestos = [r for r in ranking if not r["es_mo"]]
        mo        = [r for r in ranking if r["es_mo"]]

        txt = f"🏆 *Top más vendidos — {label}*\n\n"
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
        return f"❌ Error: {e}"
    finally:
        db.close()


def _tool_consultar_stock(args: dict) -> str:
    producto = (args.get("producto") or "").strip()
    from utils.models import get_db, ItemInventario
    db = get_db()
    try:
        if not producto:
            criticos = db.query(ItemInventario).filter(ItemInventario.stock <= ItemInventario.stock_minimo).all()
            if not criticos:
                return "✅ Todo el inventario está sobre el mínimo."
            txt = "⚠️ *Stock Crítico:*\n\n"
            for i in criticos[:10]:
                txt += f"• {i.nombre}: *{i.stock}* uds (mín: {i.stock_minimo})\n"
            return txt
        items = db.query(ItemInventario).filter(ItemInventario.nombre.ilike(f"%{producto}%")).all()
        if not items:
            return f"❌ No encontré *{producto}* en el inventario."
        if len(items) == 1:
            i = items[0]
            return (f"{'✅' if i.stock > i.stock_minimo else '⚠️'} *{i.nombre}*\n"
                    f"📦 Stock: *{i.stock}* uds\n"
                    f"💰 Precio: S/ {i.precio:.2f}\n"
                    f"🔖 Código: {i.codigo or '—'}")
        txt = f"🔍 *{len(items)}* productos:\n\n"
        for i in items[:8]:
            txt += f"{'✅' if i.stock > i.stock_minimo else '⚠️'} {i.nombre} — *{i.stock}* uds @ S/{i.precio:.2f}\n"
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
            return (f"❌ No encontré órdenes para *{referencia}*." if referencia
                    else "ℹ️ No hay órdenes activas.")

        emojis = {"APROBACIÓN":"⏳","REPUESTOS":"🔧",
                  "EN PROCESO":"⚙️","ENTREGA":"🚗","ARCHIVADO":"✅"}
        txt = "📋 *Órdenes:*\n\n"
        for o in ordenes:
            cl = ""
            if o.cliente_id:
                c = db.query(Cliente).filter_by(id=o.cliente_id).first()
                if c: cl = f"{c.nombre} {c.apellidos or ''}".strip()
            em = emojis.get(o.estado, "🔵")
            txt += (f"{em} *{o.consecutivo}* — {o.estado}\n"
                    f"   🚗 {o.vehiculo_placa or '—'} | 👤 {cl or '—'}\n"
                    f"   📅 {str(o.fecha or '')[:10]} | {(o.motivo or '')[:40]}\n\n")
        return txt
    finally:
        db.close()


def _tool_buscar_contacto(args: dict) -> str:
    nombre = (args.get("nombre") or "").strip()
    tipo   = (args.get("tipo") or "cualquiera").lower()
    if not nombre:
        return "⚠️ Dime el nombre del cliente o proveedor."

    from utils.models import get_db, Cliente, Proveedor
    db = get_db()
    try:
        resultados = []

        if tipo in ("cliente", "cualquiera"):
            clientes = db.query(Cliente).filter(
                (Cliente.nombre.ilike(f"%{nombre}%")) |
                (Cliente.apellidos.ilike(f"%{nombre}%"))
            ).limit(5).all()
            for c in clientes:
                resultados.append(
                    f"👤 *{c.nombre} {c.apellidos or ''}*\n"
                    f"   📱 {c.telefono or '—'} | ✉️ {c.email or '—'}\n"
                    f"   📍 {c.direccion or '—'}"
                )

        if tipo in ("proveedor", "cualquiera"):
            provs = db.query(Proveedor).filter(
                Proveedor.nombre.ilike(f"%{nombre}%")
            ).limit(5).all()
            for p in provs:
                resultados.append(
                    f"🏢 *{p.nombre}*\n"
                    f"   📱 {p.telefono or '—'} | ✉️ {p.email or '—'}\n"
                    f"   📍 {p.direccion or '—'}"
                )

        if not resultados:
            return f"❌ No encontré '{nombre}' en clientes ni proveedores."

        return "\n\n".join(resultados)
    finally:
        db.close()


def _tool_ver_creditos(args: dict) -> str:
    nombre_filtro = (args.get("nombre_filtro") or "").strip()
    try:
        from utils.telegram_bot import _buscar_creditos_por_nombre, _get_todos_creditos_pendientes, _formato_credito
        creditos = _buscar_creditos_por_nombre(nombre_filtro) if nombre_filtro else _get_todos_creditos_pendientes()
        if not creditos:
            return "✅ No hay créditos pendientes."
        texto = f"📋 *Créditos Pendientes* ({len(creditos)})\n\n"
        for c in creditos[:10]:
            texto += _formato_credito(c) + "\n\n"
        return texto
    except Exception as e:
        return f"❌ Error: {e}"


def _tool_buscar_pdf(args: dict) -> str:
    referencia = (args.get("referencia") or "").strip()
    if not referencia:
        return "⚠️ Dime el número de cotización u orden."

    pdfs_dir = os.path.join(BASE_DIR, "pdfs")
    if not os.path.exists(pdfs_dir):
        return "❌ No hay PDFs generados aún."

    # Buscar archivo que contenga la referencia
    ref_clean = referencia.upper().replace(" ", "").replace("-", "")
    encontrados = []
    for fname in os.listdir(pdfs_dir):
        fname_clean = fname.upper().replace("-", "").replace("_", "")
        if ref_clean in fname_clean:
            encontrados.append(os.path.join(pdfs_dir, fname))

    if not encontrados:
        return f"❌ No encontré PDF para '{referencia}'."

    # Devolver el más reciente
    encontrados.sort(key=lambda x: os.path.getmtime(x), reverse=True)
    pdf_path = encontrados[0]
    return json.dumps({
        "pdf_path": pdf_path,
        "numero":   referencia,
        "cliente":  "",
    })


def _tool_crear_nota_venta(args: dict) -> str:
    # Con confirmación si no fue ya confirmado
    if not args.get("__ya_confirmado__"):
        items_raw = args.get("items", [])
        if not items_raw:
            return "⚠️ No detecté productos para la nota de venta."
        subtotal_est = sum(float(i.get("precio", 0) or 0) * float(i.get("cantidad", 1) or 1) for i in items_raw)
        items_txt = "\n".join(
            f"  • {i.get('cantidad',1)}x {i.get('nombre','?')} — S/ {float(i.get('precio',0)):.2f}"
            for i in items_raw
        )
        preview = (
            f"📝 *Confirmar Nota de Venta*\n\n"
            f"👤 Cliente: {args.get('cliente_nombre', 'Mostrador') or 'Mostrador'}\n\n"
            f"📦 *Ítems:*\n{items_txt}\n\n"
            f"💰 *Total estimado: S/ {subtotal_est:.2f}*\n\n"
            f"¿Confirmas?"
        )
        return {"__confirm__": True, "tool": "crear_nota_venta", "args": args, "preview": preview}

    # Ejecución real
    items_raw = args.get("items", [])
    from utils.models import get_db, NotaVenta, ItemInventario, Cliente
    from sqlalchemy import text as sqlt
    db = get_db()
    try:
        items_procesados = []
        for it in items_raw:
            nombre = (it.get("nombre") or "").strip()
            cant   = float(it.get("cantidad", 1) or 1)
            precio = float(it.get("precio", 0) or 0)
            tipo   = (it.get("tipo") or "repuesto").lower()
            codigo = ""
            if precio == 0 and nombre and tipo != "mano_obra":
                prod = db.query(ItemInventario).filter(ItemInventario.nombre.ilike(f"%{nombre}%")).first()
                if prod:
                    precio = float(prod.precio); nombre = prod.nombre; codigo = prod.codigo or ""
            items_procesados.append({
                "codigo": codigo, "nombre": nombre or "Sin nombre",
                "cantidad": cant, "precio": precio, "subtotal": round(precio * cant, 2),
                "categoria": "Mano de obra" if tipo == "mano_obra" else "Repuesto",
            })
        subtotal = round(sum(i["subtotal"] for i in items_procesados), 2)
        res = db.execute(sqlt("SELECT numero FROM notas_venta ORDER BY id DESC LIMIT 1")).fetchone()
        if res and res[0] and res[0].startswith("NV-"):
            try: numero = f"NV-{int(res[0].split('-')[1]) + 1:05d}"
            except: numero = f"NV-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        else: numero = "NV-00001"
        cliente_id = None
        cliente_nombre = (args.get("cliente_nombre") or "Mostrador").strip()
        if cliente_nombre and cliente_nombre.lower() != "mostrador":
            cl = db.query(Cliente).filter(Cliente.nombre.ilike(f"%{cliente_nombre.split()[0]}%")).first()
            if cl: cliente_id = str(cl.id); cliente_nombre = f"{cl.nombre} {cl.apellidos or ''}".strip()
        db.add(NotaVenta(numero=numero, cliente_id=cliente_id, cliente_nombre=cliente_nombre,
                         subtotal=subtotal, igv=0, total=subtotal, estado="pagada",
                         notas="Creada vía Telegram Bot", items=items_procesados))
        for it in items_procesados:
            if it.get("codigo"):
                inv = db.query(ItemInventario).filter_by(codigo=it["codigo"]).first()
                if inv: inv.stock = max(0, inv.stock - int(it["cantidad"]))
        db.commit()
        items_txt = "\n".join(f"  • {it['cantidad']}x {it['nombre']} — S/ {it['subtotal']:.2f}" for it in items_procesados)
        return (f"✅ *Nota de Venta {numero} creada*\n\n"
                f"👤 Cliente: {cliente_nombre}\n\n"
                f"📦 *Productos:*\n{items_txt}\n\n"
                f"💰 *Total: S/ {subtotal:.2f}*\n"
                f"_Ya aparece en Notas de Venta._")
    except Exception as e:
        db.rollback(); logger.error(f"[AGENT] crear_nota_venta: {e}", exc_info=True)
        return f"❌ Error: {e}"
    finally:
        db.close()


def _tool_crear_cotizacion(args: dict) -> str:
    if not args.get("items"):
        return "⚠️ No detecté ítems para la cotización."
    try:
        from utils.telegram_bot import _crear_cotizacion_desde_bot
        msg, pdf_path = _crear_cotizacion_desde_bot(args)
        if pdf_path and os.path.exists(pdf_path):
            return json.dumps({"pdf_path": pdf_path, "numero": "COT", "cliente": args.get("cliente_nombre", "Cliente")})
        return msg
    except Exception as e:
        logger.error(f"[AGENT] crear_cotizacion: {e}", exc_info=True)
        return f"❌ Error: {e}"


def _tool_crear_orden(args: dict) -> str:
    from utils.models import get_db, Orden, Cliente, Vehiculo
    from sqlalchemy import text as sqlt
    cliente_nombre = (args.get("cliente_nombre") or "").strip()
    placa  = (args.get("placa") or "").upper().replace("-", "").replace(" ", "")
    motivo = (args.get("motivo") or "Sin especificar").strip()
    if not placa and not cliente_nombre:
        return "⚠️ Necesito la placa o el nombre del cliente."
    db = get_db()
    try:
        cliente_id = None
        if cliente_nombre:
            cl = db.query(Cliente).filter(Cliente.nombre.ilike(f"%{cliente_nombre.split()[0]}%")).first()
            if cl: cliente_id = cl.id
        if placa and not cliente_id:
            v = db.query(Vehiculo).filter_by(placa=placa).first()
            if v and v.cliente_id: cliente_id = v.cliente_id
        res = db.execute(sqlt("SELECT consecutivo FROM ordenes ORDER BY id DESC LIMIT 1")).fetchone()
        if res and res[0] and res[0].startswith("OS-"):
            try: consecutivo = f"OS-{int(res[0].split('-')[1]) + 1:05d}"
            except: consecutivo = f"OS-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        else: consecutivo = "OS-00001"
        db.add(Orden(consecutivo=consecutivo, fecha=datetime.now().strftime("%Y-%m-%d"),
                     cliente_id=cliente_id, vehiculo_placa=placa or None,
                     motivo=motivo, estado="EN PROCESO", items_cotizacion="[]"))
        db.commit()
        return (f"✅ *Orden {consecutivo} creada*\n\n"
                f"👤 {cliente_nombre or '—'} | 🚗 {placa or '—'}\n"
                f"🔧 {motivo}\n_Agrega el presupuesto desde el panel web._")
    except Exception as e:
        db.rollback(); return f"❌ Error: {e}"
    finally:
        db.close()


def _tool_cambiar_estado_orden(args: dict) -> str:
    referencia   = (args.get("referencia") or "").strip()
    nuevo_estado = (args.get("nuevo_estado") or "").strip().upper()
    if not referencia or not nuevo_estado:
        return "⚠️ Necesito el número de orden y el nuevo estado."

    estados_validos = {"APROBACIÓN", "REPUESTOS", "EN PROCESO", "ENTREGA", "ARCHIVADO"}
    if nuevo_estado not in estados_validos:
        return f"❌ Estado inválido. Opciones: {', '.join(estados_validos)}"

    if not args.get("__ya_confirmado__"):
        preview = (f"🔄 *Cambiar estado de orden*\n\n"
                   f"🔍 Orden: *{referencia}*\n"
                   f"➡️ Nuevo estado: *{nuevo_estado}*\n\n"
                   f"¿Confirmas?")
        return {"__confirm__": True, "tool": "cambiar_estado_orden", "args": args, "preview": preview}

    from utils.models import get_db, Orden
    db = get_db()
    try:
        ref_clean = referencia.upper().replace("-", "").replace(" ", "")
        orden = db.query(Orden).filter(
            (Orden.consecutivo.ilike(f"%{referencia}%")) |
            (Orden.vehiculo_placa.ilike(f"%{ref_clean}%"))
        ).first()
        if not orden:
            return f"❌ No encontré la orden '{referencia}'."
        estado_anterior = orden.estado
        orden.estado = nuevo_estado
        db.commit()
        return (f"✅ *Estado actualizado*\n\n"
                f"📋 {orden.consecutivo}\n"
                f"🔄 {estado_anterior} → *{nuevo_estado}*")
    except Exception as e:
        db.rollback(); return f"❌ Error: {e}"
    finally:
        db.close()


def _tool_crear_credito(args: dict) -> str:
    if not args.get("__ya_confirmado__"):
        nombre = args.get("cliente_nombre", "—")
        items  = args.get("items", [])
        total  = float(args.get("total", 0) or 0)
        if not total and items:
            total = sum(float(i.get("precio", 0)) * float(i.get("cantidad", 1)) for i in items)
        preview = (f"💳 *Confirmar Crédito / Fiado*\n\n"
                   f"👤 Cliente: *{nombre}*\n"
                   f"💰 Total: *S/ {total:.2f}*\n\n¿Confirmas?")
        return {"__confirm__": True, "tool": "crear_credito", "args": args, "preview": preview}

    try:
        from utils.telegram_bot import _crear_credito_bot
        ok = _crear_credito_bot(args)
        if ok:
            nombre = args.get("cliente_nombre", "—")
            items  = args.get("items", [])
            total  = float(args.get("total", 0) or 0)
            if not total and items:
                total = sum(float(i.get("precio", 0)) * float(i.get("cantidad", 1)) for i in items)
            return (f"✅ *Crédito registrado*\n\n"
                    f"👤 {nombre}\n💰 *S/ {total:.2f}* pendiente\n"
                    f"_Ya aparece en Créditos / Fiado._")
        return "❌ Error guardando el crédito."
    except Exception as e:
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
        c  = creditos[0]
        ok = _registrar_abono_bot(c["id"], monto, args.get("metodo_pago", "") or "")
        if ok:
            nuevo_pendiente = max(0, float(c["pendiente"]) - monto)
            estado_msg = "✅ *¡Crédito cancelado!*" if nuevo_pendiente <= 0 else f"📊 Pendiente: *S/ {nuevo_pendiente:.2f}*"
            return (f"✅ *Abono registrado*\n\n"
                    f"👤 {c['cliente_nombre']}\n"
                    f"💰 Abono: S/ {monto:.2f}\n"
                    f"💳 Método: {args.get('metodo_pago', '—') or '—'}\n"
                    f"{estado_msg}")
        return "❌ Error registrando el abono."
    except Exception as e:
        return f"❌ Error: {e}"


def _tool_crear_cita(args: dict) -> str:
    if not args.get("__ya_confirmado__"):
        preview = (f"📅 *Confirmar Cita*\n\n"
                   f"👤 {args.get('cliente_nombre', '—')}\n"
                   f"📅 {args.get('fecha', '—')} a las {args.get('hora', '—')}\n"
                   f"🔧 {args.get('motivo', '—')}\n\n¿Confirmas?")
        return {"__confirm__": True, "tool": "crear_cita", "args": args, "preview": preview}

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
            cl = db.query(Cliente).filter(Cliente.nombre.ilike(f"%{cliente_nombre.split()[0]}%")).first()
            if cl: cliente_id = cl.id
        db.execute(sqlt("""
            INSERT INTO citas (cliente_id, cliente_nombre, fecha, hora, motivo, placa, estado, creado_por)
            VALUES (:cid, :cn, :fecha, :hora, :motivo, :placa, 'pendiente', 'Bot Telegram')
        """), {"cid": cliente_id, "cn": cliente_nombre, "fecha": fecha,
               "hora": hora, "motivo": motivo, "placa": placa or None})
        db.commit()
        return (f"✅ *Cita agendada*\n\n"
                f"👤 {cliente_nombre}\n📅 {fecha} a las {hora}\n"
                f"🔧 {motivo}\n🚗 {placa or '—'}\n"
                f"_Ya aparece en Citas / Agenda._")
    except Exception as e:
        db.rollback(); return f"❌ Error: {e}"
    finally:
        db.close()

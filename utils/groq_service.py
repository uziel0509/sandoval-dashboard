"""
SANDOVAL Dashboard - Servicio Groq IA
Asistente inteligente del taller: análisis de negocio + OCR de facturas
Completamente aislado del bot universitario Jarvis
"""

import os
import json
import base64
import logging
from datetime import datetime
from groq import Groq

logger = logging.getLogger(__name__)

# ─── Cliente Groq ───────────────────────────────────────────────────────────

def get_groq_client() -> Groq:
    """Obtiene el cliente Groq con la API key configurada"""
    from utils.models import get_config
    api_key = get_config('groq_api_key', '')
    if api_key:
        api_key = api_key.strip().strip("'").strip('"')
    if not api_key:
        api_key = os.getenv('GROQ_API_KEY', '').strip().strip("'").strip('"')
    if not api_key:
        raise ValueError("API Key de Groq no configurada. Ve a Configuración → IA Sandoval.")
    if not api_key.startswith('gsk_'):
        raise ValueError("API Key INVALIDA. Debe empezar con 'gsk_'. Verifica que la copiaste bien.")
    return Groq(api_key=api_key)


# ─── System Prompts ──────────────────────────────────────────────────────────

def _get_system_prompt(context_data: dict) -> str:
    """Genera el system prompt con datos en tiempo real e históricos del taller"""
    fecha = datetime.now().strftime('%d/%m/%Y %H:%M')
    
    # Tiempo real
    ordenes_activas  = context_data.get('ordenes_activas', 0)
    ingresos_mes     = context_data.get('ingresos_mes', 0)
    ingresos_semana  = context_data.get('ingresos_semana', 0)
    clientes_total   = context_data.get('clientes_total', 0)
    stock_critico    = context_data.get('stock_critico', [])
    ordenes_hoy      = context_data.get('ordenes_hoy', [])
    
    # Historia
    ordenes_completadas_total  = context_data.get('ordenes_completadas_total', 0)
    ingresos_total_historico   = context_data.get('ingresos_total_historico', 0)
    top_meses                  = context_data.get('top_meses', 'Sin datos')
    ordenes_semana_count       = context_data.get('ordenes_semana_count', 0)
    top_clientes               = context_data.get('top_clientes', 'Sin datos')
    total_vehiculos            = context_data.get('total_vehiculos', 0)
    total_productos            = context_data.get('total_productos', 0)
    valor_inventario           = context_data.get('valor_inventario', 0)
    top_motivos                = context_data.get('top_motivos', 'Sin datos')
    ultimas_completadas        = context_data.get('ultimas_completadas', [])

    top_repuestos = context_data.get('top_repuestos', '  (Sin datos)')
    vehiculos_lista = context_data.get('vehiculos_lista', [])
    cotizaciones_detalle = context_data.get('cotizaciones_detalle', [])

    stock_str = "\n".join([f"  ⚠ {s['nombre']}: {s['stock']} uds (mín: {s['minimo']})" for s in stock_critico[:8]]) if stock_critico else "  ✅ Ninguno en stock crítico"
    ordenes_str = "\n".join([f"  🔧 {o}" for o in ordenes_hoy]) if ordenes_hoy else "  (Ninguna activa)"
    ultimas_str = "\n".join(ultimas_completadas) if ultimas_completadas else "  (Sin historial)"
    vehiculos_str = "\n".join(vehiculos_lista) if vehiculos_lista else "  (Sin vehículos registrados)"
    cotizaciones_str = "\n".join(cotizaciones_detalle) if cotizaciones_detalle else "  (Sin cotizaciones pendientes)"

    return f"""Eres el Asistente IA de MECÁNICA Y REPUESTOS SANDOVAL EIRL.
Tu nombre es "Asistente Sandoval". Eres directo, profesional y conoces todos los datos del taller.
Fecha y hora: {fecha}

╔══════════════════════════════════════════════════════════╗
║            MEMORIA HISTÓRICA COMPLETA DEL TALLER         ║
╠══════════════════════════════════════════════════════════╣
║ RESUMEN HISTÓRICO TOTAL                                   ║
╠══════════════════════════════════════════════════════════╣
  • Órdenes completadas TOTAL histórico:  {ordenes_completadas_total}
  • Ingresos TOTALES históricos:           S/ {ingresos_total_historico:,.2f}
  • Clientes registrados:                  {clientes_total}
  • Vehículos en el sistema:               {total_vehiculos}
  • Productos en inventario:               {total_productos} (Valor: S/ {valor_inventario:,.2f})

╠══════════════════════════════════════════════════════════╣
║ ESTE MES ({datetime.now().strftime('%B %Y').upper()})
╠══════════════════════════════════════════════════════════╣
  • Ingresos del mes:     S/ {ingresos_mes:,.2f}
  • Órdenes activas:      {ordenes_activas}
  • Órdenes completadas esta semana: {ordenes_semana_count} (S/ {ingresos_semana:,.2f})

╠══════════════════════════════════════════════════════════╣
║ RANKING DE MESES POR INGRESOS
╠══════════════════════════════════════════════════════════╣
  {top_meses}

╠══════════════════════════════════════════════════════════╣
║ CLIENTES MÁS FRECUENTES
╠══════════════════════════════════════════════════════════╣
{top_clientes if top_clientes else "  Sin datos suficientes"}

╠══════════════════════════════════════════════════════════╣
║ TIPOS DE TRABAJO MÁS FRECUENTES (HISTÓRICO)
╠══════════════════════════════════════════════════════════╣
  {top_motivos}

╠══════════════════════════════════════════════════════════╣
║ ÓRDENES ACTIVAS EN ESTE MOMENTO (CON PRESUPUESTO COMPLETO)
╠══════════════════════════════════════════════════════════╣
{ordenes_str}

╠══════════════════════════════════════════════════════════╣
║ COTIZACIONES PENDIENTES
╠══════════════════════════════════════════════════════════╣
{cotizaciones_str}

╠══════════════════════════════════════════════════════════╣
║ VEHÍCULOS REGISTRADOS (CON DUEÑOS Y PLACAS)
╠══════════════════════════════════════════════════════════╣
{vehiculos_str}

╠══════════════════════════════════════════════════════════╣
║ ÚLTIMAS 10 ÓRDENES COMPLETADAS
╠══════════════════════════════════════════════════════════╣
{ultimas_str}

╠══════════════════════════════════════════════════════════╣
║ REPUESTOS / SERVICIOS MÁS COTIZADOS (HISTÓRICO TOTAL)
╠══════════════════════════════════════════════════════════╣
{top_repuestos}

╠══════════════════════════════════════════════════════════╣
║ STOCK CRÍTICO (por debajo del mínimo)
╠══════════════════════════════════════════════════════════╣
{stock_str}
╚══════════════════════════════════════════════════════════╝

CAPACIDADES:
- Analizar el negocio completo usando la memoria histórica real de arriba
- Responder preguntas de cualquier período: hoy, semana, mes, histórico
- Identificar tendencias, patrones, clientes frecuentes
- Dar recomendaciones basadas en datos reales
- Leer facturas cuando el usuario sube una imagen

REGLAS:
- Usa SIEMPRE los datos reales de esta memoria para responder
- Si el dato pedido no está en la memoria, dilo claramente
- Sé conciso pero preciso con los números"""


FACTURA_PROMPT = """Eres un sistema experto en lectura de facturas y boletas.
Analiza la imagen de la factura y extrae TODA la información posible.

Devuelve ÚNICAMENTE un JSON válido con esta estructura exacta:
{
  "proveedor": "Nombre del proveedor/tienda",
  "ruc_proveedor": "El RUC o DNI del local, si figura. Sino vacio.",
  "numero_factura": "Número de factura o boleta",
  "fecha": "DD/MM/YYYY o la fecha que aparezca",
  "subtotal": 0.00,
  "igv": 0.00,
  "total": 0.00,
  "moneda": "PEN",
  "tipo_detectado": "mercaderia|gasto|mixto",
  "categoria_gasto": "gasolina|medicinas|alimentacion|servicios|otros",
  "items": [
    {
      "nombre": "Nombre del producto/servicio",
      "cantidad": 1,
      "precio_unitario": 0.00,
      "total": 0.00,
      "unidad": "unidad|litro|kg|etc"
    }
  ],
  "notas": "Cualquier observación relevante"
}

Si no puedes leer algún dato claramente, usa null o 0.
El campo tipo_detectado debe ser:
- "mercaderia": si son repuestos, aceites, filtros, herramientas para el taller
- "gasto": si es gasolina, medicinas, alimentación, servicios del hogar/empresa
- "mixto": si tiene ambos tipos
NO incluyas texto adicional fuera del JSON."""


# ─── Funciones principales ────────────────────────────────────────────────────

def chat_con_asistente(mensajes: list, context_data: dict = None) -> str:
    """
    Envía mensajes al Asistente Sandoval y devuelve la respuesta.
    mensajes: lista de {'role': 'user'|'assistant', 'content': str}
    context_data: datos en tiempo real del taller
    """
    try:
        client = get_groq_client()
        system = _get_system_prompt(context_data or {})
        
        all_messages = [{"role": "system", "content": system}] + mensajes[-20:]  # Últimos 20 mensajes
        
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=all_messages,
            max_tokens=1024,
            temperature=0.7,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"Error Groq chat: {e}")
        return f"⚠️ Error al conectar con la IA: {str(e)}"


def analizar_factura_imagen(image_path: str) -> dict:
    """
    Usa Groq Vision para leer una factura desde una imagen.
    Devuelve dict con los datos extraídos.
    """
    try:
        client = get_groq_client()
        
        # Convertir imagen a base64
        with open(image_path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode("utf-8")
        
        # Detectar tipo MIME
        ext = os.path.splitext(image_path)[1].lower()
        mime_map = {'.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', 
                    '.png': 'image/png', '.webp': 'image/webp'}
        mime_type = mime_map.get(ext, 'image/jpeg')
        
        response = client.chat.completions.create(
            model="meta-llama/llama-4-scout-17b-16e-instruct", # Modelo de vision estable de Groq
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": FACTURA_PROMPT},
                    {"type": "image_url", "image_url": {
                        "url": f"data:{mime_type};base64,{img_b64}"
                    }}
                ]
            }],
            max_tokens=2000,
            temperature=0.1,
        )
        
        raw = response.choices[0].message.content.strip()
        # Limpiar posible markdown
        raw = raw.replace("```json", "").replace("```", "").strip()
        return json.loads(raw)
        
    except json.JSONDecodeError as e:
        logger.error(f"Groq Vision respuesta inválida JSON: {e}")
        return {"error": "No se pudo parsear la respuesta de la IA", "raw": raw if 'raw' in locals() else ""}
    except Exception as e:
        logger.error(f"Error Groq Vision: {e}")
        return {"error": str(e)}


def analizar_intencion_cotizacion(texto: str) -> dict:
    """Evalúa si el texto es para cotizar y devuelve los datos estructurados"""
    try:
        client = get_groq_client()
        prompt = """Determina si el texto es una solicitud para CREAR o HACER UNA COTIZACIÓN o presupuesto.
Si ES una cotización, responde ÚNICAMENTE con JSON válido:
{
  "is_cotizacion": true,
  "placa": "XYZ-123",
  "cliente_nombre": "Juan",
  "telefono": "999999999",
  "kilometraje": "10000",
  "items": [
     {"nombre": "Cambio aceite", "cantidad": 1, "precio": 120, "tipo": "servicio"}
  ]
}
Si un dato no se menciona, pon "". Deduce precios y cantidades implícitas si es posible.
Si NO es una solicitud de cotización, responde ÚNICAMENTE: {"is_cotizacion": false}"""

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": texto}
            ],
            response_format={"type": "json_object"},
            max_tokens=1000,
            temperature=0.1,
        )
        return json.loads(response.choices[0].message.content.strip())
    except Exception as e:
        logger.error(f"Error AI intencion cotizacion: {e}")
        return {"is_cotizacion": False}


def get_context_data() -> dict:
    """
    Obtiene todos los datos históricos y en tiempo real del taller
    para inyectar al prompt de la IA.
    """
    try:
        from utils.models import get_db, Orden, Cliente, ItemInventario, Vehiculo
        import json as _json
        db = get_db()
        try:
            # ── Órdenes activas ──────────────────────────────────────
            ordenes_activas_q = db.query(Orden).filter(
                Orden.estado.notin_(['ARCHIVADO'])
            ).all()
            ordenes_activas = len(ordenes_activas_q)
            
            ordenes_activas_detalle = []
            for o in ordenes_activas_q:
                items = o.items_cotizacion or []
                if isinstance(items, str):
                    try: items = _json.loads(items)
                    except: items = []
                # Calcular total del presupuesto
                total_o = sum(float(it.get('total', 0) or 0) for it in items if isinstance(it, dict) and it.get('categoria') not in ('Resumen', 'Impuesto', 'Total'))
                items_str = ', '.join([
                    f"{it.get('nombre','')[:30]} x{it.get('cantidad',1)} @S/{float(it.get('precio_unitario', it.get('precio', 0)) or 0):,.1f} = S/{float(it.get('total',0) or 0):,.1f}"
                    for it in items if isinstance(it, dict) and it.get('nombre') and it.get('categoria') not in ('Resumen', 'Impuesto', 'Total')
                ])
                # Buscar nombre del cliente
                cliente_nombre = ''
                if o.cliente_id:
                    cl = db.query(Cliente).filter_by(id=o.cliente_id).first()
                    if cl: cliente_nombre = f"{cl.nombre} {cl.apellidos or ''}".strip()
                ordenes_activas_detalle.append(
                    f"{o.consecutivo} | ESTADO: {o.estado} | Placa: {getattr(o,'vehiculo_placa','')} | Cliente: {cliente_nombre} | "
                    f"Motivo: {(o.motivo or '')[:60]} | Presupuesto: S/ {total_o:,.2f} | "
                    f"Items: {items_str[:200] or 'Sin ítems'}"
                )

            # ── Órdenes archivadas (historial completo) ──────────────
            ordenes_archivadas = db.query(Orden).filter(
                Orden.estado == 'ARCHIVADO'
            ).order_by(Orden.fecha.desc()).all()
            
            # Ingresos totales históricos y por mes
            ingresos_por_mes = {}
            ingresos_total_historico = 0
            ordenes_completadas_total = len(ordenes_archivadas)
            
            for o in ordenes_archivadas:
                items = o.items_cotizacion or []
                if isinstance(items, str):
                    try: items = _json.loads(items)
                    except: items = []
                total_orden = sum(float(item.get('total', 0) or 0) for item in items if isinstance(item, dict))
                ingresos_total_historico += total_orden
                
                # Agrupar por mes YYYY-MM
                mes = str(o.fecha or '')[:7] if o.fecha else 'Sin fecha'
                ingresos_por_mes[mes] = ingresos_por_mes.get(mes, 0) + total_orden

            # Mes actual
            mes_actual = datetime.now().strftime('%Y-%m')
            ingresos_mes = ingresos_por_mes.get(mes_actual, 0)
            
            # Semana actual (últimos 7 días)
            from datetime import timedelta
            hace_7_dias = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
            ordenes_semana = [o for o in ordenes_archivadas if str(o.fecha or '') >= hace_7_dias]
            ingresos_semana = 0
            for o in ordenes_semana:
                items = o.items_cotizacion or []
                if isinstance(items, str):
                    try: items = _json.loads(items)
                    except: items = []
                ingresos_semana += sum(float(i.get('total', 0) or 0) for i in items if isinstance(i, dict))

            # Top 5 meses con más ingresos
            top_meses = sorted(ingresos_por_mes.items(), key=lambda x: x[1], reverse=True)[:6]
            top_meses_str = " | ".join([f"{m}: S/{v:,.0f}" for m, v in top_meses])

            # ── Clientes ─────────────────────────────────────────────
            total_clientes = db.query(Cliente).count()
            
            # Clientes más frecuentes (por número de órdenes)
            clientes_frecuencia = {}
            for o in ordenes_archivadas:
                if o.cliente_id:
                    clientes_frecuencia[o.cliente_id] = clientes_frecuencia.get(o.cliente_id, 0) + 1
            
            top_clientes_ids = sorted(clientes_frecuencia.items(), key=lambda x: x[1], reverse=True)[:5]
            top_clientes_str = ''
            for cid, cnt in top_clientes_ids:
                cl = db.query(Cliente).filter_by(id=cid).first()
                if cl:
                    top_clientes_str += f"\n  • {cl.nombre} {cl.apellidos or ''} — {cnt} visita(s)"

            # ── Inventario ───────────────────────────────────────────
            todos_items = db.query(ItemInventario).all()
            total_productos = len(todos_items)
            stock_critico = [
                {'nombre': i.nombre, 'stock': i.stock, 'minimo': i.stock_minimo}
                for i in todos_items if i.stock <= i.stock_minimo
            ]
            valor_total_inventario = sum((i.precio or 0) * (i.stock or 0) for i in todos_items)
            
            # ── Vehículos ────────────────────────────────────────────
            vehiculos_q = db.query(Vehiculo).all()
            total_vehiculos = len(vehiculos_q)
            vehiculos_lista = []
            for v in vehiculos_q:
                dueno = "Desconocido"
                if getattr(v, 'cliente_id', None):
                    cl = db.query(Cliente).filter_by(id=v.cliente_id).first()
                    if cl: dueno = f"{cl.nombre} {cl.apellidos or ''}".strip()
                vehiculos_lista.append(f"  🚗 {v.placa} | Dueño: {dueno} | {v.marca} {v.modelo}")
                
            # ── Cotizaciones ─────────────────────────────────────────
            cotizaciones_q = db.query(Orden).filter(Orden.estado == 'COTIZACIÓN').all()
            cotizaciones_detalle = []
            for c in cotizaciones_q:
                try: 
                    items_cot = _json.loads(c.items_cotizacion) if isinstance(c.items_cotizacion, str) else (c.items_cotizacion or [])
                    cot_total = sum(float(i.get('total', 0) or 0) for i in items_cot if isinstance(i, dict))
                except: cot_total = 0
                cotizaciones_detalle.append(f"  📝 {c.consecutivo} | Placa: {c.vehiculo_placa} | Dueño: {c.cliente_nombre} | S/ {cot_total:,.2f}")
            
            # ── Órdenes por tipo de trabajo (motivos más frecuentes) ─
            motivos = {}
            for o in ordenes_archivadas:
                mot = (o.motivo or 'Sin especificar')[:30]
                motivos[mot] = motivos.get(mot, 0) + 1
            top_motivos = sorted(motivos.items(), key=lambda x: x[1], reverse=True)[:5]
            top_motivos_str = " | ".join([f"{m}({c})" for m, c in top_motivos])

            # ── Últimas 10 órdenes completadas (con repuestos) ──────
            ultimas_completadas = []
            top_repuestos = {}  # Acumular repuestos más usados
            
            for o in ordenes_archivadas[:10]:
                items = o.items_cotizacion or []
                if isinstance(items, str):
                    try: items = _json.loads(items)
                    except: items = []
                total_o = sum(float(i.get('total', 0) or 0) for i in items if isinstance(i, dict))
                items_str = ', '.join([
                    f"{i.get('nombre','')[:25]} x{i.get('cantidad',1)} @S/{float(i.get('precio_unitario', i.get('precio', i.get('costo', 0))) or 0):,.1f}"
                    for i in items[:5] if isinstance(i, dict) and i.get('nombre')
                ])
                ultimas_completadas.append(
                    f"  {o.consecutivo} | {str(o.fecha or '')[:10]} | {getattr(o,'vehiculo_placa','')} | S/{total_o:,.0f} | {items_str or 'Sin ítems'}"
                )

            # ── Top repuestos/servicios más cotizados (historial TOTAL) ──
            for o in ordenes_archivadas:
                items = o.items_cotizacion or []
                if isinstance(items, str):
                    try: items = _json.loads(items)
                    except: items = []
                for item in items:
                    if isinstance(item, dict) and item.get('nombre'):
                        nombre = item['nombre'][:40]
                        cant = int(item.get('cantidad', 1) or 1)
                        top_repuestos[nombre] = top_repuestos.get(nombre, 0) + cant
            
            top_repuestos_sorted = sorted(top_repuestos.items(), key=lambda x: x[1], reverse=True)[:10]
            top_repuestos_str = "\n".join([f"  • {n}: {c} unidades cotizadas" for n, c in top_repuestos_sorted]) if top_repuestos_sorted else "  (Sin datos de repuestos)"

            # ── Órdenes activas detalladas ───────────────────────────
            ordenes_hoy = ordenes_activas_detalle  # todas sin limite


            return {
                # Tiempo real
                'ordenes_activas': ordenes_activas,
                'ordenes_hoy': ordenes_hoy,
                'ingresos_mes': ingresos_mes,
                'clientes_total': total_clientes,
                'stock_critico': stock_critico,
                # Historia completa
                'ordenes_completadas_total': ordenes_completadas_total,
                'ingresos_semana': ingresos_semana,
                'ingresos_total_historico': ingresos_total_historico,
                'top_meses': top_meses_str,
                'ordenes_semana_count': len(ordenes_semana),
                'top_clientes': top_clientes_str,
                'total_vehiculos': total_vehiculos,
                'total_productos': total_productos,
                'valor_inventario': valor_total_inventario,
                'top_motivos': top_motivos_str,
                'ultimas_completadas': ultimas_completadas,
                'top_repuestos': top_repuestos_str,
                'vehiculos_lista': vehiculos_lista,
                'cotizaciones_detalle': cotizaciones_detalle,
            }
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Error obteniendo context data: {e}")
        return {}


FACTURA_HISTORICA_PROMPT = """Eres un experto en lectura de facturas automotrices peruanas.
Analiza la imagen y extrae los datos para un registro histórico.

Devuelve ÚNICAMENTE un JSON válido con esta estructura exacta:
{
  "placa": "Placa del vehículo (ejemplo: ABC-123 o 0080-1P), si no figura deja vacío",
  "cliente_nombre": "Nombre o razón social del COMPRADOR (quien paga la factura)",
  "ruc_cliente": "RUC o DNI del COMPRADOR (11 dígitos si es RUC, 8 si es DNI), vacío si no aparece",
  "fecha": "DD/MM/YYYY o la fecha que aparezca en la factura",
  "items": [
    {
      "nombre": "Nombre del repuesto o servicio",
      "cantidad": 1,
      "precio_unitario": 0.00,
      "total": 0.00
    }
  ],
  "notas": "Cualquier observación relevante"
}
NO incluyas texto adicional fuera del JSON."""

def _pdf_to_image_path(pdf_path: str) -> str:
    """Convierte la primera página de un PDF a JPEG y retorna la ruta de la imagen."""
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(pdf_path)
        page = doc[0]
        mat = fitz.Matrix(200/72, 200/72)  # 200 DPI para buena calidad
        pix = page.get_pixmap(matrix=mat)
        img_path = pdf_path.replace('.pdf', '_p1.jpg')
        pix.save(img_path)
        doc.close()
        print(f"[HISTORICO] PDF convertido a imagen: {img_path}")
        return img_path
    except ImportError:
        raise Exception("PyMuPDF no instalado. Ejecuta: pip install pymupdf")
    except Exception as e:
        raise Exception(f"Error convirtiendo PDF: {e}")


def analizar_factura_historica_imagen(file_path: str) -> dict:
    import base64
    import json
    try:
        # Si es PDF, convertir primera página a imagen
        actual_path = file_path
        if file_path.lower().endswith('.pdf'):
            print(f"[HISTORICO] PDF detectado, convirtiendo...")
            actual_path = _pdf_to_image_path(file_path)

        ext = os.path.splitext(actual_path)[1].lower()
        mime_map = {'.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png', '.webp': 'image/webp'}
        mime_type = mime_map.get(ext, 'image/jpeg')

        with open(actual_path, "rb") as image_file:
            encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
        client = get_groq_client()
        response = client.chat.completions.create(
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": FACTURA_HISTORICA_PROMPT},
                    {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{encoded_string}"}}
                ]
            }],
            max_tokens=2000,
            temperature=0.1,
        )
        raw_content = response.choices[0].message.content.strip()
        raw_content = raw_content.replace('```json', '').replace('```', '').strip()
        result = json.loads(raw_content)
        print(f"[HISTORICO] IA respondio: {result}")
        return result
    except Exception as e:
        logger.error(f"[HISTORICO] Error analizando factura: {e}")
        return {"error": str(e)}


def analizar_edicion_cotizacion(texto: str, items_actuales: list) -> dict:
    """
    Determina si el texto es una edición de cotización existente.
    Retorna: {'es_edicion': bool, 'items': [...lista actualizada...]}
    """
    try:
        client = get_groq_client()
        items_json = json.dumps(items_actuales, ensure_ascii=False)
        prompt = f"""Tienes una cotización activa con estos ítems:
{items_json}

El usuario dice: "{texto}"

Determina si el usuario quiere MODIFICAR esta cotización (agregar, quitar o cambiar precio/cantidad de ítems).
Si SÍ es una modificación, responde ÚNICAMENTE con JSON:
{{
  "es_edicion": true,
  "items": [lista completa actualizada con los cambios aplicados]
}}

Cada ítem debe tener: nombre, cantidad, precio (precio unitario), tipo ("repuesto" o "mano_obra").

Si NO es una modificación (es una consulta, saludo u otra cosa), responde ÚNICAMENTE:
{{"es_edicion": false}}

NO incluyas texto adicional fuera del JSON."""

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            max_tokens=1000,
            temperature=0.1,
        )
        return json.loads(response.choices[0].message.content.strip())
    except Exception as e:
        logger.error(f"Error analizar_edicion_cotizacion: {e}")
        return {"es_edicion": False}


# ─── CRÉDITOS / FIADO ──────────────────────────────────────────────────────

def analizar_intencion_credito(texto: str) -> dict:
    """
    Detecta si el texto es sobre créditos/fiado:
    - crear_credito: 'Mario debe 150 soles, llevó 2 filtros'
    - registrar_abono: 'Mario abonó 40 soles, pagó con yape'
    - ver_creditos: 'créditos pendientes', 'quién me debe'
    - crear_nota_venta: 'nota de venta para Pedro, 3 filtros a 25 soles'
    """
    try:
        client = get_groq_client()
        prompt = """Analiza el texto y determina la intención. Responde ÚNICAMENTE con JSON válido.

INTENCIONES POSIBLES:

1. crear_credito - alguien se lleva algo fiado/al crédito
JSON: {"intencion": "crear_credito", "cliente_nombre": "Mario Flores", "telefono": "999888777", "descripcion": "2 filtros de aceite, 1 bujía", "total": 150.0, "nota": "paga el viernes", "items": [{"nombre": "filtro de aceite", "cantidad": 2, "precio": 25.0}, {"nombre": "bujía", "cantidad": 1, "precio": 15.0}]}
IMPORTANTE: Si se mencionan precios por producto, extráelos en "items". Si no se menciona precio individual, pon 0.0 en precio. Si se menciona total global sin desglose, pon los items sin precio y el total en "total".
- Para mano de obra (ej: "cambio de frenos 80 soles", "revisión eléctrica 50 soles"), agrégala en items con "tipo": "mano_obra". Ejemplo: {"nombre": "Cambio de frenos", "cantidad": 1, "precio": 80.0, "tipo": "mano_obra"}
- Los repuestos/productos tienen stock, la mano de obra NO tiene stock ni item_id.

2. registrar_abono - alguien abona/paga parte de su deuda
JSON: {"intencion": "registrar_abono", "cliente_nombre": "Mario Flores", "monto": 40.0, "metodo_pago": "yape", "nota": "abono parcial"}

3. ver_creditos - quieren ver quién debe o los créditos pendientes
JSON: {"intencion": "ver_creditos", "filtro": "pendientes"}

4. crear_nota_venta - venta directa (no al crédito)
JSON: {"intencion": "crear_nota_venta", "cliente_nombre": "Pedro", "items": [{"nombre": "filtro de aceite", "cantidad": 3, "precio": 25.0}], "total": 75.0}

5. ninguna - no es sobre créditos ni ventas
JSON: {"intencion": "ninguna"}

REGLAS:
- Si dice 'fiado', 'al crédito', 'anotarlo', 'debe', 'le fío' → crear_credito
- Si dice 'abonó', 'pagó', 'canceló', 'entregó', 'depositó' → registrar_abono
- Si dice 'quién debe', 'pendientes', 'créditos', 'deudas' → ver_creditos
- Si dice 'nota de venta', 'venta', 'vendí' → crear_nota_venta
- Si no hay total numérico explícito, pon 0.0
- Extrae nombre completo del cliente si se menciona
- Extrae método de pago: efectivo, yape, plin, transferencia, etc.

Texto a analizar: """

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt + texto}],
            temperature=0.1,
            max_tokens=400,
        )
        raw = response.choices[0].message.content.strip()
        # Limpiar markdown
        if '```' in raw:
            raw = raw.split('```')[1] if '```json' not in raw else raw.split('```json')[1].split('```')[0]
        raw = raw.strip()
        return json.loads(raw)
    except Exception as e:
        logger.error(f"Error analizar_intencion_credito: {e}")
        return {"intencion": "ninguna"}

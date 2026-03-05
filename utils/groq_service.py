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
    if not api_key:
        raise ValueError("API Key de Groq no configurada. Ve a Configuración → IA Sandoval.")
    return Groq(api_key=api_key)


# ─── System Prompts ──────────────────────────────────────────────────────────

def _get_system_prompt(context_data: dict) -> str:
    """Genera el system prompt con datos en tiempo real del taller"""
    fecha = datetime.now().strftime('%d/%m/%Y %H:%M')
    ordenes_activas = context_data.get('ordenes_activas', 0)
    ingresos_mes   = context_data.get('ingresos_mes', 0)
    stock_critico  = context_data.get('stock_critico', [])
    clientes_total = context_data.get('clientes_total', 0)
    ordenes_hoy    = context_data.get('ordenes_hoy', [])

    stock_str = ", ".join([f"{s['nombre']} ({s['stock']} uds)" for s in stock_critico[:5]]) if stock_critico else "Ninguno"
    ordenes_str = "\n".join([f"  - {o}" for o in ordenes_hoy[:5]]) if ordenes_hoy else "  - Ninguna"

    return f"""Eres el Asistente Inteligente de MECÁNICA Y REPUESTOS SANDOVAL EIRL.
Tu nombre es "Asistente Sandoval". Hablas español con tono profesional, directo y amigable.
Fecha y hora actual: {fecha}

═══════════════════════════════════════════════
DATOS EN TIEMPO REAL DEL TALLER (HOY):
═══════════════════════════════════════════════
• Órdenes activas en taller:  {ordenes_activas}
• Ingresos del mes:           S/ {ingresos_mes:,.2f}
• Clientes registrados:       {clientes_total}
• Productos con stock crítico: {stock_str}

Órdenes del día:
{ordenes_str}
═══════════════════════════════════════════════

CAPACIDADES:
- Analizar el estado del taller y dar recomendaciones
- Identificar órdenes retrasadas o problemáticas
- Responder preguntas sobre el negocio usando los datos reales
- Leer e interpretar facturas de compra (cuando se te comparte una imagen)
- Extraer productos de facturas para actualizar el inventario

REGLAS:
- Responde siempre en español
- Usa los datos reales que tienes para dar análisis precisos
- Si te preguntan algo fuera del área del taller, dilo amablemente
- Cuando analices una factura, devuelve los datos en formato estructurado
- Sé conciso pero completo. Máximo 3 párrafos salvo que se pida más detalle"""


FACTURA_PROMPT = """Eres un sistema experto en lectura de facturas y boletas.
Analiza la imagen de la factura y extrae TODA la información posible.

Devuelve ÚNICAMENTE un JSON válido con esta estructura exacta:
{
  "proveedor": "Nombre del proveedor/tienda",
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
            model="meta-llama/llama-4-scout-17b-16e-instruct",
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


def get_context_data() -> dict:
    """
    Obtiene los datos en tiempo real del taller para inyectar al prompt.
    """
    try:
        from utils.models import get_db, Orden, Cliente, ItemInventario
        db = get_db()
        try:
            # Órdenes activas (no archivadas)
            ordenes_activas = db.query(Orden).filter(
                Orden.estado.notin_(['ARCHIVADO'])
            ).count()
            
            # Clientes totales
            clientes_total = db.query(Cliente).count()
            
            # Stock crítico
            items_criticos = db.query(ItemInventario).filter(
                ItemInventario.stock <= ItemInventario.stock_minimo
            ).limit(10).all()
            stock_critico = [{'nombre': i.nombre, 'stock': i.stock, 'minimo': i.stock_minimo} for i in items_criticos]
            
            # Ingresos del mes (órdenes finalizadas este mes)
            from datetime import datetime
            import json as _json
            mes_actual = datetime.now().strftime('%Y-%m')
            ordenes_mes = db.query(Orden).filter(
                Orden.estado == 'ARCHIVADO',
                Orden.fecha.like(f'{mes_actual}%')
            ).all()
            
            ingresos_mes = 0
            for o in ordenes_mes:
                items = o.items_cotizacion or []
                if isinstance(items, str):
                    try: items = _json.loads(items)
                    except: items = []
                for item in items:
                    if isinstance(item, dict):
                        ingresos_mes += float(item.get('total', 0) or 0)
            
            # Resumen órdenes activas
            ordenes_recientes = db.query(Orden).filter(
                Orden.estado.notin_(['ARCHIVADO'])
            ).order_by(Orden.fecha.desc()).limit(5).all()
            ordenes_hoy = [f"{o.consecutivo} - {o.estado} - {getattr(o, 'vehiculo_placa', '')}" for o in ordenes_recientes]
            
            return {
                'ordenes_activas': ordenes_activas,
                'clientes_total': clientes_total,
                'stock_critico': stock_critico,
                'ingresos_mes': ingresos_mes,
                'ordenes_hoy': ordenes_hoy,
            }
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Error obteniendo context data: {e}")
        return {}

"""
SANDOVAL Dashboard — Informe final de orden (todas las 7 fases + evidencias).
Genera un PDF completo, profesional, descargable por staff y por el cliente.

API pública:
  generar_informe_orden(consecutivo: str, taller_id: int) -> str
    Devuelve la ruta absoluta del PDF generado en static/informes/.
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    HRFlowable, Image, KeepTogether, PageBreak, Paragraph,
    SimpleDocTemplate, Spacer, Table, TableStyle,
)
from sqlalchemy import text

from utils.models import get_db
import logging
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────
# Constantes de branding (espejo de pdf_generator.py)
# ─────────────────────────────────────────────────────────────────
SANDOVAL_BLUE = colors.HexColor('#154c79')
SANDOVAL_DARK = colors.HexColor('#333333')
SANDOVAL_GRAY = colors.HexColor('#666666')
SANDOVAL_LIGHT = colors.HexColor('#f3f4f6')
SANDOVAL_BORDER = colors.HexColor('#e5e7eb')
SANDOVAL_GREEN = colors.HexColor('#10b981')
SANDOVAL_RED = colors.HexColor('#dc2626')
SANDOVAL_AMBER = colors.HexColor('#f59e0b')

STATIC_ROOT = '/var/www/sandoval/static'
EVIDENCIA_ROOT = os.path.join(STATIC_ROOT, 'evidencia')
INFORMES_ROOT = os.path.join(STATIC_ROOT, 'informes')

# Orden canónico de fases que queremos mostrar en el informe.
FASES_CANONICAS: List[Tuple[str, str, List[str]]] = [
    # (clave, etiqueta, aliases normalizados para buscar fotos/data)
    ('recepcion',     'RECEPCIÓN',       ['recepcion', 'reception', 'recepción']),
    ('diagnostico',   'DIAGNÓSTICO',     ['diagnostico', 'diagnóstico', 'diagnostic']),
    ('presupuesto',   'PRESUPUESTO',     ['presupuesto', 'repuestos', 'parts']),
    ('aprobacion',    'APROBACIÓN',      ['aprobacion', 'aprobación', 'approval']),
    ('reparacion',    'REPARACIÓN',      ['reparacion', 'reparación', 'repair']),
    ('control_calidad', 'CONTROL CALIDAD', ['control_calidad', 'calidad', 'quality']),
    ('entrega',       'ENTREGA',         ['entrega', 'delivery', 'listo_para_entrega']),
]


# ─────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────
def _styles():
    s = getSampleStyleSheet()
    add = lambda name, **kw: s.add(ParagraphStyle(name=name, **kw)) if name not in s else None
    add('SandovalTitle', fontSize=18, fontName='Helvetica-Bold', textColor=SANDOVAL_BLUE, alignment=TA_LEFT)
    add('SandovalH2',    fontSize=12, fontName='Helvetica-Bold', textColor=SANDOVAL_BLUE,
        spaceBefore=5*mm, spaceAfter=2*mm)
    add('SandovalH3',    fontSize=10, fontName='Helvetica-Bold', textColor=SANDOVAL_DARK,
        spaceBefore=2*mm, spaceAfter=1*mm)
    add('SandovalBody',  fontSize=9.5, fontName='Helvetica', textColor=SANDOVAL_DARK, leading=12)
    add('SandovalSmall', fontSize=8, fontName='Helvetica', textColor=SANDOVAL_GRAY, leading=10)
    add('SandovalKV',    fontSize=9, fontName='Helvetica', textColor=SANDOVAL_DARK, leading=11)
    add('SandovalKVk',   fontSize=8, fontName='Helvetica-Bold', textColor=SANDOVAL_GRAY, leading=11)
    return s


def _fmt_money(v: Any, moneda: str = 'S/') -> str:
    try:
        return f"{moneda} {float(v or 0):,.2f}"
    except (TypeError, ValueError):
        return f"{moneda} 0.00"


def _fmt_fecha(v: Any) -> str:
    if not v:
        return '—'
    if isinstance(v, datetime):
        return v.strftime('%Y-%m-%d %H:%M')
    s = str(v).strip()
    # Tolerar 'YYYY-MM-DD HH:MM:SS' y '17/04/2026'
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M',
                '%Y-%m-%d', '%d/%m/%Y %H:%M', '%d/%m/%Y'):
        try:
            dt = datetime.strptime(s[:len(fmt)+2], fmt)
            return dt.strftime('%Y-%m-%d %H:%M') if '%H' in fmt else dt.strftime('%Y-%m-%d')
        except ValueError:
            continue
    return s[:16]


def _parse_json(v: Any) -> Any:
    if v is None or v == '':
        return None
    if isinstance(v, (dict, list)):
        return v
    try:
        return json.loads(v)
    except (TypeError, ValueError):
        return None


def _norm(s: str) -> str:
    return (s or '').lower().strip().replace('á','a').replace('é','e').replace('í','i') \
        .replace('ó','o').replace('ú','u').replace('ñ','n').replace('-','_').replace(' ','_')


def _url_to_fspath(url: str) -> Optional[str]:
    """Convierte '/static/evidencia/foo.jpg' o '/evidencia/foo.jpg' → ruta absoluta."""
    if not url:
        return None
    u = url.lstrip('/')
    candidates = [
        os.path.join('/var/www/sandoval', u),
        os.path.join(STATIC_ROOT, u.replace('static/', '', 1)) if u.startswith('static/') else None,
        os.path.join(EVIDENCIA_ROOT, os.path.basename(u)),
    ]
    for c in candidates:
        if c and os.path.isfile(c):
            return c
    return None


def _draw_watermark(canvas, doc):
    canvas.saveState()
    logo = '/var/www/sandoval/assets/logo_sandoval.jpg'
    if not os.path.isfile(logo):
        logo = '/var/www/sandoval/static/logo_sandoval.jpg'
    if os.path.isfile(logo):
        canvas.setFillAlpha(0.06)
        w, h = 120*mm, 120*mm
        canvas.drawImage(logo, (A4[0]-w)/2, (A4[1]-h)/2, width=w, height=h,
                          preserveAspectRatio=True, mask='auto')
    canvas.restoreState()
    # Pie de página
    canvas.saveState()
    canvas.setFont('Helvetica', 7.5)
    canvas.setFillColor(SANDOVAL_GRAY)
    canvas.drawCentredString(
        A4[0]/2, 10*mm,
        f'MECÁNICA Y REPUESTOS SANDOVAL EIRL · RUC 20608755111 · sandoval.pe · Página {doc.page}'
    )
    canvas.restoreState()


def _header_block(styles, consecutivo: str, fecha_str: str) -> List:
    """Header corporativo con logo + nº orden a la derecha."""
    logo_path = '/var/www/sandoval/assets/logo_sandoval.jpg'
    if not os.path.isfile(logo_path):
        logo_path = '/var/www/sandoval/static/logo_sandoval.jpg'

    company = [
        Paragraph('<b>MECÁNICA Y REPUESTOS SANDOVAL EIRL</b>',
                  ParagraphStyle('c1', fontSize=12, fontName='Helvetica-Bold',
                                 textColor=SANDOVAL_BLUE, leading=14)),
        Paragraph('RUC: 20608755111',
                  ParagraphStyle('c2', fontSize=8, textColor=SANDOVAL_GRAY, leading=10)),
        Paragraph('Piura, Perú · sandoval.pe',
                  ParagraphStyle('c3', fontSize=8, textColor=SANDOVAL_GRAY, leading=10)),
    ]
    right = [
        Paragraph('INFORME DE SERVICIO',
                  ParagraphStyle('r1', fontSize=9.5, textColor=SANDOVAL_GRAY,
                                 alignment=TA_RIGHT, leading=12)),
        Paragraph(consecutivo or '—',
                  ParagraphStyle('r2', fontSize=16, fontName='Helvetica-Bold',
                                 textColor=SANDOVAL_BLUE, alignment=TA_RIGHT, leading=19)),
        Paragraph(f'Emitido: {fecha_str}',
                  ParagraphStyle('r3', fontSize=8, textColor=SANDOVAL_GRAY,
                                 alignment=TA_RIGHT, leading=11)),
    ]
    if os.path.isfile(logo_path):
        img = Image(logo_path, width=22*mm, height=22*mm)
        left_cell = Table([[img, company]], colWidths=[24*mm, 78*mm], style=TableStyle([
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'), ('LEFTPADDING', (0,0), (-1,-1), 0),
        ]))
    else:
        left_cell = Table([[company]], colWidths=[102*mm])

    head = Table([[left_cell, right]], colWidths=[110*mm, 65*mm], style=TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 2),
    ]))
    return [
        head,
        Spacer(1, 3*mm),
        HRFlowable(width='100%', thickness=1.2, color=SANDOVAL_BLUE, spaceAfter=4*mm),
    ]


def _kv_table(pairs: List[Tuple[str, str]], col_widths=(45*mm, 130*mm)) -> Table:
    """Tabla de clave/valor con estilo uniforme."""
    rows = [[Paragraph(f'<b>{k}</b>',
                        ParagraphStyle('k', fontSize=8.5, textColor=SANDOVAL_GRAY)),
              Paragraph(v or '—',
                        ParagraphStyle('v', fontSize=9.5, textColor=SANDOVAL_DARK, leading=12))]
            for k, v in pairs]
    t = Table(rows, colWidths=list(col_widths))
    t.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('LEFTPADDING', (0,0), (-1,-1), 4),
        ('RIGHTPADDING', (0,0), (-1,-1), 4),
        ('TOPPADDING', (0,0), (-1,-1), 2),
        ('BOTTOMPADDING', (0,0), (-1,-1), 2),
        ('LINEBELOW', (0,0), (-1,-2), 0.25, SANDOVAL_BORDER),
    ]))
    return t


def _section_title(styles, text_: str, color=SANDOVAL_BLUE):
    p = Paragraph(f'<b>{text_.upper()}</b>',
                  ParagraphStyle('sec', fontSize=11, fontName='Helvetica-Bold',
                                 textColor=color, spaceBefore=4*mm, spaceAfter=2*mm,
                                 leftIndent=0))
    line = HRFlowable(width='100%', thickness=0.8, color=color, spaceAfter=3*mm)
    return [p, line]


# ─────────────────────────────────────────────────────────────────
# Query de datos de la orden
# ─────────────────────────────────────────────────────────────────
def _fetch_orden(db, consecutivo: str, taller_id: int) -> Optional[Dict[str, Any]]:
    """Lee la orden + datos de cliente y vehículo con LEFT JOIN.
    Calcula total a partir de items_cotizacion (no hay columna `total` en ordenes).
    """
    row = db.execute(text('''
        SELECT o.consecutivo, o.fecha, o.estado, o.motivo, o.diagnostico, o.tecnico,
               o.km, o.items_cotizacion, o.fotos_evidencia, o.checklist_reparacion,
               o.approval_status, o.approval_date, o.notas_entrega, o.proximo_mantenimiento,
               o.monto_cobrado, o.pagos, o.encuesta, o.historial, o.observaciones,
               o.vehiculo_placa, o.cliente_id,
               COALESCE(c.nombre, '') AS cliente_nombre,
               COALESCE(c.apellidos, '') AS cliente_apellidos,
               COALESCE(c.telefono, '') AS cliente_telefono,
               COALESCE(c.documento, '') AS cliente_documento,
               COALESCE(c.email, '') AS cliente_email,
               COALESCE(v.marca, '') AS veh_marca,
               COALESCE(v.modelo, '') AS veh_modelo,
               COALESCE(v."año", '') AS veh_anio,
               COALESCE(v.color, '') AS veh_color
          FROM ordenes o
          LEFT JOIN clientes  c ON c.id    = o.cliente_id
          LEFT JOIN vehiculos v ON v.placa = o.vehiculo_placa
         WHERE o.consecutivo = :c AND o.taller_id = :t
    '''), {"c": consecutivo, "t": taller_id}).fetchone()
    if not row:
        return None
    items = _parse_json(row.items_cotizacion) or []
    # Calcular total sumando items (misma lógica que el frontend)
    total = 0.0
    for it in items:
        if not isinstance(it, dict):
            continue
        try:
            cant = float(it.get('cantidad') or 1)
            pu = float(it.get('precio_unitario') or it.get('precio') or 0)
            sub = float(it.get('total') or it.get('subtotal') or (cant * pu))
            total += sub
        except (TypeError, ValueError):
            continue
    nombre_full = (str(row.cliente_nombre or '') + ' ' + str(row.cliente_apellidos or '')).strip() or '—'
    return {
        'consecutivo': row.consecutivo,
        'fecha': row.fecha, 'estado': row.estado or '',
        'cliente_nombre': nombre_full,
        'cliente_telefono': row.cliente_telefono or '',
        'cliente_documento': row.cliente_documento or '',
        'cliente_email': row.cliente_email or '',
        'vehiculo_placa': row.vehiculo_placa or '',
        'vehiculo_marca': row.veh_marca or '',
        'vehiculo_modelo': row.veh_modelo or '',
        'vehiculo_anio': row.veh_anio or '',
        'vehiculo_color': row.veh_color or '',
        'km': row.km or '', 'motivo': row.motivo or '',
        'observaciones': row.observaciones or '',
        'diagnostico': row.diagnostico or '', 'tecnico': row.tecnico or '',
        'items': items,
        'fotos': _parse_json(row.fotos_evidencia) or [],
        'checklist': _parse_json(row.checklist_reparacion) or {},
        'approval_status': row.approval_status or '',
        'approval_date': row.approval_date or '',
        'notas_entrega': row.notas_entrega or '',
        'proximo_mantenimiento': row.proximo_mantenimiento or '',
        'total': round(total, 2),
        'cobrado': float(row.monto_cobrado or 0),
        'pagos': _parse_json(row.pagos) or [],
        'encuesta': _parse_json(row.encuesta) or {},
        'historial': _parse_json(row.historial) or [],
    }


def _group_media_by_fase(fotos: List[Any]) -> Dict[str, Dict[str, List[Dict[str, Any]]]]:
    """Devuelve {clave_fase: {'fotos':[...],'videos':[...],'pdfs':[...]}}."""
    out: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
    for item in (fotos or []):
        if isinstance(item, str):
            url, fase, tipo, nombre = item, 'general', 'foto', ''
        elif isinstance(item, dict):
            url = item.get('url') or item.get('path') or ''
            fase = item.get('fase') or item.get('phase') or 'general'
            tipo = item.get('tipo') or item.get('type') or ''
            nombre = item.get('nombre') or item.get('filename') or ''
        else:
            continue
        if not url:
            continue
        fase_n = _norm(fase)
        if not tipo:
            lower = url.lower()
            if lower.endswith('.pdf'):
                tipo = 'pdf'
            elif any(lower.endswith(e) for e in ('.mp4', '.mov', '.avi', '.webm', '.mkv')):
                tipo = 'video'
            else:
                tipo = 'foto'
        slot = {'foto': 'fotos', 'video': 'videos', 'pdf': 'pdfs'}.get(tipo, 'fotos')
        out.setdefault(fase_n, {'fotos': [], 'videos': [], 'pdfs': []})
        out[fase_n][slot].append({'url': url, 'nombre': nombre})
    return out


def _media_for_fase(grouped: Dict[str, Dict[str, List[Dict[str, Any]]]],
                    aliases: List[str]) -> Dict[str, List[Dict[str, Any]]]:
    acc = {'fotos': [], 'videos': [], 'pdfs': []}
    for a in aliases:
        a_n = _norm(a)
        bucket = grouped.get(a_n)
        if not bucket:
            continue
        acc['fotos'].extend(bucket['fotos'])
        acc['videos'].extend(bucket['videos'])
        acc['pdfs'].extend(bucket['pdfs'])
    return acc


# ─────────────────────────────────────────────────────────────────
# Flowables por fase
# ─────────────────────────────────────────────────────────────────
def _photo_grid(photos: List[Dict[str, Any]], max_per_row: int = 4, thumb_mm: float = 38) -> List:
    """Crea una tabla con miniaturas de fotos. Se salta archivos que no existen
    o que tienen formato corrupto / no soportado por PIL.
    """
    flow = []
    cells = []
    for p in photos:
        path = _url_to_fspath(p.get('url'))
        if not path:
            continue
        # Verificar que PIL puede leer la imagen ANTES de pasar a ReportLab.
        # Una imagen corrupta tumba todo el PDF si llega a ReportLab.
        try:
            from PIL import Image as _PILImage
            with _PILImage.open(path) as _verify:
                _verify.verify()
        except Exception:
            continue
        try:
            img = Image(path, width=thumb_mm*mm, height=thumb_mm*mm, kind='bound')
            cells.append(img)
        except Exception:
            continue
    if not cells:
        return flow
    rows = []
    for i in range(0, len(cells), max_per_row):
        chunk = cells[i:i+max_per_row]
        while len(chunk) < max_per_row:
            chunk.append('')
        rows.append(chunk)
    col_w = thumb_mm * mm + 2*mm
    t = Table(rows, colWidths=[col_w]*max_per_row)
    t.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('TOPPADDING', (0,0), (-1,-1), 2),
        ('BOTTOMPADDING', (0,0), (-1,-1), 2),
    ]))
    flow.append(t)
    return flow


def _pdf_list(pdfs: List[Dict[str, Any]]) -> List:
    if not pdfs:
        return []
    items = []
    for p in pdfs:
        name = p.get('nombre') or os.path.basename(p.get('url') or '') or 'Documento.pdf'
        items.append(Paragraph(
            f'📎 <b>{name}</b> — adjunto disponible en el sistema ({p.get("url","")})',
            ParagraphStyle('pdfrow', fontSize=8.5, textColor=SANDOVAL_RED, leading=11)
        ))
    return items


def _video_list(videos: List[Dict[str, Any]]) -> List:
    if not videos:
        return []
    return [Paragraph(
        f'🎥 {len(videos)} video(s) de evidencia disponibles en el sistema.',
        ParagraphStyle('vrow', fontSize=8.5, textColor=SANDOVAL_GRAY, leading=11)
    )]


# Etiquetas legibles para keys comunes del checklist de recepción.
_RECEPCION_LABELS = {
    'exterior': 'Exterior', 'interior': 'Interior', 'pertenencias': 'Pertenencias',
    'rayones': 'Rayones', 'abolladuras': 'Abolladuras', 'vidrios': 'Vidrios',
    'parabrisas': 'Parabrisas', 'espejos': 'Espejos', 'faros': 'Faros',
    'parachoques': 'Parachoques', 'llantas': 'Llantas', 'pintura': 'Pintura',
    'tapiceria': 'Tapicería', 'tablero': 'Tablero', 'tapetes': 'Tapetes',
    'radio': 'Radio', 'aire': 'Aire acondicionado', 'asientos': 'Asientos',
    'gata': 'Gata', 'llave_ruedas': 'Llave de ruedas', 'llanta_repuesto': 'Llanta de repuesto',
    'triangulo': 'Triángulo', 'extintor': 'Extintor', 'botiquin': 'Botiquín',
    'documentos': 'Documentos', 'control_alarma': 'Control de alarma', 'manual': 'Manual',
    'combustible': 'Nivel de combustible',
    'carroceria': 'Carrocería', 'luces': 'Luces', 'accesorios': 'Accesorios',
}

# Catálogo canónico (mismo orden y keys que admin PC / móvil PWA).
_RECEPCION_CANON = [
    ('carroceria',  'Carrocería'),
    ('interior',    'Interior'),
    ('llantas',     'Llantas / Neumáticos'),
    ('luces',       'Luces'),
    ('combustible', 'Nivel de combustible'),
    ('documentos',  'Documentos'),
    ('accesorios',  'Accesorios'),
    ('vidrios',     'Vidrios y parabrisas'),
    ('espejos',     'Espejos'),
    ('pintura',     'Pintura'),
]

# Map de keys legacy (móvil antiguo con exterior/interior/pertenencias) a los
# keys canónicos. Varios items viejos pueden agruparse bajo el mismo canónico
# y sus labels concatenan como descripción del defecto.
_RECEPCION_LEGACY_MAP = {
    # exterior
    'rayones':     ('carroceria', 'rayones'),
    'abolladuras': ('carroceria', 'abolladuras'),
    'pintura':     ('pintura',    'pintura descascarada'),
    'parabrisas':  ('vidrios',    'parabrisas con grietas'),
    'vidrios':     ('vidrios',    'vidrios rotos'),
    'espejos':     ('espejos',    'espejos dañados'),
    'faros':       ('luces',      'faros / luces dañadas'),
    'parachoques': ('carroceria', 'parachoques dañado'),
    'llantas':     ('llantas',    'llantas en mal estado'),
    # interior
    'tapiceria':   ('interior',   'tapicería rota/manchada'),
    'tablero':     ('interior',   'tablero dañado'),
    'tapetes':     ('interior',   'tapetes faltantes'),
    'radio':       ('interior',   'radio/pantalla dañada'),
    'aire':        ('interior',   'A/C no funciona'),
    'asientos':    ('interior',   'asientos en mal estado'),
    # pertenencias (faltantes = defecto del ítem "accesorios")
    'gata':            ('accesorios', 'gata faltante'),
    'llave_ruedas':    ('accesorios', 'llave de ruedas faltante'),
    'llanta_repuesto': ('accesorios', 'llanta de repuesto faltante'),
    'triangulo':       ('accesorios', 'triángulo faltante'),
    'extintor':        ('accesorios', 'extintor faltante'),
    'botiquin':        ('accesorios', 'botiquín faltante'),
    'documentos':      ('documentos', 'documentos incompletos'),
    'control_alarma':  ('accesorios', 'control de alarma faltante'),
    'manual':          ('accesorios', 'manual faltante'),
}

# Keys del checklist de recepción que son metadatos técnicos, no del vehículo.
_RECEPCION_SKIP = {'fecha_ingreso', 'responsable', 'kilometraje', 'observaciones', 'checklist_items'}


def _legacy_to_checklist_items(rec: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Convierte formato móvil legacy {exterior:{rayones:true,...}, ...} al
    modelo canónico [{key,label,estado,defecto}], agrupando flags por ítem.
    Un ítem queda en estado 'defecto' si alguna sub-key legacy está en True.
    """
    items = [{'key': k, 'label': lbl, 'estado': 'ok', 'defecto': ''}
             for k, lbl in _RECEPCION_CANON]
    by_key = {it['key']: it for it in items}

    # Si no hay ninguna sección legacy, devolvemos vacío (no sabemos si se revisó).
    sections_seen = False
    for grp in ('exterior', 'interior', 'pertenencias'):
        sec = rec.get(grp)
        if not isinstance(sec, dict):
            continue
        sections_seen = True
        for k, v in sec.items():
            if not v:
                continue
            canon = _RECEPCION_LEGACY_MAP.get(k)
            if not canon:
                continue
            canon_key, defect_desc = canon
            item = by_key.get(canon_key)
            if not item:
                continue
            item['estado'] = 'defecto'
            item['defecto'] = (
                (item['defecto'] + ', ' if item['defecto'] else '') + defect_desc
            )
    if not sections_seen:
        return []
    return items


def _label(key: str) -> str:
    return _RECEPCION_LABELS.get(key, key.replace('_', ' ').capitalize())


def _render_recepcion_checklist(rec_raw: Any) -> List:
    """Formatea el checklist de recepción como una lista uniforme con ✓/⚠.
    Acepta:
      - Nuevo formato: dict con `checklist: [{key,label,estado,defecto}]`.
      - Legacy admin PC: dict con `checklist: [{key,label,ok}]`.
      - Legacy móvil: dict con `exterior:{rayones:true,...}, interior:{...}, pertenencias:{...}` (true = defecto presente).
    También renderiza observaciones generales si existen.
    """
    flow: List = []
    if not rec_raw or not isinstance(rec_raw, (dict, list)):
        return flow

    # 1. Extraer items canónicos
    items: List[Dict[str, Any]] = []
    if isinstance(rec_raw, list):
        items = [x for x in rec_raw if isinstance(x, dict)]
    elif isinstance(rec_raw, dict):
        if isinstance(rec_raw.get('checklist'), list):
            items = [x for x in rec_raw['checklist'] if isinstance(x, dict)]
        else:
            # Convertir desde legacy móvil (exterior/interior/pertenencias)
            items = _legacy_to_checklist_items(rec_raw)

    # 2. Renderizar lista unificada (estilo control de calidad)
    if items:
        flow.append(Spacer(1, 2*mm))
        defectos_count = sum(1 for it in items if (it.get('estado') == 'defecto' or
                              (not it.get('estado') and not it.get('ok') and 'defecto' in str(it).lower())))
        ok_count = sum(1 for it in items if (it.get('estado') == 'ok' or
                       (not it.get('estado') and it.get('ok') is True)))
        # Header con resumen
        flow.append(Paragraph(
            f'<b>Inspección al ingreso</b> — '
            f'<font color="{SANDOVAL_GREEN.hexval()}">{ok_count} ✓</font> · '
            f'<font color="{SANDOVAL_RED.hexval()}">{defectos_count} ⚠</font>',
            ParagraphStyle('rh', fontSize=9.5, fontName='Helvetica-Bold',
                           textColor=SANDOVAL_DARK, spaceBefore=1*mm, spaceAfter=2*mm)
        ))
        rows = []
        for it in items:
            estado = it.get('estado')
            if not estado:
                estado = 'ok' if it.get('ok') else 'pendiente'
            lbl = it.get('label') or _label(str(it.get('key') or ''))
            if estado == 'defecto':
                defecto = it.get('defecto') or 'Defecto reportado'
                rows.append([
                    Paragraph(f'<font color="{SANDOVAL_RED.hexval()}"><b>⚠</b></font>',
                              ParagraphStyle('di', fontSize=12, alignment=TA_CENTER)),
                    Paragraph(
                        f'<b><font color="{SANDOVAL_RED.hexval()}">{lbl}</font></b> — '
                        f'<font color="#7f1d1d">{defecto}</font>',
                        ParagraphStyle('dl', fontSize=9.5, textColor=SANDOVAL_DARK, leading=12)),
                ])
            elif estado == 'ok':
                rows.append([
                    Paragraph(f'<font color="{SANDOVAL_GREEN.hexval()}"><b>✓</b></font>',
                              ParagraphStyle('oi', fontSize=12, alignment=TA_CENTER)),
                    Paragraph(lbl,
                              ParagraphStyle('ol', fontSize=9.5, textColor=SANDOVAL_DARK)),
                ])
            else:
                rows.append([
                    Paragraph(f'<font color="{SANDOVAL_GRAY.hexval()}"><b>—</b></font>',
                              ParagraphStyle('pi', fontSize=12, alignment=TA_CENTER)),
                    Paragraph(f'<font color="{SANDOVAL_GRAY.hexval()}">{lbl}</font>',
                              ParagraphStyle('pl', fontSize=9.5, textColor=SANDOVAL_GRAY)),
                ])
        if rows:
            t = Table(rows, colWidths=[10*mm, 165*mm])
            t.setStyle(TableStyle([
                ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                ('LINEBELOW', (0,0), (-1,-2), 0.25, SANDOVAL_BORDER),
                ('TOPPADDING', (0,0), (-1,-1), 3),
                ('BOTTOMPADDING', (0,0), (-1,-1), 3),
                ('LEFTPADDING', (0,0), (-1,-1), 4),
            ]))
            flow.append(t)

    # 3. Observaciones generales (siempre, si existen)
    obs = ''
    if isinstance(rec_raw, dict):
        obs = (rec_raw.get('observaciones') or '').strip()
    if obs:
        flow.append(Spacer(1, 3*mm))
        flow.append(Paragraph('<b>Observaciones de ingreso</b>',
                               ParagraphStyle('obh', fontSize=9, fontName='Helvetica-Bold',
                                              textColor=SANDOVAL_BLUE)))
        flow.append(Paragraph(
            obs.replace('\n', '<br/>'),
            ParagraphStyle('obt', fontSize=9.5, textColor=SANDOVAL_DARK, leading=12,
                           leftIndent=2*mm, borderPadding=4,
                           backColor=colors.HexColor('#f8fafc'))
        ))
    return flow

    # Caso: secciones agrupadas (exterior/interior/pertenencias con sub-dicts de bools)
    secciones = []
    for key, val in rec_raw.items():
        if key in _RECEPCION_SKIP:
            continue
        if isinstance(val, dict) and val:
            secciones.append((key, val))

    if secciones:
        flow.append(Spacer(1, 2*mm))
        flow.append(Paragraph('<b>Checklist de recepción</b>',
                               ParagraphStyle('xh', fontSize=9, fontName='Helvetica-Bold',
                                              textColor=SANDOVAL_DARK)))
        for sec_key, sec_val in secciones:
            flow.append(Spacer(1, 1*mm))
            flow.append(Paragraph(
                f'<b>{_label(sec_key).upper()}</b>',
                ParagraphStyle('sh', fontSize=8.5, fontName='Helvetica-Bold',
                               textColor=SANDOVAL_BLUE, spaceBefore=1*mm, spaceAfter=1*mm)
            ))
            # Interpretar bools como OK/daño: en estos checklists True = tiene daño/presencia.
            # Para pertenencias, True = presente. Lo marcamos neutro con ✓/✗.
            rows = []
            for k, v in sec_val.items():
                if v in (None, ''):
                    continue
                marcado = bool(v) if isinstance(v, bool) else str(v).lower() in ('true', '1', 'sí', 'si', 'ok')
                icon = '✓' if marcado else '✗'
                color = SANDOVAL_GREEN if marcado else SANDOVAL_GRAY
                rows.append([
                    Paragraph(f'<font color="{color.hexval()}"><b>{icon}</b></font>',
                              ParagraphStyle('qi', fontSize=10, alignment=TA_CENTER)),
                    Paragraph(_label(k), ParagraphStyle('ql', fontSize=9, textColor=SANDOVAL_DARK)),
                ])
            if rows:
                t = Table(rows, colWidths=[10*mm, 160*mm])
                t.setStyle(TableStyle([
                    ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                    ('LINEBELOW', (0,0), (-1,-2), 0.2, SANDOVAL_BORDER),
                    ('TOPPADDING', (0,0), (-1,-1), 1),
                    ('BOTTOMPADDING', (0,0), (-1,-1), 1),
                    ('LEFTPADDING', (0,0), (-1,-1), 6),
                ]))
                flow.append(t)
        return flow

    # Caso: dict plano {clave: valor} que no sea metadata — mostrar como pares
    pares_planos = [(_label(k), str(v)) for k, v in rec_raw.items()
                    if k not in _RECEPCION_SKIP and v not in (None, '', [], {})]
    if pares_planos:
        flow.append(Spacer(1, 2*mm))
        flow.append(Paragraph('<b>Checklist de recepción</b>',
                               ParagraphStyle('xh', fontSize=9, fontName='Helvetica-Bold',
                                              textColor=SANDOVAL_DARK)))
        flow.append(_kv_table(pares_planos))
    return flow


def _extract_reparacion_items(ck: Any) -> List[Dict[str, Any]]:
    """Busca actividades de reparación en cualquier ubicación conocida del checklist."""
    if not isinstance(ck, dict):
        return []
    # Formato canónico (móvil y admin PC): ck.reparacion.items
    rep = ck.get('reparacion')
    if isinstance(rep, dict):
        for k in ('items', 'actividades', 'tareas'):
            v = rep.get(k)
            if isinstance(v, list) and v:
                return [x for x in v if isinstance(x, dict)]
    elif isinstance(rep, list) and rep:
        return [x for x in rep if isinstance(x, dict)]
    # Otras ubicaciones legadas / alternativas
    for alt in ('repair_logs', 'reparacion_items', 'actividades', 'repair_items'):
        v = ck.get(alt)
        if isinstance(v, list) and v:
            return [x for x in v if isinstance(x, dict)]
    # En `repair_details` del portal cliente a veces viene {items:[]}
    rd = ck.get('repair_details') or {}
    if isinstance(rd, dict):
        v = rd.get('items') or rd.get('tareas')
        if isinstance(v, list) and v:
            return [x for x in v if isinstance(x, dict)]
    return []


def _extract_calidad_checklist(ck: Any) -> List[Dict[str, Any]]:
    """Busca el checklist de control de calidad en cualquier ubicación conocida."""
    if not isinstance(ck, dict):
        return []
    for key in ('control_calidad', 'calidad', 'quality_control', 'qc'):
        v = ck.get(key)
        if isinstance(v, dict):
            lst = v.get('checklist') or v.get('items') or v.get('tareas')
            if isinstance(lst, list) and lst:
                return [x for x in lst if isinstance(x, dict)]
        elif isinstance(v, list) and v:
            return [x for x in v if isinstance(x, dict)]
    return []


def _render_fase(fase_key: str, fase_label: str, data: Dict[str, Any],
                 media: Dict[str, List[Dict[str, Any]]]) -> List:
    """Devuelve flowables de la sección de una fase."""
    flow: List = []
    styles = _styles()
    flow.extend(_section_title(styles, fase_label))

    ck = data.get('checklist') or {}

    if fase_key == 'recepcion':
        pairs = [
            ('Motivo de ingreso', data.get('motivo') or '—'),
            ('Técnico asignado',  data.get('tecnico') or '—'),
            ('Kilometraje',       str(data.get('km') or '—')),
        ]
        flow.append(_kv_table(pairs))
        rec_raw = ck.get('recepcion') if isinstance(ck, dict) else None
        # Asegurar que las observaciones de la orden también se vean si rec_raw no las trae.
        if isinstance(rec_raw, dict) and not rec_raw.get('observaciones'):
            obs_orden = (data.get('observaciones') or '').strip()
            if obs_orden:
                rec_raw = dict(rec_raw)
                rec_raw['observaciones'] = obs_orden
        elif rec_raw is None:
            obs_orden = (data.get('observaciones') or '').strip()
            if obs_orden:
                rec_raw = {'observaciones': obs_orden}
        flow.extend(_render_recepcion_checklist(rec_raw))

    elif fase_key == 'diagnostico':
        dg = (ck.get('diagnostico') or {}) if isinstance(ck, dict) else {}
        pairs = [
            ('Sistema afectado',    dg.get('sistema_afectado') or '—'),
            ('Códigos OBD',         dg.get('codigos_error') or '—'),
            ('Pruebas realizadas',  dg.get('pruebas_realizadas') or '—'),
            ('Severidad',           dg.get('severidad') or '—'),
            ('Tiempo estimado',     dg.get('tiempo_estimado') or '—'),
        ]
        flow.append(_kv_table(pairs))
        hallazgos = data.get('diagnostico') or dg.get('hallazgos') or ''
        if hallazgos:
            flow.append(Spacer(1, 2*mm))
            flow.append(Paragraph('<b>Hallazgos / diagnóstico:</b>',
                                   ParagraphStyle('h', fontSize=9, fontName='Helvetica-Bold',
                                                  textColor=SANDOVAL_DARK)))
            flow.append(Paragraph(hallazgos.replace('\n', '<br/>'),
                                   ParagraphStyle('hb', fontSize=9.5, textColor=SANDOVAL_DARK, leading=12)))
        sol = dg.get('solucion_propuesta') or ''
        if sol:
            flow.append(Spacer(1, 1*mm))
            flow.append(Paragraph('<b>Solución propuesta:</b>',
                                   ParagraphStyle('s', fontSize=9, fontName='Helvetica-Bold',
                                                  textColor=SANDOVAL_DARK)))
            flow.append(Paragraph(sol.replace('\n', '<br/>'),
                                   ParagraphStyle('sb', fontSize=9.5, textColor=SANDOVAL_DARK, leading=12)))

    elif fase_key == 'presupuesto':
        items = data.get('items') or []
        if items:
            header = [
                Paragraph('<b>Descripción</b>', ParagraphStyle('h', fontSize=8.5, textColor=colors.white)),
                Paragraph('<b>Tipo</b>',        ParagraphStyle('h', fontSize=8.5, textColor=colors.white)),
                Paragraph('<b>Cant.</b>',       ParagraphStyle('h', fontSize=8.5, textColor=colors.white, alignment=TA_CENTER)),
                Paragraph('<b>P. Unit.</b>',    ParagraphStyle('h', fontSize=8.5, textColor=colors.white, alignment=TA_RIGHT)),
                Paragraph('<b>Total</b>',       ParagraphStyle('h', fontSize=8.5, textColor=colors.white, alignment=TA_RIGHT)),
            ]
            rows = [header]
            for it in items:
                rows.append([
                    Paragraph(str(it.get('nombre') or ''),
                              ParagraphStyle('i', fontSize=8.5, textColor=SANDOVAL_DARK)),
                    Paragraph(str(it.get('categoria') or '—'),
                              ParagraphStyle('i', fontSize=8, textColor=SANDOVAL_GRAY)),
                    Paragraph(str(it.get('cantidad') or '1'),
                              ParagraphStyle('i', fontSize=8.5, textColor=SANDOVAL_DARK, alignment=TA_CENTER)),
                    Paragraph(_fmt_money(it.get('precio_unitario', 0)),
                              ParagraphStyle('i', fontSize=8.5, textColor=SANDOVAL_DARK, alignment=TA_RIGHT)),
                    Paragraph(_fmt_money(it.get('total') or it.get('subtotal') or 0),
                              ParagraphStyle('i', fontSize=8.5, fontName='Helvetica-Bold',
                                             textColor=SANDOVAL_BLUE, alignment=TA_RIGHT)),
                ])
            t = Table(rows, colWidths=[70*mm, 25*mm, 18*mm, 28*mm, 30*mm])
            t.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), SANDOVAL_BLUE),
                ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                ('LINEBELOW', (0,0), (-1,-1), 0.25, SANDOVAL_BORDER),
                ('LEFTPADDING', (0,0), (-1,-1), 4),
                ('RIGHTPADDING', (0,0), (-1,-1), 4),
                ('TOPPADDING', (0,0), (-1,-1), 3),
                ('BOTTOMPADDING', (0,0), (-1,-1), 3),
            ]))
            flow.append(t)
        else:
            flow.append(Paragraph('Sin ítems registrados en presupuesto.',
                                   ParagraphStyle('ni', fontSize=9, textColor=SANDOVAL_GRAY)))

    elif fase_key == 'aprobacion':
        st = (data.get('approval_status') or '').lower() or 'pendiente'
        color_map = {'aprobado': SANDOVAL_GREEN, 'rechazado': SANDOVAL_RED}
        status_col = color_map.get(st, SANDOVAL_AMBER)
        pairs = [
            ('Estado',              st.upper()),
            ('Fecha decisión',      _fmt_fecha(data.get('approval_date'))),
        ]
        flow.append(_kv_table(pairs))
        flow.append(Paragraph(
            f'<font color="{status_col.hexval()}"><b>■</b></font> '
            f'Cotización {"aprobada por el cliente" if st=="aprobado" else ("rechazada por el cliente" if st=="rechazado" else "pendiente de aprobación")}.',
            ParagraphStyle('ap', fontSize=9.5, textColor=SANDOVAL_DARK, leading=12)))

    elif fase_key == 'reparacion':
        acts = _extract_reparacion_items(ck)
        if acts:
            rows = [[
                Paragraph('<b>Actividad</b>',
                          ParagraphStyle('h', fontSize=8.5, textColor=colors.white)),
                Paragraph('<b>Estado</b>',
                          ParagraphStyle('h', fontSize=8.5, textColor=colors.white, alignment=TA_CENTER)),
                Paragraph('<b>Hora</b>',
                          ParagraphStyle('h', fontSize=8.5, textColor=colors.white, alignment=TA_RIGHT)),
            ]]
            for a in acts:
                estado = '✓ Completado' if a.get('completado') else '○ Pendiente'
                color = SANDOVAL_GREEN if a.get('completado') else SANDOVAL_GRAY
                rows.append([
                    Paragraph(str(a.get('tarea') or ''),
                              ParagraphStyle('i', fontSize=9, textColor=SANDOVAL_DARK)),
                    Paragraph(f'<font color="{color.hexval()}">{estado}</font>',
                              ParagraphStyle('i', fontSize=8.5, alignment=TA_CENTER)),
                    Paragraph(str(a.get('hora') or '—'),
                              ParagraphStyle('i', fontSize=8.5, textColor=SANDOVAL_GRAY, alignment=TA_RIGHT)),
                ])
            t = Table(rows, colWidths=[105*mm, 35*mm, 30*mm])
            t.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), SANDOVAL_BLUE),
                ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                ('LINEBELOW', (0,0), (-1,-1), 0.25, SANDOVAL_BORDER),
                ('LEFTPADDING', (0,0), (-1,-1), 4),
                ('RIGHTPADDING', (0,0), (-1,-1), 4),
                ('TOPPADDING', (0,0), (-1,-1), 3),
                ('BOTTOMPADDING', (0,0), (-1,-1), 3),
            ]))
            flow.append(t)
        else:
            flow.append(Paragraph('Sin actividades registradas.',
                                   ParagraphStyle('ni', fontSize=9, textColor=SANDOVAL_GRAY)))

    elif fase_key == 'control_calidad':
        lista = _extract_calidad_checklist(ck)
        if lista:
            rows = []
            for q in lista:
                ok = bool(q.get('ok'))
                icon = '✓' if ok else '✗'
                color = SANDOVAL_GREEN if ok else SANDOVAL_RED
                rows.append([
                    Paragraph(f'<font color="{color.hexval()}"><b>{icon}</b></font>',
                              ParagraphStyle('qi', fontSize=11, alignment=TA_CENTER)),
                    Paragraph(str(q.get('label') or q.get('key') or ''),
                              ParagraphStyle('ql', fontSize=9.5, textColor=SANDOVAL_DARK)),
                ])
            t = Table(rows, colWidths=[12*mm, 158*mm])
            t.setStyle(TableStyle([
                ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                ('LINEBELOW', (0,0), (-1,-2), 0.25, SANDOVAL_BORDER),
                ('TOPPADDING', (0,0), (-1,-1), 2),
                ('BOTTOMPADDING', (0,0), (-1,-1), 2),
            ]))
            flow.append(t)
        else:
            flow.append(Paragraph('Sin checklist de control de calidad registrado.',
                                   ParagraphStyle('ni', fontSize=9, textColor=SANDOVAL_GRAY)))

    elif fase_key == 'entrega':
        pairs = [
            ('Notas al cliente',       data.get('notas_entrega') or '—'),
            ('Próximo mantenimiento',  data.get('proximo_mantenimiento') or '—'),
        ]
        flow.append(_kv_table(pairs))

    # Evidencias: fotos + PDFs + videos
    if media.get('fotos'):
        flow.append(Spacer(1, 2*mm))
        flow.append(Paragraph(f'<b>Fotos de la fase ({len(media["fotos"])}):</b>',
                               ParagraphStyle('pv', fontSize=9, fontName='Helvetica-Bold',
                                              textColor=SANDOVAL_DARK)))
        flow.extend(_photo_grid(media['fotos']))
    for pdf_row in _pdf_list(media.get('pdfs', [])):
        flow.append(pdf_row)
    for v_row in _video_list(media.get('videos', [])):
        flow.append(v_row)

    flow.append(Spacer(1, 3*mm))
    return flow


# ─────────────────────────────────────────────────────────────────
# Builder principal
# ─────────────────────────────────────────────────────────────────
def _build_story(data: Dict[str, Any]) -> List:
    styles = _styles()
    story: List = []
    story.extend(_header_block(styles, data['consecutivo'],
                                datetime.now().strftime('%Y-%m-%d %H:%M')))

    # Cliente & vehículo
    story.extend(_section_title(styles, 'Datos del cliente y vehículo'))
    pairs_main = [
        ('Cliente',        data.get('cliente_nombre') or '—'),
        ('Teléfono',       data.get('cliente_telefono') or '—'),
        ('Vehículo',       f"{data.get('vehiculo_marca','')} {data.get('vehiculo_modelo','')}".strip() or '—'),
        ('Placa',          data.get('vehiculo_placa') or '—'),
        ('Año',            str(data.get('vehiculo_anio') or '—')),
        ('Kilometraje',    str(data.get('km') or '—')),
        ('Fecha de ingreso', _fmt_fecha(data.get('fecha'))),
        ('Estado actual',  data.get('estado') or '—'),
    ]
    story.append(_kv_table(pairs_main))

    # Agrupar evidencias por fase
    grouped = _group_media_by_fase(data.get('fotos') or [])

    # Recorrer fases canónicas
    for fkey, flabel, aliases in FASES_CANONICAS:
        media = _media_for_fase(grouped, aliases)
        story.extend(_render_fase(fkey, flabel, data, media))

    # Totales financieros
    story.extend(_section_title(styles, 'Resumen financiero'))
    total = float(data.get('total') or 0)
    cobrado = float(data.get('cobrado') or 0)
    saldo = max(0.0, total - cobrado)
    rows = [
        [Paragraph('Total', ParagraphStyle('t', fontSize=10, textColor=SANDOVAL_DARK)),
         Paragraph(_fmt_money(total), ParagraphStyle('t', fontSize=10, fontName='Helvetica-Bold',
                                                      textColor=SANDOVAL_BLUE, alignment=TA_RIGHT))],
        [Paragraph('Cobrado', ParagraphStyle('t', fontSize=10, textColor=SANDOVAL_DARK)),
         Paragraph(_fmt_money(cobrado), ParagraphStyle('t', fontSize=10, fontName='Helvetica-Bold',
                                                        textColor=SANDOVAL_GREEN, alignment=TA_RIGHT))],
        [Paragraph('Saldo pendiente', ParagraphStyle('t', fontSize=10, fontName='Helvetica-Bold',
                                                     textColor=SANDOVAL_DARK)),
         Paragraph(_fmt_money(saldo), ParagraphStyle('t', fontSize=10, fontName='Helvetica-Bold',
                                                      textColor=(SANDOVAL_RED if saldo > 0 else SANDOVAL_GREEN),
                                                      alignment=TA_RIGHT))],
    ]
    tfin = Table(rows, colWidths=[130*mm, 45*mm])
    tfin.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('LINEBELOW', (0,0), (-1,-2), 0.25, SANDOVAL_BORDER),
        ('TOPPADDING', (0,0), (-1,-1), 3),
        ('BOTTOMPADDING', (0,0), (-1,-1), 3),
    ]))
    story.append(tfin)

    # Encuesta
    enc = data.get('encuesta') or {}
    if enc.get('estrellas'):
        story.extend(_section_title(styles, 'Calificación del cliente'))
        stars = '★' * int(enc.get('estrellas') or 0) + '☆' * (5 - int(enc.get('estrellas') or 0))
        story.append(Paragraph(
            f'<font color="{SANDOVAL_AMBER.hexval()}"><b>{stars}</b></font> '
            f'({enc.get("estrellas")} de 5)',
            ParagraphStyle('st', fontSize=12, leading=14)
        ))
        if enc.get('comentario'):
            story.append(Paragraph(f'<i>"{enc.get("comentario")}"</i>',
                                    ParagraphStyle('ci', fontSize=9, textColor=SANDOVAL_DARK, leading=12)))

    # Firma
    story.append(Spacer(1, 10*mm))
    sig = Table([[
        Paragraph('_______________________<br/><b>Técnico responsable</b><br/>' + (data.get('tecnico') or ''),
                  ParagraphStyle('s1', fontSize=8.5, alignment=TA_CENTER, textColor=SANDOVAL_DARK, leading=11)),
        Paragraph('_______________________<br/><b>Cliente conforme</b><br/>' + (data.get('cliente_nombre') or ''),
                  ParagraphStyle('s2', fontSize=8.5, alignment=TA_CENTER, textColor=SANDOVAL_DARK, leading=11)),
    ]], colWidths=[87*mm, 87*mm])
    sig.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                              ('TOPPADDING', (0,0), (-1,-1), 6)]))
    story.append(sig)

    return story


# ─────────────────────────────────────────────────────────────────
# API pública
# ─────────────────────────────────────────────────────────────────
def _build_anexo_cover(numero: int, fase: str, nombre_archivo: str,
                         consecutivo: str) -> str:
    """Genera un PDF de UNA página de carátula para anexar antes de cada
    PDF scanner. Devuelve la ruta del archivo temporal."""
    import tempfile
    fd, path = tempfile.mkstemp(suffix='.pdf', prefix='anexo_cover_')
    os.close(fd)
    fase_label = (fase or '').upper().replace('_', ' ') or 'ANEXO'
    doc = SimpleDocTemplate(path, pagesize=A4,
                             leftMargin=20*mm, rightMargin=20*mm,
                             topMargin=30*mm, bottomMargin=30*mm,
                             title=f'Anexo {numero} — {fase_label}')
    elems = []
    elems.append(Paragraph(
        f'<font color="{SANDOVAL_BLUE.hexval()}">ANEXO {numero}</font>',
        ParagraphStyle('a1', fontSize=42, fontName='Helvetica-Bold',
                        textColor=SANDOVAL_BLUE, alignment=TA_CENTER, leading=48,
                        spaceBefore=40*mm, spaceAfter=8*mm)
    ))
    elems.append(HRFlowable(width='60%', thickness=2, color=SANDOVAL_BLUE,
                              spaceAfter=10*mm, hAlign='CENTER'))
    elems.append(Paragraph(
        f'Reporte del scanner — fase de <b>{fase_label}</b>',
        ParagraphStyle('a2', fontSize=16, textColor=SANDOVAL_DARK,
                        alignment=TA_CENTER, leading=22, spaceAfter=14*mm)
    ))
    elems.append(Paragraph(
        nombre_archivo,
        ParagraphStyle('a3', fontSize=11, textColor=SANDOVAL_GRAY,
                        alignment=TA_CENTER, leading=14)
    ))
    elems.append(Spacer(1, 30*mm))
    elems.append(Paragraph(
        f'Orden de servicio: <b>{consecutivo}</b><br/>'
        f'Documento adjunto al informe final.',
        ParagraphStyle('a4', fontSize=10, textColor=SANDOVAL_GRAY,
                        alignment=TA_CENTER, leading=14)
    ))
    doc.build(elems, onFirstPage=_draw_watermark)
    return path


def _embed_scanner_pdfs(out_path: str, fotos_evidencia, consecutivo: str) -> int:
    """Anexa los PDFs scanner del listado de fotos_evidencia al final del PDF.
    Cada anexo va precedido por una carátula con número, fase y nombre.
    Devuelve cuántos PDFs se embebieron.
    """
    try:
        from pypdf import PdfReader, PdfWriter
    except ImportError:
        return 0

    if not isinstance(fotos_evidencia, list):
        return 0

    # Recopilar PDFs scanner ordenados por fase canónica
    fase_orden = {'recepcion': 0, 'diagnostico': 1, 'reparacion': 2,
                   'control_calidad': 3, 'entrega': 4, 'general': 5}
    pdfs = []
    for it in fotos_evidencia:
        if not isinstance(it, dict):
            continue
        url = it.get('url') or it.get('path') or ''
        tipo = (it.get('tipo') or '').lower()
        if tipo != 'pdf' or not url:
            continue
        fpath = _url_to_fspath(url)
        if not fpath:
            continue
        fase = _norm(it.get('fase') or 'general')
        pdfs.append((fase_orden.get(fase, 99), fase, fpath,
                     it.get('nombre') or os.path.basename(fpath)))
    pdfs.sort(key=lambda x: x[0])
    if not pdfs:
        return 0

    writer = PdfWriter()
    # 1) Anexar páginas del informe principal
    try:
        with open(out_path, 'rb') as f:
            base = PdfReader(f)
            for page in base.pages:
                writer.add_page(page)
    except Exception:
        return 0

    # 2) Por cada PDF scanner: cover + páginas
    embebidos = 0
    cover_temp_paths = []
    try:
        for idx, (_, fase, fpath, nombre) in enumerate(pdfs, 1):
            try:
                # Carátula
                cover_path = _build_anexo_cover(idx, fase, nombre, consecutivo)
                cover_temp_paths.append(cover_path)
                with open(cover_path, 'rb') as f:
                    for page in PdfReader(f).pages:
                        writer.add_page(page)
                # Páginas del PDF scanner
                with open(fpath, 'rb') as f:
                    for page in PdfReader(f).pages:
                        writer.add_page(page)
                embebidos += 1
            except Exception as e:
                # Si un PDF está corrupto, lo saltamos pero no rompemos el informe
                logger.warning("[informe] no se pudo embeber %s: %s", fpath, e)
                continue

        # 3) Sobrescribir el PDF final
        if embebidos:
            with open(out_path, 'wb') as f:
                writer.write(f)
    finally:
        # Limpiar covers temporales
        for p in cover_temp_paths:
            try:
                os.remove(p)
            except OSError:
                pass
    return embebidos


def generar_informe_orden(consecutivo: str, taller_id: int) -> str:
    """Genera el informe final PDF y devuelve la ruta absoluta en disco.
    Si falla (orden no existe, etc.) lanza ValueError.
    El nombre es predecible para cachear: informe_{consecutivo}.pdf

    Si la orden tiene PDFs adjuntos del scanner (subidos en diagnóstico o
    reparación), se anexan al final como ANEXOS con carátula propia.
    """
    if not consecutivo:
        raise ValueError('consecutivo vacío')
    os.makedirs(INFORMES_ROOT, exist_ok=True)

    db = get_db()
    try:
        data = _fetch_orden(db, consecutivo, taller_id)
    finally:
        db.close()
    if not data:
        raise ValueError(f'Orden {consecutivo} no encontrada para taller {taller_id}')

    safe = consecutivo.replace('/', '_').replace(' ', '_').replace('#', '')
    out_path = os.path.join(INFORMES_ROOT, f'informe_{safe}.pdf')

    doc = SimpleDocTemplate(
        out_path, pagesize=A4,
        leftMargin=18*mm, rightMargin=18*mm,
        topMargin=16*mm, bottomMargin=18*mm,
        title=f'Informe {consecutivo} — SANDOVAL',
        author='SANDOVAL PRO',
    )
    story = _build_story(data)
    # FIRMA + SELLO DEL TITULAR antes del build final
    try:
        from utils.pdf_generator import _firma_block
        _t_id = 1
        try:
            _t_id = int(data.get('taller_id', 1) if isinstance(data, dict) else 1)
        except Exception:
            _t_id = 1
        for _ff in _firma_block(taller_id=_t_id):
            story.append(_ff)
    except Exception as _e:
        logger.warning('[informe firma error] %s', _e)
    doc.build(story, onFirstPage=_draw_watermark, onLaterPages=_draw_watermark)

    # Anexar PDFs scanner adjuntos (diagnóstico + reparación) como anexos al final
    try:
        n = _embed_scanner_pdfs(out_path, data.get('fotos') or [], consecutivo)
        if n > 0:
            logger.info("[informe] %d PDF(s) scanner anexados a %s", n, out_path)
    except Exception as e:
        # Nunca romper el informe por un fallo del anexado
        logger.warning("[informe] embedding scanner PDFs fallo: %s", e)

    try:
        os.chmod(out_path, 0o644)
    except OSError:
        pass
    return out_path

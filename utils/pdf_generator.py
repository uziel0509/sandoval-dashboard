"""
SANDOVAL Dashboard - Generador de PDFs Profesionales
PDFs de calidad empresarial con ReportLab
"""

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm, cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    Image, HRFlowable, KeepTogether, PageTemplate, Frame, PageBreak
)
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
from datetime import datetime
import os

# Colores corporativos (Actualizados a diseño sophisticated)
SANDOVAL_BLUE = colors.HexColor('#154c79')
SANDOVAL_DARK = colors.HexColor('#333333')
SANDOVAL_GRAY = colors.HexColor('#666666')
SANDOVAL_LIGHT_GRAY = colors.HexColor('#f3f4f6')
SANDOVAL_BORDER = colors.HexColor('#e5e7eb')
SANDOVAL_WHITE = colors.white
SANDOVAL_GREEN = colors.HexColor('#10b981')

def _draw_watermark(canvas, doc):
    """Dibuja el logo como fondo de agua profesional (centrado y sutil)"""
    canvas.saveState()
    img_path = 'assets/logo_sandoval.jpg'
    if os.path.exists(img_path):
        # Logo en el centro con opacidad muy sutil (8%) para no interferir con la lectura
        canvas.setFillAlpha(0.08) 
        # Centrar en A4 (210x297mm)
        w, h = 140*mm, 140*mm
        canvas.drawInlineImage(img_path, (210*mm - w)/2, (297*mm - h)/2, width=w, height=h, preserveAspectRatio=True)
    canvas.restoreState()

def _get_styles():
    """Crea estilos personalizados para los PDFs"""
    styles = getSampleStyleSheet()
    
    styles.add(ParagraphStyle(
        name='SandovalTitle',
        fontSize=18,
        fontName='Helvetica-Bold',
        textColor=SANDOVAL_BLUE,
        alignment=TA_LEFT,
    ))
    styles.add(ParagraphStyle(
        name='SandovalSection',
        fontSize=11,
        fontName='Helvetica-Bold',
        textColor=SANDOVAL_BLUE,
        spaceBefore=8*mm,
        spaceAfter=4*mm,
        textTransform='uppercase',
    ))
    styles.add(ParagraphStyle(
        name='SandovalBody',
        fontSize=9.5,
        fontName='Helvetica',
        textColor=SANDOVAL_DARK,
        leading=12,
    ))
    styles.add(ParagraphStyle(
        name='SandovalSmall',
        fontSize=8,
        fontName='Helvetica',
        textColor=SANDOVAL_GRAY,
        leading=10,
    ))
    styles.add(ParagraphStyle(
        name='SandovalFooter',
        fontSize=7.5,
        fontName='Helvetica',
        textColor=SANDOVAL_GRAY,
        alignment=TA_CENTER,
    ))
    
    return styles

def _header_table(title: str, doc_number: str, date_str: str):
    """Crea el encabezado con el diseño sofisticado (líneas azules, jerarquía clara)"""
    logo_path = 'assets/logo_sandoval.jpg'
    
    # Columna izquierda: Logo y Datos empresa
    company_info = [
        Paragraph('<b>MECÁNICA Y REPUESTOS SANDOVAL EIRL</b>', 
                  ParagraphStyle('c', fontSize=13, fontName='Helvetica-Bold', textColor=SANDOVAL_BLUE, leading=15)),
        Paragraph('RUC: 20608755111', 
                  ParagraphStyle('c', fontSize=8, fontName='Helvetica', textColor=SANDOVAL_GRAY, leading=10)),
        Paragraph('Av. Principal 123, Piura, Perú', 
                  ParagraphStyle('c', fontSize=8, fontName='Helvetica', textColor=SANDOVAL_GRAY, leading=10)),
        Paragraph('+51 999 999 999 | contacto@sandoval.com', 
                  ParagraphStyle('c', fontSize=8, fontName='Helvetica', textColor=SANDOVAL_GRAY, leading=10)),
    ]
    
    # Columna derecha: Título doc y Número (Ajustado interlineado y tamaño)
    doc_info = [
        Paragraph(title.upper(), 
                  ParagraphStyle('d', fontSize=9.5, fontName='Helvetica', textColor=SANDOVAL_GRAY, alignment=TA_RIGHT, leading=12)),
        Paragraph(doc_number, 
                  ParagraphStyle('d', fontSize=17, fontName='Helvetica-Bold', textColor=SANDOVAL_BLUE, alignment=TA_RIGHT, leading=20)),
        Paragraph(f'Fecha: {date_str}', 
                  ParagraphStyle('d', fontSize=8.5, fontName='Helvetica', textColor=SANDOVAL_GRAY, alignment=TA_RIGHT, leading=11)),
    ]
    
    # Contenido Izquierdo
    left_content = []
    if os.path.exists(logo_path):
        img = Image(logo_path, width=22*mm, height=22*mm)
        # Reducimos ancho de la info empresa para que no empuje el folio
        left_content = [Table([[img, company_info]], colWidths=[24*mm, 70*mm], style=TableStyle([
            ('VALIGN',(0,0),(-1,-1),'MIDDLE'),
            ('LEFTPADDING', (0,0), (-1,1), 0),
        ]))]
    else:
        left_content = company_info

    data = [[left_content, doc_info]]
    
    # Ajustamos balance: Izquierda 95mm, Derecha 85mm (folio largo sin wrap)
    t = Table(data, colWidths=[100*mm, 80*mm])
    t.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        # Líneas azules gruesas arriba y abajo
        ('LINEABOVE', (0, 0), (-1, 0), 2.5, SANDOVAL_BLUE),
        ('LINEBELOW', (0, 0), (-1, 0), 1.5, SANDOVAL_BLUE),
        ('TOPPADDING', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
    ]))
    return t

def _info_pair_table(pairs: list, widths=[30*mm, 55*mm]):
    """Crea tabla de pares label:valor con diseño de cuadro sofisticado"""
    data = []
    for label, value in pairs:
        data.append([
            Paragraph(f'<b>{label}</b>', ParagraphStyle('l', fontSize=8.5, fontName='Helvetica', textColor=SANDOVAL_GRAY)),
            Paragraph(str(value or '-'), ParagraphStyle('v', fontSize=9, fontName='Helvetica', textColor=SANDOVAL_DARK)),
        ])
    
    t = Table(data, colWidths=widths)
    t.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.5, SANDOVAL_BORDER),
        ('BACKGROUND', (0, 0), (0, -1), SANDOVAL_LIGHT_GRAY),
        ('TOPPADDING', (0, 0), (-1, -1), 4.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4.5),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
    ]))
    return t


def generate_orden_ingreso(order: dict, client: dict, vehicle: dict, filepath: str):
    """
    Genera PDF de Orden de Ingreso con diseño refinado y profesional
    """
    styles = _get_styles()
    doc = SimpleDocTemplate(
        filepath, pagesize=A4,
        leftMargin=15*mm, rightMargin=15*mm,
        topMargin=12*mm, bottomMargin=20*mm
    )

    def on_page(canvas, doc):
        _draw_watermark(canvas, doc)
    
    elements = []
    date_str = order.get('fecha', datetime.now().strftime('%d/%m/%Y %H:%M'))
    
    # Header
    elements.append(_header_table('ORDEN DE INGRESO', order.get('consecutivo', ''), date_str))
    elements.append(Spacer(1, 8*mm))
    
    # Información del Cliente y Vehículo
    elements.append(Paragraph('DATOS DEL CLIENTE Y VEHÍCULO', styles['SandovalSection']))
    
    # Bloque de información
    client_info = _info_pair_table([
        ('Cliente:', f"{client.get('nombre', '')} {client.get('apellidos', '')}"),
        ('Doc:', client.get('id', '')),
        ('Teléfono:', client.get('telefono', '')),
        ('Email:', client.get('email', '')),
    ], widths=[22*mm, 62*mm])
    
    vehicle_info = _info_pair_table([
        ('Vehículo:', f"{vehicle.get('marca', '')} {vehicle.get('modelo', '')} {vehicle.get('año', '')}"),
        ('Placa:', vehicle.get('placa', '')),
        ('VIN:', vehicle.get('vin', '') or '-'),
        ('KM:', f"{order.get('km', '')}" if order.get('km') else '-'),
    ], widths=[22*mm, 62*mm])
    
    info_layout = Table([[client_info, vehicle_info]], colWidths=[88*mm, 88*mm])
    info_layout.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (0, 0), 0),
        ('RIGHTPADDING', (1, 0), (1, 0), 0),
    ]))
    elements.append(info_layout)
    
    # Motivo de ingreso
    elements.append(Paragraph('MOTIVO DE INGRESO', styles['SandovalSection']))
    elements.append(Paragraph(order.get('motivo', 'No especificado'), styles['SandovalBody']))
    elements.append(Spacer(1, 4*mm))
    
    if order.get('tipo'):
        elements.append(Paragraph(f"Tipo de servicio: <b>{order.get('tipo', '')}</b>", styles['SandovalBody']))
    if order.get('tecnico'):
        elements.append(Paragraph(f"Técnico asignado: <b>{order.get('tecnico', '')}</b>", styles['SandovalBody']))
    
    # Términos y Condiciones
    elements.append(Paragraph('TÉRMINOS Y CONDICIONES', styles['SandovalSection']))
    terms = [
        '1. El cliente autoriza los trabajos descritos y el desmontaje necesario para el diagnóstico.',
        '2. La empresa no se responsabiliza por objetos de valor dejados dentro del vehículo.',
        '3. Todo diagnóstico tiene un costo, el cual será descontado si se aprueba la reparación.',
        '4. Los repuestos retirados serán devueltos al cliente si este lo solicita.',
        '5. El plazo de entrega es estimado y puede variar según disponibilidad de repuestos.',
    ]
    for t in terms:
        elements.append(Paragraph(t, styles['SandovalSmall']))
        elements.append(Spacer(1, 0.5*mm))
    
    elements.append(Spacer(1, 25*mm))
    
    # Firmas balanceadas
    sig_data = [
        ['' , ''], # Espacio para firma
        ['_' * 45, '_' * 45],
        ['Firma del Cliente', 'Firma del Taller'],
    ]
    sig_table = Table(sig_data, colWidths=[90*mm, 90*mm])
    sig_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTSIZE', (0, 2), (-1, 2), 8.5),
        ('TEXTCOLOR', (0, 2), (-1, 2), SANDOVAL_DARK),
        ('TOPPADDING', (0, 1), (-1, 1), 2),
    ]))
    elements.append(sig_table)
    
    # Footer
    elements.append(Spacer(1, 12*mm))
    elements.append(Paragraph(
        'MECÁNICA Y REPUESTOS SANDOVAL EIRL - Gracias por su confianza',
        styles['SandovalFooter']
    ))
    
    doc.build(elements, onFirstPage=on_page, onLaterPages=on_page)
    return filepath
    
    doc.build(elements, onFirstPage=on_page, onLaterPages=on_page)
    return filepath


def generate_cotizacion(order: dict, client: dict, vehicle: dict, items: list, filepath: str):
    """
    Genera PDF de Cotización con diseño premium
    """
    styles = _get_styles()
    doc = SimpleDocTemplate(
        filepath, pagesize=A4,
        leftMargin=15*mm, rightMargin=15*mm,
        topMargin=12*mm, bottomMargin=20*mm
    )

    def on_page(canvas, doc):
        _draw_watermark(canvas, doc)
    
    elements = []
    date_str = datetime.now().strftime('%d/%m/%Y %H:%M')
    
    # Header
    elements.append(_header_table('COTIZACIÓN', order.get('consecutivo', ''), date_str))
    elements.append(Spacer(1, 8*mm))
    
    # Información del Cliente y Vehículo
    elements.append(Paragraph('DATOS DEL CLIENTE', styles['SandovalSection']))
    
    client_info = _info_pair_table([
        ('Cliente:', f"{client.get('nombre', '')} {client.get('apellidos', '')}"),
        ('Doc:', client.get('id', '')),
        ('Teléfono:', client.get('telefono', '')),
    ], widths=[22*mm, 62*mm])
    
    vehicle_info = _info_pair_table([
        ('Vehículo:', f"{vehicle.get('marca', '')} {vehicle.get('modelo', '')}"),
        ('Placa:', vehicle.get('placa', '')),
        ('KM:', f"{order.get('km', '')}" if order.get('km') else '-'),
    ], widths=[22*mm, 62*mm])
    
    info_layout = Table([[client_info, vehicle_info]], colWidths=[88*mm, 88*mm])
    info_layout.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (0, 0), 0),
        ('RIGHTPADDING', (1, 0), (1, 0), 0),
    ]))
    elements.append(info_layout)
    
    # Tabla de ítems
    elements.append(Paragraph('DETALLE DE SERVICIOS Y REPUESTOS', styles['SandovalSection']))
    
    # Header de tabla
    table_data = [['#', 'Descripción', 'Tipo', 'Cant.', 'Precio']]
    
    total_general = 0
    for i, item in enumerate(items, 1):
        if not item: continue
        p_unit = float(item.get('precio_unitario', item.get('valor_unitario', item.get('precio', 0))) or 0)
        can = float(item.get('cantidad', 1) or 1)
        item_total = float(item.get('total', p_unit * can) or (p_unit * can))
        
        total_general += item_total
        nombre_txt = str(item.get('item', item.get('nombre', '')) or '')
        # Paragraph para wrap automático cuando es largo
        from reportlab.lib.styles import ParagraphStyle as _PS
        _ps_cell = _PS('cellNombre', fontSize=8.5, leading=11, textColor=SANDOVAL_DARK)
        cant_str = ('%.2f' % can).rstrip('0').rstrip('.') if can != int(can) else str(int(can))
        table_data.append([
            str(i),
            Paragraph(nombre_txt.replace('&','&amp;').replace('<','&lt;').replace('>','&gt;'), _ps_cell),
            item.get('tipo', 'Servicio'),
            cant_str,
            f"S/ {item_total:.2f}",
        ])
    
    # Colwidths: # (10), Desc (90), Tipo (30), Cant (15), Total (30)
    col_widths = [10*mm, 85*mm, 25*mm, 20*mm, 35*mm]
    t = Table(table_data, colWidths=col_widths)
    
    style_commands = [
        ('BACKGROUND', (0, 0), (-1, 0), SANDOVAL_BLUE),
        ('TEXTCOLOR', (0, 0), (-1, 0), SANDOVAL_WHITE),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('FONTSIZE', (0, 1), (-1, -1), 9),
        ('ALIGN', (3, 0), (-1, -1), 'CENTER'),
        ('ALIGN', (4, 0), (-1, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.5, SANDOVAL_BORDER),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]
    
    # Alternar colores de fila
    for i in range(1, len(table_data)):
        if i % 2 == 0:
            style_commands.append(('BACKGROUND', (0, i), (-1, i), SANDOVAL_LIGHT_GRAY))
    
    t.setStyle(TableStyle(style_commands))
    elements.append(t)
    
    # Total Final
    total_data = [['', '', '', 'TOTAL:', f'S/ {total_general:.2f}']]
    total_table = Table(total_data, colWidths=col_widths)
    total_table.setStyle(TableStyle([
        ('ALIGN', (3, 0), (3, 0), 'RIGHT'),
        ('ALIGN', (4, 0), (4, 0), 'RIGHT'),
        ('FONTNAME', (3, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (3, 0), (-1, 0), 11),
        ('TEXTCOLOR', (4, 0), (4, 0), SANDOVAL_GREEN),
        ('TOPPADDING', (0, 0), (-1, 0), 5),
    ]))
    elements.append(total_table)
    elements.append(Spacer(1, 8*mm))
    
    # Resumen de Diagnóstico (NUEVO)
    if order.get('diagnostico'):
        elements.append(Paragraph('RESUMEN DE DIAGNÓSTICO', styles['SandovalSection']))
        elements.append(Paragraph(order['diagnostico'].replace('\n', '<br/>'), styles['SandovalBody']))
        elements.append(Spacer(1, 6*mm))
    
    # Notas
    elements.append(Paragraph('NOTAS', styles['SandovalSection']))
    notes = [
        '• Esta cotización tiene una validez de 15 días calendario.',
        '• Los precios ya incluyen costos de mano de obra salvo indicación contraria.',
        '• Los repuestos retirados serán devueltos al cliente si lo solicita.',
        '• El plazo estimado de entrega se confirmará al aprobar el presupuesto.',
    ]
    for n in notes:
        elements.append(Paragraph(n, styles['SandovalSmall']))
        elements.append(Spacer(1, 0.5*mm))
    
    # Footer con teléfono real del taller (lee de config_sistema, fallback default)
    _emp_tel = '+51 924 980 586'
    _emp_nom = 'MECÁNICA Y REPUESTOS SANDOVAL EIRL'
    try:
        from utils.models import get_db
        from sqlalchemy import text as _sql
        _db = get_db()
        try:
            _t_id = int(order.get('taller_id', 1) or 1) if isinstance(order, dict) else 1
            _r = _db.execute(_sql(
                "SELECT clave, valor FROM config_sistema WHERE taller_id=:t AND clave IN ('telefono','empresa_nombre','nombre_taller')"
            ), {'t': _t_id}).fetchall()
            for k, v in _r:
                if k == 'telefono' and v: _emp_tel = v if v.startswith('+') else ('+51 ' + v.lstrip('+51').strip())
                elif k in ('empresa_nombre','nombre_taller') and v: _emp_nom = v
        finally:
            _db.close()
    except Exception:
        pass

    # Firma + sello al final
    try:
        for _ff in _firma_block(taller_id=int(order.get('taller_id', 1) or 1) if isinstance(order, dict) else 1):
            elements.append(_ff)
    except Exception:
        pass

    elements.append(Spacer(1, 8*mm))
    elements.append(Paragraph(
        f'{_emp_nom} - Consultas al {_emp_tel}',
        styles['SandovalFooter']
    ))
    # NOTA: sección de diagnóstico/evidencia REMOVIDA del presupuesto.
    # El presupuesto solo lleva los items + firma + footer.
    
    doc.build(elements, onFirstPage=on_page, onLaterPages=on_page)
    return filepath

def _add_diagnostic_report_section(elements, order, styles):
    """Añade el reporte técnico completo como anexos a la cotización"""
    import json
    chk = order.get('checklist_reparacion', {})
    if isinstance(chk, str):
        try: chk = json.loads(chk)
        except: chk = {}
    
    fotos = order.get('fotos_evidencia', [])
    diag_details = (chk or {}).get('diagnostic_details', {})
    quick_check = (chk or {}).get('quick_check', {})

    if not any([fotos, diag_details, quick_check]):
        return

    elements.append(PageBreak())
    elements.append(Paragraph('REPORTE TÉCNICO DE DIAGNÓSTICO', styles['SandovalTitle']))
    elements.append(Spacer(1, 4*mm))
    
    # 1. Inspección Visual
    if quick_check:
        elements.append(Paragraph('INSPECCIÓN VISUAL PREVENTIVA', styles['SandovalSection']))
        check_data = []
        for item, data in quick_check.items():
            status = data.get('status') if isinstance(data, dict) else data
            note = data.get('note', '') if isinstance(data, dict) else ''
            check_data.append([
                Paragraph(item, styles['SandovalBody']),
                Paragraph(f"<b>{status}</b>" + (f" - {note}" if note else ""), styles['SandovalBody'])
            ])
        if check_data:
            t = Table(check_data, colWidths=[60*mm, 120*mm])
            t.setStyle(TableStyle([
                ('GRID', (0,0), (-1,-1), 0.5, SANDOVAL_BORDER),
                ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                ('BACKGROUND', (0,0), (0,-1), SANDOVAL_LIGHT_GRAY),
            ]))
            elements.append(t)
            elements.append(Spacer(1, 6*mm))

    # 2. Detalles del diagnóstico
    if diag_details:
        elements.append(Paragraph('ANÁLISIS TÉCNICO Y HALLAZGOS', styles['SandovalSection']))
        
        def _add_detail(lbl, val):
            if val:
                elements.append(Paragraph(f"<b>{lbl.upper()}:</b>", styles['SandovalSmall']))
                elements.append(Paragraph(str(val).replace('\n', '<br/>'), styles['SandovalBody']))
                elements.append(Spacer(1, 4*mm))

        systems = diag_details.get('system', [])
        if systems:
            _add_detail('Sistemas Evaluados', ", ".join(systems) if isinstance(systems, list) else systems)
        
        _add_detail('Pruebas e Inspecciones', diag_details.get('tests'))
        _add_detail('Hallazgos / Causa Raíz', diag_details.get('analysis'))
        _add_detail('Solución Recomendada', diag_details.get('solution'))

    # 3. Evidencia Fotográfica
    if fotos and isinstance(fotos, list):
        elements.append(Paragraph('EVIDENCIA FOTOGRÁFICA', styles['SandovalSection']))
        img_cells = []
        row = []
        for path in fotos:
            # Normalizar: si es dict, extraer url; si no es string válida, saltar
            if isinstance(path, dict):
                path = path.get('url') or path.get('path') or ''
            if not isinstance(path, str) or not path:
                continue
            # Filtrar videos/PDFs (solo imágenes en el PDF de cotización)
            if any(path.lower().endswith(ext) for ext in ('.mp4','.mov','.webm','.avi','.pdf')):
                continue
            p = path.lstrip('/')
            # Ajuste de ruta para ReportLab
            if p.startswith('evidencia'): p = 'static/' + p
            
            if os.path.exists(p):
                try:
                    img = Image(p, width=54*mm, height=40*mm, kind='proportional')
                    row.append(img)
                except:
                    pass
            
            if len(row) == 3:
                img_cells.append(row)
                row = []
        
        if row:
            while len(row) < 3: row.append("")
            img_cells.append(row)
        
        if img_cells:
            t = Table(img_cells, colWidths=[60*mm, 60*mm, 60*mm])
            t.setStyle(TableStyle([
                ('ALIGN', (0,0), (-1,-1), 'CENTER'),
                ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                ('TOPPADDING', (0,0), (-1,-1), 2*mm),
                ('BOTTOMPADDING', (0,0), (-1,-1), 2*mm),
            ]))
            elements.append(t)


def generate_factura(order: dict, client: dict, items: list, filepath: str, tipo: str = 'BOLETA'):
    """
    Genera PDF de Factura/Boleta con diseño sofisticado
    """
    styles = _get_styles()
    doc = SimpleDocTemplate(
        filepath, pagesize=A4,
        leftMargin=15*mm, rightMargin=15*mm,
        topMargin=12*mm, bottomMargin=20*mm
    )

    def on_page(canvas, doc):
        _draw_watermark(canvas, doc)
    
    elements = []
    date_str = datetime.now().strftime('%d/%m/%Y %H:%M')
    
    # Header
    elements.append(_header_table(tipo, order.get('consecutivo', ''), date_str))
    elements.append(Spacer(1, 8*mm))
    
    # Datos cliente
    elements.append(Paragraph('INFORMACIÓN DEL CLIENTE', styles['SandovalSection']))
    client_data = [
        ('Cliente:', f"{client.get('nombre', '')} {client.get('apellidos', '')}"),
        ('DNI/RUC:', client.get('id', '')),
        ('Dirección:', client.get('direccion', '')),
    ]
    elements.append(_info_pair_table(client_data, widths=[35*mm, 140*mm]))
    elements.append(Spacer(1, 8*mm))
    
    # Tabla ítems
    elements.append(Paragraph('DETALLE DEL DOCUMENTO', styles['SandovalSection']))
    table_data = [['#', 'Descripción', 'Cant.', 'Precio Unit.', 'Total']]
    
    subtotal = 0
    for i, item in enumerate(items, 1):
        if not item: continue
        p_unit = float(item.get('precio_unitario', item.get('valor_unitario', item.get('precio', 0))) or 0)
        can = float(item.get('cantidad', 1) or 1)
        item_total = float(item.get('total', p_unit * can) or (p_unit * can))
        
        subtotal += item_total
        table_data.append([
            str(i),
            item.get('nombre', item.get('item', '')),
            str(int(can)),
            f"S/ {p_unit:.2f}",
            f"S/ {item_total:.2f}",
        ])
    
    col_widths = [10*mm, 90*mm, 20*mm, 25*mm, 30*mm]
    t = Table(table_data, colWidths=col_widths)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), SANDOVAL_BLUE),
        ('TEXTCOLOR', (0, 0), (-1, 0), SANDOVAL_WHITE),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('ALIGN', (2, 0), (-1, -1), 'CENTER'),
        ('ALIGN', (3, 0), (-1, -1), 'RIGHT'),
        ('ALIGN', (4, 0), (-1, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.5, SANDOVAL_BORDER),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    elements.append(t)
    
    # Total
    total_table = Table([['', '', '', 'TOTAL:', f'S/ {subtotal:.2f}']], colWidths=col_widths)
    total_table.setStyle(TableStyle([
        ('ALIGN', (3, 0), (4, 0), 'RIGHT'),
        ('FONTNAME', (3, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (3, 0), (-1, 0), 11),
        ('TEXTCOLOR', (4, 0), (4, 0), SANDOVAL_BLUE),
    ]))
    elements.append(total_table)
    
    # Footer
    elements.append(Spacer(1, 20*mm))
    elements.append(Paragraph(
        'Este documento es una representación impresa de un comprobante electrónico.',
        styles['SandovalFooter']
    ))
    
    doc.build(elements, onFirstPage=on_page, onLaterPages=on_page)
    return filepath


def generate_list_report(title: str, headers: list, data: list, filepath: str):
    """
    Genera un PDF profesional para listados (Clientes, Vehículos, Proveedores, etc.)
    """
    styles = _get_styles()
    doc = SimpleDocTemplate(
        filepath, pagesize=A4,
        leftMargin=10*mm, rightMargin=10*mm,
        topMargin=12*mm, bottomMargin=20*mm
    )

    if len(headers) > 6:
        from reportlab.lib.pagesizes import landscape
        doc.pagesize = landscape(A4)

    def on_page(canvas, doc):
        _draw_watermark(canvas, doc)
    
    elements = []
    date_str = datetime.now().strftime('%d/%m/%Y %H:%M')
    
    elements.append(_header_table(title, 'REPORTE GENERAL', date_str))
    elements.append(Spacer(1, 10*mm))
    
    table_data = [headers] + data
    page_width = doc.pagesize[0] - 20*mm
    col_width = page_width / len(headers)
    col_widths = [col_width] * len(headers)
    
    if headers[0].lower() in ('#', 'id'):
        col_widths[0] = 20*mm
        remaining = page_width - 20*mm
        col_widths[1:] = [remaining / (len(headers)-1)] * (len(headers)-1)

    t = Table(table_data, colWidths=col_widths, repeatRows=1)
    
    style_commands = [
        ('BACKGROUND', (0, 0), (-1, 0), SANDOVAL_BLUE),
        ('TEXTCOLOR', (0, 0), (-1, 0), SANDOVAL_WHITE),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.5, SANDOVAL_BORDER),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]
    
    for i in range(1, len(table_data)):
        if i % 2 == 0:
            style_commands.append(('BACKGROUND', (0, i), (-1, i), SANDOVAL_LIGHT_GRAY))
    
    t.setStyle(TableStyle(style_commands))
    elements.append(t)
    
    elements.append(Spacer(1, 15*mm))
    elements.append(Paragraph(
        f'MECÁNICA Y REPUESTOS SANDOVAL EIRL - {title} - {len(data)} registros',
        styles['SandovalFooter']
    ))
    
    doc.build(elements, onFirstPage=on_page, onLaterPages=on_page)
    return filepath


def generate_qr_flyer(qr_data_url: str, filepath: str):
    """
    Genera un PDF 'Flyer' ultra profesional con el código QR para el portal del cliente.
    """
    import urllib.request
    from reportlab.lib.pagesizes import A4
    
    styles = _get_styles()
    doc = SimpleDocTemplate(
        filepath, pagesize=A4,
        leftMargin=20*mm, rightMargin=20*mm,
        topMargin=20*mm, bottomMargin=20*mm
    )

    elements = []
    
    # 1. LOGO PRINCIPAL (Grande y centrado)
    logo_path = 'assets/logo_sandoval.jpg'
    if os.path.exists(logo_path):
        elements.append(Image(logo_path, width=60*mm, height=60*mm))
        elements.append(Spacer(1, 10*mm))
    
    # 2. TÍTULO DE BIENVENIDA
    title_style = ParagraphStyle(
        'FlyerTitle',
        parent=styles['SandovalTitle'],
        fontSize=28,
        alignment=TA_CENTER,
        leading=34,
        textColor=SANDOVAL_BLUE
    )
    elements.append(Paragraph('BIENVENIDOS A<br/>MECÁNICA Y REPUESTOS SANDOVAL', title_style))
    elements.append(Spacer(1, 8*mm))
    
    # 3. MENSAJE DE MARKETING (FLORO)
    body_style = ParagraphStyle(
        'FlyerBody',
        parent=styles['SandovalBody'],
        fontSize=14,
        alignment=TA_CENTER,
        leading=18,
        textColor=SANDOVAL_DARK
    )
    marketing_text = (
        "Su confianza es nuestro motor. En nuestro taller, la <b>transparencia</b> es primordial. "
        "Hemos diseñado un sistema exclusivo para que usted tenga el control total de su servicio."
    )
    elements.append(Paragraph(marketing_text, body_style))
    elements.append(Spacer(1, 10*mm))
    
    # 4. INSTRUCCIONES
    inst_style = ParagraphStyle(
        'FlyerInst',
        parent=styles['SandovalBody'],
        fontSize=12,
        alignment=TA_CENTER,
        textColor=SANDOVAL_GRAY
    )
    elements.append(Paragraph("Escanee este código QR para acceder a nuestro <b>Portal de Clientes</b> y visualice en tiempo real:", inst_style))
    elements.append(Spacer(1, 6*mm))
    
    # 5. BENEFICIOS (Lista)
    benefit_style = ParagraphStyle(
        'FlyerBenefit',
        parent=styles['SandovalBody'],
        fontSize=11,
        alignment=TA_LEFT,
        leftIndent=40*mm,
        leading=14
    )
    benefits = [
        "✅ Diagnóstico detallado con reporte de escáner.",
        "📸 Evidencia fotográfica de los trabajos realizados.",
        "💰 Presupuestos claros y aprobaciones inmediatas.",
        "🚀 Seguimiento de las 7 fases de su reparación."
    ]
    for b in benefits:
        elements.append(Paragraph(b, benefit_style))
        elements.append(Spacer(1, 2*mm))
    
    elements.append(Spacer(1, 12*mm))
    
    # 6. EL CÓDIGO QR (Centrado y de buen tamaño)
    # Descargar la imagen del QR temporalmente
    temp_qr = "pdfs/temp_qr.png"
    try:
        urllib.request.urlretrieve(qr_data_url, temp_qr)
        qr_img = Image(temp_qr, width=85*mm, height=85*mm)
        
        # Tabla para centrar el QR
        qr_table = Table([[qr_img]], colWidths=[170*mm])
        qr_table.setStyle(TableStyle([
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            # Borde elegante alrededor del QR
            ('BOX', (0,0), (-1,-1), 2, SANDOVAL_BLUE),
            ('TOPPADDING', (0,0), (-1,-1), 5*mm),
            ('BOTTOMPADDING', (0,0), (-1,-1), 5*mm),
        ]))
        elements.append(qr_table)
    except Exception as e:
        elements.append(Paragraph(f"Error al cargar QR: {str(e)}", styles['SandovalBody']))
    
    elements.append(Spacer(1, 10*mm))
    elements.append(Paragraph("¡Llevamos la tecnología al cuidado de su vehículo!", body_style))
    
    # 7. FOOTER
    elements.append(Spacer(1, 15*mm))
    line = HRFlowable(width="100%", thickness=1, color=SANDOVAL_BLUE, spaceBefore=1, spaceAfter=5)
    elements.append(line)
    
    footer_text = "<b>SANDOVAL Dashboard v2.0</b>  |  Atención: +51 924 980 586  |  Piura, Perú"
    elements.append(Paragraph(footer_text, styles['SandovalFooter']))

    doc.build(elements)
    
    # Limpiar temporal
    if os.path.exists(temp_qr):
        try: os.remove(temp_qr)
        except: pass
        
    return filepath


def generate_pdf(order: dict, client: dict, vehicle: dict, pdf_type: str, filepath: str):
    """
    Controlador central para generar diferentes tipos de PDF (Ingreso, Cotización, Factura)
    """
    # Protección extra contra None
    order = order if order is not None else {}
    client = client if client is not None else {}
    vehicle = vehicle if vehicle is not None else {}
    
    if pdf_type in ('ingreso', 'recepcion'):
        return generate_orden_ingreso(order, client, vehicle, filepath)
    elif pdf_type == 'cotizacion':
        items = order.get('items_cotizacion', []) or []
        return generate_cotizacion(order, client, vehicle, items, filepath)
    elif pdf_type == 'factura':
        items = (order.get('items_cotizacion', []) or [])
        return generate_factura(order, client, items, filepath, 'BOLETA DE VENTA')
    elif pdf_type == 'qr_flyer':
        # En este caso, order se usa para pasar la URL del QR
        url = order.get('qr_url')
        return generate_qr_flyer(url, filepath)
    else:
        raise ValueError(f"Tipo de PDF no reconocido: {pdf_type}")


# ── HELPER: solo la imagen digitalizada de firma + sello ──────────
def _firma_block(taller_id: int = 1, **kwargs):
    """Devuelve solo la imagen digitalizada del sello+firma del taller.
    El upload_firma ya procesa la imagen (fondo transparente, contraste).
    Si no existe, devuelve fallback texto simple."""
    from reportlab.platypus import Spacer, Paragraph, Image as RLImage
    from reportlab.lib import colors
    from reportlab.lib.units import cm, mm
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_CENTER

    elems = []
    elems.append(Spacer(1, 1.0*cm))

    firma_path = "/var/www/sandoval/assets/firma/taller_" + str(taller_id) + ".png"
    if os.path.isfile(firma_path):
        try:
            img = RLImage(firma_path, width=8*cm, height=4*cm, kind='proportional')
            img.hAlign = 'CENTER'
            elems.append(img)
            return elems
        except Exception:
            pass

    # Fallback texto si no hay imagen
    s_name = ParagraphStyle('FrName', fontSize=12, leading=15, textColor=colors.HexColor('#0f172a'),
                            alignment=TA_CENTER, fontName='Helvetica-Oblique')
    s_cargo = ParagraphStyle('FrCargo', fontSize=8, leading=11, textColor=colors.HexColor('#274495'),
                             alignment=TA_CENTER, fontName='Helvetica-Bold')
    elems.append(Spacer(1, 1.5*cm))
    elems.append(Paragraph('Milton Fabio Sandoval Horna', s_name))
    elems.append(Paragraph('TITULAR GERENTE', s_cargo))
    return elems

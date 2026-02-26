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
    Image, HRFlowable, KeepTogether
)
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
from datetime import datetime
import os

# Colores corporativos
SANDOVAL_LIME = colors.HexColor('#ccff00')
SANDOVAL_DARK = colors.HexColor('#0e1117')
SANDOVAL_CARD = colors.HexColor('#1c2025')
SANDOVAL_BORDER = colors.HexColor('#333333')
SANDOVAL_WHITE = colors.white
SANDOVAL_GRAY = colors.HexColor('#a0a0a0')
SANDOVAL_GREEN = colors.HexColor('#10b981')

def _get_styles():
    """Crea estilos personalizados para los PDFs"""
    styles = getSampleStyleSheet()
    
    styles.add(ParagraphStyle(
        name='SandovalTitle',
        fontSize=20,
        fontName='Helvetica-Bold',
        textColor=SANDOVAL_DARK,
        spaceAfter=6*mm,
        alignment=TA_CENTER,
    ))
    styles.add(ParagraphStyle(
        name='SandovalSubtitle',
        fontSize=12,
        fontName='Helvetica',
        textColor=SANDOVAL_GRAY,
        spaceAfter=4*mm,
        alignment=TA_CENTER,
    ))
    styles.add(ParagraphStyle(
        name='SandovalSection',
        fontSize=12,
        fontName='Helvetica-Bold',
        textColor=SANDOVAL_DARK,
        spaceBefore=6*mm,
        spaceAfter=3*mm,
    ))
    styles.add(ParagraphStyle(
        name='SandovalBody',
        fontSize=10,
        fontName='Helvetica',
        textColor=SANDOVAL_DARK,
        spaceAfter=2*mm,
    ))
    styles.add(ParagraphStyle(
        name='SandovalSmall',
        fontSize=8,
        fontName='Helvetica',
        textColor=SANDOVAL_GRAY,
    ))
    styles.add(ParagraphStyle(
        name='SandovalFooter',
        fontSize=7,
        fontName='Helvetica',
        textColor=SANDOVAL_GRAY,
        alignment=TA_CENTER,
    ))
    
    return styles

def _header_table(title: str, doc_number: str, date_str: str):
    """Crea el encabezado del documento"""
    data = [
        [
            Paragraph('<b>MECÁNICA Y REPUESTOS<br/>SANDOVAL EIRL</b>', 
                      ParagraphStyle('h', fontSize=14, fontName='Helvetica-Bold', textColor=SANDOVAL_DARK)),
            '',
            Paragraph(f'<b>{title}</b><br/><font size="14" color="#ccff00">{doc_number}</font>', 
                      ParagraphStyle('h', fontSize=10, fontName='Helvetica', textColor=SANDOVAL_DARK, alignment=TA_RIGHT)),
        ],
        [
            Paragraph('RUC: 20608755111<br/>Piura, Perú<br/>+51 999 999 999', 
                      ParagraphStyle('h', fontSize=8, fontName='Helvetica', textColor=SANDOVAL_GRAY)),
            '',
            Paragraph(f'Fecha: {date_str}', 
                      ParagraphStyle('h', fontSize=9, fontName='Helvetica', textColor=SANDOVAL_GRAY, alignment=TA_RIGHT)),
        ]
    ]
    
    t = Table(data, colWidths=[60*mm, 30*mm, 80*mm])
    t.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LINEBELOW', (0, -1), (-1, -1), 1, SANDOVAL_LIME),
        ('BOTTOMPADDING', (0, -1), (-1, -1), 6),
    ]))
    return t

def _info_pair_table(pairs: list):
    """Crea tabla de pares label:valor"""
    data = []
    for label, value in pairs:
        data.append([
            Paragraph(f'<b>{label}</b>', ParagraphStyle('l', fontSize=9, fontName='Helvetica-Bold', textColor=SANDOVAL_GRAY)),
            Paragraph(str(value or '-'), ParagraphStyle('v', fontSize=9, fontName='Helvetica', textColor=SANDOVAL_DARK)),
        ])
    
    t = Table(data, colWidths=[35*mm, 50*mm])
    t.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('LINEBELOW', (0, 0), (-1, -1), 0.5, colors.HexColor('#eeeeee')),
    ]))
    return t


def generate_orden_ingreso(order: dict, client: dict, vehicle: dict, filepath: str):
    """
    Genera PDF de Orden de Ingreso (para el cliente al recepcionar vehículo)
    """
    styles = _get_styles()
    doc = SimpleDocTemplate(
        filepath, pagesize=A4,
        leftMargin=15*mm, rightMargin=15*mm,
        topMargin=15*mm, bottomMargin=20*mm
    )
    
    elements = []
    date_str = order.get('fecha', datetime.now().strftime('%Y-%m-%d %H:%M'))
    
    # Header
    elements.append(_header_table('ORDEN DE INGRESO', order.get('consecutivo', ''), date_str))
    elements.append(Spacer(1, 6*mm))
    
    # Estado
    estado = order.get('estado', 'RECEPCIÓN')
    elements.append(Paragraph(f'Estado: <b>{estado}</b>', styles['SandovalBody']))
    elements.append(Spacer(1, 4*mm))
    
    # Info del cliente y vehículo lado a lado
    client_info = _info_pair_table([
        ('Cliente:', f"{client.get('nombre', '')} {client.get('apellidos', '')}"),
        ('Doc:', client.get('id', '')),
        ('Teléfono:', client.get('telefono', '')),
        ('Email:', client.get('email', '')),
    ])
    
    vehicle_info = _info_pair_table([
        ('Vehículo:', f"{vehicle.get('marca', '')} {vehicle.get('modelo', '')} {vehicle.get('año', '')}"),
        ('Placa:', vehicle.get('placa', '')),
        ('VIN:', vehicle.get('vin', '')),
        ('KM:', order.get('km', '')),
    ])
    
    main_table = Table([[client_info, vehicle_info]], colWidths=[85*mm, 85*mm])
    main_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (0, 0), 0),
        ('RIGHTPADDING', (1, 0), (1, 0), 0),
    ]))
    elements.append(main_table)
    elements.append(Spacer(1, 6*mm))
    
    # Motivo de ingreso
    elements.append(Paragraph('MOTIVO DE INGRESO', styles['SandovalSection']))
    elements.append(Paragraph(order.get('motivo', 'No especificado'), styles['SandovalBody']))
    elements.append(Spacer(1, 4*mm))
    
    # Procedimiento
    if order.get('tipo'):
        elements.append(Paragraph(f"Tipo de servicio: <b>{order.get('tipo', '')}</b>", styles['SandovalBody']))
    if order.get('tecnico'):
        elements.append(Paragraph(f"Técnico asignado: <b>{order.get('tecnico', '')}</b>", styles['SandovalBody']))
    
    elements.append(Spacer(1, 8*mm))
    
    # Términos
    elements.append(HRFlowable(width="100%", color=SANDOVAL_BORDER, thickness=0.5))
    elements.append(Spacer(1, 3*mm))
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
        elements.append(Spacer(1, 1*mm))
    
    elements.append(Spacer(1, 15*mm))
    
    # Firmas
    sig_data = [
        ['_' * 35, '', '_' * 35],
        ['Firma del Cliente', '', 'Firma del Taller'],
    ]
    sig_table = Table(sig_data, colWidths=[70*mm, 30*mm, 70*mm])
    sig_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('TEXTCOLOR', (0, 0), (-1, -1), SANDOVAL_GRAY),
    ]))
    elements.append(sig_table)
    
    # Footer
    elements.append(Spacer(1, 10*mm))
    elements.append(Paragraph(
        'MECÁNICA Y REPUESTOS SANDOVAL EIRL - Documento generado automáticamente',
        styles['SandovalFooter']
    ))
    
    doc.build(elements)
    return filepath


def generate_cotizacion(order: dict, client: dict, vehicle: dict, items: list, filepath: str):
    """
    Genera PDF de Cotización/Presupuesto profesional
    """
    styles = _get_styles()
    doc = SimpleDocTemplate(
        filepath, pagesize=A4,
        leftMargin=15*mm, rightMargin=15*mm,
        topMargin=15*mm, bottomMargin=20*mm
    )
    
    elements = []
    date_str = datetime.now().strftime('%d/%m/%Y %H:%M')
    
    # Header
    elements.append(_header_table('COTIZACIÓN', order.get('consecutivo', ''), date_str))
    elements.append(Spacer(1, 6*mm))
    
    # Info del cliente
    elements.append(Paragraph('DATOS DEL CLIENTE', styles['SandovalSection']))
    client_info = _info_pair_table([
        ('Cliente:', f"{client.get('nombre', '')} {client.get('apellidos', '')}"),
        ('Doc:', client.get('id', '')),
        ('Teléfono:', client.get('telefono', '')),
        ('Vehículo:', f"{vehicle.get('marca', '')} {vehicle.get('modelo', '')} - {vehicle.get('placa', '')}"),
    ])
    elements.append(client_info)
    elements.append(Spacer(1, 6*mm))
    
    # Tabla de ítems
    elements.append(Paragraph('DETALLE DE SERVICIOS Y REPUESTOS', styles['SandovalSection']))
    
    # Header de tabla
    table_data = [['#', 'Descripción', 'Tipo', 'Cant.', 'P.Unit.', 'Subtotal']]
    
    subtotal = 0
    for i, item in enumerate(items, 1):
        item_total = float(item.get('total', 0))
        subtotal += item_total
        table_data.append([
            str(i),
            item.get('item', item.get('nombre', '')),
            item.get('tipo', ''),
            str(item.get('cantidad', 1)),
            f"S/ {float(item.get('valor_unitario', item.get('precio', 0))):.2f}",
            f"S/ {item_total:.2f}",
        ])
    
    igv = subtotal * 0.18
    total = subtotal + igv
    
    # Totales
    table_data.append(['', '', '', '', 'Subtotal:', f'S/ {subtotal:.2f}'])
    table_data.append(['', '', '', '', 'IGV (18%):', f'S/ {igv:.2f}'])
    table_data.append(['', '', '', '', 'TOTAL:', f'S/ {total:.2f}'])
    
    col_widths = [10*mm, 55*mm, 25*mm, 15*mm, 25*mm, 30*mm]
    t = Table(table_data, colWidths=col_widths)
    
    style_commands = [
        ('BACKGROUND', (0, 0), (-1, 0), SANDOVAL_DARK),
        ('TEXTCOLOR', (0, 0), (-1, 0), SANDOVAL_WHITE),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('FONTSIZE', (0, 1), (-1, -1), 9),
        ('ALIGN', (3, 0), (-1, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -4), 0.5, SANDOVAL_BORDER),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        # Totales
        ('FONTNAME', (4, -3), (4, -1), 'Helvetica-Bold'),
        ('FONTNAME', (5, -1), (5, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (4, -1), (5, -1), 11),
        ('TEXTCOLOR', (5, -1), (5, -1), SANDOVAL_GREEN),
        ('LINEABOVE', (4, -3), (5, -3), 1, SANDOVAL_BORDER),
    ]
    
    # Alternar colores de fila
    for i in range(1, len(table_data) - 3):
        if i % 2 == 0:
            style_commands.append(('BACKGROUND', (0, i), (-1, i), colors.HexColor('#f8f8f8')))
    
    t.setStyle(TableStyle(style_commands))
    elements.append(t)
    elements.append(Spacer(1, 6*mm))
    
    # Notas
    elements.append(Paragraph('NOTAS', styles['SandovalSection']))
    notes = [
        '• Esta cotización tiene una validez de 15 días.',
        '• Los precios incluyen mano de obra salvo indicación contraria.',
        '• Los repuestos retirados serán devueltos al cliente si lo solicita.',
        '• El plazo estimado de entrega se confirmará al aprobar el presupuesto.',
    ]
    for n in notes:
        elements.append(Paragraph(n, styles['SandovalSmall']))
    
    # Footer
    elements.append(Spacer(1, 10*mm))
    elements.append(Paragraph(
        'MECÁNICA Y REPUESTOS SANDOVAL EIRL - Cotización generada automáticamente',
        styles['SandovalFooter']
    ))
    
    doc.build(elements)
    return filepath


def generate_factura(order: dict, client: dict, items: list, filepath: str, tipo: str = 'BOLETA'):
    """
    Genera PDF de Factura/Boleta
    """
    styles = _get_styles()
    doc = SimpleDocTemplate(
        filepath, pagesize=A4,
        leftMargin=15*mm, rightMargin=15*mm,
        topMargin=15*mm, bottomMargin=20*mm
    )
    
    elements = []
    date_str = datetime.now().strftime('%d/%m/%Y %H:%M')
    
    # Header
    elements.append(_header_table(tipo, order.get('consecutivo', ''), date_str))
    elements.append(Spacer(1, 6*mm))
    
    # Datos cliente
    elements.append(Paragraph('CLIENTE', styles['SandovalSection']))
    elements.append(Paragraph(
        f"{client.get('nombre', '')} {client.get('apellidos', '')}<br/>"
        f"Doc: {client.get('id', '')}<br/>"
        f"Dirección: {client.get('direccion', '')}",
        styles['SandovalBody']
    ))
    elements.append(Spacer(1, 4*mm))
    
    # Tabla ítems
    elements.append(Paragraph('DETALLE', styles['SandovalSection']))
    table_data = [['#', 'Descripción', 'Cant.', 'P.Unit.', 'Total']]
    
    subtotal = 0
    for i, item in enumerate(items, 1):
        item_total = float(item.get('total', 0))
        subtotal += item_total
        table_data.append([
            str(i),
            item.get('item', item.get('nombre', '')),
            str(item.get('cantidad', 1)),
            f"S/ {float(item.get('valor_unitario', item.get('precio', 0))):.2f}",
            f"S/ {item_total:.2f}",
        ])
    
    igv = subtotal * 0.18
    total = subtotal + igv
    
    table_data.append(['', '', '', 'Subtotal:', f'S/ {subtotal:.2f}'])
    table_data.append(['', '', '', 'IGV (18%):', f'S/ {igv:.2f}'])
    table_data.append(['', '', '', 'TOTAL:', f'S/ {total:.2f}'])
    
    col_widths = [10*mm, 75*mm, 15*mm, 30*mm, 30*mm]
    t = Table(table_data, colWidths=col_widths)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), SANDOVAL_DARK),
        ('TEXTCOLOR', (0, 0), (-1, 0), SANDOVAL_WHITE),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('ALIGN', (2, 0), (-1, -1), 'RIGHT'),
        ('GRID', (0, 0), (-1, -4), 0.5, SANDOVAL_BORDER),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('FONTNAME', (3, -3), (3, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (3, -1), (4, -1), 11),
        ('TEXTCOLOR', (4, -1), (4, -1), SANDOVAL_GREEN),
        ('LINEABOVE', (3, -3), (4, -3), 1, SANDOVAL_BORDER),
    ]))
    elements.append(t)
    
    # Footer
    elements.append(Spacer(1, 15*mm))
    elements.append(Paragraph(
        'MECÁNICA Y REPUESTOS SANDOVAL EIRL - Documento generado automáticamente',
        styles['SandovalFooter']
    ))
    
    doc.build(elements)
    return filepath

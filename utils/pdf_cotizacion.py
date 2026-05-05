"""
SANDOVAL Dashboard - PDF de Cotizaciones
PDF profesional con logo, colores corporativos y desglose de items
"""
import os
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, Image
from reportlab.lib.enums import TA_RIGHT, TA_CENTER
from utils.models import get_db, Cotizacion, ConfigSistema

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
PDFS_DIR = os.path.join(BASE_DIR, 'pdfs')
os.makedirs(PDFS_DIR, exist_ok=True)

AZUL       = colors.HexColor('#274495')
AZUL_CLARO = colors.HexColor('#EEF2FF')
GRIS       = colors.HexColor('#6B7280')
GRIS_CLARO = colors.HexColor('#F9FAFB')
BLANCO     = colors.white


def _cfg(db, clave, default=''):
    row = db.query(ConfigSistema).filter_by(clave=clave).first()
    return row.valor if row else default


def ps(name, **kw):
    return ParagraphStyle(name, **{'fontName': 'Helvetica', **kw})


def generar_pdf_cotizacion(cotizacion_id):
    # Hardening: aceptar solo int o string numérico (evita bug histórico OS-codigo)
    try:
        cotizacion_id = int(cotizacion_id)
    except (TypeError, ValueError):
        import logging as _lg
        _lg.getLogger(__name__).warning('generar_pdf_cotizacion ID inválido: %r — esperaba int', cotizacion_id)
        return None
    db = get_db()
    try:
        cot = db.query(Cotizacion).filter_by(id=cotizacion_id).first()
        if not cot:
            return None

        emp_nombre = _cfg(db, 'empresa_nombre', 'MECANICA Y REPUESTOS SANDOVAL EIRL')
        emp_ruc    = _cfg(db, 'empresa_ruc', '20608755111')
        emp_dir    = _cfg(db, 'empresa_direccion', 'Piura, Peru')
        emp_tel    = _cfg(db, 'empresa_telefono', '+51 999 999 999')
        emp_email  = _cfg(db, 'empresa_email', 'contacto@sandoval.com')
        igv_pct    = float(_cfg(db, 'igv_porcentaje', '18'))

        fname    = f'COT_{cot.numero.replace("-","_")}_{datetime.now().strftime("%Y%m%d%H%M%S")}.pdf'
        filepath = os.path.join(PDFS_DIR, fname)

        doc = SimpleDocTemplate(
            filepath, pagesize=A4,
            rightMargin=1.5*cm, leftMargin=1.5*cm,
            topMargin=1.5*cm, bottomMargin=1.5*cm
        )
        story = []

        # Logo
        logo_img = ''
        for lp in [
            os.path.join(BASE_DIR, 'logo_sandoval.jpg'),
            os.path.join(BASE_DIR, 'assets', 'logo_sandoval.jpg')
        ]:
            if os.path.exists(lp):
                try:
                    logo_img = Image(lp, width=3.2*cm, height=3.2*cm)
                    logo_img.hAlign = 'CENTER'
                    break
                except Exception:
                    pass

        fecha_str = cot.fecha_creacion.strftime('%d/%m/%Y') if cot.fecha_creacion else '-'

        emp_html = (
            f'<font color="#274495" size="13"><b>{emp_nombre}</b></font><br/>'
            f'<font color="#6B7280" size="8">RUC: {emp_ruc}</font><br/>'
            f'<font color="#6B7280" size="8">{emp_dir}</font><br/>'
            f'<font color="#6B7280" size="8">Tel: {emp_tel}</font><br/>'
            f'<font color="#6B7280" size="8">{emp_email}</font>'
        )
        cot_html = (
            f'<font color="#274495" size="16"><b>COTIZACION</b></font><br/><br/>'
            f'<font color="#111827" size="11"><b>{cot.numero}</b></font><br/>'
            f'<font color="#6B7280" size="8">Fecha: {fecha_str}</font><br/>'
            f'<font color="#6B7280" size="8">Estado: {cot.estado}</font>'
        )

        hdr = Table(
            [[logo_img or '', Paragraph(emp_html, ps('emp', leading=14)),
              Paragraph(cot_html, ps('cot', leading=14, alignment=TA_RIGHT))]],
            colWidths=[3.8*cm, 9*cm, 5.7*cm]
        )
        hdr.setStyle(TableStyle([
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('BACKGROUND', (0,0), (-1,-1), AZUL_CLARO),
            ('LEFTPADDING', (0,0), (-1,-1), 12),
            ('RIGHTPADDING', (0,0), (-1,-1), 12),
            ('TOPPADDING', (0,0), (-1,-1), 12),
            ('BOTTOMPADDING', (0,0), (-1,-1), 12),
        ]))
        story += [hdr, Spacer(1, 0.5*cm)]

        # Cliente
        cli_html = (
            f'<b><font color="#274495">CLIENTE</font></b><br/>'
            f'<font size="11"><b>{cot.nombre_cliente}</b></font>'
        )
        if cot.cliente_id:
            cli_html += f'<br/><font color="#6B7280" size="8">ID: {cot.cliente_id}</font>'

        cli_tbl = Table([[
            Paragraph(cli_html, ps('cli', fontSize=9, leading=14)),
            Paragraph(
                f'<b><font color="#274495">EMITIDO POR</font></b><br/>'
                f'{cot.creado_por or "Administrador"}<br/>'
                f'<font color="#6B7280" size="8">Valido por 30 dias</font>',
                ps('emi', fontSize=9, leading=14, alignment=TA_RIGHT)
            )
        ]], colWidths=[9.5*cm, 9*cm])
        cli_tbl.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), GRIS_CLARO),
            ('LEFTPADDING', (0,0), (-1,-1), 12),
            ('RIGHTPADDING', (0,0), (-1,-1), 12),
            ('TOPPADDING', (0,0), (-1,-1), 10),
            ('BOTTOMPADDING', (0,0), (-1,-1), 10),
            ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor('#E5E7EB')),
        ]))
        story += [cli_tbl, Spacer(1, 0.4*cm)]

        # Nota
        if cot.nota:
            story.append(Paragraph(
                f'<i><font color="#6B7280" size="8">Nota: {cot.nota}</font></i>',
                ps('nota', fontSize=8, leading=12,
                   backColor=colors.HexColor('#FFFBEB'),
                   leftPadding=8, rightPadding=8,
                   borderColor=colors.HexColor('#FCD34D'),
                   borderWidth=0.5, borderPadding=6)
            ))
            story.append(Spacer(1, 0.4*cm))

        # Tabla items
        ch  = ps('ch',  fontSize=8, textColor=BLANCO, alignment=TA_CENTER, fontName='Helvetica-Bold')
        cc  = ps('cc',  fontSize=9, leading=12)
        cr  = ps('cr',  fontSize=9, leading=12, alignment=TA_RIGHT)
        ccc = ps('ccc', fontSize=9, leading=12, alignment=TA_CENTER)

        rows = [[Paragraph(h, ch) for h in ['TIPO', 'DESCRIPCION', 'CANT.', 'P. UNIT.', 'SUBTOTAL']]]
        for it in (cot.items or []):
            lbl = 'Repuesto' if it.tipo == 'repuesto' else 'Mano de obra'
            rows.append([
                Paragraph(lbl, cc),
                Paragraph(it.descripcion or '-', cc),
                Paragraph(str(it.cantidad), ccc),
                Paragraph(f'S/ {it.precio_unitario:.2f}', cr),
                Paragraph(f'S/ {it.subtotal:.2f}', cr),
            ])

        itbl = Table(rows, colWidths=[3*cm, 8*cm, 1.8*cm, 2.8*cm, 2.9*cm])
        itbl.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), AZUL),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [BLANCO, GRIS_CLARO]),
            ('GRID', (0,0), (-1,-1), 0.3, colors.HexColor('#E5E7EB')),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('LEFTPADDING', (0,0), (-1,-1), 8),
            ('RIGHTPADDING', (0,0), (-1,-1), 8),
            ('TOPPADDING', (0,0), (-1,-1), 8),
            ('BOTTOMPADDING', (0,0), (-1,-1), 8),
        ]))
        story += [itbl, Spacer(1, 0.4*cm)]

        # Totales
        subtotal  = cot.total / (1 + igv_pct / 100)
        igv_monto = cot.total - subtotal

        tot_tbl = Table([
            ['', '', Paragraph('Subtotal (sin IGV):', ps('tl', fontSize=9, textColor=GRIS, alignment=TA_RIGHT)),
             Paragraph(f'S/ {subtotal:.2f}', ps('tv', fontSize=9, alignment=TA_RIGHT))],
            ['', '', Paragraph(f'IGV ({igv_pct:.0f}%):', ps('tl2', fontSize=9, textColor=GRIS, alignment=TA_RIGHT)),
             Paragraph(f'S/ {igv_monto:.2f}', ps('tv2', fontSize=9, alignment=TA_RIGHT))],
            ['', '', Paragraph('TOTAL FINAL:', ps('tf', fontSize=12, textColor=AZUL, fontName='Helvetica-Bold', alignment=TA_RIGHT)),
             Paragraph(f'S/ {cot.total:.2f}', ps('tfv', fontSize=12, textColor=AZUL, fontName='Helvetica-Bold', alignment=TA_RIGHT))],
        ], colWidths=[5*cm, 5.5*cm, 5*cm, 3*cm])
        tot_tbl.setStyle(TableStyle([
            ('BACKGROUND', (2,2), (-1,2), AZUL_CLARO),
            ('BOX', (2,2), (-1,2), 1, AZUL),
            ('TOPPADDING', (0,0), (-1,-1), 6),
            ('BOTTOMPADDING', (0,0), (-1,-1), 6),
            ('RIGHTPADDING', (0,0), (-1,-1), 8),
        ]))
        story += [tot_tbl, Spacer(1, 0.7*cm)]

        # Pie
        story.append(HRFlowable(width='100%', thickness=0.5, color=colors.HexColor('#E5E7EB')))
        story.append(Spacer(1, 0.3*cm))
        story.append(Paragraph(
            'Esta cotizacion tiene validez de 30 dias desde su emision.<br/>'
            'Los repuestos NO se descuentan del inventario hasta la aprobacion de la orden.<br/>'
            'Para aceptar, comuniquese al telefono indicado.',
            ps('legal', fontSize=7, textColor=GRIS, leading=11)
        ))
        story.append(Spacer(1, 0.4*cm))

        # ── FIRMA + SELLO DEL TITULAR ─────────────────────────
        try:
            from utils.pdf_generator import _firma_block
            for f in _firma_block(taller_id=int(getattr(o, 'taller_id', 1) or 1)):
                story.append(f)
            story.append(Spacer(1, 0.3*cm))
        except Exception:
            pass

        footer = Table([[Paragraph(
            f'<font color="#274495"><b>{emp_nombre}</b></font> · RUC {emp_ruc} · {emp_tel}',
            ps('ft', fontSize=7, textColor=GRIS, alignment=TA_CENTER)
        )]], colWidths=[18.5*cm])
        footer.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), AZUL_CLARO),
            ('TOPPADDING', (0,0), (-1,-1), 8),
            ('BOTTOMPADDING', (0,0), (-1,-1), 8),
        ]))
        story.append(footer)

        doc.build(story)
        return filepath

    except Exception as e:
        import traceback
        print(f'[PDF COT ERROR] {e}')
        traceback.print_exc()
        return None
    finally:
        db.close()

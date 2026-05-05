"""
utils/pdf_libros.py — PDF y TXT PLE-SUNAT para Libros Contables
================================================================
Usa reportlab para PDF e ISO-8859-1 para TXT PLE.
"""
from __future__ import annotations

import io
from datetime import date, datetime
from decimal import Decimal
from typing import Any

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fmt_date(d) -> str:
    """Fecha a DD/MM/YYYY (formato PLE-SUNAT)."""
    if d is None:
        return ""
    if isinstance(d, str):
        try:
            d = datetime.strptime(d[:10], "%Y-%m-%d").date()
        except Exception:
            return str(d)[:10]
    try:
        return d.strftime("%d/%m/%Y")
    except Exception:
        return str(d)


def _fmt_num(v, decimals: int = 2) -> str:
    """Número a string con decimals fijos."""
    try:
        return f"{float(v):.{decimals}f}"
    except Exception:
        return "0.00"


def _get_db_data(tipo: str, taller_id: int, **kwargs) -> dict:
    """
    Obtiene datos via httpx interno al endpoint JSON ya implementado.
    Usa SQLAlchemy directamente para evitar dependencia circular.
    """
    from sqlalchemy import text
    from utils.models import get_db

    db = get_db()
    try:
        db.execute(text("SET app.taller_id = :t"), {"t": taller_id})

        periodo = kwargs.get("periodo")
        desde   = kwargs.get("desde")
        hasta   = kwargs.get("hasta")
        cuenta  = kwargs.get("cuenta")
        fecha   = kwargs.get("fecha")

        if tipo == "diario":
            today = date.today()
            d = desde or today.replace(day=1).isoformat()
            h = hasta or today.isoformat()
            rows = db.execute(text("""
                SELECT a.id, a.numero, a.fecha, a.glosa,
                       SUM(l.debe), SUM(l.haber)
                FROM   asientos_contables a
                JOIN   asiento_lineas l ON l.asiento_id = a.id
                WHERE  a.taller_id=:t AND a.fecha BETWEEN :d AND :h
                GROUP BY a.id, a.numero, a.fecha, a.glosa
                ORDER BY a.fecha, a.numero
            """), {"t": taller_id, "d": d, "h": h}).fetchall()
            return {
                "titulo": "LIBRO DIARIO",
                "cabeceras": ["Fecha", "Numero", "Glosa", "Debe", "Haber"],
                "filas": [
                    [_fmt_date(r[2]), r[1], r[3][:60], _fmt_num(r[4]), _fmt_num(r[5])]
                    for r in rows
                ],
                "totales": [
                    "", "", "TOTAL",
                    _fmt_num(sum(float(r[4] or 0) for r in rows)),
                    _fmt_num(sum(float(r[5] or 0) for r in rows)),
                ],
            }

        elif tipo == "mayor":
            today = date.today()
            d = desde or today.replace(day=1).isoformat()
            h = hasta or today.isoformat()
            cta = cuenta or "101"
            rows = db.execute(text("""
                SELECT a.fecha, a.numero, a.glosa, l.debe, l.haber
                FROM   asiento_lineas l
                JOIN   asientos_contables a ON a.id = l.asiento_id
                WHERE  l.taller_id=:t AND l.cuenta_codigo=:cta
                  AND  a.fecha BETWEEN :d AND :h AND a.estado='ACTIVO'
                ORDER BY a.fecha, a.numero
            """), {"t": taller_id, "cta": cta, "d": d, "h": h}).fetchall()
            saldo = 0.0
            filas = []
            for r in rows:
                debe  = float(r[3] or 0)
                haber = float(r[4] or 0)
                saldo += debe - haber
                filas.append([_fmt_date(r[0]), r[1], r[2][:60], _fmt_num(debe), _fmt_num(haber), _fmt_num(saldo)])
            return {
                "titulo": f"LIBRO MAYOR — Cuenta {cta}",
                "cabeceras": ["Fecha", "Numero", "Glosa", "Debe", "Haber", "Saldo"],
                "filas": filas,
                "totales": ["", "", "TOTAL",
                    _fmt_num(sum(float(r[3] or 0) for r in rows)),
                    _fmt_num(sum(float(r[4] or 0) for r in rows)),
                    _fmt_num(saldo)],
            }

        elif tipo == "ventas":
            if not periodo:
                raise ValueError("periodo requerido para ventas")
            from utils.pdf_libros import _periodo_range_local
            d, h = _periodo_range_local(periodo)
            rows = db.execute(text("""
                SELECT numero, CAST(fecha AS date), cliente_nombre,
                       COALESCE(subtotal,0), COALESCE(igv,0), COALESCE(total,0)
                FROM   notas_venta
                WHERE  taller_id=:t AND CAST(fecha AS date) BETWEEN :d AND :h
                  AND  estado != 'ANULADA'
                ORDER BY fecha
            """), {"t": taller_id, "d": d, "h": h}).fetchall()
            filas = []
            for r in rows:
                sub = float(r[3] or 0)
                igv = round(sub * 0.18, 2)
                tot = round(sub + igv, 2)
                filas.append([_fmt_date(r[1]), r[0], r[2][:40], _fmt_num(sub), _fmt_num(igv), _fmt_num(tot)])
            return {
                "titulo": f"REGISTRO DE VENTAS — {periodo}",
                "cabeceras": ["Fecha", "Comprobante", "Cliente", "Base Imp.", "IGV 18%", "Total"],
                "filas": filas,
                "totales": ["", "", "TOTAL",
                    _fmt_num(sum(float(r[3] or 0) for r in rows)),
                    _fmt_num(sum(round(float(r[3] or 0)*0.18,2) for r in rows)),
                    _fmt_num(sum(float(r[5] or 0) for r in rows))],
            }

        elif tipo == "compras":
            if not periodo:
                raise ValueError("periodo requerido para compras")
            from utils.pdf_libros import _periodo_range_local
            d, h = _periodo_range_local(periodo)
            # 2026-05-04 B2 fix: facturas.fecha es TEXT (DD/MM/YYYY o YYYY-MM-DD).
            # CAST(... AS date) fallaba en formato peruano. Usar parse_fecha_text().
            rows = db.execute(text("""
                SELECT numero_factura, parse_fecha_text(fecha), proveedor,
                       COALESCE(subtotal,0), COALESCE(igv,0), COALESCE(total,0)
                FROM   facturas
                WHERE  taller_id=:t AND parse_fecha_text(fecha) BETWEEN :d AND :h
                  AND  estado NOT IN ('ANULADA')
                ORDER BY parse_fecha_text(fecha), id
            """), {"t": taller_id, "d": d, "h": h}).fetchall()
            filas = []
            for r in rows:
                sub = float(r[3] or 0)
                igv = round(sub * 0.18, 2)
                tot = round(sub + igv, 2)
                filas.append([_fmt_date(r[1]), r[0] or "", r[2][:40], _fmt_num(sub), _fmt_num(igv), _fmt_num(tot)])
            return {
                "titulo": f"REGISTRO DE COMPRAS — {periodo}",
                "cabeceras": ["Fecha", "N° Factura", "Proveedor", "Base Imp.", "IGV 18%", "Total"],
                "filas": filas,
                "totales": ["", "", "TOTAL",
                    _fmt_num(sum(float(r[3] or 0) for r in rows)),
                    _fmt_num(sum(round(float(r[3] or 0)*0.18,2) for r in rows)),
                    _fmt_num(sum(float(r[5] or 0) for r in rows))],
            }

        else:
            return {"titulo": tipo.upper(), "cabeceras": [], "filas": [], "totales": []}
    finally:
        db.close()


def _periodo_range_local(periodo: str):
    """Replica local de _periodo_range para evitar importar del router."""
    from datetime import timedelta
    year, month = int(periodo[:4]), int(periodo[4:])
    desde = date(year, month, 1)
    if month == 12:
        hasta = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        hasta = date(year, month + 1, 1) - timedelta(days=1)
    return desde, hasta


# ---------------------------------------------------------------------------
# Generador PDF con reportlab
# ---------------------------------------------------------------------------

def generar_pdf_libro(
    tipo: str,
    taller_id: int,
    periodo: str = None,
    desde: str = None,
    hasta: str = None,
    cuenta: str = None,
    fecha: str = None,
) -> bytes:
    """
    Genera PDF imprimible para el libro solicitado.
    Retorna bytes del PDF.
    """
    try:
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib import colors
        from reportlab.lib.units import cm
        from reportlab.platypus import (
            SimpleDocTemplate, Table, TableStyle,
            Paragraph, Spacer, HRFlowable,
        )
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.enums import TA_CENTER, TA_RIGHT
    except ImportError:
        raise RuntimeError("reportlab no está instalado. Ejecutar: pip install reportlab")

    data = _get_db_data(
        tipo, taller_id,
        periodo=periodo, desde=desde, hasta=hasta,
        cuenta=cuenta, fecha=fecha,
    )

    buf = io.BytesIO()
    page_size = landscape(A4) if len(data.get("cabeceras", [])) > 5 else A4
    doc = SimpleDocTemplate(
        buf, pagesize=page_size,
        leftMargin=1.5*cm, rightMargin=1.5*cm,
        topMargin=2*cm, bottomMargin=2*cm,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "Title", parent=styles["Heading1"],
        fontSize=14, alignment=TA_CENTER, spaceAfter=6,
    )
    sub_style = ParagraphStyle(
        "Sub", parent=styles["Normal"],
        fontSize=9, alignment=TA_CENTER, spaceAfter=12,
    )

    elems = []
    elems.append(Paragraph("MECÁNICA Y REPUESTOS SANDOVAL E.I.R.L.", title_style))
    elems.append(Paragraph(data.get("titulo", tipo.upper()), title_style))
    periodo_str = periodo or f"{desde or ''} al {hasta or ''}"
    elems.append(Paragraph(f"Período: {periodo_str}", sub_style))
    elems.append(Spacer(1, 0.3*cm))

    cabeceras = data.get("cabeceras", [])
    filas     = data.get("filas", [])
    totales   = data.get("totales", [])

    if cabeceras:
        table_data = [cabeceras] + filas
        if totales:
            table_data.append(totales)

        num_cols = len(cabeceras)
        col_width = (page_size[0] - 3*cm) / num_cols
        col_widths = [col_width] * num_cols

        tbl = Table(table_data, colWidths=col_widths, repeatRows=1)
        style = TableStyle([
            ("BACKGROUND",  (0, 0), (-1, 0),     colors.HexColor("#1565C0")),
            ("TEXTCOLOR",   (0, 0), (-1, 0),     colors.white),
            ("FONTNAME",    (0, 0), (-1, 0),     "Helvetica-Bold"),
            ("FONTSIZE",    (0, 0), (-1, 0),     8),
            ("FONTSIZE",    (0, 1), (-1, -1),    7),
            ("ALIGN",       (-2, 0), (-1, -1),   "RIGHT"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#EEF2F7")]),
            ("GRID",        (0, 0), (-1, -1),    0.3, colors.grey),
            ("TOPPADDING",  (0, 0), (-1, -1),    3),
            ("BOTTOMPADDING", (0, 0), (-1, -1),  3),
        ])
        if totales:
            last = len(table_data) - 1
            style.add("BACKGROUND", (0, last), (-1, last), colors.HexColor("#E3F2FD"))
            style.add("FONTNAME",   (0, last), (-1, last), "Helvetica-Bold")
        tbl.setStyle(style)
        elems.append(tbl)
    else:
        elems.append(Paragraph("Sin datos para el período seleccionado.", styles["Normal"]))

    elems.append(Spacer(1, 0.5*cm))
    elems.append(HRFlowable(width="100%", thickness=0.5, color=colors.grey))
    elems.append(Paragraph(
        f"Generado: {datetime.now().strftime('%d/%m/%Y %H:%M')} — Sistema SANDOVAL PRO",
        ParagraphStyle("Footer", parent=styles["Normal"], fontSize=7, alignment=TA_CENTER),
    ))

    doc.build(elems)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Generador PLE (TXT pipe-separated, ISO-8859-1)
# ---------------------------------------------------------------------------

def generar_ple(
    tipo: str,
    taller_id: int,
    periodo: str,
    cuenta: str = None,
) -> bytes:
    """
    Genera archivo TXT en formato PLE-SUNAT.
    Encoding: ISO-8859-1. Separador: pipe |. Fecha: DD/MM/YYYY.
    Retorna bytes.
    """
    from sqlalchemy import text
    from utils.models import get_db

    db = get_db()
    try:
        db.execute(text("SET app.taller_id = :t"), {"t": taller_id})
        lines = []

        if tipo == "ventas":
            from utils.pdf_libros import _periodo_range_local
            d, h = _periodo_range_local(periodo)
            # Formato: 14.1 Registro de Ventas e Ingresos
            # Periodo|CUO|CUO_Correlativo|Fecha_Emision|Tipo_CP|Serie|Numero|
            # Tipo_Doc_Identidad|Numero_RUC|Base_Imponible|IGV|Total|...
            rows = db.execute(text("""
                SELECT numero, CAST(fecha AS date), cliente_nombre,
                       COALESCE(subtotal,0), COALESCE(igv,0), COALESCE(total,0),
                       estado
                FROM   notas_venta
                WHERE  taller_id=:t AND CAST(fecha AS date) BETWEEN :d AND :h
                  AND  estado != 'ANULADA'
                ORDER BY fecha, id
            """), {"t": taller_id, "d": d, "h": h}).fetchall()

            periodo_ple = f"{periodo[:4]}{periodo[4:6]}00"
            for idx, r in enumerate(rows, 1):
                sub = float(r[3] or 0)
                igv = round(sub * 0.18, 2)
                tot = round(sub + igv, 2)
                estado_ple = "1" if r[6] not in ("ANULADA",) else "2"
                line = "|".join([
                    periodo_ple,
                    f"M{idx:05d}",           # CUO
                    f"M{idx:05d}",           # Correlativo
                    _fmt_date(r[1]),          # Fecha emisión
                    "",                       # Fecha vcto (blanco)
                    "03",                     # Tipo CP: boleta
                    "B001",                   # Serie
                    str(r[0] or "").replace("NV-",""),  # Número
                    "6",                      # Tipo doc: RUC
                    "",                       # RUC cliente (no disponible)
                    str(r[2] or "")[:40],     # Nombre cliente
                    _fmt_num(sub),
                    "0.00",                   # Base no gravada
                    "0.00",                   # Base exonerada
                    _fmt_num(igv),
                    "0.00",                   # ISC
                    "0.00",                   # ICBPER
                    "0.00",                   # Otros tributos
                    _fmt_num(tot),
                    "PEN",
                    "1.000",                  # TC
                    "",                       # Fecha ref doc
                    "",                       # Tipo ref doc
                    "",                       # Serie ref doc
                    "",                       # Nro ref doc
                    estado_ple,
                    "",                       # Campo libre
                ])
                lines.append(line)

        elif tipo == "compras":
            from utils.pdf_libros import _periodo_range_local
            d, h = _periodo_range_local(periodo)
            # Formato simplificado: 8.1 Registro de Compras
            # 2026-05-04 B2 fix: parse_fecha_text() para soportar facturas en DD/MM/YYYY
            rows = db.execute(text("""
                SELECT numero_factura, parse_fecha_text(fecha), proveedor,
                       ruc_proveedor,
                       COALESCE(subtotal,0), COALESCE(igv,0), COALESCE(total,0),
                       estado
                FROM   facturas
                WHERE  taller_id=:t AND parse_fecha_text(fecha) BETWEEN :d AND :h
                  AND  estado NOT IN ('ANULADA')
                ORDER BY parse_fecha_text(fecha), id
            """), {"t": taller_id, "d": d, "h": h}).fetchall()

            periodo_ple = f"{periodo[:4]}{periodo[4:6]}00"
            for idx, r in enumerate(rows, 1):
                sub = float(r[4] or 0)
                igv = round(sub * 0.18, 2)
                tot = round(sub + igv, 2)
                line = "|".join([
                    periodo_ple,
                    f"C{idx:05d}",
                    _fmt_date(r[1]),
                    "",                       # Fecha vcto
                    "01",                     # Tipo CP: factura
                    "",                       # Serie
                    str(r[0] or ""),          # Número
                    "6",                      # Tipo doc proveedor: RUC
                    str(r[3] or ""),          # RUC proveedor
                    str(r[2] or "")[:40],     # Nombre proveedor
                    _fmt_num(sub),
                    "0.00",                   # Base no gravada
                    "0.00",                   # Base exonerada
                    _fmt_num(igv),
                    "0.00",                   # ISC
                    "0.00",                   # ICBPER
                    "0.00",                   # Otros tributos
                    _fmt_num(tot),
                    "PEN",
                    "1.000",
                    "",                       # Tipo doc ref
                    "",                       # Serie ref
                    "",                       # Nro ref
                    "1",                      # Estado
                    "",
                ])
                lines.append(line)

        elif tipo == "diario":
            from datetime import timedelta
            from utils.pdf_libros import _periodo_range_local
            d, h = _periodo_range_local(periodo)
            rows = db.execute(text("""
                SELECT a.numero, a.fecha, a.glosa,
                       l.cuenta_codigo, l.cuenta_nombre,
                       l.debe, l.haber
                FROM   asiento_lineas l
                JOIN   asientos_contables a ON a.id = l.asiento_id
                WHERE  l.taller_id=:t AND a.fecha BETWEEN :d AND :h
                  AND  a.estado='ACTIVO'
                ORDER BY a.fecha, a.numero, l.orden
            """), {"t": taller_id, "d": d, "h": h}).fetchall()

            periodo_ple = f"{periodo[:4]}{periodo[4:6]}00"
            for idx, r in enumerate(rows, 1):
                line = "|".join([
                    periodo_ple,
                    str(r[0]),               # CUO
                    _fmt_date(r[1]),          # Fecha
                    str(r[3]),               # Cuenta
                    str(r[4] or "")[:60],    # Nombre cuenta
                    str(r[2] or "")[:60],    # Glosa
                    _fmt_num(r[5]),           # Debe
                    _fmt_num(r[6]),           # Haber
                    "1",                     # Estado
                    "",
                ])
                lines.append(line)

        else:
            lines = [f"# PLE {tipo} — {periodo}"]

        content = "\r\n".join(lines)
        if lines:
            content += "\r\n"
        return content.encode("iso-8859-1", errors="replace")
    finally:
        db.close()

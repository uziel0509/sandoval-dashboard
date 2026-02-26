"""
SANDOVAL Dashboard — Página Pública de Reporte de Entrega
Acceso: /reporte/{token}
Sin login requerido. Se envía el link al cliente vía WhatsApp.
"""

import json, os
from datetime import datetime
from nicegui import ui
from utils.models import get_db, Orden, Cliente, Vehiculo


def reporte_entrega_page(token: str):
    """
    Página pública completa del reporte de entrega al cliente.
    Muestra: diagnóstico + repuestos + reparación + evidencias fotográficas.
    Logo Sandoval como marca de agua de fondo.
    """
    db = get_db()
    try:
        order = db.query(Orden).filter_by(report_token=token).first()
        if not order:
            _not_found()
            return

        client  = db.query(Cliente).filter_by(id=order.cliente_id).first()  if order.cliente_id   else None
        vehicle = db.query(Vehiculo).filter_by(placa=order.vehiculo_placa).first() if order.vehiculo_placa else None

        raw = order.checklist_reparacion
        if isinstance(raw, str):
            try: data = json.loads(raw)
            except: data = {}
        elif isinstance(raw, dict):
            data = dict(raw)
        else:
            data = {}
    finally:
        db.close()

    client_name   = f"{client.nombre} {client.apellidos or ''}".strip() if client else '—'
    client_phone  = client.telefono if client else '—'
    vehicle_info  = f"{vehicle.marca} {vehicle.modelo} {vehicle.año}" if vehicle else '—'
    vehicle_placa = vehicle.placa if vehicle else '—'
    vehicle_vin   = getattr(vehicle, 'vin', '—') or '—' if vehicle else '—'
    technician    = order.tecnico or '—'
    fecha_str     = order.fecha[:10] if order.fecha else '—'
    motivo        = order.motivo or '—'
    diagnostico   = order.diagnostico or '—'

    # Datos estructurados
    items_cotizacion = order.items_cotizacion or []
    if isinstance(items_cotizacion, str):
        try: items_cotizacion = json.loads(items_cotizacion)
        except: items_cotizacion = []

    repair_logs = data.get('repair_logs', [])
    ev_cats     = data.get('evidence_cats', {})
    qc_data     = data.get('quality_control', {})

    # Total de repuestos
    total_rep = sum(float(i.get('total', 0)) for i in items_cotizacion)

    # Logo URL (servido como asset estático)
    logo_url = '/assets/logo_sandoval.jpg'

    ui.add_head_html(f'''
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Reporte de Servicio — {order.consecutivo}</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
    <style>
      *, *::before, *::after {{ box-sizing: border-box; margin:0; padding:0; }}
      body {{
        font-family: 'Inter', sans-serif;
        background: #f4f6f9;
        color: #1e293b;
        min-height: 100vh;
      }}

      /* ── MARCA DE AGUA ── */
      body::before {{
        content: '';
        position: fixed;
        top: 50%; left: 50%;
        transform: translate(-50%, -50%);
        width: 520px; height: 520px;
        background: url('{logo_url}') center/contain no-repeat;
        opacity: 0.045;
        pointer-events: none;
        z-index: 0;
      }}

      .page-wrap {{
        position: relative; z-index: 1;
        max-width: 860px; margin: 0 auto; padding: 32px 20px 60px;
      }}

      /* ── CABECERA ── */
      .rpt-header {{
        background: white; border-radius: 18px; padding: 28px 32px;
        margin-bottom: 24px; display: flex; align-items: center; gap: 24px;
        box-shadow: 0 2px 12px rgba(0,0,0,.07);
      }}
      .rpt-logo {{
        width: 80px; height: 80px; object-fit: contain; flex-shrink: 0;
      }}
      .rpt-title-block {{ flex: 1; }}
      .rpt-company {{
        font-size: 20px; font-weight: 800; color: #1e5c3a;
        letter-spacing: .02em;
      }}
      .rpt-subtitle {{
        font-size: 12px; color: #64748b; margin-top: 2px;
      }}
      .rpt-badge {{
        background: linear-gradient(135deg,#1d4ed8,#3b82f6);
        color: white; border-radius: 12px; padding: 8px 20px;
        text-align: center; font-weight: 700; font-size: 12px; flex-shrink: 0;
        box-shadow: 0 4px 14px rgba(59,130,246,.35);
      }}
      .rpt-badge small {{
        display: block; font-size: 9px; font-weight: 400; opacity: .85;
      }}

      /* ── GRID INFO ── */
      .info-grid {{
        display: grid; grid-template-columns: 1fr 1fr; gap: 16px;
        margin-bottom: 24px;
      }}
      @media (max-width:600px) {{ .info-grid {{ grid-template-columns: 1fr; }} }}

      .info-card {{
        background: white; border-radius: 14px; padding: 20px;
        box-shadow: 0 1px 6px rgba(0,0,0,.06); border: 1px solid #e8edf2;
      }}
      .info-card-title {{
        font-size: 9px; font-weight: 800; color: #94a3b8;
        text-transform: uppercase; letter-spacing: .14em;
        margin-bottom: 12px; padding-bottom: 8px;
        border-bottom: 1px solid #f1f5f9;
      }}
      .info-row {{ display: flex; justify-content: space-between; padding: 5px 0; }}
      .info-lbl {{ font-size: 11px; color: #64748b; }}
      .info-val {{ font-size: 12px; font-weight: 600; color: #1e293b; text-align: right; }}

      /* ── SECCIONES ── */
      .section {{
        background: white; border-radius: 14px; padding: 24px;
        margin-bottom: 20px; box-shadow: 0 1px 6px rgba(0,0,0,.06);
        border: 1px solid #e8edf2;
      }}
      .section-hdr {{
        display: flex; align-items: center; gap: 10px;
        margin-bottom: 16px; padding-bottom: 12px;
        border-bottom: 1px solid #f1f5f9;
      }}
      .section-icon {{
        width: 34px; height: 34px; border-radius: 10px;
        display: flex; align-items: center; justify-content: center;
        font-size: 16px; flex-shrink: 0;
      }}
      .section-title {{
        font-size: 14px; font-weight: 700; color: #1e293b;
      }}
      .section-subtitle {{
        font-size: 11px; color: #64748b; margin-top: 1px;
      }}

      /* ── DIAGNÓSTICO ── */
      .diag-box {{
        background: #eff6ff; border: 1px solid #bfdbfe; border-radius: 10px;
        padding: 14px 16px; font-size: 13px; color: #1e40af; line-height: 1.7;
      }}

      /* ── TABLA REPUESTOS ── */
      .rep-table {{ width: 100%; border-collapse: collapse; margin-top: 4px; }}
      .rep-table th {{
        background: #f8fafc; font-size: 10px; font-weight: 700;
        color: #94a3b8; text-transform: uppercase; letter-spacing: .08em;
        padding: 8px 14px; text-align: left; border-bottom: 1px solid #e2e8f0;
      }}
      .rep-table td {{
        padding: 10px 14px; font-size: 12px; color: #374151;
        border-bottom: 1px solid #f1f5f9;
      }}
      .rep-table tr:last-child td {{ border-bottom: none; }}
      .rep-table .td-num {{ text-align: right; font-weight: 600; }}
      .rep-total {{
        background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 10px;
        padding: 12px 16px; margin-top: 12px; display: flex;
        justify-content: space-between; align-items: center;
      }}
      .rep-total-lbl {{ font-size: 12px; font-weight: 700; color: #166534; }}
      .rep-total-val {{ font-size: 18px; font-weight: 800; color: #166534; }}

      /* ── LOGS REPARACIÓN ── */
      .log-item {{
        background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 10px;
        padding: 14px 16px; margin-bottom: 10px;
      }}
      .log-num {{
        font-size: 10px; font-weight: 800; color: #3b82f6;
        text-transform: uppercase; letter-spacing: .08em; margin-bottom: 4px;
      }}
      .log-falla  {{ font-size: 13px; font-weight: 700; color: #1e293b; }}
      .log-solucion {{ font-size: 12px; color: #10b981; margin-top: 6px; font-weight: 500; }}
      .log-solucion::before {{ content: '↳ Solución: '; font-weight: 700; }}

      /* ── GALERÍA EVIDENCIAS ── */
      .ev-cat-title {{
        font-size: 10px; font-weight: 800; color: #64748b;
        text-transform: uppercase; letter-spacing: .1em; margin: 16px 0 10px;
      }}
      .ev-grid {{
        display: grid; grid-template-columns: repeat(auto-fill, minmax(150px,1fr));
        gap: 10px;
      }}
      .ev-img {{
        width: 100%; aspect-ratio: 4/3; object-fit: cover;
        border-radius: 10px; border: 1px solid #e2e8f0;
        box-shadow: 0 1px 4px rgba(0,0,0,.08);
      }}

      /* ── CHECKLIST QC ── */
      .qc-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }}
      @media (max-width:500px) {{ .qc-grid {{ grid-template-columns: 1fr; }} }}
      .qc-item {{
        display: flex; align-items: center; gap: 8px;
        padding: 8px 12px; border-radius: 8px; font-size: 12px; font-weight: 500;
      }}
      .qc-item.ok   {{ background: #f0fdf4; color: #166534; border: 1px solid #bbf7d0; }}
      .qc-item.obs  {{ background: #fffbeb; color: #92400e; border: 1px solid #fde68a; }}
      .qc-item.none {{ background: #f1f5f9; color: #64748b; border: 1px solid #e2e8f0; }}

      /* ── FIRMA / FOOTER ── */
      .rpt-footer {{
        background: #1e5c3a; border-radius: 14px; padding: 24px 28px;
        color: white; text-align: center; margin-top: 28px;
        box-shadow: 0 4px 16px rgba(30,92,58,.3);
      }}
      .rpt-footer-title {{ font-size: 14px; font-weight: 800; letter-spacing: .04em; }}
      .rpt-footer-sub {{ font-size: 11px; opacity: .75; margin-top: 4px; }}

      /* ── BOTÓN IMPRIMIR ── */
      .print-bar {{
        position: fixed; bottom: 24px; right: 24px; z-index: 999;
      }}
      .btn-print {{
        background: linear-gradient(135deg,#1d4ed8,#3b82f6);
        color: white; border: none; border-radius: 50px;
        padding: 14px 28px; font-size: 13px; font-weight: 700;
        cursor: pointer; box-shadow: 0 6px 20px rgba(59,130,246,.4);
        font-family: 'Inter', sans-serif; letter-spacing: .02em;
        display: flex; align-items: center; gap: 8px; transition: all .2s;
      }}
      .btn-print:hover {{ box-shadow: 0 8px 28px rgba(59,130,246,.55); transform:translateY(-2px); }}

      @media print {{
        .print-bar {{ display: none !important; }}
        body::before {{ opacity: .06 !important; }}
        body {{ background: white; }}
        .page-wrap {{ max-width: 100%; padding: 16px; }}
      }}
    </style>
    ''')

    with ui.element('div').classes('page-wrap'):

        # ── CABECERA ──────────────────────────────────────────────────
        with ui.element('div').classes('rpt-header'):
            ui.html(f'<img src="{logo_url}" class="rpt-logo" alt="Logo Sandoval">')
            with ui.element('div').classes('rpt-title-block'):
                ui.html('<div class="rpt-company">MECÁNICA Y REPUESTOS SANDOVAL</div>')
                ui.html(f'<div class="rpt-subtitle">Reporte de Servicio Completo &nbsp;·&nbsp; {fecha_str}</div>')
            with ui.element('div').classes('rpt-badge'):
                ui.html(f'{order.consecutivo}<small>REPORTE DE ENTREGA</small>')

        # ── GRID INFO ─────────────────────────────────────────────────
        with ui.element('div').classes('info-grid'):
            # Datos del cliente
            with ui.element('div').classes('info-card'):
                ui.html('<div class="info-card-title">👤 Datos del cliente</div>')
                for lbl, val in [
                    ('Nombre',  client_name),
                    ('Teléfono', client_phone),
                ]:
                    ui.html(f'''<div class="info-row">
                        <span class="info-lbl">{lbl}</span>
                        <span class="info-val">{val}</span>
                    </div>''')

            # Datos del vehículo
            with ui.element('div').classes('info-card'):
                ui.html('<div class="info-card-title">🚗 Datos del vehículo</div>')
                for lbl, val in [
                    ('Vehículo', vehicle_info),
                    ('Placa',    vehicle_placa),
                    ('VIN',      vehicle_vin),
                    ('Técnico',  technician),
                    ('Ingreso',  fecha_str),
                    ('Kilómetros', str(order.km or '—')),
                ]:
                    ui.html(f'''<div class="info-row">
                        <span class="info-lbl">{lbl}</span>
                        <span class="info-val">{val}</span>
                    </div>''')

        # ── 1. MOTIVO DE INGRESO & DIAGNÓSTICO ───────────────────────
        with ui.element('div').classes('section'):
            ui.html('''<div class="section-hdr">
                <div class="section-icon" style="background:#eff6ff;">🔍</div>
                <div>
                  <div class="section-title">Diagnóstico Técnico</div>
                  <div class="section-subtitle">Evaluación profesional del vehículo</div>
                </div>
            </div>''')
            
            # Bloque Motivo (Lo que el cliente reporta)
            ui.html(f'''
            <div style="margin-bottom:20px;">
                <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">
                    <span style="font-size:10px;font-weight:800;color:#3b82f6;text-transform:uppercase;letter-spacing:1px;">● Reporte del Cliente</span>
                </div>
                <div style="background:#f8fafc; border:1px solid #e2e8f0; border-radius:12px; padding:16px; font-size:13px; color:#475569; line-height:1.6; border-left:4px solid #3b82f6;">
                    {motivo}
                </div>
            </div>
            ''')

            # Bloque Diagnóstico (Lo que el técnico encontró)
            ui.html(f'''
            <div>
                <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">
                    <span style="font-size:10px;font-weight:800;color:#059669;text-transform:uppercase;letter-spacing:1px;">● Hallazgos del Especialista</span>
                </div>
                <div class="diag-box" style="background:#f0fdf4; border:1px solid #bbf7d0; color:#166534; border-left:4px solid #10b981; font-weight:500;">
                    {diagnostico}
                </div>
            </div>
            ''')

        # ── 2. REPUESTOS / COTIZACIÓN ─────────────────────────────────
        if items_cotizacion:
            with ui.element('div').classes('section'):
                ui.html(f'''<div class="section-hdr">
                    <div class="section-icon" style="background:#f0fdf4;">🔩</div>
                    <div>
                      <div class="section-title">Repuestos e Insumos</div>
                      <div class="section-subtitle">{len(items_cotizacion)} ítem(s) utilizados en la reparación</div>
                    </div>
                </div>''')

                rows_html = ''
                for i in items_cotizacion:
                    # El sistema usa 'nombre' o 'descripcion' según el módulo
                    desc  = i.get('nombre') or i.get('descripcion') or '—'
                    cant  = i.get('cantidad') or 1
                    pu     = float(i.get('precio_unitario') or i.get('precio', 0))
                    total = float(i.get('total') or (pu * float(cant)))
                    
                    rows_html += f'''<tr>
                      <td style="font-weight:600; color:#1e293b;">{desc}</td>
                      <td class="td-num" style="color:#64748b;">x{cant}</td>
                      <td class="td-num" style="color:#64748b;">S/ {pu:.2f}</td>
                      <td class="td-num" style="font-weight:700; color:#1e293b;">S/ {total:.2f}</td>
                    </tr>'''

                ui.html(f'''<table class="rep-table">
                  <thead><tr>
                    <th>Descripción del Ítem</th><th style="text-align:right">Cant.</th>
                    <th style="text-align:right">Unit.</th><th style="text-align:right">Total</th>
                  </tr></thead>
                  <tbody>{rows_html}</tbody>
                </table>''')

                ui.html(f'''<div class="rep-total">
                  <div style="display:flex; flex-direction:column;">
                    <span style="font-size:10px; font-weight:800; color:#166534; opacity:.7; text-transform:uppercase;">Inversión en Repuestos</span>
                    <span class="rep-total-lbl" style="font-size:14px;">TOTAL GENERAL</span>
                  </div>
                  <span class="rep-total-val">S/ {total_rep:.2f}</span>
                </div>''')

        # ── 3. REPARACIÓN (bitácora de fallas) ───────────────────────
        if repair_logs:
            with ui.element('div').classes('section'):
                ui.html(f'''<div class="section-hdr">
                    <div class="section-icon" style="background:#fff7ed;">🔧</div>
                    <div>
                      <div class="section-title">Trabajo de Reparación</div>
                      <div class="section-subtitle">{len(repair_logs)} intervención(s) registrada(s)</div>
                    </div>
                </div>''')
                for i, log in enumerate(repair_logs):
                    falla    = log.get('falla','—')
                    solucion = log.get('solucion','')
                    sol_html = f'<div class="log-solucion">{solucion}</div>' if solucion else ''
                    ui.html(f'''<div class="log-item">
                        <div class="log-num">Intervención #{i+1}</div>
                        <div class="log-falla">{falla}</div>
                        {sol_html}
                    </div>''')

        # ── 4. EVIDENCIA FOTOGRÁFICA ──────────────────────────────────
        total_fotos = sum(len(v) for v in ev_cats.values())
        if total_fotos > 0:
            with ui.element('div').classes('section'):
                ui.html(f'''<div class="section-hdr">
                    <div class="section-icon" style="background:#fdf4ff;">📷</div>
                    <div>
                      <div class="section-title">Evidencia Fotográfica</div>
                      <div class="section-subtitle">{total_fotos} foto(s) registrada(s)</div>
                    </div>
                </div>''')

                for cat_key, fotos in ev_cats.items():
                    if not fotos: continue
                    cat_label = cat_key.replace('_', ' ').title()
                    ui.html(f'<div class="ev-cat-title">{cat_label} ({len(fotos)} foto(s))</div>')
                    imgs_html = ''.join(
                        f'<img src="/evidencia/{order.consecutivo}/{cat_key}/{fn}" class="ev-img" loading="lazy" onerror="this.style.display=\'none\'">'
                        for fn in fotos
                    )
                    ui.html(f'<div class="ev-grid">{imgs_html}</div>')

        # ── 5. CONTROL DE CALIDAD ─────────────────────────────────────
        if qc_data:
            LABELS = {
                'repair_done':'Reparación completada','parts_ok':'Repuestos instalados',
                'no_leaks':'Sin fugas','fluids_level':'Niveles de fluidos',
                'engine_start':'Motor arranca','brakes_test':'Prueba de frenos',
                'bodywork_ok':'Carrocería','interior_ok':'Cabina limpia',
                'glass_ok':'Vidrios','lights_ok':'Alumbrado',
                'tires_ok':'Neumáticos','tools_removed':'Herramientas retiradas',
                'evidence_ok':'Evidencia fotográfica','order_signed':'Orden firmada',
                'warranty_given':'Garantía entregada','payment_ok':'Pago / factura',
            }
            with ui.element('div').classes('section'):
                ui.html('''<div class="section-hdr">
                    <div class="section-icon" style="background:#f0fdf4;">✅</div>
                    <div>
                      <div class="section-title">Control de Calidad — Inspección Final</div>
                      <div class="section-subtitle">Verificación antes de entrega</div>
                    </div>
                </div>''')

                items_html = ''
                for k, v in qc_data.items():
                    st   = v.get('status') if isinstance(v, dict) else None
                    note = v.get('note','') if isinstance(v, dict) else ''
                    lbl  = LABELS.get(k, k.replace('_',' ').title())
                    if st == 'ok':
                        ico, cls = '✓', 'ok'
                    elif st == 'obs':
                        ico, cls = '⚠', 'obs'
                    else:
                        ico, cls = '–', 'none'
                    note_span = f' <em style="opacity:.7">({note})</em>' if note else ''
                    items_html += f'<div class="qc-item {cls}">{ico} {lbl}{note_span}</div>'

                ui.html(f'<div class="qc-grid">{items_html}</div>')

        # ── FOOTER ────────────────────────────────────────────────────
        gen_date = datetime.now().strftime('%d/%m/%Y %H:%M')
        ui.html(f'''<div class="rpt-footer">
            <div class="rpt-footer-title">MECÁNICA Y REPUESTOS SANDOVAL EIRL</div>
            <div class="rpt-footer-sub">Piura, Perú &nbsp;|&nbsp; Reporte generado el {gen_date}</div>
            <div class="rpt-footer-sub" style="margin-top:8px;opacity:.5;">
                Este documento es válido como comprobante del servicio prestado.
            </div>
        </div>''')

    # Botón flotante imprimir
    ui.html('''<div class="print-bar">
        <button class="btn-print" onclick="window.print()">
            🖨️ Imprimir / Guardar PDF
        </button>
    </div>''')


def _not_found():
    ui.html('''<div style="display:flex;flex-direction:column;align-items:center;
        justify-content:center;min-height:100vh;font-family:Inter,sans-serif;
        background:#f4f6f9;color:#64748b;gap:12px;">
        <div style="font-size:48px;">🔍</div>
        <div style="font-size:20px;font-weight:700;color:#1e293b;">Reporte no encontrado</div>
        <div style="font-size:13px;">El enlace puede haber expirado o es inválido.</div>
    </div>''')

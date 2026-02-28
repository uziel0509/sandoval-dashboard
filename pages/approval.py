"""
SANDOVAL Dashboard - Página de Aprobación Pública
El cliente puede ver su orden y aprobar/rechazar sin login
Acceso: /aprobacion/{token}
"""

from nicegui import ui
from utils.models import get_db, Orden, Cliente, Vehiculo, log_actividad
from datetime import datetime
import os
from utils.pdf_generator import generate_orden_ingreso


def approval_page(token: str):
    """Página pública de aprobación de orden"""

    ui.add_head_html('''
        <style>
            body {
                background: #f1f5f9;
                margin: 0; font-family: 'Inter', 'Roboto', sans-serif;
                color: #1e293b;
            }
            .aprov-card {
                background: white; border-radius: 20px;
                border: 1px solid #e2e8f0;
                box-shadow: 0 2px 12px rgba(0,0,0,.06);
                padding: 24px; margin-bottom: 16px;
                width: 100%; max-width: 680px;
            }
            .aprov-section-title {
                font-size: 11px; font-weight: 900;
                text-transform: uppercase; letter-spacing: 1.5px;
                color: #16a34a; margin-bottom: 16px;
                display: flex; align-items: center; gap: 8px;
            }
            .aprov-row {
                display: flex; align-items: flex-start; gap: 12px;
                padding: 12px; background: #f8fafc;
                border-radius: 12px; border: 1px solid #e2e8f0;
                margin-bottom: 8px;
            }
            .aprov-row-label {
                font-size: 10px; font-weight: 900; color: #94a3b8;
                text-transform: uppercase; letter-spacing: 1px;
                margin-bottom: 3px;
            }
            .aprov-row-value {
                font-size: 14px; font-weight: 600; color: #1e293b;
                line-height: 1.5;
            }
            .aprov-chk-ok  { background:#f0fdf4; border-color:#bbf7d0; }
            .aprov-chk-bad { background:#fef2f2; border-color:#fecaca; }
            .aprov-badge-ok  { background:#dcfce7; color:#15803d; font-size:9px; font-weight:900;
                               padding:3px 10px; border-radius:100px; letter-spacing:1px; white-space:nowrap; }
            .aprov-badge-bad { background:#fee2e2; color:#dc2626; font-size:9px; font-weight:900;
                               padding:3px 10px; border-radius:100px; letter-spacing:1px; white-space:nowrap; }
            .scanner-card {
                background: linear-gradient(135deg,#f0fdf4,#dcfce7);
                border: 2px solid #16a34a; border-radius: 16px; padding: 20px;
                margin-top: 16px;
            }
            .scanner-badge {
                display:inline-flex; align-items:center; gap:6px;
                background:#16a34a; color:white; font-size:10px; font-weight:900;
                letter-spacing:1.5px; text-transform:uppercase;
                padding:5px 14px; border-radius:100px; margin-bottom:12px;
            }
            .scanner-title { font-size:17px; font-weight:800; color:#14532d; margin-bottom:6px; }
            .scanner-desc  { font-size:12px; color:#166534; line-height:1.6; margin-bottom:18px; }
            .scanner-viewer {
                background:white; border-radius:12px; overflow:hidden;
                border:1.5px solid #bbf7d0;
                box-shadow: 0 4px 24px rgba(22,163,74,.15);
                margin-bottom: 14px;
            }
            .scanner-viewer-bar {
                background:#14532d; color:white; padding:10px 16px;
                font-size:11px; font-weight:700; letter-spacing:.5px;
                display:flex; align-items:center; gap:8px;
            }
            .scanner-btn-open {
                flex:1; display:flex; align-items:center; justify-content:center;
                gap:8px; background:#f0fdf4; color:#14532d;
                text-decoration:none; font-weight:800; font-size:13px;
                padding:12px 20px; border-radius:12px; border:2px solid #16a34a;
                transition: all .18s;
            }
            .scanner-btn-dl {
                flex:1; display:flex; align-items:center; justify-content:center;
                gap:8px; background:#16a34a; color:white;
                text-decoration:none; font-weight:800; font-size:13px;
                padding:12px 20px; border-radius:12px;
                box-shadow:0 4px 14px rgba(22,163,74,.4);
                transition: all .18s;
            }
            .foto-thumb {
                width:120px; height:120px; border-radius:12px;
                overflow:hidden; border:2px solid #e2e8f0;
                background:#f1f5f9; flex-shrink:0;
                position:relative; cursor:pointer;
            }
            .foto-thumb img { width:100%; height:100%; object-fit:cover; display:block; }
            .foto-thumb:hover .foto-overlay { opacity:1; }
            .foto-overlay {
                position:absolute; inset:0; background:rgba(0,0,0,.3);
                display:flex; align-items:center; justify-content:center;
                opacity:0; transition:.2s; color:white; font-size:22px;
            }
            .video-card {
                background:#0f172a; border-radius:14px; overflow:hidden;
                border:1.5px solid #3b82f6; margin-bottom:12px;
                box-shadow:0 4px 20px rgba(59,130,246,.2);
            }
            .video-bar {
                padding:10px 14px; display:flex; align-items:center; gap:8px;
            }
            .item-row {
                display:flex; justify-content:space-between; align-items:center;
                padding:12px 0; border-bottom:1px solid #f1f5f9;
            }
            .item-name  { font-size:14px; font-weight:700; color:#1e293b; }
            .item-sub   { font-size:11px; color:#94a3b8; margin-top:2px; }
            .item-price { font-size:14px; font-weight:800; color:#1e293b; margin-left:16px; white-space:nowrap; }
            .decision-card {
                background:white; border:2px solid #86efac;
                border-radius:20px; padding:28px; margin-bottom:24px;
                box-shadow: 0 4px 24px rgba(22,163,74,.12);
                width:100%; max-width:680px;
            }
        </style>
    ''')

    db = get_db()
    try:
        order = db.query(Orden).filter_by(approval_token=token).first()

        if not order:
            _render_error('Enlace inválido', 'Este enlace de aprobación no es válido o ha expirado.')
            return

        client  = db.query(Cliente).filter_by(id=order.cliente_id).first()
        vehicle = db.query(Vehiculo).filter_by(placa=order.vehiculo_placa).first()

        if order.approval_status in ('aprobado', 'rechazado'):
            _render_already_responded(order, client, vehicle)
            return

        _render_approval(order, client, vehicle, token)
    finally:
        db.close()


def _render_error(title, message):
    with ui.column().classes('w-full min-h-screen items-center justify-center p-4'):
        with ui.card().classes('w-full max-w-md bg-white border border-red-200 p-8 text-center shadow-lg'):
            ui.icon('error', size='64px').classes('text-red-500')
            ui.label(title).classes('text-2xl font-bold text-gray-800 mt-4')
            ui.label(message).classes('text-gray-600 mt-2')


def _render_already_responded(order, client, vehicle):
    color = 'green' if order.approval_status == 'aprobado' else 'red'
    icon  = 'check_circle' if order.approval_status == 'aprobado' else 'cancel'
    is_budget = len(order.items_cotizacion or []) > 0

    if order.approval_status == 'aprobado':
        status_text = 'SU PRESUPUESTO FUE APROBADO' if is_budget else 'SU ORDEN FUE APROBADA'
    else:
        status_text = 'PRESUPUESTO RECHAZADO' if is_budget else 'ORDEN RECHAZADA'

    with ui.column().classes('w-full min-h-screen items-center justify-center p-4 bg-gray-50'):
        with ui.card().classes(f'w-full max-w-lg bg-white border-t-8 border-{color}-500 p-8 text-center shadow-xl'):
            ui.icon(icon, size='80px').classes(f'text-{color}-500 mb-4')
            ui.label(status_text).classes(f'text-3xl font-bold text-{color}-700 mb-2')
            ui.separator().classes('my-4')
            ui.label(f'Orden N° {order.consecutivo}').classes('text-xl text-gray-800 font-bold')
            ui.label(f'Confirmado el: {order.approval_date}').classes('text-gray-500 text-sm')
            ui.label('Gracias por su respuesta.').classes('text-gray-600 mt-6 text-lg')

            if order.approval_status == 'aprobado':
                lbl = 'Su presupuesto ha sido formalizado y se procederá con el servicio.' if is_budget \
                      else 'Se ha generado su reporte de ingreso con las evidencias fotográficas.'
                ui.label(lbl).classes('text-gray-500 text-sm mt-2 mb-6')

                def download_pdf():
                    from utils import pdf_generator as pg
                    try:
                        o_dict = {c.name: getattr(order, c.name) for c in order.__table__.columns}
                        c_dict = {c.name: getattr(client, c.name) for c in client.__table__.columns} if client else {}
                        v_dict = {c.name: getattr(vehicle, c.name) for c in vehicle.__table__.columns} if vehicle else {}
                        o_dict['fotos_evidencia'] = order.fotos_evidencia
                        os.makedirs('pdfs', exist_ok=True)
                        ts = datetime.now().strftime('%H%M%S')
                        if is_budget:
                            filename = f"pdfs/Cotizacion_{order.consecutivo.replace('#','')}_{ts}.pdf"
                            pg.generate_pdf(o_dict, c_dict, v_dict, 'cotizacion', filename)
                        else:
                            filename = f"pdfs/Ingreso_{order.consecutivo.replace('#','')}_{ts}.pdf"
                            pg.generate_pdf(o_dict, c_dict, v_dict, 'ingreso', filename)
                        ui.download(filename)
                        ui.notify('Generando descarga...', type='positive')
                    except Exception as e:
                        ui.notify(f'Error al generar PDF: {e}', type='negative')

                btn_label = 'Descargar Cotización (PDF)' if is_budget else 'Descargar Reporte de Ingreso (PDF)'
                ui.button(btn_label, icon='picture_as_pdf', on_click=download_pdf).props(
                    'unelevated color=green-7 text-color=white size=lg').classes('w-full font-bold shadow-lg')

                import json
                chk = order.checklist_reparacion
                if isinstance(chk, str):
                    try: chk = json.loads(chk)
                    except: chk = {}
                sc_path = (chk or {}).get('diagnostic_details', {}).get('scanner_path')
                if sc_path:
                    ui.button('Descargar Reporte de Escáner', icon='file_download',
                              on_click=lambda: ui.download(sc_path)
                              ).props('outline color=blue size=md').classes('w-full mt-4 font-bold')


# ─────────────────────────────────────────────────────────────────────────────
# RENDER PRINCIPAL DE APROBACIÓN
# ─────────────────────────────────────────────────────────────────────────────
def _render_approval(order, client, vehicle, token):
    _VID = {'.mp4', '.mov', '.avi', '.webm', '.mkv', '.m4v', '.3gp', '.ogg'}
    def _is_vid(p): return os.path.splitext((p or '').lower())[1] in _VID

    import json
    chk = order.checklist_reparacion
    if isinstance(chk, str):
        try:    chk = json.loads(chk)
        except: chk = {}
    diag   = (chk or {}).get('diagnostic_details', {})
    qcheck = (chk or {}).get('quick_check', {})
    items  = order.items_cotizacion or []
    sc_path = (diag or {}).get('scanner_path', '')   # escáner PDF path

    with ui.column().classes('w-full min-h-screen items-center py-8 px-3 bg-slate-100'):

        # ══════════════════ 1. HEADER ══════════════════
        ui.html(f"""
        <div class="aprov-card" style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px;">
            <div style="display:flex;align-items:center;gap:12px;">
                <div style="width:48px;height:48px;background:#f0fdf4;border-radius:12px;
                            display:flex;align-items:center;justify-content:center;font-size:24px;">🔧</div>
                <div>
                    <div style="font-size:22px;font-weight:900;color:#1e293b;line-height:1.1;">SANDOVAL</div>
                    <div style="font-size:11px;color:#64748b;font-weight:500;">Mecánica y Repuestos — Reporte Digital de Servicio</div>
                </div>
            </div>
            <div style="text-align:right;">
                <div style="font-size:16px;font-weight:800;color:#1e293b;">Orden {order.consecutivo}</div>
                <div style="font-size:11px;color:#94a3b8;font-family:monospace;">Estado: {order.estado}</div>
            </div>
        </div>
        """)

        # ══════════════════ 2. VEHÍCULO ══════════════════
        if vehicle:
            marca   = vehicle.marca or '—'
            modelo  = vehicle.modelo or '—'
            anio    = str(vehicle.año or '—')
            placa   = vehicle.placa or '—'
            color_v = vehicle.color or '—'
            km_str  = f'{order.km} km' if order.km else '—'
            tec     = order.tecnico or '—'
            ui.html(f"""
            <div class="aprov-card">
                <div class="aprov-section-title">🚗 Información del Vehículo</div>
                <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:10px;">
                    {_ifield('Marca',    marca)}
                    {_ifield('Modelo',   modelo)}
                    {_ifield('Año',      anio)}
                    {_ifield('Placa',    placa)}
                    {_ifield('Color',    color_v)}
                    {_ifield('Técnico',  tec)}
                </div>
                {f'<div style="margin-top:10px;padding:8px 12px;background:#f0fdf4;border-radius:8px;font-size:12px;color:#166534;font-weight:700;">Kilometraje al ingreso: {km_str}</div>' if order.km else ''}
            </div>
            """)

        # ══════════════════ 3. DIAGNÓSTICO TÉCNICO ══════════════════
        with ui.element('div').classes('aprov-card'):
            ui.html('<div class="aprov-section-title">🔬 Diagnóstico Técnico</div>')

            if diag:
                # Sistemas
                systems = diag.get('system', [])
                if isinstance(systems, str): systems = [systems]
                if systems:
                    tags_html = ''.join(
                        f'<span style="background:#f0fdf4;color:#166534;font-size:10px;font-weight:800;'
                        f'padding:4px 12px;border-radius:100px;border:1px solid #bbf7d0;'
                        f'text-transform:uppercase;">{s}</span>'
                        for s in systems
                    )
                    ui.html(f'<div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:14px;">'
                            f'<span style="font-size:10px;font-weight:900;color:#94a3b8;text-transform:uppercase;">Sistemas:</span>'
                            f'{tags_html}</div>')

                def _drow(icon_name, label, value):
                    if not value: return
                    with ui.row().classes('w-full items-start gap-3 p-3 rounded-xl mb-2').style(
                            'background:#f8fafc;border:1px solid #e2e8f0;'):
                        ui.icon(icon_name, size='18px').classes('text-lime-600 mt-1 flex-shrink-0')
                        with ui.column().classes('gap-0 flex-1'):
                            ui.label(label).classes('text-[10px] font-black text-gray-400 uppercase tracking-widest mb-1')
                            ui.label(value).classes('text-sm text-gray-800 leading-relaxed font-semibold')

                _drow('biotech',             'Pruebas Realizadas',           diag.get('tests'))
                _drow('manage_search',        'Códigos de Falla Detectados',   diag.get('codes'))
                _drow('psychology',           'Análisis Técnico / Hallazgo',   diag.get('analysis'))
                _drow('check_circle_outline', 'Solución Recomendada',          diag.get('solution'))

            elif order.diagnostico:
                ui.html(f"""
                <div style="background:#f8fafc;border:1.5px solid #e2e8f0;border-radius:12px;padding:16px;">
                    <div style="font-size:10px;font-weight:900;color:#94a3b8;
                                text-transform:uppercase;letter-spacing:1.5px;margin-bottom:10px;">
                        Descripción del Diagnóstico
                    </div>
                    <div style="font-size:14px;color:#1e293b;line-height:1.7;
                                white-space:pre-wrap;font-weight:500;">{order.diagnostico}</div>
                </div>
                """)
            else:
                ui.html("""
                <div style="text-align:center;padding:28px;color:#94a3b8;">
                    <div style="font-size:36px;margin-bottom:8px;">🔬</div>
                    <div style="font-size:13px;font-weight:600;">El diagnóstico técnico está en proceso.</div>
                </div>
                """)

            # ── ESCÁNER — siempre visible si existe ─────────────────────
            if sc_path:
                ui.separator().classes('mt-5 mb-4')
                ui.html(f"""
                <div class="scanner-card">
                    <div class="scanner-badge">🔬 Diagnóstico Digital Certificado</div>
                    <div style="font-size:11px;color:#166534;font-weight:600;margin-bottom:14px;">
                        Escáner electrónico OBD ejecutado en su vehículo
                    </div>
                    <div class="scanner-title">📊 Reporte Completo de Escáner Vehicular</div>
                    <div class="scanner-desc">
                        Su vehículo fue analizado con herramienta de diagnóstico electrónico
                        profesional OBD/OBD2. El reporte incluye todos los códigos de falla
                        activos, parámetros de sensores y el estado de los sistemas electrónicos.
                    </div>

                    <!-- Visor PDF embebido -->
                    <div class="scanner-viewer">
                        <div class="scanner-viewer-bar">
                            <span>📄</span>
                            <span>REPORTE DE ESCÁNER — Vista Completa (desplázate para leer)</span>
                        </div>
                        <iframe src="/{sc_path}"
                            style="width:100%;height:540px;border:none;display:block;background:#f9f9f9;"
                            title="Reporte de Escáner Vehicular">
                            <div style="padding:32px;text-align:center;color:#6b7280;">
                                <div style="font-size:40px;margin-bottom:12px;">📄</div>
                                <div>Tu navegador no puede mostrar el PDF aquí.<br>
                                     Usa los botones de abajo para verlo.</div>
                            </div>
                        </iframe>
                    </div>

                    <!-- Botones -->
                    <div style="display:flex;gap:12px;flex-wrap:wrap;">
                        <a href="/{sc_path}" target="_blank" class="scanner-btn-open">
                            🔍 Ver en pantalla completa
                        </a>
                        <a href="/{sc_path}" download class="scanner-btn-dl">
                            ⬇️ Descargar PDF
                        </a>
                    </div>
                </div>
                """)

        # ══════════════════ 4. INSPECCIÓN DE SEGURIDAD ══════════════════
        if qcheck:
            with ui.element('div').classes('aprov-card'):
                ui.html('<div class="aprov-section-title">✅ Inspección de Seguridad y Estado</div>')
                for chk_item, data in qcheck.items():
                    status = data.get('status') if isinstance(data, dict) else data
                    note   = (data.get('note', '') if isinstance(data, dict) else '') or ''
                    is_ok  = status == 'OK'
                    cls_c  = 'aprov-chk-ok' if is_ok else 'aprov-chk-bad'
                    badge  = 'aprov-badge-ok' if is_ok else 'aprov-badge-bad'
                    lbl_b  = 'CONFORME' if is_ok else 'REVISAR'
                    icon_c = '✅' if is_ok else '⚠️'
                    note_html = f'<span style="font-size:11px;color:#dc2626;font-style:italic;flex:1;"> — {note}</span>' if note else ''
                    ui.html(f"""
                    <div class="aprov-row {cls_c}" style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px;margin-bottom:6px;">
                        <div style="display:flex;align-items:center;gap:10px;flex:1;">
                            <span style="font-size:16px;">{icon_c}</span>
                            <span style="font-size:13px;font-weight:700;color:#1e293b;">{chk_item}</span>
                            {note_html}
                        </div>
                        <span class="{badge}">{lbl_b}</span>
                    </div>
                    """)

        # ══════════════════ 5. EVIDENCIA — FOTOS Y VIDEOS ══════════════════
        medios = [p for p in (order.fotos_evidencia or []) if isinstance(p, str)]
        if medios:
            fotos_ev  = [p for p in medios if not _is_vid(p)]
            videos_ev = [p for p in medios if _is_vid(p)]

            with ui.element('div').classes('aprov-card'):
                total_ev = len(medios)
                ui.html(f'<div class="aprov-section-title">📷 Evidencia Adjunta &nbsp;'
                        f'<span style="background:#f1f5f9;color:#64748b;font-size:10px;font-weight:700;'
                        f'padding:2px 10px;border-radius:100px;">{total_ev} archivo{"s" if total_ev!=1 else ""}</span></div>')

                if fotos_ev:
                    ui.html(f'<div style="font-size:11px;font-weight:700;color:#64748b;margin-bottom:10px;">'
                            f'Fotografías ({len(fotos_ev)})</div>')
                    with ui.row().classes('gap-3 flex-wrap mb-4'):
                        for path in fotos_ev:
                            ui.html(f"""
                            <a href="{path}" target="_blank" class="foto-thumb">
                                <img src="{path}" alt="Evidencia" onerror="this.style.display='none'"/>
                                <div class="foto-overlay">🔍</div>
                            </a>
                            """)

                if videos_ev:
                    if fotos_ev:
                        ui.separator().classes('my-4')
                    ui.html(f'<div style="font-size:11px;font-weight:700;color:#3b82f6;margin-bottom:10px;">'
                            f'📹 Videos del técnico ({len(videos_ev)})</div>')
                    for path in videos_ev:
                        fname = path.split('/')[-1]
                        ui.html(f"""
                        <div class="video-card">
                            <video src="{path}" controls preload="metadata" playsinline
                                style="width:100%;max-height:400px;display:block;">
                                Tu navegador no soporta reproducción de video.
                                <a href="{path}" target="_blank">Descargar video</a>
                            </video>
                            <div class="video-bar">
                                <span style="font-size:18px;">🎥</span>
                                <div style="flex:1;">
                                    <div style="font-size:12px;color:white;font-weight:700;">Video diagnóstico del técnico</div>
                                    <div style="font-size:10px;color:#64748b;font-family:monospace;">{fname}</div>
                                </div>
                                <a href="{path}" target="_blank"
                                   style="color:#60a5fa;font-size:12px;font-weight:700;text-decoration:none;white-space:nowrap;">
                                    Abrir →
                                </a>
                            </div>
                        </div>
                        """)

        # ══════════════════ 6. COTIZACIÓN ══════════════════
        if items:
            with ui.element('div').classes('aprov-card'):
                ui.html('<div class="aprov-section-title">🔩 Cotización de Repuestos y Servicios</div>')

                subtotal = 0.0
                rows_html = ''
                for it in items:
                    it_total  = float(it.get('total', 0))
                    subtotal += it_total
                    nombre   = it.get('nombre', it.get('item', 'Ítem'))
                    cant     = it.get('cantidad', 1)
                    pu       = float(it.get('precio_unitario', 0))
                    cat      = it.get('categoria', 'Repuesto')
                    rows_html += f"""
                    <div class="item-row">
                        <div>
                            <div class="item-name">{nombre}</div>
                            <div class="item-sub">Cant: {cant} × S/ {pu:.2f} &nbsp;|&nbsp; {cat}</div>
                        </div>
                        <div class="item-price">S/ {it_total:.2f}</div>
                    </div>
                    """
                base_igv = subtotal / 1.18
                igv_inc  = subtotal - base_igv
                ui.html(f"""
                <div>{rows_html}</div>
                <div style="margin-top:16px;border-top:2px solid #f1f5f9;padding-top:14px;text-align:right;">
                    <div style="font-size:12px;color:#94a3b8;margin-bottom:6px;">
                        Base imponible (inc. IGV): S/ {base_igv:,.2f}
                        &nbsp;|&nbsp;
                        IGV 18% (incluido): S/ {igv_inc:,.2f}
                    </div>
                    <div style="font-size:30px;font-weight:900;color:#16a34a;letter-spacing:-.5px;">
                        TOTAL &nbsp; S/ {subtotal:,.2f}
                    </div>
                    <div style="font-size:10px;color:#94a3b8;margin-top:2px;">
                        Todos los precios incluyen IGV 18%
                    </div>
                </div>
                """)
        else:
            ui.html("""
            <div class="aprov-card" style="background:#fffbeb;border-color:#fde68a;">
                <div style="display:flex;align-items:center;gap:12px;">
                    <span style="font-size:24px;">ℹ️</span>
                    <div>
                        <div style="font-size:13px;font-weight:800;color:#92400e;">Cotización en preparación</div>
                        <div style="font-size:12px;color:#a16207;margin-top:2px;">
                            El taller está preparando la cotización de repuestos y servicios.
                            Se le enviará un nuevo enlace para su aprobación cuando esté lista.
                        </div>
                    </div>
                </div>
            </div>
            """)

        # ══════════════════ 7. MENSAJE PROFESIONAL (ADELANTO) ══════════════════
        ui.html("""
        <div style="background: #eff6ff; border: 1px solid #bfdbfe; border-radius: 16px; padding: 20px; margin-bottom: 24px;">
            <div style="display: flex; gap: 12px; align-items: flex-start;">
                <div style="font-size: 20px;">ℹ️</div>
                <div style="flex: 1;">
                    <div style="font-size: 11px; font-weight: 900; color: #1e40af; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 4px;">Política de Inicio de Servicios</div>
                    <div style="font-size: 13px; color: #1e3a8a; line-height: 1.5; font-weight: 500;">
                        Estimado cliente, una vez autorizada la reparación, le solicitamos ponerse en contacto con nuestra administración para gestionar el adelanto correspondiente. Esto nos permite el aseguramiento inmediato de los repuestos y el cumplimiento de los tiempos de entrega pactados.
                    </div>
                </div>
            </div>
        </div>
        """)

        # ══════════════════ 8. DECISIÓN ══════════════════
        with ui.element('div').classes('decision-card'):
            ui.html(f"""
            <div style="font-size:11px;font-weight:900;color:#16a34a;text-transform:uppercase;
                        letter-spacing:1.5px;margin-bottom:10px;">📋 Su Decisión</div>
            <div style="font-size:17px;font-weight:800;color:#1e293b;margin-bottom:6px;">
                {'¿Aprueba el diagnóstico y la cotización de repuestos?' if items
                 else '¿Aprueba el diagnóstico inicial de su vehículo?'}
            </div>
            <div style="font-size:12px;color:#64748b;line-height:1.5;margin-bottom:20px;">
                Al <strong>APROBAR</strong>, el taller procederá inmediatamente con los trabajos autorizados.<br>
                Al <strong>RECHAZAR</strong>, el taller se contactará con usted para coordinar.
            </div>
            """)

            comentario_inp = ui.textarea(
                'Comentario u observación (opcional)',
                placeholder='Ej: Estoy de acuerdo con el diagnóstico y los precios, pueden proceder...'
            ).props('outlined dense rows=3 bg-color=white').classes('w-full mb-5')

            with ui.row().classes('w-full justify-center gap-4 flex-wrap'):
                def _rechazar():
                    _process_response(token, 'rechazado', comentario_inp.value)
                def _aprobar():
                    _process_response(token, 'aprobado', comentario_inp.value)

                ui.button('✗  RECHAZAR', on_click=_rechazar).classes(
                    'text-base font-bold px-10 py-3'
                ).props('outline color=red-7 size=lg')

                ui.button('✓  APROBAR Y AUTORIZAR', on_click=_aprobar).classes(
                    'text-base font-bold px-10 py-3'
                ).props('unelevated color=lime-8 text-color=black size=lg')

        # Footer
        ui.html("""
        <div style="text-align:center;padding:16px;color:#94a3b8;font-size:11px;">
            MECÁNICA Y REPUESTOS SANDOVAL EIRL &nbsp;—&nbsp; Documento de aprobación digital confidencial<br>
            <span style="font-size:10px;opacity:.7;">Este enlace es de uso exclusivo del cliente destinatario. No compartir.</span>
        </div>
        """)


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────
def _ifield(label, value):
    """HTML para un campo info (para usar en ui.html)"""
    return (f'<div style="background:#f8fafc;border-radius:10px;padding:10px 12px;border:1px solid #e2e8f0;">'
            f'<div style="font-size:9px;font-weight:900;color:#94a3b8;text-transform:uppercase;'
            f'letter-spacing:1px;margin-bottom:3px;">{label}</div>'
            f'<div style="font-size:13px;font-weight:700;color:#1e293b;">{value}</div>'
            f'</div>')


def _info_field(label, value):
    with ui.column().classes('gap-0'):
        ui.label(label).classes('text-xs text-gray-500 uppercase font-bold')
        ui.label(str(value)).classes('text-gray-800 font-medium')


def confirm_dialog(title, msg, token, new_status):
    with ui.dialog() as dialog, ui.card().classes('bg-white border border-gray-200 p-6 w-96 text-center shadow-xl'):
        ui.label(title).classes('text-xl font-bold text-gray-800 mb-2')
        ui.label(msg).classes('text-gray-600 mb-6')

        with ui.row().classes('w-full justify-center gap-4'):
            ui.button('Cancelar', on_click=dialog.close).props('flat color=grey-8')

            def confirm():
                db = get_db()
                try:
                    o = db.query(Orden).filter_by(approval_token=token).first()
                    if o:
                        o.approval_status = new_status
                        o.approval_date = datetime.now().strftime('%Y-%m-%d %H:%M')

                        if new_status == 'aprobado':
                            if o.estado == 'RECEPCIÓN':
                                o.estado = 'DIAGNÓSTICO'
                            else:
                                o.estado = 'REPARACIÓN'
                        elif new_status == 'rechazado':
                            if o.estado != 'RECEPCIÓN':
                                o.estado = 'DIAGNÓSTICO'

                        if new_status == 'aprobado' and o.items_cotizacion:
                            try:
                                from utils import pdf_generator as pg
                                from utils.models import Cliente, Vehiculo
                                c_row = db.query(Cliente).filter_by(id=o.cliente_id).first()
                                v_row = db.query(Vehiculo).filter_by(placa=o.vehiculo_placa).first()
                                o_dict = {c.name: getattr(o, c.name) for c in o.__table__.columns}
                                c_dict = {c.name: getattr(c_row, c.name) for c in c_row.__table__.columns} if c_row else {}
                                v_dict = {c.name: getattr(v_row, c.name) for c in v_row.__table__.columns} if v_row else {}
                                o_dict['fotos_evidencia'] = o.fotos_evidencia
                                os.makedirs('pdfs', exist_ok=True)
                                ts = datetime.now().strftime('%Y%m%d_%H%M%S')
                                safe_cons = o.consecutivo.replace('#', '').replace('/', '-')
                                pdf_path = f"pdfs/Aprobado_{safe_cons}_{ts}.pdf"
                                pg.generate_pdf(o_dict, c_dict, v_dict, 'cotizacion', pdf_path)
                                o.pdf_cotizacion = pdf_path
                            except Exception as pdf_err:
                                print(f"[PDF] Error al generar PDF de aprobación: {pdf_err}")

                        log_actividad(f'Orden {o.consecutivo} {new_status} por cliente', 'ordenes')

                        hist = list(o.historial or [])
                        hist.append({
                            'fecha':   datetime.now().strftime('%Y-%m-%d %H:%M'),
                            'accion':  f'Cliente {new_status.upper()} presupuesto',
                            'usuario': 'Cliente Web'
                        })
                        o.historial = hist

                        db.commit()
                        ui.notify('Respuesta registrada correctamente', type='positive')
                        dialog.close()
                        ui.run_javascript('location.reload()')
                finally:
                    db.close()

            color = 'green' if new_status == 'aprobado' else 'red'
            ui.button('CONFIRMAR', on_click=confirm).props(f'unelevated color={color}-7')

    dialog.open()


def _process_response(token: str, status: str, comentario: str = ''):
    confirm_dialog(
        'Aprobar Orden' if status == 'aprobado' else 'Rechazar Orden',
        '¿Está seguro de su respuesta?' if status == 'rechazado' else '¿Confirma la aprobación?',
        token, status
    )

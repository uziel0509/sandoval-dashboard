"""
SANDOVAL Dashboard - Página de Aprobación Pública
El cliente puede ver su orden y aprobar/rechazar sin login
Acceso: /aprobacion/{token}
"""

from nicegui import ui
from utils.models import get_db, Orden, Cliente, Vehiculo, log_actividad
from datetime import datetime
import os
from utils.pdf_generator import generate_pdf


def approval_page(token: str):
    """Página pública de aprobación de orden"""

    ui.add_head_html('''
        <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;800;900&display=swap" rel="stylesheet">
        <link href="https://fonts.googleapis.com/icon?family=Material+Icons+Round" rel="stylesheet">
        <style>
            :root {
                --primary: #274495;
                --emerald: #10b981;
                --slate: #1e293b;
                --bg: #f8fafc;
            }
            body {
                background: var(--bg);
                margin: 0; font-family: 'Outfit', sans-serif;
                color: var(--slate);
                -webkit-font-smoothing: antialiased;
            }
            .main-container {
                max-width: 800px;
                margin: 0 auto;
                padding: 24px 16px 120px 16px;
                width: 100%;
            }
            .premium-header {
                text-align: center;
                margin-bottom: 40px;
                padding: 32px 0;
            }
            .aprov-card {
                background: rgba(255, 255, 255, 0.95);
                border-radius: 28px;
                border: 1px solid rgba(226, 232, 240, 0.8);
                box-shadow: 0 10px 40px -10px rgba(0,0,0,0.05);
                padding: 32px;
                margin-bottom: 24px;
                backdrop-filter: blur(10px);
                position: relative;
                overflow: hidden;
            }
            .aprov-section-title {
                font-size: 10px; font-weight: 900;
                text-transform: uppercase; letter-spacing: 2px;
                color: var(--primary); margin-bottom: 24px;
                display: flex; align-items: center; gap: 10px;
                opacity: 0.8;
            }
            .technical-box {
                background: linear-gradient(135deg, #f8fafc 0%, #eff6ff 100%);
                border-left: 5px solid var(--primary);
                border-radius: 12px;
                padding: 24px;
                margin-top: 10px;
                font-weight: 600;
                color: #334155;
                line-height: 1.6;
            }
            .scanner-card {
                background: linear-gradient(135deg, #ecfdf5, #d1fae5);
                border: 1px solid #10b981; border-radius: 24px; padding: 28px;
                margin-top: 24px; box-shadow: 0 15px 40px -10px rgba(16, 185, 129, 0.2);
            }
            .scanner-badge {
                display:inline-flex; align-items:center; gap:6px;
                background: var(--emerald); color:white; font-size:9px; font-weight:900;
                letter-spacing:1.5px; text-transform:uppercase;
                padding:6px 16px; border-radius:100px; margin-bottom:16px;
            }
            .scanner-viewer {
                background:white; border-radius:20px; overflow:hidden;
                border:1px solid #bbf7d0; box-shadow: 0 12px 40px rgba(0,0,0,0.08);
                margin: 24px 0;
            }
            .foto-thumb {
                width: 160px; height: 160px; border-radius:20px;
                overflow:hidden; border:3px solid white;
                box-shadow: 0 8px 20px rgba(0,0,0,0.1);
                position:relative; transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            }
            .foto-thumb:hover { transform: scale(1.05) translateY(-5px); z-index:10; }
            .video-card {
                background: #0f172a; border-radius: 24px; overflow: hidden;
                box-shadow: 0 20px 50px -10px rgba(0,0,0,0.4); margin-bottom: 24px;
                border: 1px solid rgba(255,255,255,0.1);
            }
            .item-table { width: 100%; border-collapse: separate; border-spacing: 0 10px; }
            .item-row-tr { background: #f8fafc; border-radius: 14px; transition: all 0.2s; }
            .item-row-tr:hover { background: #f1f5f9; transform: translateX(5px); }
            .item-row-td { padding: 18px; border: none; }
            .item-row-td:first-child { border-radius: 14px 0 0 14px; }
            .item-row-td:last-child { border-radius: 0 14px 14px 0; }
            .total-card {
                background: linear-gradient(135deg, #274495 0%, #1e3a8a 100%);
                color: white; padding: 40px; border-radius: 32px;
                text-align: right; box-shadow: 0 25px 60px -15px rgba(39, 68, 149, 0.4);
                margin-top: 32px;
            }
            .decision-card {
                background: white; border: 2px solid var(--emerald);
                border-radius: 32px; padding: 48px; margin-bottom: 48px;
                box-shadow: 0 25px 80px -20px rgba(16, 185, 129, 0.25);
            }
            .support-float {
                position: fixed; bottom: 32px; right: 32px; z-index: 2000;
                background: #25d366; color: white; padding: 18px 32px;
                border-radius: 100px; font-weight: 900; font-size: 14px;
                display: flex; align-items: center; gap: 12px;
                box-shadow: 0 15px 40px rgba(37, 211, 102, 0.4);
                text-decoration: none; transition: all 0.3s;
                letter-spacing: 1px;
            }
            .support-float:hover { transform: translateY(-8px); box-shadow: 0 20px 50px rgba(37, 211, 102, 0.5); }
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
    with ui.column().classes('w-full min-h-screen items-center justify-center p-4 bg-slate-50'):
        with ui.card().classes('w-full max-w-md bg-white border border-red-100 p-10 text-center shadow-2xl rounded-[32px]'):
            ui.icon('error', size='72px').classes('text-red-500 mb-4')
            ui.label(title).classes('text-3xl font-black text-gray-900 mt-2')
            ui.label(message).classes('text-gray-500 mt-3 text-lg leading-relaxed')
            ui.button('VOLVER A INICIO', on_click=lambda: ui.open('/')).classes('mt-8 bg-slate-900 text-white rounded-2xl px-8 py-3 font-black')


def _render_already_responded(order, client, vehicle):
    color = 'emerald' if order.approval_status == 'aprobado' else 'red'
    icon  = 'verified' if order.approval_status == 'aprobado' else 'block'
    is_budget = len(order.items_cotizacion or []) > 0

    with ui.column().classes('w-full min-h-screen items-center justify-center p-4 bg-slate-50'):
        with ui.card().classes(f'w-full max-w-xl bg-white border-t-8 border-{color}-500 p-12 text-center shadow-2xl rounded-[40px]'):
            ui.icon(icon, size='96px').classes(f'text-{color}-500 mb-6')
            status_title = 'SERVICIO AUTORIZADO' if order.approval_status == 'aprobado' else 'RESPUESTA REGISTRADA'
            ui.label(status_title).classes(f'text-4xl font-black text-gray-900 mb-2')
            ui.label(f'Orden de Servicio N° {order.consecutivo}').classes('text-xl text-slate-400 font-bold mb-8')
            
            ui.separator().classes('mb-8')
            
            msg = 'Estamos iniciando los trabajos según lo autorizado. Le informaremos sobre el avance de su vehículo.' if order.approval_status == 'aprobado' \
                  else 'Hemos recibido su decisión. Un asesor se pondrá en contacto con usted a la brevedad posible.'
            ui.label(msg).classes('text-gray-600 text-lg leading-relaxed mb-10')

            with ui.row().classes('w-full justify-center gap-4'):
                if order.approval_status == 'aprobado' and order.pdf_cotizacion:
                    ui.button('DESCARGAR PRESUPUESTO PDF', on_click=lambda: ui.download(order.pdf_cotizacion)).classes('bg-emerald-500 text-white font-black px-8 py-4 rounded-2xl shadow-lg')
                ui.button('CONTACTAR POR WHATSAPP', on_click=lambda: ui.open('https://wa.me/51936495143')).classes('bg-slate-900 text-white font-black px-8 py-4 rounded-2xl')


def _render_approval(order, client, vehicle, token):
    """Renderiza el contenido principal de aprobación con look premium"""
    items   = order.items_cotizacion or []
    sc_path = (order.checklist_reparacion or {}).get('diagnostic_details', {}).get('scanner_path')
    
    with ui.column().classes('main-container'):
        # ══════════════════ 1. HEADER ══════════════════
        with ui.element('div').classes('premium-header'):
            ui.image('/assets/logo_sandoval.jpg').style('width:130px;margin:0 auto 24px auto;border-radius:24px;box-shadow:0 15px 40px rgba(0,0,0,0.1);display:block;')
            ui.label('CERTIFICADO TÉCNICO Y PRESUPUESTO').style('font-size:11px;font-weight:900;letter-spacing:4px;color:#274495;opacity:0.6;margin-bottom:12px;')
            ui.label(f'Orden de Servicio {order.consecutivo}').style('font-size:32px;font-weight:900;color:#1e293b;margin:0;letter-spacing:-1px;')

        # ══════════════════ 2. DATOS UNIDAD ══════════════════
        with ui.element('div').classes('aprov-card'):
            ui.html('<div class="aprov-section-title"><span class="material-icons-round" style="font-size:18px">directions_car</span> Identificación de la Unidad</div>')
            with ui.row().classes('w-full gap-8 flex-wrap'):
                with ui.column().classes('flex-1 min-w-[200px]'):
                    _ifield_premium('Placa / Matrícula', order.vehiculo_placa)
                    _ifield_premium('Marca y Modelo', f"{vehicle.marca if vehicle else '—'} {vehicle.modelo if vehicle else ''}")
                with ui.column().classes('flex-1 min-w-[200px]'):
                    _ifield_premium('Cliente / Titular', client.nombre if client else '—')
                    _ifield_premium('Kilometraje al Ingreso', f"{order.km or '—'} KM")

        # ══════════════════ 3. DIAGNÓSTICO ══════════════════
        with ui.element('div').classes('aprov-card'):
            ui.html('<div class="aprov-section-title"><span class="material-icons-round" style="font-size:18px">biotech</span> Hallazgos y Diagnóstico Técnico</div>')
            
            diag_f = (order.checklist_reparacion or {}).get('diagnosis_form', {})
            if diag_f:
                if diag_f.get('analysis'):
                    ui.html(f'<div style="font-size:9px;font-weight:900;color:#94a3b8;text-transform:uppercase;letter-spacing:1px;margin-bottom:8px;">Análisis del Especialista</div>')
                    ui.html(f'<div class="technical-box">{diag_f.get("analysis")}</div>')
                if diag_f.get('solution'):
                    ui.html(f'<div style="font-size:9px;font-weight:900;color:#10b981;text-transform:uppercase;letter-spacing:1px;margin:20px 0 8px 0;">Solución Recomendada</div>')
                    ui.html(f'<div class="technical-box" style="border-left-color:#10b981;">{diag_f.get("solution")}</div>')
            elif order.diagnostico:
                ui.html(f'<div class="technical-box">"{order.diagnostico}"</div>')
            else:
                ui.label('Análisis técnico final en proceso de consolidación...').classes('text-gray-400 italic font-medium')

            # Escáner
            if sc_path:
                ui.html(f"""
                <div class="scanner-card">
                    <div class="scanner-badge">✅ Diagnóstico por Escáner</div>
                    <div style="font-size:20px;font-weight:900;color:#064e3b;margin-bottom:8px;letter-spacing:-.5px;">Reporte Electrónico OBD-II</div>
                    <p style="font-size:14px;color:#065f46;opacity:0.8;margin-bottom:24px;line-height:1.5;">Se ejecutó una prueba de salud electrónica detectando parámetros en tiempo real de los módulos de control.</p>
                    <div class="scanner-viewer">
                        <iframe src="/{sc_path}" style="width:100%;height:500px;border:none;"></iframe>
                    </div>
                    <div style="display:flex;gap:12px;">
                        <a href="/{sc_path}" target="_blank" class="support-float" style="position:static;box-shadow:none;flex:1;justify-content:center;background:#10b981;">VER PANTALLA COMPLETA</a>
                        <a href="/{sc_path}" download class="support-float" style="position:static;box-shadow:none;flex:1;justify-content:center;background:#0f172a;">DESCARGAR PDF</a>
                    </div>
                </div>
                """)

        # ══════════════════ 4. EVIDENCIAS ══════════════════
        medios = [p for p in (order.fotos_evidencia or []) if isinstance(p, str)]
        if medios:
            with ui.element('div').classes('aprov-card'):
                ui.html('<div class="aprov-section-title"><span class="material-icons-round" style="font-size:18px">photo_library</span> Galería de Evidencias Técnicas</div>')
                with ui.row().classes('gap-5 flex-wrap justify-start'):
                    for path in medios:
                        if any(path.lower().endswith(ext) for ext in ('.mp4', '.mov', '.avi')):
                            ui.html(f'<div class="video-card w-full max-w-sm"><video src="{path}" controls class="w-full"></video></div>')
                        else:
                            ui.html(f'<a href="{path}" target="_blank" class="foto-thumb"><img src="{path}" style="width:100%;height:100%;object-fit:cover;"/></a>')

        # ══════════════════ 5. COTIZACIÓN ══════════════════
        if items:
            with ui.element('div').classes('aprov-card'):
                ui.html('<div class="aprov-section-title"><span class="material-icons-round" style="font-size:18px">receipt_long</span> Desglose del Presupuesto</div>')
                
                rows_html = ""
                total = 0
                for it in items:
                    val = float(it.get('total', 0))
                    total += val
                    rows_html += f"""
                    <tr class="item-row-tr">
                        <td class="item-row-td">
                            <div style="font-weight:900;font-size:16px;color:#1e293b;">{it.get('nombre', 'Item')}</div>
                            <div style="font-size:11px;color:#94a3b8;font-weight:700;margin-top:2px;">Cantidad: {it.get('cantidad', 1)} &nbsp;|&nbsp; CAT: {it.get('categoria', 'SERVICIO')}</div>
                        </td>
                        <td class="item-row-td" style="text-align:right;font-weight:900;color:var(--primary);font-size:18px;">S/ {val:,.2f}</td>
                    </tr>
                    """
                
                ui.html(f"""
                <table class="item-table">
                    {rows_html}
                </table>
                <div class="total-card">
                    <div style="font-size:11px;font-weight:900;text-transform:uppercase;letter-spacing:3px;opacity:0.7;margin-bottom:8px;">Importe Total Bruto Autorizado</div>
                    <div style="font-size:42px;font-weight:900;letter-spacing:-1.5px;">S/ {total:,.2f}</div>
                    <p style="font-size:11px;opacity:0.6;margin:8px 0 0 0;font-weight:600;">INCLUYE IGV 18% Y MANO DE OBRA ESPECIALIZADA</p>
                </div>
                """)

        # ══════════════════ 6. POLÍTICA ══════════════════
        ui.html("""
        <div style="background: #eff6ff; border: 1px solid #bfdbfe; border-radius: 24px; padding: 32px; margin-bottom: 40px; border-left: 8px solid #3b82f6;">
            <div style="display: flex; gap: 20px;">
                <span class="material-icons-round" style="font-size:32px;color:#2563eb;">info</span>
                <div>
                    <h4 style="margin:0;font-size:14px;font-weight:900;color:#1e40af;text-transform:uppercase;letter-spacing:1px;">Política de Gestión de Compras</h4>
                    <p style="margin:10px 0 0 0;font-size:14px;color:#1e3a8a;line-height:1.7;font-weight:500;">
                        Estimado cliente, para asegurar el stock de repuestos y honrar los tiempos de entrega pactados, se requiere la autorización digital de este presupuesto y la posterior coordinación del adelanto con nuestra administración.
                    </p>
                </div>
            </div>
        </div>
        """)

        # ══════════════════ 7. DECISIÓN ══════════════════
        with ui.element('div').classes('decision-card'):
            ui.html("""
            <div style="text-align:center;margin-bottom:32px;">
                <div style="font-size:10px;font-weight:900;color:#10b981;letter-spacing:3px;text-transform:uppercase;margin-bottom:12px;">Panel de Autorización Digital</div>
                <h2 style="font-size:26px;font-weight:900;margin:0;color:#1e293b;letter-spacing:-0.5px;">¿Autoriza el inicio del servicio?</h2>
                <p style="font-size:14px;color:#64748b;margin-top:10px;font-weight:500;">Al dar click en Aprobar, usted autoriza al taller el inicio de los trabajos especificados.</p>
            </div>
            """)
            
            note_inp = ui.textarea(placeholder='Opcional: Alguna observación o consulta para el técnico...').props('outlined autogrow bg-color=white').classes('w-full mb-8').style('border-radius:16px;')
            
            with ui.row().classes('w-full justify-center gap-6 flex-wrap'):
                ui.button('POSPONER / RECHAZAR', on_click=lambda: _process_response(token, 'rechazado', note_inp.value)).props('outline color=slate-400 size=lg').classes('px-10 py-4 rounded-2xl font-black rounded-2xl')
                ui.button('CONFIRMAR Y APROBAR', on_click=lambda: _process_response(token, 'aprobado', note_inp.value)).props('unelevated color=emerald-500 size=lg').classes('px-12 py-5 rounded-2xl font-black shadow-xl hover:scale-105 transition-all text-lg')

        # Footer
        ui.html('<div style="text-align:center;opacity:0.3;font-size:11px;font-weight:800;letter-spacing:1px;text-transform:uppercase;margin-bottom:40px;">Mecánica y Repuestos Sandoval EIRL &nbsp;|&nbsp; RUC 20601234567</div>')

    # Float Support
    ui.html('<a href="https://wa.me/51936495143" class="support-float"><span class="material-icons-round">whatsapp</span> APOYO EN LÍNEA</a>')


def _ifield_premium(label, value):
    ui.html(f"""
    <div style="margin-bottom:20px;">
        <div style="font-size:10px;font-weight:900;color:#94a3b8;text-transform:uppercase;letter-spacing:1px;margin-bottom:6px;">{label}</div>
        <div style="font-size:16px;font-weight:800;color:#1e293b;">{value or '—'}</div>
    </div>
    """)


def _process_response(token: str, status: str, comentario: str = ''):
    """Procesar aprobación/rechazo"""
    db = get_db()
    try:
        o = db.query(Orden).filter_by(approval_token=token).first()
        if not o: return

        o.approval_status = status
        o.approval_date = datetime.now().strftime('%Y-%m-%d %H:%M')
        o.comentario_cliente = comentario

        if status == 'aprobado':
            if o.estado == 'RECEPCIÓN': o.estado = 'DIAGNÓSTICO'
            else: o.estado = 'REPARACIÓN'
            
            # Generar PDF de cotización oficial
            try:
                from utils.models import Cliente, Vehiculo
                c = db.query(Cliente).filter_by(id=o.cliente_id).first()
                v = db.query(Vehiculo).filter_by(placa=o.vehiculo_placa).first()
                o_dict = {col.name: getattr(o, col.name) for col in o.__table__.columns}
                c_dict = {col.name: getattr(c, col.name) for col in c.__table__.columns} if c else {}
                v_dict = {col.name: getattr(v, col.name) for col in v.__table__.columns} if v else {}
                o_dict['fotos_evidencia'] = o.fotos_evidencia
                
                os.makedirs('pdfs', exist_ok=True)
                pdf_p = f"pdfs/Cotizacion_{o.consecutivo.replace('#','')}.pdf"
                generate_pdf(o_dict, c_dict, v_dict, 'cotizacion', pdf_p)
                o.pdf_cotizacion = pdf_p
            except Exception as e:
                print(f"Error PDF: {e}")

        log_actividad(f'Orden {o.consecutivo} {status} via web', 'ordenes')
        db.commit()
        ui.notify('Su respuesta ha sido registrada. Muchas gracias.', type='positive')
        ui.run_javascript('location.reload()')
    finally:
        db.close()

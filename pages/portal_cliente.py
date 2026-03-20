"""
SANDOVAL Dashboard - Portal del Cliente v5.0 (Premium Corporate Design)
Diseño premium con sidebar, flota completa, historial y orden activa.
"""
import json
from datetime import datetime, timedelta
from nicegui import ui
from utils.models import get_db, Cliente, Vehiculo, Orden, Cita
from utils.auth import get_current_user
import theme


# ─── CSS GLOBAL ──────────────────────────────────────────────────────────────
PORTAL_CSS = """
<style>
.portal-wrap { width:100%; background:#f0f4f8; min-height:100vh; font-family:inherit }
.p-sidebar { width:220px; background:#0f1f4a; min-height:calc(100vh - 56px);
             position:fixed; top:56px; left:0; padding:16px 0; overflow-y:auto; z-index:10 }
.p-main { margin-left:220px; padding:28px 32px; min-height:calc(100vh - 56px) }
.p-topbar { background:#0f1f4a; height:56px; display:flex; align-items:center;
            justify-content:space-between; padding:0 28px;
            position:fixed; top:0; left:0; right:0; z-index:20 }
.p-brand { color:#fff; font-size:14px; font-weight:500; line-height:1.2 }
.p-brand span { color:#7aa2e0; font-size:11px; font-weight:400; display:block }
.p-logo { width:32px; height:32px; background:#274495; border-radius:8px;
          display:flex; align-items:center; justify-content:center;
          color:#fff; font-size:14px; font-weight:500; flex-shrink:0 }
.p-user-chip { background:#ffffff15; border:0.5px solid #ffffff25; border-radius:20px;
               padding:5px 14px; display:flex; align-items:center; gap:7px }
.p-user-dot { width:7px; height:7px; background:#34d399; border-radius:50% }
.p-user-name { color:#e0e8f5; font-size:12px; font-weight:500 }
.p-logout { background:transparent; border:0.5px solid #ffffff30; border-radius:6px;
            color:#ffffff60; font-size:11px; padding:5px 12px; cursor:pointer; transition:.15s }
.p-logout:hover { color:#fff; border-color:#ffffff60 }
.nav-section { font-size:9px; font-weight:500; color:#4a6fa5; letter-spacing:1.5px;
               text-transform:uppercase; padding:0 20px; margin:14px 0 4px }
.nav-item { display:flex; align-items:center; gap:10px; padding:9px 20px;
            cursor:pointer; transition:.15s; border-left:2px solid transparent }
.nav-item:hover { background:#ffffff08 }
.nav-item.active { background:#274495; border-left:2px solid #60a5fa }
.nav-label { font-size:13px; color:#a0b8d8 }
.nav-item.active .nav-label { color:#fff; font-weight:500 }
.nav-badge { margin-left:auto; background:#ef4444; color:#fff; font-size:9px;
             font-weight:500; padding:2px 6px; border-radius:10px }
.p-page-title { font-size:22px; font-weight:500; color:#0f172a; margin-bottom:2px }
.p-page-sub { font-size:13px; color:#64748b; margin-bottom:20px }
.p-kpi-grid { display:grid; grid-template-columns:repeat(4,minmax(0,1fr));
              gap:12px; margin-bottom:24px }
.p-kpi { background:#fff; border:0.5px solid #e2e8f0; border-radius:12px;
         padding:16px; position:relative; overflow:hidden }
.p-kpi::before { content:''; position:absolute; top:0; left:0; right:0; height:3px }
.p-kpi.c1::before { background:#274495 }
.p-kpi.c2::before { background:#059669 }
.p-kpi.c3::before { background:#d97706 }
.p-kpi.c4::before { background:#7c3aed }
.p-kpi-num { font-size:24px; font-weight:500; color:#0f172a; line-height:1; margin-top:10px }
.p-kpi-label { font-size:12px; color:#64748b; margin-top:3px }
.p-card { background:#fff; border:0.5px solid #e2e8f0; border-radius:12px; padding:20px }
.p-section-title { font-size:13px; font-weight:500; color:#0f172a;
                   margin-bottom:12px; margin-top:20px }
.p-fleet-grid { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:10px }
.p-fleet-card { background:#fff; border:0.5px solid #e2e8f0; border-radius:12px;
                padding:14px; cursor:pointer; transition:.15s; position:relative }
.p-fleet-card:hover { border-color:#93c5fd; background:#fafbff }
.p-fleet-card.sel { border:1.5px solid #3b82f6; background:#eff6ff }
.p-fleet-plate { font-size:15px; font-weight:500; color:#0f172a }
.p-fleet-model { font-size:11px; color:#94a3b8; margin:2px 0 4px }
.p-fleet-resp { font-size:12px; color:#475569; font-weight:500; margin-bottom:8px }
.p-fleet-bar { height:4px; background:#f1f5f9; border-radius:2px; overflow:hidden; margin-bottom:5px }
.p-fleet-fill { height:100%; border-radius:2px }
.p-fleet-phase { font-size:10px; color:#94a3b8 }
.p-badge { font-size:10px; font-weight:500; padding:2px 8px; border-radius:10px;
           position:absolute; top:10px; right:10px }
.p-phases { display:grid; grid-template-columns:repeat(7,1fr); gap:0;
            position:relative; margin-bottom:24px }
.p-phases::before { content:''; position:absolute; top:15px; left:6%; right:6%;
                    height:2px; background:#e2e8f0; z-index:0 }
.p-ph { display:flex; flex-direction:column; align-items:center; gap:5px;
        position:relative; z-index:2 }
.p-ph-c { width:30px; height:30px; border-radius:50%; display:flex;
          align-items:center; justify-content:center; font-size:11px;
          border:2px solid #e2e8f0; background:#fff }
.p-ph.done .p-ph-c { background:#274495; border-color:#274495; color:#fff }
.p-ph.active .p-ph-c { background:#3b82f6; border-color:#93c5fd; color:#fff;
                        box-shadow:0 0 0 4px #dbeafe }
.p-ph.pending .p-ph-c { background:#f8fafc; color:#94a3b8 }
.p-ph-lbl { font-size:9px; color:#94a3b8; text-align:center; white-space:nowrap }
.p-ph.done .p-ph-lbl { color:#274495 }
.p-ph.active .p-ph-lbl { color:#3b82f6; font-weight:500 }
.p-history-head { display:grid; grid-template-columns:100px 1fr 80px 80px 110px;
                  padding:10px 16px; background:#f8fafc;
                  border-bottom:0.5px solid #e2e8f0; border-radius:10px 10px 0 0 }
.p-history-head span { font-size:10px; font-weight:500; color:#94a3b8;
                        letter-spacing:.8px; text-transform:uppercase }
.p-history-row { display:grid; grid-template-columns:100px 1fr 80px 80px 110px;
                 padding:12px 16px; border-bottom:0.5px solid #f1f5f9;
                 align-items:center; transition:.1s }
.p-history-row:hover { background:#fafbff }
.p-history-row:last-child { border-bottom:none }
.p-status { font-size:11px; font-weight:500; padding:3px 10px;
            border-radius:20px; display:inline-block }
.p-tab-pills { display:flex; gap:6px; margin-bottom:16px;
               background:#fff; border:0.5px solid #e2e8f0;
               border-radius:10px; padding:4px; width:fit-content }
.p-tab-pill { font-size:12px; font-weight:500; padding:6px 14px; border-radius:7px;
              cursor:pointer; color:#64748b; background:transparent;
              border:none; transition:.15s }
.p-tab-pill.active { background:#274495; color:#fff }
.p-ev-row { display:flex; gap:8px; flex-wrap:wrap; margin-top:8px }
.p-ev-thumb { width:64px; height:64px; border-radius:8px; background:#f1f5f9;
              border:0.5px solid #e2e8f0; display:flex; align-items:center;
              justify-content:center; font-size:11px; color:#94a3b8;
              cursor:pointer; overflow:hidden; flex-shrink:0 }
</style>
"""

# ─── FASES ───────────────────────────────────────────────────────────────────
PHASES = ['RECEPCIÓN','DIAGNÓSTICO','REPUESTOS','APROBACIÓN','REPARACIÓN','CONTROL','ENTREGA']

def _phase_idx(estado):
    estado_u = (estado or '').upper()
    for i, p in enumerate(PHASES):
        if p in estado_u or estado_u in p:
            return i
    return 0

def _safe_json(data):
    if not data: return []
    if isinstance(data, list): return data
    if isinstance(data, str):
        try: return json.loads(data)
        except: return []
    return []

def _status_badge(estado):
    m = {
        'ENTREGA':    ('background:#d1fae5;color:#065f46','Entregada'),
        'ARCHIVADO':  ('background:#d1fae5;color:#065f46','Completada'),
        'CONTROL':    ('background:#dbeafe;color:#1e40af','Control Q.'),
        'REPARACIÓN': ('background:#dbeafe;color:#1e40af','En reparación'),
        'APROBACIÓN': ('background:#fef3c7;color:#92400e','Aprobación'),
        'REPUESTOS':  ('background:#fef3c7;color:#92400e','Repuestos'),
        'DIAGNÓSTICO':('background:#fef3c7;color:#92400e','Diagnóstico'),
        'RECEPCIÓN':  ('background:#f3f4f6;color:#374151','Recepción'),
    }
    for k,(style,lbl) in m.items():
        if k in (estado or '').upper():
            return style, lbl
    return 'background:#f3f4f6;color:#374151', estado or '—'

def _fleet_badge(estado):
    e = (estado or '').upper()
    if 'ENTREGA' in e or 'ARCHIV' in e:
        return '#d1fae5','#065f46','Entregada'
    if 'CONTROL' in e or 'REPARA' in e:
        return '#dbeafe','#1e40af','En taller'
    if 'APROB' in e or 'REPUES' in e or 'DIAGN' in e:
        return '#fef3c7','#92400e','En proceso'
    if 'RECEP' in e:
        return '#f3f4f6','#374151','Recepción'
    return '#f1f5f9','#64748b','Disponible'

def _fleet_bar_color(estado):
    e = (estado or '').upper()
    if 'ENTREGA' in e or 'ARCHIV' in e: return '#10b981'
    if 'CONTROL' in e or 'REPARA' in e: return '#3b82f6'
    if 'DIAGN' in e or 'REPUES' in e or 'APROB' in e: return '#f59e0b'
    return '#94a3b8'


# ─── PORTAL PRINCIPAL ────────────────────────────────────────────────────────
def show_portal(container):
    user = get_current_user()
    if not user or user.get('rol') != 'cliente':
        with container:
            ui.label('Acceso no autorizado').classes('text-red-500 p-10')
        return

    db = get_db()
    try:
        user_id    = user.get('id')
        user_plate = user.get('placa','')
        cliente    = db.query(Cliente).filter_by(id=user_id).first()
        if not cliente:
            with container:
                ui.label('Cliente no encontrado').classes('text-red-500 p-10')
            return

        # Todos los vehículos del cliente
        vehiculos  = db.query(Vehiculo).filter_by(cliente_id=user_id).all()
        todas_placas = [v.placa for v in vehiculos]

        # Todas las órdenes de la flota
        ordenes_flota = []
        for placa in todas_placas:
            ords = db.query(Orden).filter_by(vehiculo_placa=placa).order_by(Orden.fecha.desc()).all()
            ordenes_flota.extend(ords)
        ordenes_flota.sort(key=lambda o: str(o.fecha or ''), reverse=True)

        # Orden activa de la moto propia
        ordenes_prop = [o for o in ordenes_flota if o.vehiculo_placa == user_plate]
        orden_activa = next((o for o in ordenes_prop if o.estado not in ('ARCHIVADO','ENTREGA')), None)

        # KPIs flota
        total_motos  = len(vehiculos)
        en_taller    = sum(1 for o in ordenes_flota
                          if o.estado not in ('ARCHIVADO','ENTREGA')
                          and o.vehiculo_placa in todas_placas
                          and o == next((x for x in ordenes_flota if x.vehiculo_placa==o.vehiculo_placa), None))
        listas       = sum(1 for o in ordenes_flota if 'ENTREGA' in (o.estado or '').upper()
                          and str(o.fecha or '').startswith(datetime.now().strftime('%Y-%m-%d')))

        # Calcular inversión del mes
        mes_actual = datetime.now().strftime('%Y-%m')
        inv_mes = sum(
            sum(float(it.get('total',0) or 0) for it in _safe_json(o.items_cotizacion))
            for o in ordenes_flota if str(o.fecha or '').startswith(mes_actual)
        )

    except Exception as e:
        import traceback
        with container:
            ui.label(f'Error: {e}').classes('text-red-500 p-10')
            ui.label(traceback.format_exc()).classes('text-xs font-mono p-10')
        db.close()
        return

    # ── Inyectar CSS ──────────────────────────────────────────────────────────
    ui.add_head_html(PORTAL_CSS)

    view_ref = {'current': 'dashboard'}

    with container:
        # ── TOPBAR ────────────────────────────────────────────────────────────
        with ui.element('div').classes('p-topbar'):
            with ui.row().classes('items-center gap-3'):
                ui.element('div').classes('p-logo').style('display:flex;align-items:center;justify-content:center').bind_text_from(cliente, 'nombre', lambda n: n[0].upper() if n else 'C')
                with ui.column().classes('gap-0'):
                    ui.label('Mecánica Sandoval EIRL').classes('p-brand')
                    ui.label(f'Portal Corporativo — {cliente.nombre}').style('color:#7aa2e0;font-size:11px')
            with ui.row().classes('items-center gap-2'):
                with ui.element('div').classes('p-user-chip'):
                    ui.element('div').classes('p-user-dot')
                    ui.label(cliente.nombre).classes('p-user-name')
                ui.button('Cerrar sesión', on_click=lambda: _logout()).classes('p-logout').props('flat no-caps')

        # ── CONTENEDOR PRINCIPAL ──────────────────────────────────────────────
        with ui.element('div').style('display:flex;margin-top:56px'):

            # ── SIDEBAR ───────────────────────────────────────────────────────
            sidebar = ui.element('div').classes('p-sidebar')
            main_area = ui.column().style('margin-left:220px;padding:28px 32px;width:100%;min-height:calc(100vh - 56px)')

            nav_items = {}
            with sidebar:
                ui.element('div').classes('nav-section').style('padding:0 20px;margin:14px 0 4px;font-size:9px;font-weight:500;color:#4a6fa5;letter-spacing:1.5px;text-transform:uppercase').set_text('Principal')

                def make_nav(icon_svg, label, view_name, badge=None):
                    with ui.element('div').classes('nav-item').on('click', lambda v=view_name: switch_view(v)) as item:
                        ui.html(icon_svg)
                        ui.label(label).classes('nav-label')
                        if badge:
                            ui.element('span').classes('nav-badge').set_text(str(badge))
                    nav_items[view_name] = item
                    return item

                make_nav('<svg width="16" height="16" fill="none" viewBox="0 0 24 24" stroke="#60a5fa" stroke-width="2"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>', 'Dashboard', 'dashboard')
                make_nav('<svg width="16" height="16" fill="none" viewBox="0 0 24 24" stroke="#a0b8d8" stroke-width="2"><path d="M5 17H3a2 2 0 01-2-2V5a2 2 0 012-2h11l5 5v5"/><circle cx="16" cy="17" r="2"/><circle cx="7" cy="17" r="2"/><path d="M5 17H14"/></svg>', 'Mi Flota', 'flota', total_motos)
                make_nav('<svg width="16" height="16" fill="none" viewBox="0 0 24 24" stroke="#a0b8d8" stroke-width="2"><path d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"/></svg>', 'Historial', 'historial')

                ui.html('<div class="nav-section">Mi vehículo</div>')
                make_nav('<svg width="16" height="16" fill="none" viewBox="0 0 24 24" stroke="#a0b8d8" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg>', 'Orden activa', 'orden')
                make_nav('<svg width="16" height="16" fill="none" viewBox="0 0 24 24" stroke="#a0b8d8" stroke-width="2"><rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/></svg>', 'Agendar cita', 'cita')

            # ── VISTAS ────────────────────────────────────────────────────────
            views = {}
            with main_area:
                # DASHBOARD
                with ui.column().classes('w-full') as v_dashboard:
                    ui.label('Dashboard').classes('p-page-title')
                    ui.label(f'Bienvenido, {cliente.nombre} — resumen de tu flota').classes('p-page-sub')
                    with ui.element('div').classes('p-kpi-grid'):
                        _kpi('c1', total_motos, 'Motos en flota', '#274495')
                        _kpi('c2', en_taller, 'En taller ahora', '#059669')
                        _kpi('c3', listas, 'Entregadas hoy', '#d97706')
                        _kpi('c4', f'S/ {inv_mes:,.0f}', 'Inversión este mes', '#7c3aed')

                    ui.html('<div class="p-section-title">Estado de flota — vista rápida</div>')
                    with ui.element('div').classes('p-fleet-grid'):
                        for v in vehiculos[:5]:
                            orden_v = next((o for o in ordenes_flota
                                           if o.vehiculo_placa == v.placa
                                           and o.estado not in ('ARCHIVADO',)), None)
                            _fleet_card(v, orden_v, lambda vn=v.placa: switch_view('orden'))
                        if len(vehiculos) > 5:
                            with ui.element('div').style('background:#fff;border:0.5px dashed #e2e8f0;border-radius:12px;display:flex;align-items:center;justify-content:center;min-height:100px;cursor:pointer').on('click', lambda: switch_view('flota')):
                                with ui.column().style('text-align:center;gap:4px'):
                                    ui.label(f'+{len(vehiculos)-5} más').style('font-size:14px;color:#94a3b8')
                                    ui.label('Ver todas').style('font-size:11px;color:#cbd5e1')

                    ui.html('<div class="p-section-title">Últimas órdenes</div>')
                    with ui.element('div').style('background:#fff;border:0.5px solid #e2e8f0;border-radius:12px;overflow:hidden'):
                        _history_header()
                        for o in ordenes_flota[:5]:
                            veh_o = next((v for v in vehiculos if v.placa == o.vehiculo_placa), None)
                            _history_row(o, veh_o)
                views['dashboard'] = v_dashboard

                # FLOTA
                with ui.column().classes('w-full') as v_flota:
                    v_flota.set_visibility(False)
                    ui.label('Mi Flota').classes('p-page-title')
                    ui.label(f'{total_motos} vehículos registrados').classes('p-page-sub')
                    with ui.element('div').classes('p-fleet-grid'):
                        for v in vehiculos:
                            orden_v = next((o for o in ordenes_flota
                                           if o.vehiculo_placa == v.placa
                                           and o.estado not in ('ARCHIVADO',)), None)
                            _fleet_card(v, orden_v, lambda: None, big=True)
                views['flota'] = v_flota

                # HISTORIAL
                with ui.column().classes('w-full') as v_hist:
                    v_hist.set_visibility(False)
                    ui.label('Historial de servicios').classes('p-page-title')
                    ui.label('Todas las órdenes de tu flota').classes('p-page-sub')
                    with ui.element('div').style('background:#fff;border:0.5px solid #e2e8f0;border-radius:12px;overflow:hidden'):
                        _history_header()
                        for o in ordenes_flota:
                            veh_o = next((v for v in vehiculos if v.placa == o.vehiculo_placa), None)
                            _history_row(o, veh_o)
                views['historial'] = v_hist

                # ORDEN ACTIVA
                with ui.column().classes('w-full') as v_orden:
                    v_orden.set_visibility(False)
                    if orden_activa:
                        veh_prop = next((v for v in vehiculos if v.placa == user_plate), None)
                        ui.label(f'Orden activa — {user_plate}').classes('p-page-title')
                        resp = getattr(veh_prop, 'responsable', '') if veh_prop else ''
                        ui.label(f'{getattr(veh_prop,"marca","")} {getattr(veh_prop,"modelo","")} · Responsable: {resp or "—"}').classes('p-page-sub')
                        _orden_detalle(orden_activa)
                    else:
                        ui.label('Sin orden activa').classes('p-page-title')
                        ui.label(f'El vehículo {user_plate} no tiene órdenes activas actualmente.').classes('p-page-sub')
                        with ui.element('div').classes('p-card').style('text-align:center;padding:40px'):
                            ui.icon('check_circle', size='48px').style('color:#10b981')
                            ui.label('Todo al día').style('font-size:16px;font-weight:500;color:#0f172a;margin-top:8px;display:block')
                            ui.label('Tu vehículo fue atendido y entregado.').style('font-size:13px;color:#64748b;display:block')
                views['orden'] = v_orden

                # CITA
                with ui.column().classes('w-full') as v_cita:
                    v_cita.set_visibility(False)
                    ui.label('Agendar cita').classes('p-page-title')
                    ui.label('Solicita una revisión para tu vehículo').classes('p-page-sub')
                    with ui.element('div').classes('p-card').style('max-width:500px'):
                        veh_opts = {v.placa: f'{v.marca} {v.modelo} — {v.placa}' for v in vehiculos}
                        veh_sel  = ui.select(veh_opts, label='Vehículo', value=user_plate if user_plate in veh_opts else None).props('outlined dense').classes('w-full mb-3')
                        fecha_in = ui.input('Fecha deseada').props('outlined dense type=date').classes('w-full mb-3')
                        hora_sel = ui.select(['08:00 AM','09:00 AM','10:00 AM','11:00 AM','02:00 PM','03:00 PM','04:00 PM'], label='Hora', value='08:00 AM').props('outlined dense').classes('w-full mb-3')
                        serv_sel = ui.select(['Mantenimiento General','Cambio de Aceite','Revisión de Frenos','Diagnóstico Eléctrico','Revisión Preventiva','Otro'], label='Servicio', value='Mantenimiento General').props('outlined dense').classes('w-full mb-3')
                        desc_in  = ui.textarea('Descripción (opcional)').props('outlined dense rows=2').classes('w-full mb-4')

                        async def solicitar_cita():
                            if not fecha_in.value or not veh_sel.value:
                                ui.notify('Selecciona fecha y vehículo', type='warning')
                                return
                            db2 = get_db()
                            try:
                                db2.add(Cita(cliente_id=user_id, vehiculo_placa=veh_sel.value,
                                            fecha_cita=fecha_in.value, hora=hora_sel.value,
                                            motivo=f'[{serv_sel.value}] {desc_in.value}'))
                                db2.commit()
                                ui.notify('¡Cita solicitada con éxito!', type='positive')
                                desc_in.value = ''
                            except Exception as ex:
                                ui.notify(f'Error: {ex}', type='negative')
                            finally:
                                db2.close()

                        ui.button('Confirmar cita', icon='event', on_click=solicitar_cita).classes('btn-sandoval w-full')
                views['cita'] = v_cita

            # ── Activar dashboard al inicio ───────────────────────────────────
            nav_items['dashboard'].classes(add='active')

            def switch_view(name):
                for k, v in views.items():
                    v.set_visibility(k == name)
                for k, n in nav_items.items():
                    if k == name:
                        n.classes(add='active')
                    else:
                        n.classes(remove='active')
                view_ref['current'] = name

    db.close()


def _logout():
    from utils.auth import logout
    logout()
    ui.navigate.to('/')


# ─── HELPERS UI ──────────────────────────────────────────────────────────────
def _kpi(cls, value, label, color):
    with ui.element('div').classes(f'p-kpi {cls}'):
        ui.label(str(value)).classes('p-kpi-num')
        ui.label(label).classes('p-kpi-label')


def _fleet_card(v, orden, on_click_fn, big=False):
    estado = orden.estado if orden else None
    bg, fg, lbl = _fleet_badge(estado)
    bar_color   = _fleet_bar_color(estado)
    idx = _phase_idx(estado) if estado else 0
    pct = int((idx / max(len(PHASES)-1,1)) * 100) if estado else 0
    resp = getattr(v, 'responsable', '') or '—'
    phase_lbl = f'Fase {idx+1}/{len(PHASES)} — {estado}' if estado else 'Sin orden activa'

    with ui.element('div').classes('p-fleet-card').on('click', on_click_fn):
        with ui.row().style('display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:4px'):
            ui.label(v.placa).classes('p-fleet-plate')
        ui.label(f'{v.marca} {v.modelo} {v.año}'.strip()).classes('p-fleet-model')
        ui.label(resp).classes('p-fleet-resp')
        with ui.element('div').classes('p-fleet-bar'):
            ui.element('div').classes('p-fleet-fill').style(f'width:{pct}%;background:{bar_color}')
        ui.label(phase_lbl).classes('p-fleet-phase')
        ui.element('span').classes('p-badge').style(f'background:{bg};color:{fg}').set_text(lbl)


def _history_header():
    with ui.element('div').classes('p-history-head'):
        for h in ['Orden','Descripción','Vehículo','Monto','Estado']:
            ui.element('span').set_text(h)


def _history_row(o, veh):
    style, lbl = _status_badge(o.estado)
    total = sum(float(it.get('total',0) or 0) for it in _safe_json(o.items_cotizacion))
    resp  = getattr(veh, 'responsable', '') or '—' if veh else '—'
    with ui.element('div').classes('p-history-row'):
        ui.label(str(o.consecutivo or '—')).style('font-size:12px;color:#475569;font-weight:500')
        with ui.column().style('gap:1px'):
            ui.label((o.motivo or 'Revisión')[:45]).style('font-size:13px;font-weight:500;color:#0f172a')
            ui.label(f'{str(o.fecha or "")[:10]} · {resp}').style('font-size:11px;color:#94a3b8')
        ui.label(o.vehiculo_placa or '—').style('font-size:12px;color:#64748b')
        ui.label(f'S/ {total:,.0f}').style('font-size:13px;font-weight:500;color:#0f172a')
        ui.element('span').classes('p-status').style(style).set_text(lbl)


def _orden_detalle(o):
    idx = _phase_idx(o.estado)
    with ui.element('div').classes('p-card'):
        # Header orden
        with ui.row().style('display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:20px'):
            with ui.column().style('gap:3px'):
                ui.label(str(o.consecutivo)).style('font-size:12px;color:#94a3b8')
                ui.label(o.motivo or 'Orden de servicio').style('font-size:16px;font-weight:500;color:#0f172a')
                ui.label(f'Ingreso: {str(o.fecha or "—")[:10]} · KM: {o.km or "—"} · Técnico: {o.tecnico or "—"}').style('font-size:12px;color:#64748b')
            with ui.element('div').style('background:#eff6ff;border:0.5px solid #bfdbfe;border-radius:8px;padding:8px 14px;text-align:right'):
                ui.label('Entrega estimada').style('font-size:10px;color:#3b82f6;font-weight:500')
                ui.label(str(getattr(o,'proximo_mantenimiento','') or 'Por confirmar')).style('font-size:14px;font-weight:500;color:#1e40af')

        # Tracker fases
        with ui.element('div').classes('p-phases'):
            for i, phase in enumerate(PHASES):
                status = 'done' if i < idx else ('active' if i == idx else 'pending')
                with ui.element('div').classes(f'p-ph {status}'):
                    icon = '✓' if i < idx else ('⚙' if i == idx else str(i+1))
                    ui.element('div').classes('p-ph-c').set_text(icon)
                    ui.element('div').classes('p-ph-lbl').set_text(phase.capitalize())

        # Detalle en 2 columnas
        with ui.row().style('display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px'):
            with ui.element('div').style('background:#f8fafc;border-radius:10px;padding:14px'):
                ui.label('DIAGNÓSTICO TÉCNICO').style('font-size:10px;font-weight:500;color:#94a3b8;letter-spacing:.8px;margin-bottom:6px;display:block')
                ui.label(o.diagnostico or 'Diagnóstico en proceso...').style('font-size:13px;color:#334155;line-height:1.6')

            with ui.element('div').style('background:#f8fafc;border-radius:10px;padding:14px'):
                ui.label('REPUESTOS Y SERVICIOS').style('font-size:10px;font-weight:500;color:#94a3b8;letter-spacing:.8px;margin-bottom:6px;display:block')
                items = _safe_json(o.items_cotizacion)
                if items:
                    total = 0
                    for it in items:
                        val = float(it.get('total',0) or 0)
                        total += val
                        with ui.row().style('display:flex;justify-content:space-between;font-size:12px;margin-bottom:3px'):
                            ui.label(it.get('nombre', it.get('item','—'))).style('color:#475569')
                            ui.label(f'S/ {val:,.2f}').style('font-weight:500;color:#0f172a')
                    with ui.row().style('display:flex;justify-content:space-between;font-size:13px;padding-top:6px;border-top:0.5px solid #e2e8f0;margin-top:4px'):
                        ui.label('Total').style('font-weight:500;color:#0f172a')
                        ui.label(f'S/ {total:,.2f}').style('font-weight:500;color:#274495')
                else:
                    ui.label('Cotización en preparación...').style('font-size:12px;color:#94a3b8;font-style:italic')

        # Evidencias
        import os
        medios = []
        fev = _safe_json(o.fotos_evidencia) if o.fotos_evidencia else []
        for m in fev:
            path = m.get('path') if isinstance(m, dict) else m
            if path: medios.append(path)

        if medios:
            ui.label('EVIDENCIA FOTOGRÁFICA').style('font-size:10px;font-weight:500;color:#94a3b8;letter-spacing:.8px;margin-bottom:8px;display:block')
            with ui.element('div').classes('p-ev-row'):
                for path in medios[:8]:
                    ext = os.path.splitext(path)[1].lower()
                    with ui.element('div').classes('p-ev-thumb'):
                        if ext in ['.mp4','.mov','.avi','.webm']:
                            ui.video(path).style('width:100%;height:100%;object-fit:cover')
                        else:
                            ui.image(path).style('width:100%;height:100%;object-fit:cover').on('click', lambda p=path: ui.navigate.to(p))
                if len(medios) > 8:
                    ui.element('div').classes('p-ev-thumb').set_text(f'+{len(medios)-8}')

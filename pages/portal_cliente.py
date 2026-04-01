"""
SANDOVAL Dashboard - Portal del Cliente v9.3
Ruta dedicada /portal — sin theme.frame(), layout NiceGUI nativo.
"""

import unicodedata
from datetime import datetime
from nicegui import ui
from utils.models import get_db, Cliente, Vehiculo, Orden, Cita
from utils.auth import get_current_user

# ─── Helpers ─────────────────────────────────────────────────────────────────

def _norm(t):
    return unicodedata.normalize('NFD', str(t)).encode('ascii','ignore').decode().lower()

def _badge(estado):
    e = _norm(estado)
    if   'recep'  in e:                        bg,c='#f1f5f9','#475569'
    elif 'diagn'  in e:                        bg,c='#f5f3ff','#6b21a8'
    elif 'repar'  in e or 'taller' in e:       bg,c='#fef3c7','#92400e'
    elif 'lista'  in e or 'list'   in e:       bg,c='#dbeafe','#1e40af'
    elif 'entreg' in e or 'archiv' in e:       bg,c='#dcfce7','#166534'
    else:                                       bg,c='#f1f5f9','#475569'
    return (f'<span style="background:{bg};color:{c};font-size:11px;font-weight:600;'
            f'padding:3px 10px;border-radius:20px;display:inline-block;white-space:nowrap">{estado}</span>')

FASES = ['Recepción','Diagnóstico','Cotización','Reparación','Listo','Entrega']

def _fase_idx(estado):
    e = _norm(estado)
    if 'recep'  in e:                   return 0
    if 'diagn'  in e:                   return 1
    if 'cotiz'  in e or 'aprob' in e:   return 2
    if 'repar'  in e or 'taller' in e:  return 3
    if 'lista'  in e or 'list'  in e:   return 4
    return 5

def _total(o):
    try: return sum(float(i.get('subtotal',0)) for i in (o.items_cotizacion or []))
    except: return 0.0

def _fases_html(estado):
    fi  = _fase_idx(estado)
    pct = int(fi/(len(FASES)-1)*100) if fi>0 else 0
    cols = []
    for i,name in enumerate(FASES):
        if i < fi:
            cs = 'background:#2563eb;border:2px solid #2563eb;color:#fff'
            ls = 'color:#2563eb;font-weight:600'; txt='✓'
        elif i == fi:
            cs = 'background:#fff;border:2px solid #2563eb;color:#2563eb;box-shadow:0 0 0 4px #dbeafe'
            ls = 'color:#2563eb;font-weight:700'; txt=str(i+1)
        else:
            cs = 'background:#f8fafc;border:2px solid #e2e8f0;color:#94a3b8'
            ls = 'color:#94a3b8'; txt=str(i+1)
        cols.append(
            f'<div style="flex:1;display:flex;flex-direction:column;align-items:center;gap:6px;position:relative;z-index:2">'
            f'<div style="width:28px;height:28px;border-radius:50%;{cs};display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:700">{txt}</div>'
            f'<div style="font-size:9.5px;{ls};text-align:center;white-space:nowrap">{name}</div>'
            f'</div>'
        )
    return (
        f'<div style="display:flex;position:relative;padding:0 4px;margin:16px 0">'
        f'<div style="position:absolute;top:14px;left:20px;right:20px;height:2px;background:#e2e8f0;z-index:0"></div>'
        f'<div style="position:absolute;top:14px;left:20px;height:2px;background:#2563eb;z-index:1;width:{pct}%"></div>'
        + ''.join(cols) + '</div>'
    )

# ─── Página standalone (llamada desde @ui.page('/portal')) ───────────────────

def show_portal_page():
    """
    Portal del cliente como página NiceGUI independiente.
    Llamar desde @ui.page('/portal') en main.py.
    """
    user = get_current_user()
    if not user or user.get('rol') != 'cliente':
        ui.navigate.to('/login')
        return

    db = get_db()
    try:
        client_id = user.get('id')
        cli = db.query(Cliente).filter_by(id=client_id).first()
        if not cli:
            ui.navigate.to('/login')
            return

        es_empresa  = (cli.tipo or 'Persona').lower() in ('empresa','corporativo','corporativa')
        vehs        = db.query(Vehiculo).filter_by(cliente_id=client_id).all()
        placas      = [v.placa for v in vehs]
        ords        = (db.query(Orden).filter(Orden.vehiculo_placa.in_(placas))
                       .order_by(Orden.fecha.desc()).all()) if placas else []
        citas_all   = db.query(Cita).filter_by(cliente_id=client_id).order_by(Cita.fecha_cita.asc()).all()
        ahora       = datetime.now().strftime('%Y-%m-%d')
        citas_fut   = [c for c in citas_all if c.fecha_cita >= ahora]
        ord_act     = [o for o in ords if o.estado not in ('ARCHIVADO','ENTREGA','ENTREGADO')]
        ord_hist    = [o for o in ords if o.estado     in ('ARCHIVADO','ENTREGA','ENTREGADO')]
        nombre      = cli.nombre if es_empresa else f"{cli.nombre} {cli.apellidos or ''}".strip()
        initials    = ''.join(p[0].upper() for p in nombre.split()[:2]) or 'C'
        _view       = {'v':'dashboard','d':None}
    except Exception as e:
        ui.label(f'Error: {e}').classes('text-red-500 p-10')
        return

    # ── Reset estilos NiceGUI ──────────────────────────────────────────────
    ui.add_head_html('''<style>
      body,html{margin:0;padding:0;background:#f0f4f8;overflow:hidden}
      .q-header{height:64px!important;background:#fff!important;
        border-bottom:1px solid #e2e8f0!important;
        box-shadow:0 1px 3px rgba(0,0,0,.06)!important}
      .q-drawer{background:#fff!important;border-right:1px solid #e2e8f0!important;
        box-shadow:none!important}
      .q-page-container{padding-top:64px!important}
      .q-page{background:#f0f4f8!important;padding:0!important;min-height:0!important;overflow-y:auto!important}
      .nicegui-content{padding:0!important;max-width:none!important;height:auto!important;
        overflow:visible!important;animation:none!important}
      /* reset theme.py overrides */
      h1,h2,h3{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif!important;
        font-size:inherit!important;font-weight:inherit!important;
        letter-spacing:inherit!important;text-shadow:none!important}
      /* Portal vars */
      :root{--pb:#2563eb;--pbl:#eff6ff;--pbm:#bfdbfe;
        --pg:#16a34a;--pa:#d97706;
        --ps:#f8fafc;--pbo:#e2e8f0;
        --pt:#1e293b;--pt2:#64748b;--pt3:#94a3b8}
      /* nav items */
      .pni{display:flex;align-items:center;gap:10px;padding:9px 16px 9px 20px;
        cursor:pointer;border-left:2.5px solid transparent;margin:1px 0;transition:.12s}
      .pni:hover{background:#f8fafc}
      .pni.on{background:#eff6ff;border-left-color:#2563eb}
      .pni.on .pnl{color:#2563eb!important;font-weight:600!important}
      .pni:hover .pnl{color:#1e293b!important}
      .pnl{font-size:13px;font-weight:500;color:#64748b;flex:1}
      .pnb{background:#eff6ff;color:#2563eb;font-size:9.5px;font-weight:700;
        padding:2px 7px;border-radius:10px;margin-left:auto}
      /* cards */
      .pc{background:#fff;border:1px solid #e2e8f0;border-radius:14px;
        padding:20px;margin-bottom:20px}
      .poc{background:#fff;border:1px solid #e2e8f0;border-radius:14px;
        padding:20px;margin-bottom:20px;border-left:4px solid #2563eb}
      /* kpi */
      .pkpi{background:#fff;border:1px solid #e2e8f0;border-radius:14px;
        padding:18px 18px 16px;position:relative;overflow:hidden;transition:.2s}
      .pkpi:hover{box-shadow:0 4px 16px rgba(0,0,0,.07);transform:translateY(-1px)}
      .pkpi::after{content:'';position:absolute;top:0;left:0;right:0;height:3px;border-radius:14px 14px 0 0}
      .k1::after{background:linear-gradient(90deg,#2563eb,#60a5fa)}
      .k2::after{background:linear-gradient(90deg,#16a34a,#4ade80)}
      .k3::after{background:linear-gradient(90deg,#d97706,#fbbf24)}
      .k4::after{background:linear-gradient(90deg,#7c3aed,#c084fc)}
      /* table */
      .pt{width:100%;border-collapse:collapse}
      .pt thead th{font-size:10px;font-weight:700;color:#94a3b8;letter-spacing:.8px;
        text-transform:uppercase;padding:10px 14px;background:#f8fafc;
        border-bottom:1px solid #e2e8f0;text-align:left}
      .pt tbody tr:hover td{background:#fafbff}
      .pt tbody td{padding:11px 14px;border-bottom:1px solid #f1f5f9;vertical-align:middle}
      .pt tbody tr:last-child td{border-bottom:none}
      .pp{font-size:13px;font-weight:700;color:#0f172a;background:#f1f5f9;
        display:inline-block;padding:3px 9px;border-radius:6px;letter-spacing:.5px}
      .pb2{display:inline-flex;align-items:center;gap:6px;padding:8px 14px;
        border-radius:8px;background:#fff;border:1px solid #e2e8f0;font-size:12px;
        font-weight:600;color:#64748b;cursor:pointer;margin-bottom:20px;transition:.15s}
      .pb2:hover{border-color:#94a3b8;color:#0f172a}
      .pec{margin:0 12px 16px;padding:12px 14px;
        background:linear-gradient(135deg,#eff6ff,#f0f9ff);
        border:1px solid #bfdbfe;border-radius:10px}
    </style>''')

    # ── HEADER (NiceGUI nativo) ────────────────────────────────────────────
    with ui.header(elevated=False).style(
        'height:64px;background:#fff;border-bottom:1px solid #e2e8f0;'
        'padding:0 24px 0 0;box-shadow:0 1px 3px rgba(0,0,0,.06)'
    ):
        with ui.row().style(
            'display:flex;align-items:center;justify-content:space-between;'
            'height:100%;width:100%;flex-wrap:nowrap'
        ):
            # Logo + brand
            ui.html(
                f'<div style="display:flex;align-items:center;gap:12px;width:240px;'
                f'height:100%;padding:0 20px;border-right:1px solid #e2e8f0;flex-shrink:0;box-sizing:border-box">'
                f'<div style="width:36px;height:36px;background:#2563eb;border-radius:10px;'
                f'display:flex;align-items:center;justify-content:center;font-weight:800;'
                f'font-size:16px;color:#fff;box-shadow:0 2px 8px rgba(37,99,235,.35);flex-shrink:0">S</div>'
                f'<div><div style="font-size:14px;font-weight:700;color:#0f172a;line-height:1.2">SANDOVAL</div>'
                f'<div style="font-size:11px;color:#64748b">Portal del Cliente</div></div>'
                f'</div>'
            )
            # User chip + logout
            ui.html(
                f'<div style="display:flex;align-items:center;gap:10px">'
                f'<div style="display:flex;align-items:center;gap:9px;padding:6px 14px 6px 8px;'
                f'border-radius:24px;background:#f8fafc;border:1px solid #e2e8f0">'
                f'<div style="width:30px;height:30px;border-radius:50%;background:#2563eb;'
                f'display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:700;color:#fff">{initials}</div>'
                f'<div><div style="font-size:12px;font-weight:600;color:#0f172a">{nombre}</div>'
                f'<div style="font-size:10px;color:#64748b">{"Empresa" if es_empresa else "Cliente"}</div>'
                f'</div></div>'
                f'<button onclick="window.location.href=\'/login\'" style="padding:7px 14px;border-radius:8px;'
                f'background:#fff;border:1px solid #e2e8f0;font-size:12px;color:#64748b;cursor:pointer;font-weight:500">'
                f'Cerrar sesión</button>'
                f'</div>'
            )

    # ── DRAWER (NiceGUI nativo) ────────────────────────────────────────────
    with ui.left_drawer(value=True).style(
        'background:#fff;border-right:1px solid #e2e8f0;width:240px;'
        'padding-top:16px;padding-bottom:24px'
    ) as drawer_el:
        pass  # se llena abajo

    # ── MAIN (NiceGUI page body) ───────────────────────────────────────────
    with ui.column().style(
        'width:100%;padding:28px 32px;background:#f0f4f8;'
        'min-height:calc(100vh - 64px);box-sizing:border-box'
    ) as main_el:
        pass  # se llena abajo

    def refresh():
        _fill_drawer(drawer_el, _view, cli, es_empresa, vehs, ord_act, refresh)
        _fill_main(main_el, _view, cli, es_empresa, vehs, ords, ord_act, ord_hist,
                   citas_all, citas_fut, db, refresh)

    refresh()
    db.close()


# ─── Compatibilidad: llamado desde dentro del frame del admin ─────────────────
def show_portal(container):
    """
    Fallback: si se llama desde dentro del frame admin,
    redirige al usuario a la ruta /portal dedicada.
    """
    ui.navigate.to('/portal')


# ─── Drawer ──────────────────────────────────────────────────────────────────

def _fill_drawer(drawer_el, _view, cli, es_empresa, vehs, ord_act, refresh):
    drawer_el.clear()
    with drawer_el:
        if es_empresa:
            en_t = sum(1 for o in ord_act if _norm(o.estado) not in ('lista','listo'))
            lst  = sum(1 for o in ord_act if _norm(o.estado)     in ('lista','listo'))
            ui.html(
                f'<div class="pec">'
                f'<div style="font-size:9px;font-weight:700;color:#2563eb;text-transform:uppercase;letter-spacing:1px;margin-bottom:5px">Empresa</div>'
                f'<div style="font-size:13px;font-weight:700;color:#0f172a">{cli.nombre}</div>'
                f'<div style="font-size:11px;color:#64748b;margin-top:2px">RUC {cli.id}</div>'
                f'<div style="display:flex;gap:16px;margin-top:8px">'
                f'  <div style="text-align:center"><div style="font-size:20px;font-weight:700;color:#2563eb;line-height:1">{len(vehs)}</div><div style="font-size:9px;color:#64748b;margin-top:2px">Vehículos</div></div>'
                f'  <div style="text-align:center"><div style="font-size:20px;font-weight:700;color:#2563eb;line-height:1">{en_t}</div><div style="font-size:9px;color:#64748b;margin-top:2px">En taller</div></div>'
                f'  <div style="text-align:center"><div style="font-size:20px;font-weight:700;color:#2563eb;line-height:1">{lst}</div><div style="font-size:9px;color:#64748b;margin-top:2px">Listos</div></div>'
                f'</div></div>'
            )

        def nav(v):
            _view['v'] = v; _view['d'] = None; refresh()

        _sb_sec('Principal')
        _nb('dashboard',    '🏠','Dashboard',       _view,nav)
        _nb('flota',        '🚗','Mi Flota',         _view,nav, str(len(vehs)) if len(vehs)>1 else None)
        _sb_sec('Servicios')
        _nb('ordenes',      '🔧','Órdenes Activas', _view,nav, str(len(ord_act)) if ord_act else None)
        _nb('historial',    '📋','Historial',        _view,nav)
        _nb('citas',        '📅','Citas',             _view,nav)
        if es_empresa:
            _sb_sec('Empresa')
            _nb('empresa',      '🏢','Mi Empresa',   _view,nav)
            _nb('responsables', '👥','Responsables', _view,nav)
        _sb_sec('Cuenta')
        _nb('perfil','👤','Mi Perfil',_view,nav)


def _sb_sec(txt):
    ui.html(f'<div style="font-size:9.5px;font-weight:700;color:#94a3b8;letter-spacing:1.2px;'
            f'text-transform:uppercase;padding:0 20px;margin:20px 0 6px">{txt}</div>')

def _nb(view,icon,label,_view,nav_fn,badge=None):
    on='on' if _view['v']==view else ''
    with ui.element('div').classes(f'pni {on}').on('click',lambda v=view:nav_fn(v)):
        ui.html(f'<span style="font-size:18px;line-height:1;flex-shrink:0">{icon}</span>')
        ui.html(f'<span class="pnl">{label}</span>')
        if badge: ui.html(f'<span class="pnb">{badge}</span>')


# ─── Main filler ─────────────────────────────────────────────────────────────

def _fill_main(main_el,_view,cli,es_empresa,vehs,ords,ord_act,ord_hist,citas_all,citas_fut,db,refresh):
    main_el.clear()
    with main_el:
        v = _view['v']
        if   v=='dashboard':    _vw_dash(main_el,_view,cli,vehs,ord_act,ord_hist,citas_fut,refresh)
        elif v=='flota':        _vw_flota(vehs,ord_act)
        elif v=='ordenes':      _vw_ordenes(main_el,_view,ord_act,refresh)
        elif v=='historial':    _vw_hist(ord_hist)
        elif v=='citas':        _vw_citas(citas_all,citas_fut)
        elif v=='empresa':      _vw_empresa(cli,vehs,ord_act)
        elif v=='responsables': _vw_resps(vehs,ord_act)
        elif v=='perfil':       _vw_perfil(cli,db)
        elif v=='detalle':      _vw_detalle(_view,ords,vehs,refresh)


def _ph(h1,sub=''):
    ui.html(
        f'<div style="margin-bottom:24px">'
        f'<div style="font-size:22px;font-weight:700;color:#0f172a;letter-spacing:-.4px">{h1}</div>'
        + (f'<div style="font-size:13px;color:#64748b;margin-top:4px">{sub}</div>' if sub else '')
        + '</div>'
    )


# ─── Dashboard ───────────────────────────────────────────────────────────────

def _vw_dash(container,_view,cli,vehs,ord_act,ord_hist,citas_fut,refresh):
    _ph(f'Bienvenido, {cli.nombre.split()[0]}',
        f'Resumen de su cuenta · {datetime.now().strftime("%d/%m/%Y")}')

    # KPI grid
    with ui.element('div').style('display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:28px'):
        _kpi('k1','🚗',str(len(vehs)),       'Vehículos',  'Registrados','#eff6ff')
        _kpi('k2','🔧',str(len(ord_act)),     'Activos',    'En servicio','#f0fdf4')
        _kpi('k3','📋',str(len(ord_hist)),    'Servicios',  'Completados','#fffbeb')
        _kpi('k4','📅',str(len(citas_fut)),   'Citas',      'Próximas',   '#f5f3ff')

    # Orden activa
    if ord_act:
        _orden_card(container,_view,ord_act[0],refresh)

    # Grid 2 col
    with ui.element('div').style('display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:20px'):
        with ui.element('div').classes('pc').style('margin-bottom:0'):
            ui.html('<div style="font-size:14px;font-weight:700;color:#0f172a;margin-bottom:14px">Mi Flota</div>')
            if vehs:
                with ui.element('table').classes('pt'):
                    ui.html('<thead><tr><th>Placa</th><th>Modelo</th><th>Estado</th></tr></thead>')
                    with ui.element('tbody'):
                        for v in vehs[:5]:
                            ov=next((o for o in ord_act if o.vehiculo_placa==v.placa),None)
                            est=_badge(ov.estado) if ov else '<span style="color:#94a3b8">—</span>'
                            ui.html(f'<tr><td><span class="pp">{v.placa}</span></td>'
                                    f'<td><div style="font-size:12px;font-weight:600;color:#0f172a">{v.marca} {v.modelo}</div>'
                                    f'<div style="font-size:11px;color:#64748b">{v.año}</div></td>'
                                    f'<td>{est}</td></tr>')
            else:
                ui.html('<p style="color:#94a3b8;text-align:center;padding:20px">Sin vehículos</p>')

        with ui.element('div').classes('pc').style('margin-bottom:0'):
            ui.html('<div style="font-size:14px;font-weight:700;color:#0f172a;margin-bottom:4px">Próximas Citas</div>')
            if citas_fut:
                for c in citas_fut[:4]: _cita_html(c)
            else:
                ui.html('<p style="color:#94a3b8;text-align:center;padding:20px">Sin citas programadas</p>')

    if ord_hist:
        with ui.element('div').classes('pc'):
            ui.html('<div style="font-size:14px;font-weight:700;color:#0f172a;margin-bottom:14px">Historial Reciente</div>')
            with ui.element('table').classes('pt'):
                ui.html('<thead><tr><th>Orden</th><th>Descripción</th><th>Fecha</th><th>Estado</th><th>Total</th></tr></thead>')
                with ui.element('tbody'):
                    for o in ord_hist[:5]:
                        t=_total(o)
                        ui.html(f'<tr><td style="font-size:12px;font-weight:600;color:#334155">{o.consecutivo}</td>'
                                f'<td><div style="font-size:13px;font-weight:500;color:#0f172a">{(o.motivo or "Servicio")[:40]}</div>'
                                f'<div style="font-size:11px;color:#64748b">{o.vehiculo_placa}</div></td>'
                                f'<td style="font-size:12px;color:#64748b">{o.fecha}</td>'
                                f'<td>{_badge(o.estado)}</td>'
                                f'<td style="font-size:13px;font-weight:700;color:#0f172a">{"S/ "+f"{t:,.2f}" if t else "—"}</td></tr>')


def _kpi(cls,icon,num,lbl,tag,icon_bg):
    with ui.element('div').classes(f'pkpi {cls}'):
        with ui.element('div').style('display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:12px'):
            ui.html(f'<div style="width:40px;height:40px;border-radius:10px;background:{icon_bg};'
                    f'display:flex;align-items:center;justify-content:center;font-size:20px">{icon}</div>')
            ui.html(f'<span style="font-size:10px;font-weight:600;padding:3px 8px;border-radius:20px;'
                    f'background:#f8fafc;color:#64748b">{tag}</span>')
        ui.html(f'<div style="font-size:26px;font-weight:700;color:#0f172a;line-height:1;letter-spacing:-.5px">{num}</div>')
        ui.html(f'<div style="font-size:12px;color:#64748b;margin-top:4px">{lbl}</div>')


def _cita_html(c,past=False):
    try: dt=datetime.strptime(c.fecha_cita,'%Y-%m-%d');day=dt.strftime('%d');mon=dt.strftime('%b').upper()
    except: day,mon='--','---'
    bg='#f8fafc' if past else '#eff6ff'; col='#64748b' if past else '#2563eb'
    tb='#fef3c7' if c.estado=='programada' else ('#f1f5f9' if past else '#dcfce7')
    tc='#92400e' if c.estado=='programada' else ('#475569' if past else '#166534')
    ui.html(
        f'<div style="display:flex;align-items:center;gap:14px;padding:12px 0;border-bottom:1px solid #f1f5f9">'
        f'<div style="min-width:46px;height:52px;background:{bg};border-radius:10px;'
        f'display:flex;flex-direction:column;align-items:center;justify-content:center;flex-shrink:0">'
        f'<div style="font-size:20px;font-weight:800;color:{col};line-height:1">{day}</div>'
        f'<div style="font-size:9px;font-weight:700;color:{col};text-transform:uppercase">{mon}</div>'
        f'</div>'
        f'<div style="flex:1;min-width:0">'
        f'<div style="font-size:13px;font-weight:600;color:#0f172a">{c.motivo or "Cita"}</div>'
        f'<div style="font-size:12px;color:#64748b;margin-top:2px">🕐 {c.hora or "Por confirmar"}'
        +(f' · {c.vehiculo_placa}' if c.vehiculo_placa else '')+
        f'</div></div>'
        f'<span style="background:{tb};color:{tc};font-size:10px;font-weight:600;'
        f'padding:3px 9px;border-radius:20px;white-space:nowrap">{c.estado.capitalize()}</span>'
        f'</div>'
    )


def _orden_card(container,_view,orden,refresh):
    t=_total(orden)
    with ui.element('div').classes('poc'):
        with ui.element('div').style('display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:16px'):
            with ui.element('div'):
                ui.html(f'<div style="font-size:11px;color:#64748b;margin-bottom:4px">Orden activa · {orden.consecutivo}</div>')
                ui.html(f'<div style="font-size:15px;font-weight:700;color:#0f172a;margin-bottom:6px">{orden.motivo or "Servicio en curso"}</div>')
                ui.html(f'<div style="display:flex;gap:16px;flex-wrap:wrap">'
                        f'<span style="font-size:12px;color:#64748b">🚗 {orden.vehiculo_placa}</span>'
                        f'<span style="font-size:12px;color:#64748b">📅 {orden.fecha}</span>'
                        +(f'<span style="font-size:12px;color:#64748b">🔧 {orden.tecnico}</span>' if orden.tecnico else '')
                        +(f'<span style="font-size:12px;color:#64748b">💰 S/ {t:,.2f}</span>' if t else '')
                        +f'</div>')
            ui.html(_badge(orden.estado))
        ui.html(_fases_html(orden.estado))
        def _go(o=orden):
            _view['v']='detalle';_view['d']=o.consecutivo;refresh()
        ui.button('Ver detalle completo',icon='arrow_forward',on_click=_go).props('flat').classes('text-blue-600 text-xs mt-1')


# ─── Flota ───────────────────────────────────────────────────────────────────

def _vw_flota(vehs,ord_act):
    _ph('Mi Flota',f'{len(vehs)} vehículo{"s" if len(vehs)!=1 else ""} registrado{"s" if len(vehs)!=1 else ""}')
    with ui.element('div').classes('pc'):
        if vehs:
            with ui.element('table').classes('pt'):
                ui.html('<thead><tr><th>Placa</th><th>Vehículo</th><th>Tipo</th><th>Estado</th><th>Orden</th></tr></thead>')
                with ui.element('tbody'):
                    for v in vehs:
                        ov=next((o for o in ord_act if o.vehiculo_placa==v.placa),None)
                        ui.html(f'<tr><td><span class="pp">{v.placa}</span></td>'
                                f'<td><div style="font-size:13px;font-weight:600;color:#0f172a">{v.marca} {v.modelo}</div>'
                                f'<div style="font-size:11px;color:#64748b">{v.año} · {v.color}</div></td>'
                                f'<td style="font-size:12px;color:#64748b">{v.tipo}</td>'
                                f'<td>{_badge(ov.estado) if ov else "<span style=\'color:#94a3b8\'>—</span>"}</td>'
                                f'<td style="font-size:12px;color:#64748b">{ov.consecutivo if ov else "—"}</td></tr>')
        else:
            ui.html('<p style="color:#94a3b8;text-align:center;padding:30px">Sin vehículos</p>')


# ─── Órdenes activas ─────────────────────────────────────────────────────────

def _vw_ordenes(container,_view,ord_act,refresh):
    _ph('Órdenes Activas',f'{len(ord_act)} en proceso')
    if not ord_act:
        with ui.element('div').classes('pc'):
            ui.html('<p style="color:#94a3b8;text-align:center;padding:40px">No hay órdenes activas.</p>')
        return
    # clone view for navigation
    _vref={'v':'ordenes','d':None}
    for o in ord_act:
        _orden_card(container,_vref,o,refresh)


# ─── Historial ───────────────────────────────────────────────────────────────

def _vw_hist(ord_hist):
    _ph('Historial de Servicios',f'{len(ord_hist)} completado{"s" if len(ord_hist)!=1 else ""}')
    with ui.element('div').classes('pc'):
        if ord_hist:
            with ui.element('table').classes('pt'):
                ui.html('<thead><tr><th>Orden</th><th>Descripción</th><th>Placa</th><th>Fecha</th><th>Estado</th><th>Total</th></tr></thead>')
                with ui.element('tbody'):
                    for o in ord_hist:
                        t=_total(o)
                        ui.html(f'<tr><td style="font-size:12px;font-weight:600;color:#334155">{o.consecutivo}</td>'
                                f'<td><div style="font-size:13px;font-weight:500;color:#0f172a">{(o.motivo or "Servicio")[:40]}</div>'
                                f'<div style="font-size:11px;color:#64748b">{(o.diagnostico or "")[:35]}</div></td>'
                                f'<td><span class="pp">{o.vehiculo_placa}</span></td>'
                                f'<td style="font-size:12px;color:#64748b">{o.fecha}</td>'
                                f'<td>{_badge(o.estado)}</td>'
                                f'<td style="font-size:13px;font-weight:700;color:#0f172a">{"S/ "+f"{t:,.2f}" if t else "—"}</td></tr>')
        else:
            ui.html('<p style="color:#94a3b8;text-align:center;padding:30px">Sin historial</p>')


# ─── Citas ───────────────────────────────────────────────────────────────────

def _vw_citas(citas_all,citas_fut):
    ahora=datetime.now().strftime('%Y-%m-%d')
    past=sorted([c for c in citas_all if c.fecha_cita<ahora],key=lambda x:x.fecha_cita,reverse=True)
    _ph('Mis Citas',f'{len(citas_fut)} próxima{"s" if len(citas_fut)!=1 else ""}')
    with ui.element('div').style('display:grid;grid-template-columns:1fr 1fr;gap:20px'):
        with ui.element('div').classes('pc').style('margin-bottom:0'):
            ui.html('<div style="font-size:14px;font-weight:700;color:#0f172a;margin-bottom:4px">Próximas</div>')
            if citas_fut:
                for c in citas_fut: _cita_html(c)
            else:
                ui.html('<p style="color:#94a3b8;text-align:center;padding:20px">Sin citas próximas</p>')
        with ui.element('div').classes('pc').style('margin-bottom:0'):
            ui.html('<div style="font-size:14px;font-weight:700;color:#0f172a;margin-bottom:4px">Historial</div>')
            if past:
                for c in past[:10]: _cita_html(c,past=True)
            else:
                ui.html('<p style="color:#94a3b8;text-align:center;padding:20px">Sin historial</p>')


# ─── Empresa ─────────────────────────────────────────────────────────────────

def _vw_empresa(cli,vehs,ord_act):
    _ph(cli.nombre,f'RUC {cli.id}')
    en_t=sum(1 for o in ord_act if _norm(o.estado) not in ('lista','listo'))
    lst=sum(1 for o in ord_act  if _norm(o.estado)     in ('lista','listo'))
    with ui.element('div').style('display:grid;grid-template-columns:1fr 1fr;gap:20px'):
        with ui.element('div').classes('pc').style('margin-bottom:0'):
            ui.html('<div style="font-size:13px;font-weight:700;color:#0f172a;margin-bottom:14px;padding-bottom:8px;border-bottom:1px solid #e2e8f0">Datos Generales</div>')
            for l,v in [('RUC',cli.id),('Razón Social',cli.nombre),('Email',cli.email or '—'),
                        ('Teléfono',cli.telefono or '—'),('Dirección',cli.direccion or '—')]:
                ui.html(f'<div style="display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid #f1f5f9">'
                        f'<span style="font-size:12px;color:#94a3b8">{l}</span>'
                        f'<span style="font-size:13px;font-weight:600;color:#0f172a">{v}</span></div>')
        with ui.element('div').classes('pc').style('margin-bottom:0'):
            ui.html('<div style="font-size:13px;font-weight:700;color:#0f172a;margin-bottom:14px;padding-bottom:8px;border-bottom:1px solid #e2e8f0">Estadísticas</div>')
            for l,v in [('Total vehículos',len(vehs)),('En servicio',len(ord_act)),
                        ('En reparación',en_t),('Listos para recoger',lst)]:
                ui.html(f'<div style="display:flex;justify-content:space-between;align-items:center;padding:12px 0;border-bottom:1px solid #f1f5f9">'
                        f'<span style="font-size:13px;color:#64748b">{l}</span>'
                        f'<span style="font-size:20px;font-weight:700;color:#2563eb">{v}</span></div>')


# ─── Responsables ────────────────────────────────────────────────────────────

def _vw_resps(vehs,ord_act):
    _ph('Responsables','Vehículos y estado actual')
    with ui.element('div').style('display:grid;grid-template-columns:repeat(2,1fr);gap:16px'):
        for v in vehs:
            ov=next((o for o in ord_act if o.vehiculo_placa==v.placa),None)
            est=_badge(ov.estado) if ov else '<span style="color:#94a3b8;font-size:12px">Sin orden activa</span>'
            tec=(f'<div style="font-size:11px;color:#64748b;margin-top:4px">Técnico: {ov.tecnico}</div>' if ov and ov.tecnico else '')
            ui.html(
                f'<div style="background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:16px;'
                f'display:flex;align-items:center;gap:14px">'
                f'<div style="width:44px;height:44px;border-radius:50%;background:#eff6ff;'
                f'display:flex;align-items:center;justify-content:center;'
                f'font-size:14px;font-weight:700;color:#2563eb;flex-shrink:0">{v.placa[:2]}</div>'
                f'<div style="flex:1;min-width:0">'
                f'<div style="font-size:13px;font-weight:700;color:#0f172a">{v.placa}</div>'
                f'<div style="font-size:11px;color:#64748b;margin-top:2px">{v.marca} {v.modelo} · {v.año}</div>'
                f'<div style="margin-top:6px">{est}</div>{tec}</div></div>'
            )


# ─── Perfil ──────────────────────────────────────────────────────────────────

def _vw_perfil(cli,db):
    _ph('Mi Perfil','Información de su cuenta')
    with ui.element('div').style('display:grid;grid-template-columns:1fr 1fr;gap:20px'):
        with ui.element('div').classes('pc').style('margin-bottom:0'):
            ui.html('<div style="font-size:13px;font-weight:700;color:#0f172a;margin-bottom:14px;padding-bottom:8px;border-bottom:1px solid #e2e8f0">Datos Personales</div>')
            for l,v in [('DNI / RUC',cli.id),('Nombre',cli.nombre),('Apellidos',cli.apellidos or '—'),
                        ('Tipo',cli.tipo or 'Persona'),('Email',cli.email or '—'),
                        ('Teléfono',cli.telefono or '—'),('Ciudad',cli.ciudad or '—')]:
                ui.html(f'<div style="display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid #f1f5f9">'
                        f'<span style="font-size:12px;color:#94a3b8">{l}</span>'
                        f'<span style="font-size:13px;font-weight:600;color:#0f172a">{v}</span></div>')
        with ui.element('div').classes('pc').style('margin-bottom:0'):
            ui.html('<div style="font-size:13px;font-weight:700;color:#0f172a;margin-bottom:14px;padding-bottom:8px;border-bottom:1px solid #e2e8f0">Cambiar Contraseña</div>')
            ui.html('<p style="font-size:12px;color:#64748b;margin-bottom:12px">Su contraseña inicial es su DNI o RUC.</p>')
            np_in=ui.input('Nueva contraseña',password=True,password_toggle_button=True).props('outlined dense').classes('w-full')
            cp_in=ui.input('Confirmar',password=True).props('outlined dense').classes('w-full mt-2')
            msg=ui.label('').classes('text-xs mt-1')
            def _cambiar():
                np=(np_in.value or '').strip(); cp=(cp_in.value or '').strip()
                if len(np)<4: msg.text='Mínimo 4 caracteres';msg.style('color:#ef4444');return
                if np!=cp:   msg.text='No coinciden';msg.style('color:#ef4444');return
                try:
                    from utils.models import hash_password
                    db2=get_db(); c2=db2.query(Cliente).filter_by(id=cli.id).first()
                    if c2: c2.pin_acceso=hash_password(np); db2.commit()
                    db2.close()
                    msg.text='✓ Contraseña actualizada'; msg.style('color:#16a34a')
                    np_in.value=''; cp_in.value=''
                except Exception as e:
                    msg.text=f'Error: {e}'; msg.style('color:#ef4444')
            ui.button('Actualizar contraseña',on_click=_cambiar).props('flat').classes('text-blue-600 text-xs mt-3')


# ─── Detalle ─────────────────────────────────────────────────────────────────

def _vw_detalle(_view,ords,vehs,refresh):
    orden=next((o for o in ords if o.consecutivo==_view.get('d')),None)
    def _back(): _view['v']='dashboard';_view['d']=None;refresh()
    with ui.element('div').classes('pb2').on('click',_back):
        ui.html('← Volver')
    if not orden:
        ui.html('<p style="color:#94a3b8">Orden no encontrada</p>'); return
    t=_total(orden)
    _ph(f'Orden {orden.consecutivo}',orden.fecha)
    with ui.element('div').classes('pc'):
        ui.html(_fases_html(orden.estado))
    with ui.element('div').style('display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:20px'):
        with ui.element('div').style('background:#f8fafc;border:1px solid #f1f5f9;border-radius:10px;padding:14px'):
            ui.html('<div style="font-size:9.5px;font-weight:700;color:#94a3b8;letter-spacing:.8px;text-transform:uppercase;margin-bottom:8px">Datos del Servicio</div>')
            ui.html(f'<div style="font-size:13px;color:#334155;line-height:1.8">'
                    f'<b>Motivo:</b> {orden.motivo or "—"}<br>'
                    f'<b>Diagnóstico:</b> {orden.diagnostico or "—"}<br>'
                    f'<b>Técnico:</b> {orden.tecnico or "—"}<br>'
                    f'<b>Km:</b> {orden.km or "—"}</div>')
        veh=next((v for v in vehs if v.placa==orden.vehiculo_placa),None)
        with ui.element('div').style('background:#f8fafc;border:1px solid #f1f5f9;border-radius:10px;padding:14px'):
            ui.html('<div style="font-size:9.5px;font-weight:700;color:#94a3b8;letter-spacing:.8px;text-transform:uppercase;margin-bottom:8px">Vehículo</div>')
            if veh:
                ui.html(f'<div style="font-size:13px;color:#334155;line-height:1.8">'
                        f'<b>Placa:</b> {veh.placa}<br><b>Marca:</b> {veh.marca} {veh.modelo}<br>'
                        f'<b>Año:</b> {veh.año}<br><b>Color:</b> {veh.color}</div>')
    items=orden.items_cotizacion or []
    if items:
        with ui.element('div').classes('pc'):
            ui.html('<div style="font-size:14px;font-weight:700;color:#0f172a;margin-bottom:14px">Cotización / Ítems</div>')
            for it in items:
                nom=it.get('nombre') or it.get('descripcion','—'); sub=it.get('subtotal',0); cant=it.get('cantidad',1)
                ui.html(f'<div style="display:flex;justify-content:space-between;font-size:12px;'
                        f'padding:4px 0;border-bottom:1px solid #f1f5f9">'
                        f'<span>{nom} × {cant}</span>'
                        f'<span style="font-weight:600;color:#0f172a">S/ {float(sub):,.2f}</span></div>')
            ui.html(f'<div style="display:flex;justify-content:space-between;padding:10px 0 0;'
                    f'border-top:2px solid #e2e8f0;margin-top:4px;font-size:13px;font-weight:700">'
                    f'<span>Total</span><span style="color:#2563eb">S/ {t:,.2f}</span></div>')
    if orden.observaciones:
        with ui.element('div').classes('pc'):
            ui.html('<div style="font-size:14px;font-weight:700;color:#0f172a;margin-bottom:10px">Observaciones</div>')
            ui.html(f'<p style="font-size:13px;color:#334155;line-height:1.7">{orden.observaciones}</p>')
    fotos=orden.fotos_evidencia or []
    if fotos:
        with ui.element('div').classes('pc'):
            ui.html('<div style="font-size:14px;font-weight:700;color:#0f172a;margin-bottom:10px">Fotos de Evidencia</div>')
            with ui.element('div').style('display:flex;gap:8px;flex-wrap:wrap'):
                for fu in fotos[:12]:
                    ui.html(f'<img src="{fu}" style="width:80px;height:80px;border-radius:8px;object-fit:cover;border:1px solid #e2e8f0">')

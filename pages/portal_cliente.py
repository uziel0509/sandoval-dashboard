"""
SANDOVAL - Portal del Cliente v10.0
Estrategia: HTML puro inyectado con ui.add_body_html().
Sin NiceGUI components para evitar conflictos con Quasar/CSS.
"""

import unicodedata
from datetime import datetime
from nicegui import ui
from utils.models import get_db, Cliente, Vehiculo, Orden, Cita
from utils.auth import get_current_user

# ─── helpers ─────────────────────────────────────────────────────────────────

def _n(t): return unicodedata.normalize('NFD', str(t or '')).encode('ascii','ignore').decode().lower()

def _esc(s): return str(s or '').replace('&','&amp;').replace('<','&lt;').replace('>','&gt;').replace('"','&quot;')

def _fase_idx(estado):
    e = _n(estado)
    if 'recep' in e:                   return 0
    if 'diagn' in e:                   return 1
    if 'cotiz' in e or 'aprob' in e:   return 2
    if 'repar' in e or 'taller' in e:  return 3
    if 'lista' in e or 'listo' in e:   return 4
    return 5

FASES = [('Recep.','✓'),('Diagn.','✓'),('Cotiz.','✓'),('Repar.','⚙'),('Listo','✓'),('Entrega','✓')]

def _badge_style(estado):
    e = _n(estado)
    if 'recep' in e:              return 'background:#f1f5f9;color:#475569'
    if 'diagn' in e:              return 'background:#f5f3ff;color:#6b21a8'
    if 'repar' in e or 'taller' in e: return 'background:#fef3c7;color:#92400e'
    if 'lista' in e or 'listo' in e:  return 'background:#dbeafe;color:#1e40af'
    if 'entreg' in e or 'archiv' in e: return 'background:#dcfce7;color:#166534'
    return 'background:#f1f5f9;color:#475569'

def _total(o):
    try: return sum(float(i.get('subtotal',0)) for i in (o.items_cotizacion or []))
    except: return 0.0

MESES = ['Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic']

# ─── CSS (copia exacta del boceto) ───────────────────────────────────────────

PORTAL_CSS = """
*{box-sizing:border-box;margin:0;padding:0}
body,html{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','Inter',sans-serif;background:#f0f4f8;color:#1e293b;font-size:14px}
:root{--blue:#2563eb;--blue-light:#eff6ff;--blue-mid:#bfdbfe;--green:#16a34a;--amber:#d97706;--border:#e2e8f0;--text:#1e293b;--text2:#64748b;--text3:#94a3b8;--sidebar-w:240px;--topbar-h:64px}
/* OCULTAR todo lo de NiceGUI */
.q-header,.q-drawer,.q-footer,.q-layout-padding,.q-page-sticky{display:none!important}
.q-layout,.q-page-container,.q-page{background:#f0f4f8!important;padding:0!important;min-height:0!important}
.nicegui-content{display:none!important}
#portal-root{display:block!important}
/* TOPBAR */
.topbar{position:fixed;top:0;left:0;right:0;height:var(--topbar-h);background:#fff;border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between;padding:0 24px 0 0;z-index:100;box-shadow:0 1px 3px rgba(0,0,0,.06)}
.topbar-left{display:flex;align-items:center;gap:12px;width:var(--sidebar-w);height:100%;padding:0 20px;border-right:1px solid var(--border);flex-shrink:0}
.logo-box{width:36px;height:36px;background:var(--blue);border-radius:10px;display:flex;align-items:center;justify-content:center;font-weight:800;font-size:16px;color:#fff;flex-shrink:0;box-shadow:0 2px 8px rgba(37,99,235,.35)}
.brand-name{font-size:14px;font-weight:700;color:#0f172a}
.brand-sub{font-size:11px;color:var(--text2);margin-top:1px}
.topbar-right{display:flex;align-items:center;gap:10px}
.user-chip{display:flex;align-items:center;gap:9px;padding:6px 14px 6px 8px;border-radius:24px;background:#f8fafc;border:1px solid var(--border);cursor:default}
.user-avatar{width:30px;height:30px;border-radius:50%;background:var(--blue);display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:700;color:#fff;flex-shrink:0}
.user-info-name{font-size:12px;font-weight:600;color:#0f172a}
.user-info-role{font-size:10px;color:var(--text2);margin-top:1px}
.logout-btn{padding:7px 14px;border-radius:8px;background:#fff;border:1px solid var(--border);font-size:12px;color:var(--text2);cursor:pointer;font-weight:500;transition:.15s}
.logout-btn:hover{color:#0f172a;border-color:#94a3b8}
/* LAYOUT */
.layout{display:flex;margin-top:var(--topbar-h);min-height:calc(100vh - var(--topbar-h))}
/* SIDEBAR */
.sidebar{width:var(--sidebar-w);flex-shrink:0;background:#fff;border-right:1px solid var(--border);position:fixed;top:var(--topbar-h);bottom:0;padding:16px 0 24px;overflow-y:auto}
.sb-section{font-size:9.5px;font-weight:700;color:var(--text3);letter-spacing:1.2px;text-transform:uppercase;padding:0 20px;margin:20px 0 6px}
.sb-section:first-child{margin-top:4px}
.nav-item{display:flex;align-items:center;gap:10px;padding:9px 16px 9px 20px;cursor:pointer;transition:.12s;border-left:2.5px solid transparent;margin:1px 0}
.nav-item:hover{background:#f8fafc}
.nav-item.active{background:var(--blue-light);border-left-color:var(--blue)}
.nav-icon{width:18px;height:18px;flex-shrink:0;color:var(--text3)}
.nav-item.active .nav-icon{color:var(--blue)}
.nav-label{font-size:13px;font-weight:500;color:var(--text2);flex:1}
.nav-item.active .nav-label{color:var(--blue);font-weight:600}
.nav-item:hover .nav-label{color:var(--text)}
.nav-badge{margin-left:auto;background:var(--blue-light);color:var(--blue);font-size:9.5px;font-weight:700;padding:2px 7px;border-radius:10px}
.nav-badge.red{background:#fef2f2;color:#dc2626}
/* EMPRESA card en sidebar */
.sb-empresa{margin:0 12px 16px;padding:12px 14px;background:linear-gradient(135deg,#eff6ff,#f0f9ff);border:1px solid var(--blue-mid);border-radius:10px}
.sb-emp-label{font-size:9px;font-weight:700;color:var(--blue);text-transform:uppercase;letter-spacing:1px;margin-bottom:5px}
.sb-emp-name{font-size:13px;font-weight:700;color:#0f172a}
.sb-emp-ruc{font-size:11px;color:var(--text2);margin-top:2px}
.sb-emp-fleet{margin-top:8px;display:flex;gap:16px}
.sb-emp-stat{text-align:center}
.sb-emp-stat-num{font-size:18px;font-weight:700;color:var(--blue);line-height:1}
.sb-emp-stat-lbl{font-size:9px;color:var(--text2);margin-top:2px}
/* MAIN */
.main{margin-left:var(--sidebar-w);flex:1;padding:28px 32px;min-width:0}
/* PAGE HEADER */
.page-header{margin-bottom:24px}
.page-header h1{font-size:22px;font-weight:700;color:#0f172a;letter-spacing:-.4px}
.page-header p{font-size:13px;color:var(--text2);margin-top:4px}
/* KPI GRID */
.kpi-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:28px}
.kpi{background:#fff;border:1px solid var(--border);border-radius:14px;padding:18px 18px 16px;position:relative;overflow:hidden;transition:.2s;cursor:default}
.kpi:hover{box-shadow:0 4px 16px rgba(0,0,0,.07);transform:translateY(-1px)}
.kpi::after{content:'';position:absolute;top:0;left:0;right:0;height:3px;border-radius:14px 14px 0 0}
.kpi.k1::after{background:linear-gradient(90deg,#2563eb,#60a5fa)}
.kpi.k2::after{background:linear-gradient(90deg,#16a34a,#4ade80)}
.kpi.k3::after{background:linear-gradient(90deg,#d97706,#fbbf24)}
.kpi.k4::after{background:linear-gradient(90deg,#7c3aed,#c084fc)}
.kpi-top{display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:12px}
.kpi-icon{width:40px;height:40px;border-radius:10px;display:flex;align-items:center;justify-content:center}
.k1 .kpi-icon{background:#eff6ff} .k2 .kpi-icon{background:#f0fdf4}
.k3 .kpi-icon{background:#fffbeb} .k4 .kpi-icon{background:#f5f3ff}
.kpi-tag{font-size:10px;font-weight:600;padding:3px 8px;border-radius:20px}
.kpi-tag.up{background:#dcfce7;color:#16a34a}
.kpi-tag.neu{background:#f8fafc;color:var(--text2)}
.kpi-tag.warn{background:#fef3c7;color:#92400e}
.kpi-num{font-size:26px;font-weight:700;color:#0f172a;line-height:1;letter-spacing:-.5px}
.kpi-lbl{font-size:12px;color:var(--text2);margin-top:4px}
/* GRID 2 */
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:24px}
.grid-left,.grid-right{display:flex;flex-direction:column;gap:20px}
/* CARD */
.card{background:#fff;border:1px solid var(--border);border-radius:14px;padding:20px}
/* SECTION HEADER */
.sec-hd{display:flex;align-items:center;justify-content:space-between;margin-bottom:14px}
.sec-title{font-size:14px;font-weight:700;color:#0f172a}
.sec-link{font-size:12px;color:var(--blue);font-weight:600;cursor:pointer}
.sec-link:hover{text-decoration:underline}
/* ORDEN ACTIVA */
.orden-card{background:#fff;border:1px solid var(--border);border-radius:14px;padding:20px;margin-bottom:20px;border-left:4px solid var(--blue)}
.orden-top{display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:16px}
.orden-num{font-size:11px;color:var(--text2);margin-bottom:4px;font-weight:500}
.orden-title{font-size:15px;font-weight:700;color:#0f172a;margin-bottom:6px}
.orden-meta{display:flex;gap:16px;flex-wrap:wrap}
.orden-meta-item{font-size:12px;color:var(--text2);display:flex;align-items:center;gap:4px}
.orden-badge{font-size:11px;font-weight:600;padding:4px 12px;border-radius:20px}
.resp-chip{display:inline-flex;align-items:center;gap:6px;background:#f8fafc;border:1px solid var(--border);border-radius:20px;padding:4px 10px;font-size:11px;font-weight:500;color:var(--text);margin-top:8px}
.resp-dot{width:6px;height:6px;border-radius:50%;background:#22c55e;flex-shrink:0}
/* TIMELINE FASES */
.phases{display:flex;gap:0;position:relative;margin:20px 0;padding:0 4px}
.phases::before{content:'';position:absolute;top:15px;left:20px;right:20px;height:2px;background:#e2e8f0;z-index:0}
.phases-prog{position:absolute;top:15px;left:20px;height:2px;background:var(--blue);z-index:1;transition:width .5s}
.ph{flex:1;display:flex;flex-direction:column;align-items:center;gap:6px;position:relative;z-index:2}
.ph-circle{width:30px;height:30px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:700;border:2px solid #e2e8f0;background:#fff;transition:.2s}
.ph.done .ph-circle{background:var(--blue);border-color:var(--blue);color:#fff}
.ph.active .ph-circle{background:#fff;border-color:var(--blue);color:var(--blue);box-shadow:0 0 0 4px #dbeafe}
.ph.pending .ph-circle{background:#f8fafc;color:var(--text3);border-color:#e2e8f0}
.ph-lbl{font-size:9.5px;color:var(--text3);text-align:center;font-weight:500;white-space:nowrap}
.ph.done .ph-lbl{color:var(--blue);font-weight:600}
.ph.active .ph-lbl{color:var(--blue);font-weight:700}
/* DETAIL BOX */
.detail-2col{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin:16px 0}
.detail-box{background:#f8fafc;border:1px solid #f1f5f9;border-radius:10px;padding:14px}
.detail-box-lbl{font-size:9.5px;font-weight:700;color:var(--text3);letter-spacing:.8px;text-transform:uppercase;margin-bottom:8px}
.detail-box-txt{font-size:13px;color:#334155;line-height:1.65}
.item-row{display:flex;justify-content:space-between;font-size:12px;padding:4px 0;border-bottom:1px solid #f1f5f9}
.item-row:last-child{border-bottom:none}
.item-row span:last-child{font-weight:600;color:#0f172a}
.item-total{display:flex;justify-content:space-between;padding:10px 0 0;border-top:2px solid var(--border);margin-top:4px;font-size:13px;font-weight:700}
.item-total span:last-child{color:var(--blue)}
/* FLEET TABLE */
.fleet-table{width:100%;border-collapse:collapse}
.fleet-table thead th{font-size:10px;font-weight:700;color:var(--text3);letter-spacing:.8px;text-transform:uppercase;padding:10px 14px;background:#f8fafc;border-bottom:1px solid var(--border);text-align:left}
.fleet-row{cursor:pointer;transition:.12s}
.fleet-row:hover td{background:#fafbff}
.fleet-row td{padding:12px 14px;border-bottom:1px solid #f1f5f9;vertical-align:middle}
.fleet-row:last-child td{border-bottom:none}
.fleet-placa{font-size:13px;font-weight:700;color:#0f172a;background:#f1f5f9;display:inline-block;padding:3px 9px;border-radius:6px;letter-spacing:.5px}
.fleet-model{font-size:12px;color:var(--text2);margin-top:2px}
.fleet-bar-wrap{height:4px;background:#f1f5f9;border-radius:2px;width:80px;overflow:hidden}
.fleet-bar{height:100%;border-radius:2px}
.fleet-phase{font-size:10px;color:var(--text2);margin-top:3px}
/* HIST TABLE */
.hist-table{width:100%;border-collapse:collapse}
.hist-table thead th{font-size:10px;font-weight:700;color:var(--text3);letter-spacing:.8px;text-transform:uppercase;padding:10px 14px;background:#f8fafc;border-bottom:1px solid var(--border);text-align:left}
.hist-row{cursor:pointer;transition:.12s}
.hist-row:hover td{background:#fafbff}
.hist-row td{padding:11px 14px;border-bottom:1px solid #f1f5f9;vertical-align:middle}
.hist-row:last-child td{border-bottom:none}
/* STATUS BADGE */
.status-badge{font-size:11px;font-weight:600;padding:3px 10px;border-radius:20px;display:inline-block}
/* CITA */
.cita-item{display:flex;align-items:center;gap:14px;padding:14px 16px;border-bottom:1px solid #f1f5f9}
.cita-item:last-child{border-bottom:none}
.cita-date-box{min-width:46px;height:52px;background:var(--blue-light);border-radius:10px;display:flex;flex-direction:column;align-items:center;justify-content:center;flex-shrink:0}
.cita-day{font-size:20px;font-weight:800;color:var(--blue);line-height:1}
.cita-mon{font-size:9px;font-weight:700;color:var(--blue);text-transform:uppercase;letter-spacing:.5px}
.cita-info-title{font-size:13px;font-weight:600;color:#0f172a}
.cita-info-sub{font-size:12px;color:var(--text2);margin-top:2px}
.cita-tag{margin-left:auto;font-size:10px;font-weight:600;padding:3px 9px;border-radius:20px;background:#dcfce7;color:#166534;white-space:nowrap;flex-shrink:0}
.cita-tag.pend{background:#fef3c7;color:#92400e}
/* VIEWS */
.view{display:none}
.view.active{display:block}
/* EMPTY */
.empty{text-align:center;padding:40px 20px;color:var(--text3);font-size:13px}
/* TABS */
.tabs{display:flex;gap:4px;background:#f1f5f9;border-radius:10px;padding:4px;margin-bottom:20px;width:fit-content}
.tab{font-size:12px;font-weight:500;padding:7px 18px;border-radius:7px;cursor:pointer;color:var(--text2);transition:.15s;border:none;background:transparent}
.tab.on{background:#fff;color:var(--blue);font-weight:700;box-shadow:0 1px 3px rgba(0,0,0,.08)}
"""

# ─── SVG Icons ────────────────────────────────────────────────────────────────

SVG_DASH   = '<svg class="nav-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>'
SVG_CAR    = '<svg class="nav-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path d="M5 17H3a2 2 0 01-2-2V5a2 2 0 012-2h11l5 5v5"/><circle cx="16" cy="17" r="2"/><circle cx="7" cy="17" r="2"/></svg>'
SVG_HIST   = '<svg class="nav-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"/></svg>'
SVG_ORD    = '<svg class="nav-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg>'
SVG_CAL    = '<svg class="nav-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/></svg>'
SVG_BLDG   = '<svg class="nav-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path d="M3 9l9-7 9 7v11a2 2 0 01-2 2H5a2 2 0 01-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>'
SVG_USER   = '<svg class="nav-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><circle cx="12" cy="8" r="4"/><path d="M4 20c0-4 3.6-7 8-7s8 3 8 7"/></svg>'

# ─── Build functions ──────────────────────────────────────────────────────────

def _phases_html(estado):
    fi = _fase_idx(estado)
    pct = int(fi / (len(FASES)-1) * 100) if fi > 0 else 0
    html = f'<div class="phases"><div class="phases-prog" style="width:{pct}%"></div>'
    for i, (lbl, icon) in enumerate(FASES):
        if i < fi:
            cls = 'done'; txt = '✓'
        elif i == fi:
            cls = 'active'; txt = icon
        else:
            cls = 'pending'; txt = str(i+1)
        html += f'<div class="ph {cls}"><div class="ph-circle">{txt}</div><div class="ph-lbl">{lbl}</div></div>'
    html += '</div>'
    return html

def _badge(estado):
    st = _badge_style(estado)
    return f'<span class="status-badge" style="{st}">{_esc(estado)}</span>'

def _nav_item(view_id, svg, label, active_view, badge=None, badge_red=False):
    cls = 'active' if active_view == view_id else ''
    b = f'<span class="nav-badge{"  red" if badge_red else ""}">{badge}</span>' if badge else ''
    return f'<div class="nav-item {cls}" onclick="showView(\'{view_id}\')">{svg}<span class="nav-label">{label}</span>{b}</div>'

def _sb_section(label):
    return f'<div class="sb-section">{label}</div>'

def _fleet_bar_color(estado):
    e = _n(estado)
    if 'entreg' in e or 'archiv' in e: return '#16a34a'
    if 'lista' in e or 'listo' in e:   return '#2563eb'
    if 'repar' in e or 'taller' in e:  return '#d97706'
    if 'diagn' in e:                   return '#a855f7'
    return '#94a3b8'

def _fleet_bar_pct(estado):
    e = _n(estado)
    if 'recep' in e:  return 10
    if 'diagn' in e:  return 28
    if 'cotiz' in e:  return 42
    if 'repar' in e or 'taller' in e: return 57
    if 'lista' in e or 'listo' in e:  return 85
    if 'entreg' in e or 'archiv' in e: return 100
    return 5

# ─── View builders ────────────────────────────────────────────────────────────

def _vw_dashboard(cli, vehs, ords, ord_act, citas_fut, es_empresa):
    nombre = cli.nombre if es_empresa else f"{cli.nombre} {cli.apellidos or ''}".strip()
    mes = MESES[datetime.now().month - 1]
    en_taller = sum(1 for o in ord_act if _n(o.estado) not in ('listo','lista','entregado','archivado'))
    listos    = sum(1 for o in ord_act if _n(o.estado)     in ('listo','lista'))
    completados = len([o for o in ords if _n(o.estado) in ('entregado','archivado')])
    inversion = sum(_total(o) for o in ords if _n(o.estado) in ('entregado','archivado'))

    # KPIs
    kpis = f'''
<div class="kpi-grid">
  <div class="kpi k1">
    <div class="kpi-top">
      <div class="kpi-icon"><svg width="20" height="20" fill="none" viewBox="0 0 24 24" stroke="#2563eb" stroke-width="2"><path d="M5 17H3a2 2 0 01-2-2V5a2 2 0 012-2h11l5 5v5"/><circle cx="16" cy="17" r="2"/><circle cx="7" cy="17" r="2"/></svg></div>
      <span class="kpi-tag neu">Total</span>
    </div>
    <div class="kpi-num">{len(vehs)}</div>
    <div class="kpi-lbl">Vehículos registrados</div>
  </div>
  <div class="kpi k2">
    <div class="kpi-top">
      <div class="kpi-icon"><svg width="20" height="20" fill="none" viewBox="0 0 24 24" stroke="#16a34a" stroke-width="2"><path d="M14.7 6.3a1 1 0 000 1.4l1.6 1.6a1 1 0 001.4 0l3.77-3.77a6 6 0 01-7.94 7.94l-6.91 6.91a2.12 2.12 0 01-3-3l6.91-6.91a6 6 0 017.94-7.94l-3.76 3.76z"/></svg></div>
      <span class="kpi-tag up">Activos</span>
    </div>
    <div class="kpi-num">{en_taller}</div>
    <div class="kpi-lbl">En taller ahora</div>
  </div>
  <div class="kpi k3">
    <div class="kpi-top">
      <div class="kpi-icon"><svg width="20" height="20" fill="none" viewBox="0 0 24 24" stroke="#d97706" stroke-width="2"><path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/></svg></div>
      <span class="kpi-tag warn">Hoy</span>
    </div>
    <div class="kpi-num">{listos}</div>
    <div class="kpi-lbl">Listo para recoger</div>
  </div>
  <div class="kpi k4">
    <div class="kpi-top">
      <div class="kpi-icon"><svg width="20" height="20" fill="none" viewBox="0 0 24 24" stroke="#7c3aed" stroke-width="2"><path d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg></div>
      <span class="kpi-tag neu">{mes}</span>
    </div>
    <div class="kpi-num">S/ {inversion:,.0f}</div>
    <div class="kpi-lbl">Inversión total</div>
  </div>
</div>'''

    # Fleet table (top 4)
    fleet_rows = ''
    for v in vehs[:4]:
        ord_v = next((o for o in ord_act if o.vehiculo_placa == v.placa), None)
        estado = ord_v.estado if ord_v else 'Sin orden'
        pct = _fleet_bar_pct(estado)
        col = _fleet_bar_color(estado)
        modelo = f"{v.marca or ''} {v.modelo or ''} {v.anio or ''}".strip()
        fleet_rows += f'''<tr class="fleet-row">
  <td><div class="fleet-placa">{_esc(v.placa)}</div><div class="fleet-model">{_esc(modelo)}</div></td>
  <td><div class="fleet-bar-wrap"><div class="fleet-bar" style="width:{pct}%;background:{col}"></div></div><div class="fleet-phase">{_esc(estado)}</div></td>
  <td style="text-align:center">{_badge(estado)}</td>
</tr>'''

    fleet_card = f'''<div class="card">
  <div class="sec-hd"><span class="sec-title">Estado de flota</span><span class="sec-link" onclick="showView('flota')">Ver todas →</span></div>
  <table class="fleet-table">
    <thead><tr><th>Vehículo</th><th>Progreso</th><th style="text-align:center">Estado</th></tr></thead>
    <tbody>{fleet_rows if fleet_rows else '<tr><td colspan="3" class="empty">Sin vehículos registrados</td></tr>'}</tbody>
  </table>
</div>'''

    # Last orders
    hist_rows = ''
    ord_hist = [o for o in ords if _n(o.estado) in ('entregado','archivado')]
    for o in ord_hist[:4]:
        total = _total(o)
        hist_rows += f'''<tr class="hist-row">
  <td style="font-size:12px;font-weight:600;color:#334155">{_esc(o.numero_orden or '')}</td>
  <td><div style="font-size:13px;font-weight:500;color:#0f172a">{_esc((o.descripcion or '')[:50])}</div>
      <div style="font-size:11px;color:#64748b;margin-top:1px">{_esc(o.vehiculo_placa or '')} · {_esc(str(o.fecha)[:10] if o.fecha else '')}</div></td>
  <td style="font-size:13px;font-weight:700;color:#0f172a">S/ {total:,.0f}</td>
  <td>{_badge(o.estado)}</td>
</tr>'''

    hist_card = f'''<div class="card">
  <div class="sec-hd"><span class="sec-title">Últimas órdenes</span><span class="sec-link" onclick="showView('historial')">Ver historial →</span></div>
  <table class="hist-table">
    <thead><tr><th>Orden</th><th>Descripción</th><th>Monto</th><th>Estado</th></tr></thead>
    <tbody>{hist_rows if hist_rows else '<tr><td colspan="4" class="empty">Sin historial</td></tr>'}</tbody>
  </table>
</div>'''

    # Active order (first one)
    order_card = ''
    if ord_act:
        o = ord_act[0]
        total = _total(o)
        items_html = ''
        for it in (o.items_cotizacion or [])[:5]:
            items_html += f'<div class="item-row"><span>{_esc(it.get("descripcion",""))}</span><span>S/ {float(it.get("subtotal",0)):,.0f}</span></div>'
        if items_html:
            items_html += f'<div class="item-total"><span>Total</span><span>S/ {total:,.0f}</span></div>'
        else:
            items_html = '<div style="font-size:12px;color:#94a3b8">Sin cotización</div>'

        diag = _esc((o.diagnostico or '')[:120])
        order_card = f'''<div>
  <div class="sec-hd"><span class="sec-title">Orden activa — {_esc(o.vehiculo_placa or '')}</span></div>
  <div class="orden-card">
    <div class="orden-top">
      <div>
        <div class="orden-num">{_esc(o.numero_orden or '')}</div>
        <div class="orden-title">{_esc((o.descripcion or '')[:80])}</div>
        <div class="orden-meta">
          <div class="orden-meta-item">📅 {_esc(str(o.fecha)[:10] if o.fecha else '')}</div>
          <div class="orden-meta-item">🔧 {_esc(o.tecnico or 'Sin asignar')}</div>
        </div>
        <div class="resp-chip"><div class="resp-dot"></div>{_esc(o.tecnico or 'Sin asignar')}</div>
      </div>
      <span class="orden-badge" style="{_badge_style(o.estado)}">{_esc(o.estado)}</span>
    </div>
    {_phases_html(o.estado)}
    <div class="detail-2col">
      <div class="detail-box">
        <div class="detail-box-lbl">Diagnóstico</div>
        <div class="detail-box-txt">{diag if diag else 'Sin diagnóstico registrado.'}</div>
      </div>
      <div class="detail-box">
        <div class="detail-box-lbl">Repuestos y servicios</div>
        {items_html}
      </div>
    </div>
  </div>
</div>'''
    else:
        order_card = '<div class="card"><div class="empty">No hay órdenes activas en este momento.</div></div>'

    # Citas
    citas_html = ''
    for c in citas_fut[:3]:
        try:
            fd = datetime.strptime(str(c.fecha_cita)[:10], '%Y-%m-%d')
            day = fd.strftime('%d'); mon = MESES[fd.month-1]
        except:
            day = '--'; mon = '---'
        conf = 'pend' if _n(c.estado or '') in ('pendiente','pend') else ''
        tag_txt = 'Pendiente' if conf else 'Confirmada'
        placa = getattr(c, 'vehiculo_placa', '') or ''
        hora  = str(c.hora or '')[:5] if hasattr(c,'hora') and c.hora else ''
        citas_html += f'''<div class="cita-item">
  <div class="cita-date-box"><div class="cita-day">{day}</div><div class="cita-mon">{mon}</div></div>
  <div><div class="cita-info-title">{_esc(c.descripcion or 'Cita programada')}</div>
    <div class="cita-info-sub">{hora}{' · ' if hora else ''}{_esc(placa)}</div></div>
  <span class="cita-tag {conf}">{tag_txt}</span>
</div>'''

    citas_card = f'''<div class="card">
  <div class="sec-hd"><span class="sec-title">Próximas citas</span><span class="sec-link" onclick="showView('citas')">Ver todas →</span></div>
  {citas_html if citas_html else '<div class="empty">Sin citas programadas</div>'}
</div>'''

    return f'''<div class="page-header"><h1>Dashboard</h1>
<p>Bienvenido, {_esc(nombre)} — Resumen de su cuenta · {datetime.now().strftime("%d/%m/%Y")}</p>
</div>
{kpis}
<div class="grid2">
  <div class="grid-left">{fleet_card}{hist_card}</div>
  <div class="grid-right">{order_card}{citas_card}</div>
</div>'''


def _vw_flota(vehs, ord_act):
    rows = ''
    for v in vehs:
        ord_v = next((o for o in ord_act if o.vehiculo_placa == v.placa), None)
        estado = ord_v.estado if ord_v else 'Sin orden activa'
        pct = _fleet_bar_pct(estado)
        col = _fleet_bar_color(estado)
        modelo = f"{v.marca or ''} {v.modelo or ''} {v.anio or ''}".strip()
        rows += f'''<tr class="fleet-row">
  <td><div class="fleet-placa">{_esc(v.placa)}</div><div class="fleet-model">{_esc(modelo)}</div></td>
  <td><div class="fleet-bar-wrap"><div class="fleet-bar" style="width:{pct}%;background:{col}"></div></div><div class="fleet-phase">{_esc(estado)}</div></td>
  <td style="text-align:center">{_badge(estado)}</td>
</tr>'''
    return f'''<div class="page-header"><h1>Mi Flota</h1><p>{len(vehs)} vehículos registrados</p></div>
<div class="card">
  <table class="fleet-table">
    <thead><tr><th>Vehículo</th><th>Progreso</th><th style="text-align:center">Estado</th></tr></thead>
    <tbody>{rows if rows else '<tr><td colspan="3" class="empty">Sin vehículos</td></tr>'}</tbody>
  </table>
</div>'''


def _vw_ordenes(ord_act):
    if not ord_act:
        return '<div class="page-header"><h1>Órdenes Activas</h1></div><div class="card"><div class="empty">No hay órdenes activas.</div></div>'
    cards = ''
    for o in ord_act:
        total = _total(o)
        items_html = ''
        for it in (o.items_cotizacion or [])[:5]:
            items_html += f'<div class="item-row"><span>{_esc(it.get("descripcion",""))}</span><span>S/ {float(it.get("subtotal",0)):,.0f}</span></div>'
        if items_html:
            items_html += f'<div class="item-total"><span>Total</span><span>S/ {total:,.0f}</span></div>'
        else:
            items_html = '<div style="font-size:12px;color:#94a3b8">Sin cotización</div>'
        diag = _esc((o.diagnostico or '')[:200])
        cards += f'''<div class="orden-card">
  <div class="orden-top">
    <div>
      <div class="orden-num">{_esc(o.numero_orden or '')}</div>
      <div class="orden-title">{_esc((o.descripcion or '')[:80])}</div>
      <div class="orden-meta">
        <div class="orden-meta-item">🚗 {_esc(o.vehiculo_placa or '')}</div>
        <div class="orden-meta-item">📅 {_esc(str(o.fecha)[:10] if o.fecha else '')}</div>
        <div class="orden-meta-item">🔧 {_esc(o.tecnico or 'Sin asignar')}</div>
      </div>
    </div>
    <span class="orden-badge" style="{_badge_style(o.estado)}">{_esc(o.estado)}</span>
  </div>
  {_phases_html(o.estado)}
  <div class="detail-2col">
    <div class="detail-box"><div class="detail-box-lbl">Diagnóstico</div>
      <div class="detail-box-txt">{diag if diag else 'Sin diagnóstico.'}</div></div>
    <div class="detail-box"><div class="detail-box-lbl">Repuestos y servicios</div>{items_html}</div>
  </div>
</div>'''
    return f'<div class="page-header"><h1>Órdenes Activas</h1><p>{len(ord_act)} en proceso</p></div>{cards}'


def _vw_historial(ords):
    ord_hist = [o for o in ords if _n(o.estado) in ('entregado','archivado')]
    rows = ''
    for o in ord_hist:
        total = _total(o)
        rows += f'''<tr class="hist-row">
  <td style="font-size:12px;font-weight:600;color:#334155">{_esc(o.numero_orden or '')}</td>
  <td><div style="font-size:13px;font-weight:500;color:#0f172a">{_esc((o.descripcion or '')[:60])}</div>
      <div style="font-size:11px;color:#64748b;margin-top:1px">{_esc(o.vehiculo_placa or '')} · {_esc(str(o.fecha)[:10] if o.fecha else '')} · {_esc(o.tecnico or '')}</div></td>
  <td style="font-size:13px;font-weight:700;color:#0f172a">S/ {total:,.0f}</td>
  <td>{_badge(o.estado)}</td>
</tr>'''
    return f'''<div class="page-header"><h1>Historial de Servicios</h1><p>{len(ord_hist)} órdenes completadas</p></div>
<div class="card">
  <table class="hist-table">
    <thead><tr><th>Orden</th><th>Descripción</th><th>Monto</th><th>Estado</th></tr></thead>
    <tbody>{rows if rows else '<tr><td colspan="4" class="empty">Sin historial</td></tr>'}</tbody>
  </table>
</div>'''


def _vw_citas(citas_all):
    ahora = datetime.now().strftime('%Y-%m-%d')
    fut = [c for c in citas_all if str(c.fecha_cita or '')[:10] >= ahora]
    pas = [c for c in citas_all if str(c.fecha_cita or '')[:10] < ahora]
    def _cita_rows(lst):
        out = ''
        for c in lst:
            try:
                fd = datetime.strptime(str(c.fecha_cita)[:10],'%Y-%m-%d')
                day = fd.strftime('%d'); mon = MESES[fd.month-1]
            except:
                day='--'; mon='---'
            conf = 'pend' if _n(c.estado or '') in ('pendiente','pend') else ''
            tag_txt = 'Pendiente' if conf else 'Confirmada'
            placa = getattr(c,'vehiculo_placa','') or ''
            hora  = str(c.hora or '')[:5] if hasattr(c,'hora') and c.hora else ''
            out += f'''<div class="cita-item">
  <div class="cita-date-box"><div class="cita-day">{day}</div><div class="cita-mon">{mon}</div></div>
  <div style="flex:1"><div class="cita-info-title">{_esc(c.descripcion or 'Cita programada')}</div>
    <div class="cita-info-sub">{hora}{' · ' if hora else ''}{_esc(placa)}</div></div>
  <span class="cita-tag {conf}">{tag_txt}</span>
</div>'''
        return out or '<div class="empty">Sin citas</div>'
    return f'''<div class="page-header"><h1>Citas Programadas</h1><p>{len(fut)} próximas · {len(pas)} anteriores</p></div>
<div class="card" style="margin-bottom:20px">
  <div class="sec-hd"><span class="sec-title">Próximas citas</span></div>
  {_cita_rows(fut)}
</div>
<div class="card">
  <div class="sec-hd"><span class="sec-title">Citas anteriores</span></div>
  {_cita_rows(pas[:5])}
</div>'''


def _vw_empresa(cli, vehs, ords):
    nombre = cli.nombre or ''
    ruc    = cli.id or ''
    email  = getattr(cli,'email','') or ''
    tel    = getattr(cli,'telefono','') or ''
    completados = len([o for o in ords if _n(o.estado) in ('entregado','archivado')])
    inversion   = sum(_total(o) for o in ords if _n(o.estado) in ('entregado','archivado'))
    initials = ''.join(p[0].upper() for p in nombre.split()[:2]) or 'E'
    return f'''<div class="page-header"><h1>Mi Empresa</h1></div>
<div style="background:linear-gradient(135deg,#eff6ff,#f0f9ff);border:1px solid #bfdbfe;border-radius:14px;padding:24px;margin-bottom:20px;display:flex;align-items:center;gap:20px">
  <div style="width:64px;height:64px;background:#2563eb;border-radius:16px;display:flex;align-items:center;justify-content:center;font-size:24px;font-weight:800;color:#fff;flex-shrink:0;box-shadow:0 4px 12px rgba(37,99,235,.3)">{initials}</div>
  <div>
    <div style="font-size:20px;font-weight:800;color:#0f172a;letter-spacing:-.3px">{_esc(nombre)}</div>
    <div style="font-size:13px;color:#64748b;margin-top:3px">RUC {_esc(str(ruc))} · {_esc(email)} · {_esc(tel)}</div>
    <div style="display:flex;gap:12px;margin-top:12px">
      <div style="text-align:center;padding:10px 16px;background:#fff;border-radius:10px;border:1px solid #e2e8f0">
        <div style="font-size:20px;font-weight:800;color:#2563eb">{len(vehs)}</div>
        <div style="font-size:10px;color:#64748b;margin-top:2px">Vehículos</div>
      </div>
      <div style="text-align:center;padding:10px 16px;background:#fff;border-radius:10px;border:1px solid #e2e8f0">
        <div style="font-size:20px;font-weight:800;color:#2563eb">{completados}</div>
        <div style="font-size:10px;color:#64748b;margin-top:2px">Servicios</div>
      </div>
      <div style="text-align:center;padding:10px 16px;background:#fff;border-radius:10px;border:1px solid #e2e8f0">
        <div style="font-size:20px;font-weight:800;color:#2563eb">S/ {inversion:,.0f}</div>
        <div style="font-size:10px;color:#64748b;margin-top:2px">Inversión</div>
      </div>
    </div>
  </div>
</div>'''


# ─── Main entry ───────────────────────────────────────────────────────────────

def show_portal_page():
    user = get_current_user()
    if not user or user.get('rol') != 'cliente':
        ui.navigate.to('/login')
        return

    db = get_db()
    try:
        cli = db.query(Cliente).filter_by(id=user['id']).first()
        if not cli:
            ui.navigate.to('/login')
            return

        es_empresa  = (cli.tipo or 'Persona').lower() in ('empresa','corporativo','corporativa')
        vehs        = db.query(Vehiculo).filter_by(cliente_id=cli.id).all()
        placas      = [v.placa for v in vehs]
        ords        = (db.query(Orden).filter(Orden.vehiculo_placa.in_(placas))
                       .order_by(Orden.fecha.desc()).all()) if placas else []
        citas_all   = (db.query(Cita).filter_by(cliente_id=cli.id)
                       .order_by(Cita.fecha_cita).all())
        ahora       = datetime.now().strftime('%Y-%m-%d')
        citas_fut   = [c for c in citas_all if str(c.fecha_cita or '')[:10] >= ahora]
        ord_act     = [o for o in ords if _n(o.estado) not in ('archivado','entregado')]
        nombre_disp = cli.nombre if es_empresa else f"{cli.nombre} {cli.apellidos or ''}".strip()
        initials    = ''.join(p[0].upper() for p in nombre_disp.split()[:2]) or 'C'

        # ── Views HTML ────────────────────────────────────────────────────────
        v_dash    = _vw_dashboard(cli, vehs, ords, ord_act, citas_fut, es_empresa)
        v_flota   = _vw_flota(vehs, ord_act)
        v_ordenes = _vw_ordenes(ord_act)
        v_hist    = _vw_historial(ords)
        v_citas   = _vw_citas(citas_all)
        v_empresa = _vw_empresa(cli, vehs, ords) if es_empresa else ''

        # ── Sidebar empresa card ──────────────────────────────────────────────
        en_t = sum(1 for o in ord_act if _n(o.estado) not in ('listo','lista'))
        lst  = sum(1 for o in ord_act if _n(o.estado)     in ('listo','lista'))
        emp_card = ''
        if es_empresa:
            emp_card = f'''<div class="sb-empresa">
  <div class="sb-emp-label">Mi empresa</div>
  <div class="sb-emp-name">{_esc(cli.nombre)}</div>
  <div class="sb-emp-ruc">RUC {_esc(str(cli.id))}</div>
  <div class="sb-emp-fleet">
    <div class="sb-emp-stat"><div class="sb-emp-stat-num">{len(vehs)}</div><div class="sb-emp-stat-lbl">Vehículos</div></div>
    <div class="sb-emp-stat"><div class="sb-emp-stat-num" style="color:#d97706">{en_t}</div><div class="sb-emp-stat-lbl">En taller</div></div>
    <div class="sb-emp-stat"><div class="sb-emp-stat-num" style="color:#16a34a">{lst}</div><div class="sb-emp-stat-lbl">Listos</div></div>
  </div>
</div>'''

        badge_ord = f'<span class="nav-badge red">{len(ord_act)}</span>' if ord_act else ''
        badge_veh = f'<span class="nav-badge">{len(vehs)}</span>' if len(vehs) > 1 else ''
        empresa_nav = f'''
{_sb_section("Empresa")}
{SVG_BLDG.replace('class="nav-icon"','class="nav-icon"')}''' if es_empresa else ''
        empresa_view = '<div class="view" id="view-empresa">' + v_empresa + '</div>' if es_empresa else ''

        # Build empresa nav items manually
        emp_nav_html = ''
        if es_empresa:
            emp_nav_html = f'''
{_sb_section("Empresa")}
<div class="nav-item" onclick="showView('empresa')" id="nav-empresa">{SVG_BLDG}<span class="nav-label">Mi Empresa</span></div>'''

        full_html = f'''<div id="portal-root">
<style>{PORTAL_CSS}</style>

<!-- TOPBAR -->
<div class="topbar">
  <div class="topbar-left">
    <div class="logo-box">S</div>
    <div>
      <div class="brand-name">Mecánica Sandoval</div>
      <div class="brand-sub">Portal del Cliente</div>
    </div>
  </div>
  <div class="topbar-right">
    <div class="user-chip">
      <div class="user-avatar">{initials}</div>
      <div>
        <div class="user-info-name">{_esc(nombre_disp)}</div>
        <div class="user-info-role">{"Cliente Corporativo" if es_empresa else "Cliente"}</div>
      </div>
    </div>
    <button class="logout-btn" onclick="window.location.href='/portal-logout'">Cerrar sesión</button>
  </div>
</div>

<!-- LAYOUT -->
<div class="layout">
  <!-- SIDEBAR -->
  <nav class="sidebar">
    {emp_card}
    {_sb_section("Principal")}
    <div class="nav-item active" onclick="showView('dashboard')" id="nav-dashboard">{SVG_DASH}<span class="nav-label">Dashboard</span></div>
    <div class="nav-item" onclick="showView('flota')" id="nav-flota">{SVG_CAR}<span class="nav-label">Mi Flota</span>{badge_veh}</div>
    {_sb_section("Servicios")}
    <div class="nav-item" onclick="showView('ordenes')" id="nav-ordenes">{SVG_ORD}<span class="nav-label">Órdenes Activas</span>{badge_ord}</div>
    <div class="nav-item" onclick="showView('historial')" id="nav-historial">{SVG_HIST}<span class="nav-label">Historial</span></div>
    <div class="nav-item" onclick="showView('citas')" id="nav-citas">{SVG_CAL}<span class="nav-label">Citas</span></div>
    {emp_nav_html}
    {_sb_section("Cuenta")}
    <div class="nav-item" onclick="showView('perfil')" id="nav-perfil">{SVG_USER}<span class="nav-label">Mi Perfil</span></div>
  </nav>

  <!-- MAIN -->
  <main class="main">
    <div class="view active" id="view-dashboard">{v_dash}</div>
    <div class="view" id="view-flota">{v_flota}</div>
    <div class="view" id="view-ordenes">{v_ordenes}</div>
    <div class="view" id="view-historial">{v_hist}</div>
    <div class="view" id="view-citas">{v_citas}</div>
    {empresa_view}
    <div class="view" id="view-perfil">
      <div class="page-header"><h1>Mi Perfil</h1></div>
      <div class="card">
        <div style="font-size:14px;font-weight:600;color:#0f172a;margin-bottom:8px">{_esc(nombre_disp)}</div>
        <div style="font-size:13px;color:#64748b">{"RUC " + str(cli.id) if es_empresa else "DNI " + str(cli.id)}</div>
      </div>
    </div>
  </main>
</div>

<script>
function showView(name) {{
  document.querySelectorAll('.view').forEach(function(v){{v.classList.remove('active')}});
  document.querySelectorAll('.nav-item').forEach(function(n){{n.classList.remove('active')}});
  var el = document.getElementById('view-' + name);
  if (el) el.classList.add('active');
  var nav = document.getElementById('nav-' + name);
  if (nav) nav.classList.add('active');
}}
</script>
</div>'''

        ui.add_body_html(full_html)

    finally:
        db.close()


def show_portal(_container=None):
    """Fallback desde frame admin → redirige a ruta dedicada."""
    ui.navigate.to('/portal')

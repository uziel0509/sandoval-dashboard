"""
SANDOVAL - Portal del Cliente v11.0
HTML puro inyectado. Fases completas + evidencias + cotización + historial.
"""

import unicodedata, os
from datetime import datetime
from nicegui import ui
from utils.models import get_db, Cliente, Vehiculo, Orden, Cita
from utils.auth import get_current_user

# ─── helpers ─────────────────────────────────────────────────────────────────

def _n(t): return unicodedata.normalize('NFD', str(t or '')).encode('ascii','ignore').decode().lower()
def _esc(s): return str(s or '').replace('&','&amp;').replace('<','&lt;').replace('>','&gt;').replace('"','&quot;')

# 8 fases del sistema (igual que theme.py ESTADOS_CONFIG)
FASES = [
    ('RECEPCIÓN',  'Recep.',  0),
    ('DIAGNÓSTICO','Diagn.',  1),
    ('REPUESTOS',  'Reptos.', 2),
    ('APROBACIÓN', 'Aprobac.',3),
    ('REPARACIÓN', 'Repar.',  4),
    ('CONTROL',    'Control', 5),
    ('ENTREGA',    'Entrega', 6),
    ('ARCHIVADO',  'Archiv.', 7),
]

def _fase_idx(estado):
    e = _n(estado)
    if 'recep' in e:                            return 0
    if 'diagn' in e:                            return 1
    if 'repues' in e:                           return 2
    if 'aprob' in e:                            return 3
    if 'repar' in e or 'taller' in e:           return 4
    if 'control' in e or 'calidad' in e:        return 5
    if 'entreg' in e:                           return 6
    if 'archiv' in e:                           return 7
    return 0

def _badge_style(estado):
    e = _n(estado)
    if 'recep'  in e:                       return 'background:#f1f5f9;color:#475569'
    if 'diagn'  in e:                       return 'background:#ede9fe;color:#5b21b6'
    if 'repues' in e:                       return 'background:#dbeafe;color:#1e40af'
    if 'aprob'  in e:                       return 'background:#fef9c3;color:#854d0e'
    if 'repar'  in e or 'taller' in e:      return 'background:#fef3c7;color:#92400e'
    if 'control' in e or 'calidad' in e:    return 'background:#e0f2fe;color:#0369a1'
    if 'entreg' in e:                       return 'background:#dcfce7;color:#166534'
    if 'archiv' in e:                       return 'background:#f1f5f9;color:#64748b'
    return 'background:#f1f5f9;color:#475569'

def _badge(estado):
    st = _badge_style(estado)
    return f'<span class="status-badge" style="{st}">{_esc(estado)}</span>'

def _total(o):
    try:
        items = o.items_cotizacion or []
        # Buscar línea Total explícita
        for it in items:
            if isinstance(it, dict) and it.get('categoria') == 'Total':
                return float(it.get('total', it.get('precio_unitario', 0)))
        # Sumar todo excepto Resumen/Impuesto/Total
        return sum(float(i.get('total', i.get('subtotal', 0)))
                   for i in items
                   if isinstance(i, dict) and i.get('categoria') not in ('Resumen','Impuesto','Total'))
    except: return 0.0

def _grand_total(o):
    try:
        items = o.items_cotizacion or []
        for it in items:
            if isinstance(it, dict) and it.get('categoria') == 'Total':
                return float(it.get('total', it.get('precio_unitario', 0)))
        return _total(o)
    except: return 0.0

MESES = ['Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic']

# ─── Evidence helpers ─────────────────────────────────────────────────────────

EV_CATS = [
    ('recepcion',  'Recepción'),
    ('desarmado',  'Desarmado'),
    ('dañadas',    'Piezas dañadas'),
    ('reparacion', 'Reparación'),
]

def _get_evidencia(o):
    """Devuelve dict {cat_key: [url, ...]} con todas las fotos de la orden."""
    result = {k: [] for k, _ in EV_CATS}
    ck = o.checklist_reparacion or {}
    ev_cats = ck.get('evidence_cats', {}) if isinstance(ck, dict) else {}
    for cat_key, _ in EV_CATS:
        for fname in (ev_cats.get(cat_key) or []):
            result[cat_key].append(f'/evidencia/{o.consecutivo}/{cat_key}/{fname}')
    # Fallback: fotos_evidencia legacy
    for p in (o.fotos_evidencia or []):
        if isinstance(p, str) and p not in [u for urls in result.values() for u in urls]:
            result['recepcion'].append(p)
        elif isinstance(p, dict):
            url = p.get('path', '')
            if url:
                fase = _n(p.get('fase',''))
                cat = 'recepcion'
                if 'diagn' in fase: cat = 'desarmado'
                elif 'repar' in fase: cat = 'reparacion'
                if url not in [u for urls in result.values() for u in urls]:
                    result[cat].append(url)
    return result

def _is_video(url):
    return any(url.lower().endswith(ext) for ext in ('.mp4','.mov','.avi','.webm'))

# ─── CSS ─────────────────────────────────────────────────────────────────────

PORTAL_CSS = """
*{box-sizing:border-box;margin:0;padding:0}
body,html{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','Inter',sans-serif;background:#f0f4f8;color:#1e293b;font-size:14px}
:root{--blue:#2563eb;--blue-light:#eff6ff;--blue-mid:#bfdbfe;--green:#16a34a;--amber:#d97706;--border:#e2e8f0;--text:#1e293b;--text2:#64748b;--text3:#94a3b8;--sidebar-w:240px;--topbar-h:64px}
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
.user-chip{display:flex;align-items:center;gap:9px;padding:6px 14px 6px 8px;border-radius:24px;background:#f8fafc;border:1px solid var(--border)}
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
.nav-item{display:flex;align-items:center;gap:10px;padding:9px 16px 9px 20px;cursor:pointer;transition:.12s;border-left:2.5px solid transparent;margin:1px 0}
.nav-item:hover{background:#f8fafc}
.nav-item.active{background:var(--blue-light);border-left-color:var(--blue)}
.nav-icon{width:18px;height:18px;flex-shrink:0;color:var(--text3)}
.nav-item.active .nav-icon,.nav-item.active .nav-label{color:var(--blue);font-weight:600}
.nav-label{font-size:13px;font-weight:500;color:var(--text2);flex:1}
.nav-item:hover .nav-label{color:var(--text)}
.nav-badge{margin-left:auto;background:var(--blue-light);color:var(--blue);font-size:9.5px;font-weight:700;padding:2px 7px;border-radius:10px}
.nav-badge.red{background:#fef2f2;color:#dc2626}
/* EMPRESA CARD */
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
.kpi{background:#fff;border:1px solid var(--border);border-radius:14px;padding:18px 18px 16px;position:relative;overflow:hidden;transition:.2s}
.kpi:hover{box-shadow:0 4px 16px rgba(0,0,0,.07);transform:translateY(-1px)}
.kpi::after{content:'';position:absolute;top:0;left:0;right:0;height:3px;border-radius:14px 14px 0 0}
.kpi.k1::after{background:linear-gradient(90deg,#2563eb,#60a5fa)}
.kpi.k2::after{background:linear-gradient(90deg,#16a34a,#4ade80)}
.kpi.k3::after{background:linear-gradient(90deg,#d97706,#fbbf24)}
.kpi.k4::after{background:linear-gradient(90deg,#7c3aed,#c084fc)}
.kpi-top{display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:12px}
.kpi-icon{width:40px;height:40px;border-radius:10px;display:flex;align-items:center;justify-content:center}
.k1 .kpi-icon{background:#eff6ff}.k2 .kpi-icon{background:#f0fdf4}.k3 .kpi-icon{background:#fffbeb}.k4 .kpi-icon{background:#f5f3ff}
.kpi-tag{font-size:10px;font-weight:600;padding:3px 8px;border-radius:20px}
.kpi-tag.up{background:#dcfce7;color:#16a34a}.kpi-tag.neu{background:#f8fafc;color:var(--text2)}.kpi-tag.warn{background:#fef3c7;color:#92400e}
.kpi-num{font-size:26px;font-weight:700;color:#0f172a;line-height:1;letter-spacing:-.5px}
.kpi-lbl{font-size:12px;color:var(--text2);margin-top:4px}
/* GRID 2 */
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:24px}
.grid-left,.grid-right{display:flex;flex-direction:column;gap:20px}
/* CARD */
.card{background:#fff;border:1px solid var(--border);border-radius:14px;padding:20px}
.sec-hd{display:flex;align-items:center;justify-content:space-between;margin-bottom:14px}
.sec-title{font-size:14px;font-weight:700;color:#0f172a}
.sec-link{font-size:12px;color:var(--blue);font-weight:600;cursor:pointer}
.sec-link:hover{text-decoration:underline}
/* ORDEN CARD */
.orden-card{background:#fff;border:1px solid var(--border);border-radius:14px;padding:24px;margin-bottom:20px;border-left:4px solid var(--blue)}
.orden-top{display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:16px}
.orden-num{font-size:11px;color:var(--text2);margin-bottom:4px;font-weight:500}
.orden-title{font-size:15px;font-weight:700;color:#0f172a;margin-bottom:6px}
.orden-meta{display:flex;gap:16px;flex-wrap:wrap;margin-top:6px}
.orden-meta-item{font-size:12px;color:var(--text2);display:flex;align-items:center;gap:4px}
.orden-badge{font-size:11px;font-weight:600;padding:4px 12px;border-radius:20px}
.resp-chip{display:inline-flex;align-items:center;gap:6px;background:#f8fafc;border:1px solid var(--border);border-radius:20px;padding:4px 10px;font-size:11px;font-weight:500;color:var(--text);margin-top:8px}
.resp-dot{width:6px;height:6px;border-radius:50%;background:#22c55e;flex-shrink:0}
/* TIMELINE 8 FASES */
.phases{display:flex;gap:0;position:relative;margin:24px 0 20px;padding:0 4px}
.phases::before{content:'';position:absolute;top:15px;left:20px;right:20px;height:2px;background:#e2e8f0;z-index:0}
.phases-prog{position:absolute;top:15px;left:20px;height:2px;background:var(--blue);z-index:1;transition:width .5s}
.ph{flex:1;display:flex;flex-direction:column;align-items:center;gap:5px;position:relative;z-index:2}
.ph-circle{width:30px;height:30px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:10px;font-weight:700;border:2px solid #e2e8f0;background:#fff;transition:.2s}
.ph.done .ph-circle{background:var(--blue);border-color:var(--blue);color:#fff}
.ph.active .ph-circle{background:#fff;border-color:var(--blue);color:var(--blue);box-shadow:0 0 0 4px #dbeafe}
.ph.pending .ph-circle{background:#f8fafc;color:var(--text3);border-color:#e2e8f0}
.ph-lbl{font-size:8.5px;color:var(--text3);text-align:center;font-weight:500;white-space:nowrap}
.ph.done .ph-lbl{color:var(--blue);font-weight:600}
.ph.active .ph-lbl{color:var(--blue);font-weight:700}
/* SECTION CARDS INSIDE ORDEN */
.ord-section{background:#f8fafc;border:1px solid #f1f5f9;border-radius:12px;padding:16px;margin-bottom:14px}
.ord-section-title{font-size:10px;font-weight:700;color:var(--text3);letter-spacing:.8px;text-transform:uppercase;margin-bottom:10px}
/* COTIZACIÓN TABLE */
.cot-table{width:100%;border-collapse:collapse}
.cot-table thead th{font-size:10px;font-weight:700;color:var(--text3);letter-spacing:.7px;text-transform:uppercase;padding:8px 12px;background:#f1f5f9;border-bottom:1px solid var(--border);text-align:left}
.cot-table tbody td{padding:9px 12px;border-bottom:1px solid #f1f5f9;font-size:13px;vertical-align:middle}
.cot-table tbody tr:last-child td{border-bottom:none}
.cot-table tbody tr:hover td{background:#fafbff}
.cot-total-row td{background:#eff6ff!important;font-weight:700;color:var(--blue);border-top:2px solid var(--blue-mid)!important}
.cat-badge{font-size:10px;font-weight:600;padding:2px 8px;border-radius:10px;background:#eff6ff;color:var(--blue)}
.cat-badge.srv{background:#f0fdf4;color:#166534}
/* EVIDENCE GALLERY */
.ev-section{margin-top:4px}
.ev-cat-title{font-size:10px;font-weight:700;color:var(--text3);text-transform:uppercase;letter-spacing:.7px;margin:14px 0 8px}
.ev-grid{display:flex;flex-wrap:wrap;gap:8px}
.ev-thumb{width:90px;height:90px;border-radius:10px;border:1px solid var(--border);overflow:hidden;cursor:pointer;background:#f1f5f9;flex-shrink:0;position:relative}
.ev-thumb img{width:100%;height:100%;object-fit:cover}
.ev-thumb video{width:100%;height:100%;object-fit:cover}
.ev-play{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,.3);color:#fff;font-size:22px}
/* HISTORIAL */
.hist-line{display:flex;gap:12px;padding:8px 0;border-bottom:1px solid #f1f5f9}
.hist-line:last-child{border-bottom:none}
.hist-dot{width:8px;height:8px;border-radius:50%;background:var(--blue);flex-shrink:0;margin-top:4px}
.hist-fecha{font-size:10px;color:var(--text3);min-width:110px;flex-shrink:0}
.hist-accion{font-size:12px;color:#334155;flex:1}
.hist-user{font-size:10px;color:var(--text3);flex-shrink:0}
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
/* LIGHTBOX */
#lb{display:none;position:fixed;inset:0;background:rgba(0,0,0,.92);z-index:9999;align-items:center;justify-content:center}
#lb.on{display:flex}
#lb img,#lb video{max-width:90vw;max-height:90vh;border-radius:12px;object-fit:contain}
#lb-close{position:absolute;top:20px;right:24px;color:#fff;font-size:28px;cursor:pointer;line-height:1}
/* APROBACION BADGE */
.aprob-ok{display:inline-flex;align-items:center;gap:6px;background:#dcfce7;color:#166534;padding:6px 14px;border-radius:20px;font-size:12px;font-weight:600}
.aprob-pend{display:inline-flex;align-items:center;gap:6px;background:#fef3c7;color:#92400e;padding:6px 14px;border-radius:20px;font-size:12px;font-weight:600}
.aprob-rech{display:inline-flex;align-items:center;gap:6px;background:#fee2e2;color:#991b1b;padding:6px 14px;border-radius:20px;font-size:12px;font-weight:600}
"""

# ─── SVG Icons ────────────────────────────────────────────────────────────────

SVG_DASH = '<svg class="nav-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>'
SVG_CAR  = '<svg class="nav-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path d="M5 17H3a2 2 0 01-2-2V5a2 2 0 012-2h11l5 5v5"/><circle cx="16" cy="17" r="2"/><circle cx="7" cy="17" r="2"/></svg>'
SVG_HIST = '<svg class="nav-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"/></svg>'
SVG_ORD  = '<svg class="nav-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg>'
SVG_CAL  = '<svg class="nav-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/></svg>'
SVG_BLDG = '<svg class="nav-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path d="M3 9l9-7 9 7v11a2 2 0 01-2 2H5a2 2 0 01-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>'
SVG_USER = '<svg class="nav-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><circle cx="12" cy="8" r="4"/><path d="M4 20c0-4 3.6-7 8-7s8 3 8 7"/></svg>'

# ─── Phase timeline ───────────────────────────────────────────────────────────

def _phases_html(estado):
    fi  = _fase_idx(estado)
    # Para el progreso: ignorar ARCHIVADO en el pct visual
    total_active = 6  # de 0 a 6 (ENTREGA)
    pct = int(min(fi, total_active) / total_active * 100)
    html = f'<div class="phases"><div class="phases-prog" style="width:{pct}%"></div>'
    for i, (nombre, corto, _) in enumerate(FASES[:-1]):  # omitir ARCHIVADO en timeline
        if i < fi:
            cls = 'done'; txt = '✓'
        elif i == fi:
            cls = 'active'; txt = str(i+1)
        else:
            cls = 'pending'; txt = str(i+1)
        html += f'<div class="ph {cls}"><div class="ph-circle">{txt}</div><div class="ph-lbl">{corto}</div></div>'
    html += '</div>'
    return html

# ─── Full order card ──────────────────────────────────────────────────────────

def _orden_full_card(o, show_link=False):
    """Genera el HTML completo de una orden: fases, diagnóstico, cotización, evidencias, historial."""
    fi = _fase_idx(o.estado)
    total = _grand_total(o)

    # ── Info básica ──
    placa = _esc(o.vehiculo_placa or '')
    fecha = str(o.fecha or '')[:10]
    tecnico = _esc(o.tecnico or 'Sin asignar')
    km = _esc(o.km or '--')
    motivo = _esc(o.motivo or '')
    diag   = _esc(o.diagnostico or '')
    notas  = _esc(o.notas_entrega or '')

    # ── Aprobación ──
    ap = (o.approval_status or '').lower()
    if ap == 'aprobado':
        aprob_html = f'<span class="aprob-ok">✓ Presupuesto aprobado · {_esc(o.approval_date or "")}</span>'
    elif ap == 'rechazado':
        aprob_html = f'<span class="aprob-rech">✗ Presupuesto rechazado · {_esc(o.approval_date or "")}</span>'
    else:
        aprob_html = '<span class="aprob-pend">⏳ Pendiente de aprobación</span>'

    # ── Cotización ──
    cot_html = ''
    items = [i for i in (o.items_cotizacion or []) if isinstance(i, dict)]
    normales = [i for i in items if i.get('categoria') not in ('Resumen','Impuesto','Total','')]
    resumen  = [i for i in items if i.get('categoria') in ('Resumen','Impuesto','Total')]
    if normales:
        rows = ''
        for it in normales:
            cat = it.get('categoria','Repuesto')
            cat_cls = 'srv' if cat == 'Servicio' else ''
            cant = it.get('cantidad', 1)
            pu   = float(it.get('precio_unitario', it.get('total', 0)) or 0) / max(int(cant or 1), 1)
            tot  = float(it.get('total', 0) or 0)
            rows += f'''<tr>
  <td><span class="cat-badge {cat_cls}">{_esc(cat)}</span></td>
  <td style="font-weight:500;color:#0f172a">{_esc(it.get("nombre",""))}</td>
  <td style="text-align:center;color:var(--text2)">{cant}</td>
  <td style="text-align:right;color:var(--text2)">S/ {pu:,.2f}</td>
  <td style="text-align:right;font-weight:600;color:#0f172a">S/ {tot:,.2f}</td>
</tr>'''
        # Filas resumen
        for it in resumen:
            nom = it.get('nombre','')
            tot = float(it.get('total', it.get('precio_unitario', 0)) or 0)
            is_total = it.get('categoria') == 'Total'
            cls = ' cot-total-row' if is_total else ''
            rows += f'<tr class="{cls}"><td colspan="4" style="font-size:12px">{_esc(nom)}</td><td style="text-align:right">S/ {tot:,.2f}</td></tr>'
        cot_html = f'''<div class="ord-section">
  <div class="ord-section-title">Presupuesto / Cotización · {aprob_html}</div>
  <table class="cot-table">
    <thead><tr><th>Tipo</th><th>Descripción</th><th style="text-align:center">Cant.</th><th style="text-align:right">P.Unit</th><th style="text-align:right">Total</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</div>'''
    else:
        cot_html = f'<div class="ord-section"><div class="ord-section-title">Presupuesto · {aprob_html}</div><div style="font-size:13px;color:var(--text3)">Sin cotización registrada aún.</div></div>'

    # ── Evidencias ──
    ev = _get_evidencia(o)
    any_ev = any(ev[k] for k, _ in EV_CATS)
    ev_html = ''
    if any_ev:
        cats_html = ''
        for cat_key, cat_label in EV_CATS:
            urls = ev.get(cat_key, [])
            if not urls:
                continue
            thumbs = ''
            for url in urls:
                if _is_video(url):
                    thumbs += f'<div class="ev-thumb" onclick="openLb(this,true)"><video src="{_esc(url)}" muted playsinline></video><div class="ev-play">▶</div></div>'
                else:
                    thumbs += f'<div class="ev-thumb" onclick="openLb(this,false)"><img src="{_esc(url)}" loading="lazy" alt="evidencia"/></div>'
            cats_html += f'<div class="ev-cat-title">{cat_label}</div><div class="ev-grid">{thumbs}</div>'
        ev_html = f'<div class="ord-section"><div class="ord-section-title">Evidencia fotográfica y de video</div><div class="ev-section">{cats_html}</div></div>'
    else:
        ev_html = '<div class="ord-section"><div class="ord-section-title">Evidencia fotográfica</div><div style="font-size:13px;color:var(--text3)">Sin evidencias cargadas aún.</div></div>'

    # ── Checklist diagnóstico ──
    ck = o.checklist_reparacion or {}
    ck = ck if isinstance(ck, dict) else {}
    diag_detail = ck.get('diagnostic_details') or ck.get('diagnosis_form') or {}
    analysis  = _esc(diag_detail.get('analysis', '') if isinstance(diag_detail, dict) else '')
    solution  = _esc(diag_detail.get('solution', '') if isinstance(diag_detail, dict) else '')
    repair_logs = ck.get('repair_logs') or []

    diag_html = ''
    if analysis or diag:
        diag_html += f'<div style="margin-bottom:10px"><div style="font-size:11px;font-weight:700;color:var(--text3);text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px">Problema reportado</div><div style="font-size:13px;color:#334155">{diag if diag else analysis}</div></div>'
    if solution:
        diag_html += f'<div style="margin-bottom:10px"><div style="font-size:11px;font-weight:700;color:var(--text3);text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px">Solución técnica</div><div style="font-size:13px;color:#334155">{solution}</div></div>'
    if repair_logs:
        logs_html = ''
        for lg in repair_logs[:5]:
            if not isinstance(lg, dict): continue
            logs_html += f'''<div style="background:#f8fafc;border-radius:8px;padding:10px;margin-bottom:8px">
  <div style="font-size:12px;font-weight:600;color:#0f172a">{_esc(lg.get("falla",""))}</div>
  <div style="font-size:11px;color:var(--text2);margin-top:3px">Causa: {_esc(lg.get("causa",""))}</div>
  <div style="font-size:11px;color:#166534;margin-top:3px">✓ {_esc(lg.get("solucion",""))}</div>
</div>'''
        diag_html += f'<div style="margin-top:10px"><div style="font-size:11px;font-weight:700;color:var(--text3);text-transform:uppercase;letter-spacing:.5px;margin-bottom:8px">Trabajos realizados</div>{logs_html}</div>'
    if notas:
        diag_html += f'<div style="margin-top:10px;padding-top:10px;border-top:1px solid #f1f5f9"><div style="font-size:11px;font-weight:700;color:var(--text3);text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px">Notas de entrega</div><div style="font-size:13px;color:#334155">{notas}</div></div>'

    diag_section = f'<div class="ord-section"><div class="ord-section-title">Diagnóstico y trabajo realizado</div>{diag_html if diag_html else "<div style=\'font-size:13px;color:var(--text3)\'>Sin diagnóstico registrado.</div>"}</div>'

    # ── Historial de eventos ──
    hist = o.historial or []
    hist_html = ''
    if hist:
        for h in reversed(hist[-10:]):
            if not isinstance(h, dict): continue
            hist_html += f'''<div class="hist-line">
  <div class="hist-dot"></div>
  <div class="hist-fecha">{_esc(h.get("fecha",""))}</div>
  <div class="hist-accion">{_esc(h.get("accion",""))}</div>
  <div class="hist-user">{_esc(h.get("usuario",""))}</div>
</div>'''
    hist_section = f'<div class="ord-section"><div class="ord-section-title">Historial de eventos</div>{hist_html if hist_html else "<div style=\'font-size:13px;color:var(--text3)\'>Sin historial.</div>"}</div>'

    # ── PDF cotización ──
    pdf_link = ''
    if o.pdf_cotizacion:
        pdf_link = f'<a href="/pdfs/{_esc(os.path.basename(o.pdf_cotizacion))}" target="_blank" style="font-size:12px;color:var(--blue);font-weight:600;display:inline-flex;align-items:center;gap:4px;margin-top:4px">📄 Descargar cotización en PDF</a>'

    link_btn = ''
    if show_link:
        link_btn = f'<div style="margin-top:4px"><span class="sec-link" onclick="showView(\'ordenes\')" style="font-size:12px">→ Ver detalle completo</span></div>'

    return f'''<div class="orden-card">
  <div class="orden-top">
    <div>
      <div class="orden-num">{_esc(o.consecutivo)}</div>
      <div class="orden-title">{_esc(motivo[:80]) if motivo else "(Sin descripción)"}</div>
      <div class="orden-meta">
        <div class="orden-meta-item">🚗 {placa}</div>
        <div class="orden-meta-item">📅 {fecha}</div>
        <div class="orden-meta-item">📏 {km} km</div>
        <div class="orden-meta-item">🔧 {tecnico}</div>
      </div>
      <div class="resp-chip"><div class="resp-dot"></div>{tecnico}</div>
      {pdf_link}
    </div>
    <span class="orden-badge" style="{_badge_style(o.estado)}">{_esc(o.estado)}</span>
  </div>

  {_phases_html(o.estado)}

  {diag_section}
  {cot_html}
  {ev_html}
  {hist_section}
  {link_btn}
</div>'''

# ─── Helpers sidebar ──────────────────────────────────────────────────────────

def _sb_section(label):
    return f'<div class="sb-section">{label}</div>'

def _fleet_bar_pct(estado):
    e = _n(estado)
    if 'recep'   in e: return 5
    if 'diagn'   in e: return 20
    if 'repues'  in e: return 35
    if 'aprob'   in e: return 50
    if 'repar'   in e or 'taller' in e: return 65
    if 'control' in e: return 82
    if 'entreg'  in e: return 100
    if 'archiv'  in e: return 100
    return 5

def _fleet_bar_color(estado):
    e = _n(estado)
    if 'entreg' in e or 'archiv' in e: return '#16a34a'
    if 'control' in e:                 return '#0369a1'
    if 'repar'  in e:                  return '#d97706'
    if 'aprob'  in e:                  return '#854d0e'
    if 'repues' in e:                  return '#1e40af'
    if 'diagn'  in e:                  return '#6d28d9'
    return '#94a3b8'

# ─── View builders ────────────────────────────────────────────────────────────

def _vw_dashboard(cli, vehs, ords, ord_act, citas_fut, es_empresa):
    nombre = cli.nombre if es_empresa else f"{cli.nombre} {cli.apellidos or ''}".strip()
    mes = MESES[datetime.now().month - 1]
    en_taller   = sum(1 for o in ord_act if _fase_idx(o.estado) < 6)
    listos      = sum(1 for o in ord_act if _fase_idx(o.estado) in (5, 6))
    completados = len([o for o in ords if _fase_idx(o.estado) == 7])
    inversion   = sum(_grand_total(o) for o in ords if _fase_idx(o.estado) == 7)

    kpis = f'''<div class="kpi-grid">
  <div class="kpi k1"><div class="kpi-top">
    <div class="kpi-icon"><svg width="20" height="20" fill="none" viewBox="0 0 24 24" stroke="#2563eb" stroke-width="2"><path d="M5 17H3a2 2 0 01-2-2V5a2 2 0 012-2h11l5 5v5"/><circle cx="16" cy="17" r="2"/><circle cx="7" cy="17" r="2"/></svg></div>
    <span class="kpi-tag neu">Total</span></div>
    <div class="kpi-num">{len(vehs)}</div><div class="kpi-lbl">Vehículos registrados</div></div>
  <div class="kpi k2"><div class="kpi-top">
    <div class="kpi-icon"><svg width="20" height="20" fill="none" viewBox="0 0 24 24" stroke="#16a34a" stroke-width="2"><path d="M14.7 6.3a1 1 0 000 1.4l1.6 1.6a1 1 0 001.4 0l3.77-3.77a6 6 0 01-7.94 7.94l-6.91 6.91a2.12 2.12 0 01-3-3l6.91-6.91a6 6 0 017.94-7.94l-3.76 3.76z"/></svg></div>
    <span class="kpi-tag up">Activos</span></div>
    <div class="kpi-num">{en_taller}</div><div class="kpi-lbl">En taller ahora</div></div>
  <div class="kpi k3"><div class="kpi-top">
    <div class="kpi-icon"><svg width="20" height="20" fill="none" viewBox="0 0 24 24" stroke="#d97706" stroke-width="2"><path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/></svg></div>
    <span class="kpi-tag warn">Listos</span></div>
    <div class="kpi-num">{listos}</div><div class="kpi-lbl">Listo para recoger</div></div>
  <div class="kpi k4"><div class="kpi-top">
    <div class="kpi-icon"><svg width="20" height="20" fill="none" viewBox="0 0 24 24" stroke="#7c3aed" stroke-width="2"><path d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg></div>
    <span class="kpi-tag neu">{mes}</span></div>
    <div class="kpi-num">S/ {inversion:,.0f}</div><div class="kpi-lbl">Inversión total</div></div>
</div>'''

    # Fleet table
    fleet_rows = ''
    for v in vehs[:5]:
        ord_v  = next((o for o in ord_act if o.vehiculo_placa == v.placa), None)
        estado = ord_v.estado if ord_v else 'Sin orden'
        pct    = _fleet_bar_pct(estado)
        col    = _fleet_bar_color(estado)
        modelo = f"{v.marca or ''} {v.modelo or ''} {getattr(v,'año','') or ''}".strip()
        fleet_rows += f'''<tr class="fleet-row">
  <td><div class="fleet-placa">{_esc(v.placa)}</div><div class="fleet-model">{_esc(modelo)}</div></td>
  <td><div class="fleet-bar-wrap"><div class="fleet-bar" style="width:{pct}%;background:{col}"></div></div><div class="fleet-phase">{_esc(estado)}</div></td>
  <td style="text-align:center">{_badge(estado)}</td>
</tr>'''
    fleet_card = f'''<div class="card">
  <div class="sec-hd"><span class="sec-title">Estado de flota</span><span class="sec-link" onclick="showView('flota')">Ver todas →</span></div>
  <table class="fleet-table"><thead><tr><th>Vehículo</th><th>Progreso</th><th style="text-align:center">Estado</th></tr></thead>
  <tbody>{fleet_rows or "<tr><td colspan=3 class=empty>Sin vehículos</td></tr>"}</tbody></table>
</div>'''

    # Latest orders (historial)
    hist_rows = ''
    ord_hist = [o for o in ords if _fase_idx(o.estado) == 7]
    for o in ord_hist[:4]:
        tot = _grand_total(o)
        hist_rows += f'''<tr class="hist-row">
  <td style="font-size:11px;font-weight:600;color:#334155">{_esc(o.consecutivo)}</td>
  <td><div style="font-size:13px;font-weight:500;color:#0f172a">{_esc((o.motivo or '')[:50])}</div>
      <div style="font-size:11px;color:#64748b">{_esc(o.vehiculo_placa or '')} · {str(o.fecha or '')[:10]}</div></td>
  <td style="font-size:13px;font-weight:700">S/ {tot:,.0f}</td>
  <td>{_badge(o.estado)}</td>
</tr>'''
    hist_card = f'''<div class="card">
  <div class="sec-hd"><span class="sec-title">Últimas órdenes</span><span class="sec-link" onclick="showView('historial')">Ver historial →</span></div>
  <table class="hist-table"><thead><tr><th>Orden</th><th>Descripción</th><th>Monto</th><th>Estado</th></tr></thead>
  <tbody>{hist_rows or "<tr><td colspan=4 class=empty>Sin historial</td></tr>"}</tbody></table>
</div>'''

    # Active order preview (compact, link to full detail)
    if ord_act:
        o = ord_act[0]
        order_html = _orden_full_card(o, show_link=len(ord_act) > 1)
        more_link = f'<span class="sec-link" onclick="showView(\'ordenes\')">{len(ord_act)} activas →</span>' if len(ord_act) > 1 else ''
        order_section = f'<div><div class="sec-hd"><span class="sec-title">Orden activa — {_esc(o.vehiculo_placa or "")}</span>{more_link}</div>{order_html}</div>'
    else:
        order_section = '<div class="card"><div class="empty">No hay órdenes activas.</div></div>'

    # Citas
    citas_html = ''
    for c in citas_fut[:3]:
        try:
            fd = datetime.strptime(str(c.fecha_cita)[:10], '%Y-%m-%d')
            day = fd.strftime('%d'); mon = MESES[fd.month-1]
        except:
            day = '--'; mon = '---'
        conf = 'pend' if _n(c.estado or '') in ('pendiente','pend','programada') else ''
        tag_txt = 'Pendiente' if conf else 'Confirmada'
        placa = getattr(c, 'vehiculo_placa', '') or ''
        hora  = str(c.hora or '')[:5] if hasattr(c,'hora') else ''
        citas_html += f'''<div class="cita-item">
  <div class="cita-date-box"><div class="cita-day">{day}</div><div class="cita-mon">{mon}</div></div>
  <div style="flex:1"><div class="cita-info-title">{_esc(c.motivo or 'Cita programada')}</div>
    <div class="cita-info-sub">{hora}{" · " if hora else ""}{_esc(placa)}</div></div>
  <span class="cita-tag {conf}">{tag_txt}</span>
</div>'''
    citas_card = f'''<div class="card">
  <div class="sec-hd"><span class="sec-title">Próximas citas</span><span class="sec-link" onclick="showView('citas')">Ver todas →</span></div>
  {citas_html or "<div class=empty>Sin citas programadas</div>"}
</div>'''

    return f'''<div class="page-header"><h1>Dashboard</h1>
<p>Bienvenido, {_esc(nombre)} — {datetime.now().strftime("%d/%m/%Y")}</p></div>
{kpis}
<div class="grid2">
  <div class="grid-left">{fleet_card}{hist_card}</div>
  <div class="grid-right">{order_section}{citas_card}</div>
</div>'''


def _vw_flota(vehs, ord_act):
    rows = ''
    for v in vehs:
        ord_v  = next((o for o in ord_act if o.vehiculo_placa == v.placa), None)
        estado = ord_v.estado if ord_v else 'Sin orden'
        pct    = _fleet_bar_pct(estado)
        col    = _fleet_bar_color(estado)
        modelo = f"{v.marca or ''} {v.modelo or ''} {getattr(v,'año','') or ''}".strip()
        rows += f'''<tr class="fleet-row">
  <td><div class="fleet-placa">{_esc(v.placa)}</div><div class="fleet-model">{_esc(modelo)}</div></td>
  <td style="font-size:12px;color:var(--text2)">{_esc(v.tipo or '')}</td>
  <td><div class="fleet-bar-wrap"><div class="fleet-bar" style="width:{pct}%;background:{col}"></div></div><div class="fleet-phase">{_esc(estado)}</div></td>
  <td style="text-align:center">{_badge(estado)}</td>
</tr>'''
    return f'''<div class="page-header"><h1>Mi Flota</h1><p>{len(vehs)} vehículos registrados</p></div>
<div class="card"><table class="fleet-table">
  <thead><tr><th>Vehículo</th><th>Tipo</th><th>Progreso</th><th style="text-align:center">Estado</th></tr></thead>
  <tbody>{rows or "<tr><td colspan=4 class=empty>Sin vehículos</td></tr>"}</tbody>
</table></div>'''


def _vw_ordenes(ord_act):
    if not ord_act:
        return '<div class="page-header"><h1>Órdenes Activas</h1></div><div class="card"><div class="empty">No hay órdenes activas en este momento.</div></div>'
    cards = ''.join(_orden_full_card(o) for o in ord_act)
    return f'<div class="page-header"><h1>Órdenes Activas</h1><p>{len(ord_act)} en proceso</p></div>{cards}'


def _vw_historial(ords):
    ord_hist = [o for o in ords if _fase_idx(o.estado) == 7]
    cards = ''.join(_orden_full_card(o) for o in ord_hist)
    return f'''<div class="page-header"><h1>Historial de Servicios</h1><p>{len(ord_hist)} órdenes completadas</p></div>
{cards or "<div class=card><div class=empty>Sin historial de servicios.</div></div>"}'''


def _vw_citas(citas_all):
    ahora = datetime.now().strftime('%Y-%m-%d')
    fut   = [c for c in citas_all if str(c.fecha_cita or '')[:10] >= ahora]
    pas   = [c for c in citas_all if str(c.fecha_cita or '')[:10] < ahora]

    def _rows(lst):
        out = ''
        for c in lst:
            try:
                fd = datetime.strptime(str(c.fecha_cita)[:10], '%Y-%m-%d')
                day = fd.strftime('%d'); mon = MESES[fd.month-1]
            except:
                day='--'; mon='---'
            conf = 'pend' if _n(c.estado or '') in ('pendiente','pend','programada') else ''
            tag_txt = 'Pendiente' if conf else 'Confirmada'
            placa = getattr(c,'vehiculo_placa','') or ''
            hora  = str(c.hora or '')[:5] if hasattr(c,'hora') else ''
            out += f'''<div class="cita-item">
  <div class="cita-date-box"><div class="cita-day">{day}</div><div class="cita-mon">{mon}</div></div>
  <div style="flex:1"><div class="cita-info-title">{_esc(c.motivo or 'Cita programada')}</div>
    <div class="cita-info-sub">{hora}{" · " if hora else ""}{_esc(placa)}</div></div>
  <span class="cita-tag {conf}">{tag_txt}</span>
</div>'''
        return out or '<div class="empty">Sin citas</div>'

    return f'''<div class="page-header"><h1>Citas Programadas</h1><p>{len(fut)} próximas · {len(pas)} anteriores</p></div>
<div class="card" style="margin-bottom:20px"><div class="sec-hd"><span class="sec-title">Próximas citas</span></div>{_rows(fut)}</div>
<div class="card"><div class="sec-hd"><span class="sec-title">Anteriores</span></div>{_rows(pas[:8])}</div>'''


def _vw_empresa(cli, vehs, ords):
    nombre = cli.nombre or ''
    email  = getattr(cli,'email','') or ''
    tel    = getattr(cli,'telefono','') or ''
    completados = len([o for o in ords if _fase_idx(o.estado) == 7])
    en_curso    = len([o for o in ords if 0 < _fase_idx(o.estado) < 7])
    inversion   = sum(_grand_total(o) for o in ords if _fase_idx(o.estado) == 7)
    initials    = ''.join(p[0].upper() for p in nombre.split()[:2]) or 'E'
    return f'''<div class="page-header"><h1>Mi Empresa</h1></div>
<div style="background:linear-gradient(135deg,#eff6ff,#f0f9ff);border:1px solid #bfdbfe;border-radius:14px;padding:24px;margin-bottom:24px;display:flex;align-items:center;gap:20px">
  <div style="width:64px;height:64px;background:#2563eb;border-radius:16px;display:flex;align-items:center;justify-content:center;font-size:24px;font-weight:800;color:#fff;flex-shrink:0;box-shadow:0 4px 12px rgba(37,99,235,.3)">{initials}</div>
  <div>
    <div style="font-size:20px;font-weight:800;color:#0f172a">{_esc(nombre)}</div>
    <div style="font-size:13px;color:#64748b;margin-top:3px">RUC {_esc(str(cli.id))}{" · " + _esc(email) if email else ""}{" · " + _esc(tel) if tel else ""}</div>
    <div style="display:flex;gap:12px;margin-top:14px">
      <div style="text-align:center;padding:10px 16px;background:#fff;border-radius:10px;border:1px solid #e2e8f0"><div style="font-size:20px;font-weight:800;color:#2563eb">{len(vehs)}</div><div style="font-size:10px;color:#64748b;margin-top:2px">Vehículos</div></div>
      <div style="text-align:center;padding:10px 16px;background:#fff;border-radius:10px;border:1px solid #e2e8f0"><div style="font-size:20px;font-weight:800;color:#d97706">{en_curso}</div><div style="font-size:10px;color:#64748b;margin-top:2px">En proceso</div></div>
      <div style="text-align:center;padding:10px 16px;background:#fff;border-radius:10px;border:1px solid #e2e8f0"><div style="font-size:20px;font-weight:800;color:#16a34a">{completados}</div><div style="font-size:10px;color:#64748b;margin-top:2px">Completados</div></div>
      <div style="text-align:center;padding:10px 16px;background:#fff;border-radius:10px;border:1px solid #e2e8f0"><div style="font-size:20px;font-weight:800;color:#7c3aed">S/ {inversion:,.0f}</div><div style="font-size:10px;color:#64748b;margin-top:2px">Invertido</div></div>
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
        ord_act     = [o for o in ords if _fase_idx(o.estado) < 7]
        nombre_disp = cli.nombre if es_empresa else f"{cli.nombre} {cli.apellidos or ''}".strip()
        initials    = ''.join(p[0].upper() for p in nombre_disp.split()[:2]) or 'C'
        en_t = sum(1 for o in ord_act if _fase_idx(o.estado) < 5)
        lst  = sum(1 for o in ord_act if _fase_idx(o.estado) in (5,6))

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
        emp_nav   = f'{_sb_section("Empresa")}<div class="nav-item" onclick="showView(\'empresa\')" id="nav-empresa">{SVG_BLDG}<span class="nav-label">Mi Empresa</span></div>' if es_empresa else ''
        emp_view  = f'<div class="view" id="view-empresa">{_vw_empresa(cli, vehs, ords)}</div>' if es_empresa else ''

        full_html = f'''<div id="portal-root">
<style>{PORTAL_CSS}</style>

<div class="topbar">
  <div class="topbar-left">
    <div class="logo-box">S</div>
    <div><div class="brand-name">Mecánica Sandoval</div><div class="brand-sub">Portal del Cliente</div></div>
  </div>
  <div class="topbar-right">
    <div class="user-chip">
      <div class="user-avatar">{initials}</div>
      <div><div class="user-info-name">{_esc(nombre_disp)}</div>
        <div class="user-info-role">{"Cliente Corporativo" if es_empresa else "Cliente"}</div></div>
    </div>
    <button class="logout-btn" onclick="window.location.href='/portal-logout'">Cerrar sesión</button>
  </div>
</div>

<div class="layout">
  <nav class="sidebar">
    {emp_card}
    {_sb_section("Principal")}
    <div class="nav-item active" onclick="showView('dashboard')" id="nav-dashboard">{SVG_DASH}<span class="nav-label">Dashboard</span></div>
    <div class="nav-item" onclick="showView('flota')" id="nav-flota">{SVG_CAR}<span class="nav-label">Mi Flota</span>{badge_veh}</div>
    {_sb_section("Servicios")}
    <div class="nav-item" onclick="showView('ordenes')" id="nav-ordenes">{SVG_ORD}<span class="nav-label">Órdenes Activas</span>{badge_ord}</div>
    <div class="nav-item" onclick="showView('historial')" id="nav-historial">{SVG_HIST}<span class="nav-label">Historial</span></div>
    <div class="nav-item" onclick="showView('citas')" id="nav-citas">{SVG_CAL}<span class="nav-label">Citas</span></div>
    {emp_nav}
    {_sb_section("Cuenta")}
    <div class="nav-item" onclick="showView('perfil')" id="nav-perfil">{SVG_USER}<span class="nav-label">Mi Perfil</span></div>
  </nav>

  <main class="main">
    <div class="view active" id="view-dashboard">{_vw_dashboard(cli, vehs, ords, ord_act, citas_fut, es_empresa)}</div>
    <div class="view" id="view-flota">{_vw_flota(vehs, ord_act)}</div>
    <div class="view" id="view-ordenes">{_vw_ordenes(ord_act)}</div>
    <div class="view" id="view-historial">{_vw_historial(ords)}</div>
    <div class="view" id="view-citas">{_vw_citas(citas_all)}</div>
    {emp_view}
    <div class="view" id="view-perfil">
      <div class="page-header"><h1>Mi Perfil</h1></div>
      <div class="card">
        <div style="font-size:15px;font-weight:700;color:#0f172a;margin-bottom:6px">{_esc(nombre_disp)}</div>
        <div style="font-size:13px;color:#64748b">{"RUC " if es_empresa else "DNI "}{_esc(str(cli.id))}</div>
      </div>
    </div>
  </main>
</div>

<!-- LIGHTBOX -->
<div id="lb" onclick="closeLb()">
  <span id="lb-close">✕</span>
  <div id="lb-content"></div>
</div>

<script>
function showView(name) {{
  document.querySelectorAll('.view').forEach(function(v){{v.classList.remove('active')}});
  document.querySelectorAll('.nav-item').forEach(function(n){{n.classList.remove('active')}});
  var el = document.getElementById('view-' + name);
  if (el) el.classList.add('active');
  var nav = document.getElementById('nav-' + name);
  if (nav) nav.classList.add('active');
  window.scrollTo(0, 0);
}}
function openLb(el, isVideo) {{
  var src = isVideo ? el.querySelector('video').src : el.querySelector('img').src;
  var lbContent = document.getElementById('lb-content');
  lbContent.innerHTML = isVideo
    ? '<video src="' + src + '" controls autoplay style="max-width:90vw;max-height:90vh;border-radius:12px"></video>'
    : '<img src="' + src + '" style="max-width:90vw;max-height:90vh;border-radius:12px;object-fit:contain"/>';
  document.getElementById('lb').classList.add('on');
}}
function closeLb() {{
  document.getElementById('lb').classList.remove('on');
  document.getElementById('lb-content').innerHTML = '';
}}
document.addEventListener('keydown', function(e){{ if(e.key==='Escape') closeLb(); }});
</script>
</div>'''

        ui.add_body_html(full_html)

    finally:
        db.close()


def show_portal(_container=None):
    """Fallback desde frame admin."""
    ui.navigate.to('/portal')

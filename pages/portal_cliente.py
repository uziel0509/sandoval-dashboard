"""
SANDOVAL - Portal del Cliente v12.0
REGLA: Solo se toca este archivo. HTML puro via ui.add_body_html().
Portales existentes NO tocados:
  - Admin PC    → / (theme.frame + components)
  - Admin Móvil → /app/ (sandoval-app/index.html)
  - Cliente Móvil → /app/ (sandoval-app/index.html)
  - Cliente PC  → /portal (ESTE ARCHIVO)
"""

import unicodedata, os
from datetime import datetime
from nicegui import ui
from utils.models import get_db, Cliente, Vehiculo, Orden, Cita
from utils.auth import get_current_user

# ─── Helpers ─────────────────────────────────────────────────────────────────

def _n(t):
    return unicodedata.normalize('NFD', str(t or '')).encode('ascii','ignore').decode().lower()

def _esc(s):
    return str(s or '').replace('&','&amp;').replace('<','&lt;').replace('>','&gt;').replace('"','&quot;')

# 8 fases exactas del sistema (theme.py ESTADOS_CONFIG)
FASES = [
    ('RECEPCIÓN',   'Recep.'),
    ('DIAGNÓSTICO', 'Diagn.'),
    ('REPUESTOS',   'Reptos.'),
    ('APROBACIÓN',  'Aprobac.'),
    ('REPARACIÓN',  'Repar.'),
    ('CONTROL',     'Control'),
    ('ENTREGA',     'Entrega'),
    ('ARCHIVADO',   'Archiv.'),
]

def _fase_idx(estado):
    e = _n(estado)
    if 'recep'   in e:                     return 0
    if 'diagn'   in e:                     return 1
    if 'repues'  in e:                     return 2
    if 'aprob'   in e:                     return 3
    if 'repar'   in e or 'taller' in e:    return 4
    if 'control' in e or 'calidad' in e:   return 5
    if 'entreg'  in e:                     return 6
    if 'archiv'  in e:                     return 7
    return 0

def _badge_st(estado):
    e = _n(estado)
    if 'recep'   in e:                    return 'background:#f1f5f9;color:#475569'
    if 'diagn'   in e:                    return 'background:#ede9fe;color:#5b21b6'
    if 'repues'  in e:                    return 'background:#dbeafe;color:#1e40af'
    if 'aprob'   in e:                    return 'background:#fef9c3;color:#854d0e'
    if 'repar'   in e or 'taller' in e:   return 'background:#fef3c7;color:#92400e'
    if 'control' in e or 'calidad' in e:  return 'background:#e0f2fe;color:#0369a1'
    if 'entreg'  in e:                    return 'background:#dcfce7;color:#166534'
    if 'archiv'  in e:                    return 'background:#f1f5f9;color:#64748b'
    return 'background:#f1f5f9;color:#475569'

def _badge(estado):
    return f'<span style="font-size:11px;font-weight:600;padding:3px 10px;border-radius:20px;display:inline-block;{_badge_st(estado)}">{_esc(estado)}</span>'

def _grand_total(o):
    """Obtiene el total real de la orden (línea Total si existe, sino suma de items)."""
    try:
        items = o.items_cotizacion or []
        for it in items:
            if isinstance(it, dict) and it.get('categoria') == 'Total':
                return float(it.get('total', it.get('precio_unitario', 0)) or 0)
        # Sin línea Total: sumar items normales
        return sum(
            float(i.get('total', i.get('subtotal', 0)) or 0)
            for i in items
            if isinstance(i, dict) and i.get('categoria') not in ('Resumen','Impuesto','Total')
        )
    except:
        return 0.0

def _is_completed(o):
    return _fase_idx(o.estado) == 7  # ARCHIVADO

def _is_active(o):
    return 0 < _fase_idx(o.estado) < 7

MESES = ['Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic']

EV_CATS = [
    ('recepcion',  'Recepción'),
    ('desarmado',  'Desarmado'),
    ('dañadas',    'Piezas dañadas'),
    ('reparacion', 'Reparación'),
]

def _get_ev(o):
    result = {k: [] for k, _ in EV_CATS}
    ck = o.checklist_reparacion if isinstance(o.checklist_reparacion, dict) else {}
    ev_cats = ck.get('evidence_cats', {})
    for cat_key, _ in EV_CATS:
        for fname in (ev_cats.get(cat_key) or []):
            result[cat_key].append(f'/evidencia/{o.consecutivo}/{cat_key}/{fname}')
    for p in (o.fotos_evidencia or []):
        if isinstance(p, str):
            result['recepcion'].append(p)
        elif isinstance(p, dict) and p.get('path'):
            url = p['path']
            cat = 'recepcion'
            fase = _n(p.get('fase',''))
            if 'diagn' in fase: cat = 'desarmado'
            elif 'repar' in fase: cat = 'reparacion'
            if url not in [u for urls in result.values() for u in urls]:
                result[cat].append(url)
    return result

def _is_video(url):
    return any(url.lower().endswith(e) for e in ('.mp4','.mov','.avi','.webm'))

# ─── CSS ─────────────────────────────────────────────────────────────────────

CSS = """
*{box-sizing:border-box;margin:0;padding:0}
body,html{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f0f4f8;color:#1e293b;font-size:14px}
/* Ocultar todo NiceGUI/Quasar */
.q-header,.q-drawer,.q-footer,.q-layout-padding,.q-page-sticky,.nicegui-content{display:none!important}
.q-layout,.q-page-container,.q-page{background:#f0f4f8!important;padding:0!important;min-height:0!important}
#pr{display:block!important}
/* TOPBAR */
.tb{position:fixed;top:0;left:0;right:0;height:64px;background:#fff;border-bottom:1px solid #e2e8f0;display:flex;align-items:center;justify-content:space-between;padding:0 24px 0 0;z-index:100;box-shadow:0 1px 3px rgba(0,0,0,.06)}
.tb-l{display:flex;align-items:center;gap:12px;width:240px;height:100%;padding:0 20px;border-right:1px solid #e2e8f0;flex-shrink:0}
.logo{width:36px;height:36px;background:#2563eb;border-radius:10px;display:flex;align-items:center;justify-content:center;font-weight:800;font-size:16px;color:#fff;box-shadow:0 2px 8px rgba(37,99,235,.35)}
.bn{font-size:14px;font-weight:700;color:#0f172a}
.bs{font-size:11px;color:#64748b;margin-top:1px}
.tb-r{display:flex;align-items:center;gap:10px}
.uc{display:flex;align-items:center;gap:9px;padding:6px 14px 6px 8px;border-radius:24px;background:#f8fafc;border:1px solid #e2e8f0}
.ua{width:30px;height:30px;border-radius:50%;background:#2563eb;display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:700;color:#fff;flex-shrink:0}
.un{font-size:12px;font-weight:600;color:#0f172a}
.ur{font-size:10px;color:#64748b;margin-top:1px}
.logout{padding:7px 14px;border-radius:8px;background:#fff;border:1px solid #e2e8f0;font-size:12px;color:#64748b;cursor:pointer;font-weight:500;transition:.15s}
.logout:hover{color:#0f172a;border-color:#94a3b8}
/* LAYOUT */
.ly{display:flex;margin-top:64px;min-height:calc(100vh - 64px)}
/* SIDEBAR */
.sb{width:240px;flex-shrink:0;background:#fff;border-right:1px solid #e2e8f0;position:fixed;top:64px;bottom:0;padding:16px 0 24px;overflow-y:auto}
.sb-sec{font-size:9.5px;font-weight:700;color:#94a3b8;letter-spacing:1.2px;text-transform:uppercase;padding:0 20px;margin:20px 0 6px}
.ni{display:flex;align-items:center;gap:10px;padding:9px 16px 9px 20px;cursor:pointer;transition:.12s;border-left:2.5px solid transparent;margin:1px 0}
.ni:hover{background:#f8fafc}
.ni.on{background:#eff6ff;border-left-color:#2563eb}
.ni svg{width:18px;height:18px;flex-shrink:0;color:#94a3b8}
.ni.on svg,.ni.on .nl{color:#2563eb;font-weight:600}
.nl{font-size:13px;font-weight:500;color:#64748b;flex:1}
.ni:hover .nl{color:#1e293b}
.nb{margin-left:auto;background:#eff6ff;color:#2563eb;font-size:9.5px;font-weight:700;padding:2px 7px;border-radius:10px}
.nb.red{background:#fef2f2;color:#dc2626}
/* EMPRESA CARD */
.sb-emp{margin:0 12px 16px;padding:12px 14px;background:linear-gradient(135deg,#eff6ff,#f0f9ff);border:1px solid #bfdbfe;border-radius:10px}
.sb-emp-lbl{font-size:9px;font-weight:700;color:#2563eb;text-transform:uppercase;letter-spacing:1px;margin-bottom:5px}
.sb-emp-nm{font-size:13px;font-weight:700;color:#0f172a}
.sb-emp-ruc{font-size:11px;color:#64748b;margin-top:2px}
.sb-emp-fl{margin-top:8px;display:flex;gap:16px}
.sb-stat{text-align:center}
.sb-stat-n{font-size:18px;font-weight:700;color:#2563eb;line-height:1}
.sb-stat-l{font-size:9px;color:#64748b;margin-top:2px}
/* MAIN */
.mn{margin-left:240px;flex:1;padding:28px 32px;min-width:0}
/* PAGE HEADER */
.ph{margin-bottom:24px}
.ph h1{font-size:22px;font-weight:700;color:#0f172a;letter-spacing:-.4px}
.ph p{font-size:13px;color:#64748b;margin-top:4px}
/* KPI */
.kg{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:28px}
.kpi{background:#fff;border:1px solid #e2e8f0;border-radius:14px;padding:18px 18px 16px;position:relative;overflow:hidden;transition:.2s}
.kpi:hover{box-shadow:0 4px 16px rgba(0,0,0,.07);transform:translateY(-1px)}
.kpi::after{content:'';position:absolute;top:0;left:0;right:0;height:3px;border-radius:14px 14px 0 0}
.k1::after{background:linear-gradient(90deg,#2563eb,#60a5fa)}
.k2::after{background:linear-gradient(90deg,#16a34a,#4ade80)}
.k3::after{background:linear-gradient(90deg,#d97706,#fbbf24)}
.k4::after{background:linear-gradient(90deg,#7c3aed,#c084fc)}
.k5::after{background:linear-gradient(90deg,#0369a1,#38bdf8)}
.kpi-tp{display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:12px}
.kpi-ic{width:40px;height:40px;border-radius:10px;display:flex;align-items:center;justify-content:center}
.k1 .kpi-ic{background:#eff6ff}.k2 .kpi-ic{background:#f0fdf4}.k3 .kpi-ic{background:#fffbeb}.k4 .kpi-ic{background:#f5f3ff}.k5 .kpi-ic{background:#e0f2fe}
.ktag{font-size:10px;font-weight:600;padding:3px 8px;border-radius:20px}
.ktag.g{background:#dcfce7;color:#16a34a}.ktag.n{background:#f8fafc;color:#64748b}.ktag.w{background:#fef3c7;color:#92400e}
.kn{font-size:26px;font-weight:700;color:#0f172a;line-height:1;letter-spacing:-.5px}
.kl{font-size:12px;color:#64748b;margin-top:4px}
/* GRID 2 */
.g2{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:24px}
.gc{display:flex;flex-direction:column;gap:20px}
/* CARD */
.card{background:#fff;border:1px solid #e2e8f0;border-radius:14px;padding:20px}
.shd{display:flex;align-items:center;justify-content:space-between;margin-bottom:14px}
.st{font-size:14px;font-weight:700;color:#0f172a}
.sl{font-size:12px;color:#2563eb;font-weight:600;cursor:pointer}
.sl:hover{text-decoration:underline}
/* ORDEN CARD */
.oc{background:#fff;border:1px solid #e2e8f0;border-radius:14px;padding:24px;margin-bottom:20px;border-left:4px solid #2563eb}
.oc-top{display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:16px}
.oc-num{font-size:11px;color:#64748b;margin-bottom:4px;font-weight:500}
.oc-title{font-size:15px;font-weight:700;color:#0f172a;margin-bottom:6px}
.oc-meta{display:flex;gap:14px;flex-wrap:wrap;margin-top:6px}
.oc-mi{font-size:12px;color:#64748b}
.rc{display:inline-flex;align-items:center;gap:6px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:20px;padding:4px 10px;font-size:11px;font-weight:500;margin-top:8px}
.rdot{width:6px;height:6px;border-radius:50%;background:#22c55e;flex-shrink:0}
/* TIMELINE 8 FASES */
.phases{display:flex;position:relative;margin:24px 0 20px;padding:0 4px}
.phases::before{content:'';position:absolute;top:14px;left:20px;right:20px;height:2px;background:#e2e8f0;z-index:0}
.pp{position:absolute;top:14px;left:20px;height:2px;background:#2563eb;z-index:1;transition:width .5s}
.ph-item{flex:1;display:flex;flex-direction:column;align-items:center;gap:5px;position:relative;z-index:2}
.ph-c{width:28px;height:28px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:10px;font-weight:700;border:2px solid #e2e8f0;background:#fff;transition:.2s}
.ph-done .ph-c{background:#2563eb;border-color:#2563eb;color:#fff}
.ph-active .ph-c{background:#fff;border-color:#2563eb;color:#2563eb;box-shadow:0 0 0 4px #dbeafe}
.ph-pending .ph-c{background:#f8fafc;color:#94a3b8;border-color:#e2e8f0}
.ph-l{font-size:8px;color:#94a3b8;text-align:center;font-weight:500;white-space:nowrap}
.ph-done .ph-l{color:#2563eb;font-weight:600}
.ph-active .ph-l{color:#2563eb;font-weight:700}
/* SECTION inside orden */
.os{background:#f8fafc;border:1px solid #f1f5f9;border-radius:12px;padding:16px;margin-bottom:14px}
.os-t{font-size:10px;font-weight:700;color:#94a3b8;letter-spacing:.8px;text-transform:uppercase;margin-bottom:12px}
/* COT TABLE */
.ct{width:100%;border-collapse:collapse}
.ct thead th{font-size:10px;font-weight:700;color:#94a3b8;letter-spacing:.6px;text-transform:uppercase;padding:8px 12px;background:#f1f5f9;border-bottom:1px solid #e2e8f0;text-align:left}
.ct tbody td{padding:9px 12px;border-bottom:1px solid #f1f5f9;font-size:13px;vertical-align:middle}
.ct tbody tr:last-child td{border-bottom:none}
.ct tbody tr:hover td{background:#fafbff}
.ct-total td{background:#eff6ff!important;font-weight:700;color:#2563eb;border-top:2px solid #bfdbfe!important}
.cat-b{font-size:10px;font-weight:600;padding:2px 8px;border-radius:10px;background:#eff6ff;color:#2563eb}
.cat-b.s{background:#f0fdf4;color:#166534}
/* EVIDENCE */
.ev-cat{font-size:10px;font-weight:700;color:#94a3b8;text-transform:uppercase;letter-spacing:.7px;margin:12px 0 8px}
.ev-grid{display:flex;flex-wrap:wrap;gap:8px}
.ev-th{width:88px;height:88px;border-radius:10px;border:1px solid #e2e8f0;overflow:hidden;cursor:pointer;background:#f1f5f9;flex-shrink:0;position:relative}
.ev-th img,.ev-th video{width:100%;height:100%;object-fit:cover}
.ev-play{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,.3);color:#fff;font-size:20px}
/* HISTORIAL */
.hl{display:flex;gap:12px;padding:8px 0;border-bottom:1px solid #f1f5f9}
.hl:last-child{border-bottom:none}
.hdot{width:8px;height:8px;border-radius:50%;background:#2563eb;flex-shrink:0;margin-top:4px}
.hf{font-size:10px;color:#94a3b8;min-width:110px;flex-shrink:0}
.ha{font-size:12px;color:#334155;flex:1}
.hu{font-size:10px;color:#94a3b8}
/* FLEET TABLE */
.ft{width:100%;border-collapse:collapse}
.ft thead th{font-size:10px;font-weight:700;color:#94a3b8;letter-spacing:.8px;text-transform:uppercase;padding:10px 14px;background:#f8fafc;border-bottom:1px solid #e2e8f0;text-align:left}
.fr{cursor:pointer}
.fr:hover td{background:#fafbff}
.fr td{padding:11px 14px;border-bottom:1px solid #f1f5f9;vertical-align:middle;font-size:13px}
.fr:last-child td{border-bottom:none}
.placa{font-size:13px;font-weight:700;color:#0f172a;background:#f1f5f9;display:inline-block;padding:3px 9px;border-radius:6px;letter-spacing:.5px}
.fbar-w{height:4px;background:#f1f5f9;border-radius:2px;width:80px;overflow:hidden;margin-bottom:3px}
.fbar{height:100%;border-radius:2px}
/* CITA */
.ci{display:flex;align-items:center;gap:14px;padding:14px 16px;border-bottom:1px solid #f1f5f9}
.ci:last-child{border-bottom:none}
.ci-db{min-width:46px;height:52px;background:#eff6ff;border-radius:10px;display:flex;flex-direction:column;align-items:center;justify-content:center;flex-shrink:0}
.ci-day{font-size:20px;font-weight:800;color:#2563eb;line-height:1}
.ci-mon{font-size:9px;font-weight:700;color:#2563eb;text-transform:uppercase;letter-spacing:.5px}
.ci-tit{font-size:13px;font-weight:600;color:#0f172a}
.ci-sub{font-size:12px;color:#64748b;margin-top:2px}
.ci-tag{margin-left:auto;font-size:10px;font-weight:600;padding:3px 9px;border-radius:20px;background:#dcfce7;color:#166534;flex-shrink:0}
.ci-tag.p{background:#fef3c7;color:#92400e}
/* INVERSION BOX */
.inv-box{background:linear-gradient(135deg,#1d4ed8,#2563eb);border-radius:14px;padding:20px;color:#fff;margin-bottom:20px}
.inv-title{font-size:11px;font-weight:700;letter-spacing:1px;text-transform:uppercase;opacity:.8;margin-bottom:16px}
.inv-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}
.inv-item{background:rgba(255,255,255,.12);border-radius:10px;padding:12px}
.inv-num{font-size:22px;font-weight:800;line-height:1}
.inv-lbl{font-size:10px;opacity:.75;margin-top:4px}
.inv-detail{margin-top:16px;padding-top:14px;border-top:1px solid rgba(255,255,255,.2)}
.inv-row{display:flex;justify-content:space-between;font-size:12px;padding:4px 0;opacity:.85}
.inv-row.tot{font-weight:700;font-size:14px;opacity:1;border-top:1px solid rgba(255,255,255,.3);margin-top:4px;padding-top:8px}
/* VIEWS */
.view{display:none}
.view.on{display:block}
/* EMPTY */
.empty{text-align:center;padding:36px 20px;color:#94a3b8;font-size:13px}
/* LIGHTBOX */
#lb{display:none;position:fixed;inset:0;background:rgba(0,0,0,.93);z-index:9999;align-items:center;justify-content:center;cursor:pointer}
#lb.on{display:flex}
#lb img,#lb video{max-width:90vw;max-height:90vh;border-radius:12px;object-fit:contain;cursor:default}
#lb-x{position:absolute;top:18px;right:22px;color:#fff;font-size:30px;cursor:pointer;line-height:1;opacity:.8}
#lb-x:hover{opacity:1}
/* APROBACION */
.ap-ok{background:#dcfce7;color:#166534;padding:5px 12px;border-radius:20px;font-size:11px;font-weight:600;display:inline-block}
.ap-pend{background:#fef3c7;color:#92400e;padding:5px 12px;border-radius:20px;font-size:11px;font-weight:600;display:inline-block}
.ap-rech{background:#fee2e2;color:#991b1b;padding:5px 12px;border-radius:20px;font-size:11px;font-weight:600;display:inline-block}
"""

SVG = {
    'dash': '<svg fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>',
    'car':  '<svg fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path d="M5 17H3a2 2 0 01-2-2V5a2 2 0 012-2h11l5 5v5"/><circle cx="16" cy="17" r="2"/><circle cx="7" cy="17" r="2"/></svg>',
    'ord':  '<svg fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg>',
    'hist': '<svg fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"/></svg>',
    'cal':  '<svg fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/></svg>',
    'bldg': '<svg fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path d="M3 9l9-7 9 7v11a2 2 0 01-2 2H5a2 2 0 01-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>',
    'user': '<svg fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><circle cx="12" cy="8" r="4"/><path d="M4 20c0-4 3.6-7 8-7s8 3 8 7"/></svg>',
    'inv':  '<svg fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>',
}

def _ni(view, icon_key, label, active, badge=None, red=False):
    cls = 'ni on' if active == view else 'ni'
    b = ''
    if badge:
        bcls = 'nb red' if red else 'nb'
        b = f'<span class="{bcls}">{badge}</span>'
    return f'<div class="{cls}" onclick="sv(\'{view}\')" id="n-{view}">{SVG[icon_key]}<span class="nl">{label}</span>{b}</div>'

# ─── Phase timeline ───────────────────────────────────────────────────────────

def _phases_html(estado):
    fi = _fase_idx(estado)
    # Timeline visual muestra 7 fases (excluye ARCHIVADO — es estado final silencioso)
    show = FASES[:7]
    pct = int(fi / (len(show)-1) * 100) if fi > 0 else 0
    pct = min(pct, 100)
    html = f'<div class="phases"><div class="pp" style="width:{pct}%"></div>'
    for i, (_, corto) in enumerate(show):
        if i < fi:
            cls = 'ph-item ph-done'; txt = '✓'
        elif i == fi:
            cls = 'ph-item ph-active'; txt = str(i+1)
        else:
            cls = 'ph-item ph-pending'; txt = str(i+1)
        html += f'<div class="{cls}"><div class="ph-c">{txt}</div><div class="ph-l">{corto}</div></div>'
    html += '</div>'
    return html

# ─── Full order card ──────────────────────────────────────────────────────────

def _orden_card(o):
    placa  = _esc(o.vehiculo_placa or '')
    fecha  = str(o.fecha or '')[:10]
    tec    = _esc(o.tecnico or 'Sin asignar')
    km     = _esc(o.km or '--')
    motivo = _esc((o.motivo or '')[:80])
    diag_t = _esc(o.diagnostico or '')
    notas  = _esc(o.notas_entrega or '')

    # Aprobación
    ap = _n(o.approval_status or '')
    if 'apro' in ap:
        ap_html = f'<span class="ap-ok">✓ Aprobado {_esc(o.approval_date or "")}</span>'
    elif 'rech' in ap:
        ap_html = f'<span class="ap-rech">✗ Rechazado {_esc(o.approval_date or "")}</span>'
    else:
        ap_html = '<span class="ap-pend">⏳ Pendiente aprobación</span>'

    # Cotización
    items  = [i for i in (o.items_cotizacion or []) if isinstance(i, dict)]
    normal = [i for i in items if i.get('categoria') not in ('Resumen','Impuesto','Total','')]
    resumen= [i for i in items if i.get('categoria') in ('Resumen','Impuesto','Total')]

    cot_body = ''
    if normal:
        rows = ''
        for it in normal:
            cat = it.get('categoria','Repuesto')
            bc  = 'cat-b s' if cat == 'Servicio' else 'cat-b'
            cant = it.get('cantidad', 1) or 1
            tot  = float(it.get('total', 0) or 0)
            pu   = tot / int(cant) if int(cant) > 0 else tot
            rows += (f'<tr><td><span class="{bc}">{_esc(cat)}</span></td>'
                     f'<td style="font-weight:500;color:#0f172a">{_esc(it.get("nombre",""))}</td>'
                     f'<td style="text-align:center;color:#64748b">{cant}</td>'
                     f'<td style="text-align:right;color:#64748b">S/ {pu:,.2f}</td>'
                     f'<td style="text-align:right;font-weight:600">S/ {tot:,.2f}</td></tr>')
        for it in resumen:
            nom = _esc(it.get('nombre',''))
            tot = float(it.get('total', it.get('precio_unitario', 0)) or 0)
            is_tot = it.get('categoria') == 'Total'
            tcls = ' class="ct-total"' if is_tot else ''
            rows += f'<tr{tcls}><td colspan="4" style="font-size:12px">{nom}</td><td style="text-align:right">S/ {tot:,.2f}</td></tr>'
        cot_body = (f'<div class="os"><div class="os-t">Presupuesto / Cotización &nbsp;{ap_html}</div>'
                    f'<table class="ct"><thead><tr><th>Tipo</th><th>Descripción</th>'
                    f'<th style="text-align:center">Cant.</th>'
                    f'<th style="text-align:right">P.Unit</th>'
                    f'<th style="text-align:right">Total</th></tr></thead>'
                    f'<tbody>{rows}</tbody></table></div>')
    else:
        cot_body = f'<div class="os"><div class="os-t">Presupuesto &nbsp;{ap_html}</div><div class="empty" style="padding:16px">Sin cotización registrada aún.</div></div>'

    # Diagnóstico
    ck = o.checklist_reparacion if isinstance(o.checklist_reparacion, dict) else {}
    dd = ck.get('diagnostic_details') or ck.get('diagnosis_form') or {}
    analysis = _esc(dd.get('analysis','') if isinstance(dd, dict) else '')
    solution = _esc(dd.get('solution','') if isinstance(dd, dict) else '')
    logs     = ck.get('repair_logs') or []

    diag_inner = ''
    if diag_t or analysis:
        diag_inner += (f'<div style="margin-bottom:10px">'
                       f'<div style="font-size:10px;font-weight:700;color:#94a3b8;text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px">Problema reportado</div>'
                       f'<div style="font-size:13px;color:#334155">{diag_t or analysis}</div></div>')
    if solution:
        diag_inner += (f'<div style="margin-bottom:10px">'
                       f'<div style="font-size:10px;font-weight:700;color:#94a3b8;text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px">Solución técnica</div>'
                       f'<div style="font-size:13px;color:#334155">{solution}</div></div>')
    if logs:
        logs_html = ''
        for lg in logs[:6]:
            if not isinstance(lg, dict): continue
            logs_html += (f'<div style="background:#f1f5f9;border-radius:8px;padding:10px;margin-bottom:8px">'
                          f'<div style="font-size:12px;font-weight:600;color:#0f172a">{_esc(lg.get("falla",""))}</div>'
                          f'<div style="font-size:11px;color:#64748b;margin-top:2px">Causa: {_esc(lg.get("causa",""))}</div>'
                          f'<div style="font-size:11px;color:#166534;margin-top:3px">✓ {_esc(lg.get("solucion",""))}</div></div>')
        diag_inner += (f'<div style="margin-top:8px">'
                       f'<div style="font-size:10px;font-weight:700;color:#94a3b8;text-transform:uppercase;letter-spacing:.5px;margin-bottom:8px">Trabajos realizados</div>'
                       f'{logs_html}</div>')
    if notas:
        diag_inner += (f'<div style="margin-top:10px;padding-top:10px;border-top:1px solid #f1f5f9">'
                       f'<div style="font-size:10px;font-weight:700;color:#94a3b8;text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px">Notas de entrega</div>'
                       f'<div style="font-size:13px;color:#334155">{notas}</div></div>')

    _diag_fb = '<div style="color:#94a3b8;font-size:13px">Sin diagnóstico registrado.</div>'
    diag_body = (f'<div class="os"><div class="os-t">Diagnóstico y trabajo realizado</div>'
                 f'{diag_inner if diag_inner else _diag_fb}</div>')

    # Evidencias
    ev = _get_ev(o)
    any_ev = any(ev[k] for k, _ in EV_CATS)
    ev_inner = ''
    if any_ev:
        for cat_key, cat_label in EV_CATS:
            urls = ev.get(cat_key, [])
            if not urls: continue
            thumbs = ''
            for url in urls:
                eu = _esc(url)
                if _is_video(url):
                    thumbs += f'<div class="ev-th" onclick="openLb(this,true)"><video src="{eu}" muted playsinline></video><div class="ev-play">▶</div></div>'
                else:
                    thumbs += f'<div class="ev-th" onclick="openLb(this,false)"><img src="{eu}" loading="lazy"/></div>'
            ev_inner += f'<div class="ev-cat">{cat_label}</div><div class="ev-grid">{thumbs}</div>'
    _ev_fb = '<div style="color:#94a3b8;font-size:13px">Sin evidencias cargadas aún.</div>'
    ev_body = (f'<div class="os"><div class="os-t">Evidencia fotográfica y video</div>'
               f'{ev_inner if ev_inner else _ev_fb}</div>')

    # Historial
    hist = o.historial or []
    hist_inner = ''
    for h in list(reversed(hist))[:12]:
        if not isinstance(h, dict): continue
        hist_inner += (f'<div class="hl"><div class="hdot"></div>'
                       f'<div class="hf">{_esc(h.get("fecha",""))}</div>'
                       f'<div class="ha">{_esc(h.get("accion",""))}</div>'
                       f'<div class="hu">{_esc(h.get("usuario",""))}</div></div>')
    _hist_fb = '<div style="color:#94a3b8;font-size:13px">Sin historial.</div>'
    hist_body = (f'<div class="os"><div class="os-t">Historial de eventos</div>'
                 f'{hist_inner if hist_inner else _hist_fb}</div>')

    # PDF
    pdf_link = ''
    if o.pdf_cotizacion:
        fname = _esc(os.path.basename(str(o.pdf_cotizacion)))
        pdf_link = f'<a href="/pdfs/{fname}" target="_blank" style="font-size:12px;color:#2563eb;font-weight:600;display:inline-flex;align-items:center;gap:4px;margin-top:6px">📄 Descargar cotización PDF</a>'

    return (f'<div class="oc">'
            f'<div class="oc-top">'
            f'<div><div class="oc-num">{_esc(o.consecutivo)}</div>'
            f'<div class="oc-title">{motivo or "(Sin descripción)"}</div>'
            f'<div class="oc-meta">'
            f'<span class="oc-mi">🚗 {placa}</span>'
            f'<span class="oc-mi">📅 {fecha}</span>'
            f'<span class="oc-mi">📏 {km} km</span>'
            f'<span class="oc-mi">🔧 {tec}</span>'
            f'</div>'
            f'<div class="rc"><div class="rdot"></div>{tec}</div>'
            f'{pdf_link}</div>'
            f'<span style="font-size:11px;font-weight:600;padding:4px 12px;border-radius:20px;{_badge_st(o.estado)}">{_esc(o.estado)}</span>'
            f'</div>'
            f'{_phases_html(o.estado)}'
            f'{diag_body}{cot_body}{ev_body}{hist_body}'
            f'</div>')

# ─── Inversión total widget ───────────────────────────────────────────────────

def _inversion_html(ords):
    completadas = [o for o in ords if _is_completed(o)]
    en_curso    = [o for o in ords if _is_active(o)]
    total_pagado = sum(_grand_total(o) for o in completadas)
    total_activo = sum(_grand_total(o) for o in en_curso)
    total_global = total_pagado + total_activo

    # Desglose por tipo de trabajo (últimas 5 completadas)
    detalle = ''
    for o in completadas[-5:]:
        t = _grand_total(o)
        if t > 0:
            detalle += (f'<div class="inv-row">'
                        f'<span>{_esc(o.consecutivo)} · {_esc(o.vehiculo_placa or "")}</span>'
                        f'<span>S/ {t:,.2f}</span></div>')
    if total_activo > 0:
        detalle += (f'<div class="inv-row">'
                    f'<span>En proceso ({len(en_curso)} orden{"es" if len(en_curso)>1 else ""})</span>'
                    f'<span>S/ {total_activo:,.2f}</span></div>')
    detalle += f'<div class="inv-row tot"><span>TOTAL INVERTIDO</span><span>S/ {total_global:,.2f}</span></div>'

    return (f'<div class="inv-box">'
            f'<div class="inv-title">Resumen de inversión en Sandoval</div>'
            f'<div class="inv-grid">'
            f'<div class="inv-item"><div class="inv-num">S/ {total_pagado:,.0f}</div><div class="inv-lbl">Pagado / Completado</div></div>'
            f'<div class="inv-item"><div class="inv-num">S/ {total_activo:,.0f}</div><div class="inv-lbl">En proceso actual</div></div>'
            f'<div class="inv-item"><div class="inv-num">{len(ords)}</div><div class="inv-lbl">Servicios totales</div></div>'
            f'</div>'
            f'<div class="inv-detail">{detalle}</div>'
            f'</div>')

# ─── View builders ────────────────────────────────────────────────────────────

def _fleet_pct(estado):
    fi = _fase_idx(estado)
    return int(fi / 7 * 100)

def _fleet_col(estado):
    e = _n(estado)
    if 'archiv' in e or 'entreg' in e: return '#16a34a'
    if 'control' in e:                 return '#0369a1'
    if 'repar'   in e:                 return '#d97706'
    if 'aprob'   in e:                 return '#854d0e'
    if 'repues'  in e:                 return '#1e40af'
    if 'diagn'   in e:                 return '#6d28d9'
    return '#94a3b8'

def _cita_row(c):
    try:
        fd  = datetime.strptime(str(c.fecha_cita)[:10], '%Y-%m-%d')
        day = fd.strftime('%d'); mon = MESES[fd.month-1]
    except:
        day = '--'; mon = '---'
    pend = _n(c.estado or '') in ('pendiente','programada','pend')
    tag  = f'<span class="ci-tag{"  p" if pend else ""}">{"Pendiente" if pend else "Confirmada"}</span>'
    placa = _esc(getattr(c,'vehiculo_placa','') or '')
    hora  = str(c.hora or '')[:5] if hasattr(c,'hora') else ''
    return (f'<div class="ci">'
            f'<div class="ci-db"><div class="ci-day">{day}</div><div class="ci-mon">{mon}</div></div>'
            f'<div style="flex:1"><div class="ci-tit">{_esc(c.motivo or "Cita programada")}</div>'
            f'<div class="ci-sub">{hora}{" · " if hora else ""}{placa}</div></div>'
            f'{tag}</div>')

def _vw_dashboard(cli, vehs, ords, ord_act, citas_fut, es_empresa):
    nombre = cli.nombre if es_empresa else f"{cli.nombre} {cli.apellidos or ''}".strip()
    en_t   = sum(1 for o in ord_act if _fase_idx(o.estado) < 5)
    listos = sum(1 for o in ord_act if _fase_idx(o.estado) in (5,6))
    compl  = len([o for o in ords if _is_completed(o)])
    total_inv = sum(_grand_total(o) for o in ords)

    kpis = (f'<div class="kg">'
            f'<div class="kpi k1"><div class="kpi-tp"><div class="kpi-ic"><svg width="20" height="20" fill="none" viewBox="0 0 24 24" stroke="#2563eb" stroke-width="2"><path d="M5 17H3a2 2 0 01-2-2V5a2 2 0 012-2h11l5 5v5"/><circle cx="16" cy="17" r="2"/><circle cx="7" cy="17" r="2"/></svg></div><span class="ktag n">Total</span></div><div class="kn">{len(vehs)}</div><div class="kl">Vehículos registrados</div></div>'
            f'<div class="kpi k2"><div class="kpi-tp"><div class="kpi-ic"><svg width="20" height="20" fill="none" viewBox="0 0 24 24" stroke="#16a34a" stroke-width="2"><path d="M14.7 6.3a1 1 0 000 1.4l1.6 1.6a1 1 0 001.4 0l3.77-3.77a6 6 0 01-7.94 7.94l-6.91 6.91a2.12 2.12 0 01-3-3l6.91-6.91a6 6 0 017.94-7.94l-3.76 3.76z"/></svg></div><span class="ktag g">Activos</span></div><div class="kn">{en_t}</div><div class="kl">En taller ahora</div></div>'
            f'<div class="kpi k3"><div class="kpi-tp"><div class="kpi-ic"><svg width="20" height="20" fill="none" viewBox="0 0 24 24" stroke="#d97706" stroke-width="2"><path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/></svg></div><span class="ktag w">Listos</span></div><div class="kn">{listos}</div><div class="kl">Listo para recoger</div></div>'
            f'<div class="kpi k5"><div class="kpi-tp"><div class="kpi-ic">{SVG["inv"]}</div><span class="ktag n">Total</span></div><div class="kn">S/ {total_inv:,.0f}</div><div class="kl">Inversión acumulada</div></div>'
            f'</div>')

    # Fleet table
    fleet_rows = ''
    for v in vehs[:5]:
        ord_v  = next((o for o in ord_act if o.vehiculo_placa == v.placa), None)
        estado = ord_v.estado if ord_v else 'Sin orden'
        pct    = _fleet_pct(estado)
        col    = _fleet_col(estado)
        modelo = f"{v.marca or ''} {v.modelo or ''} {getattr(v,'año','') or ''}".strip()
        fleet_rows += (f'<tr class="fr">'
                       f'<td><div class="placa">{_esc(v.placa)}</div><div style="font-size:11px;color:#64748b;margin-top:2px">{_esc(modelo)}</div></td>'
                       f'<td><div class="fbar-w"><div class="fbar" style="width:{pct}%;background:{col}"></div></div><div style="font-size:10px;color:#64748b">{_esc(estado)}</div></td>'
                       f'<td>{_badge(estado)}</td></tr>')
    fleet_card = (f'<div class="card"><div class="shd"><span class="st">Estado de flota</span>'
                  f'<span class="sl" onclick="sv(\'flota\')">Ver todas →</span></div>'
                  f'<table class="ft"><thead><tr><th>Vehículo</th><th>Progreso</th><th>Estado</th></tr></thead>'
                  f'<tbody>{fleet_rows or "<tr><td colspan=3 class=empty>Sin vehículos</td></tr>"}</tbody></table></div>')

    # Recent history
    ord_hist = [o for o in ords if _is_completed(o)]
    hist_rows = ''
    for o in ord_hist[:4]:
        t = _grand_total(o)
        hist_rows += (f'<tr class="fr"><td style="font-size:11px;font-weight:600;color:#334155">{_esc(o.consecutivo)}</td>'
                      f'<td><div style="font-size:12px;font-weight:500;color:#0f172a">{_esc((o.motivo or "")[:45])}</div>'
                      f'<div style="font-size:10px;color:#64748b">{_esc(o.vehiculo_placa or "")} · {str(o.fecha or "")[:10]}</div></td>'
                      f'<td style="font-weight:700;color:#0f172a">S/ {t:,.0f}</td>'
                      f'<td>{_badge(o.estado)}</td></tr>')
    hist_card = (f'<div class="card"><div class="shd"><span class="st">Últimas órdenes</span>'
                 f'<span class="sl" onclick="sv(\'historial\')">Ver historial →</span></div>'
                 f'<table class="ft"><thead><tr><th>Orden</th><th>Descripción</th><th>Monto</th><th>Estado</th></tr></thead>'
                 f'<tbody>{hist_rows or "<tr><td colspan=4 class=empty>Sin historial</td></tr>"}</tbody></table></div>')

    # Active order (primera)
    if ord_act:
        o = ord_act[0]
        more = f'<span class="sl" onclick="sv(\'ordenes\')">{len(ord_act)} activas →</span>' if len(ord_act) > 1 else ''
        act_sec = (f'<div><div class="shd"><span class="st">Orden activa — {_esc(o.vehiculo_placa or "")}</span>{more}</div>'
                   f'{_orden_card(o)}</div>')
    else:
        act_sec = '<div class="card"><div class="empty">No hay órdenes activas.</div></div>'

    # Citas
    citas_html = ''.join(_cita_row(c) for c in citas_fut[:3])
    citas_card = (f'<div class="card"><div class="shd"><span class="st">Próximas citas</span>'
                  f'<span class="sl" onclick="sv(\'citas\')">Ver todas →</span></div>'
                  f'{citas_html or "<div class=empty>Sin citas programadas</div>"}</div>')

    return (f'<div class="ph"><h1>Dashboard</h1>'
            f'<p>Bienvenido, {_esc(nombre)} — {datetime.now().strftime("%d/%m/%Y")}</p></div>'
            f'{kpis}'
            f'{_inversion_html(ords)}'
            f'<div class="g2"><div class="gc">{fleet_card}{hist_card}</div>'
            f'<div class="gc">{act_sec}{citas_card}</div></div>')


def _vw_flota(vehs, ord_act):
    rows = ''
    for v in vehs:
        ord_v  = next((o for o in ord_act if o.vehiculo_placa == v.placa), None)
        estado = ord_v.estado if ord_v else 'Sin orden activa'
        pct    = _fleet_pct(estado)
        col    = _fleet_col(estado)
        modelo = f"{v.marca or ''} {v.modelo or ''} {getattr(v,'año','') or ''}".strip()
        rows += (f'<tr class="fr"><td><div class="placa">{_esc(v.placa)}</div>'
                 f'<div style="font-size:11px;color:#64748b;margin-top:2px">{_esc(modelo)}</div></td>'
                 f'<td style="font-size:12px;color:#64748b">{_esc(v.tipo or "")}</td>'
                 f'<td><div class="fbar-w"><div class="fbar" style="width:{pct}%;background:{col}"></div></div>'
                 f'<div style="font-size:10px;color:#64748b">{_esc(estado)}</div></td>'
                 f'<td>{_badge(estado)}</td></tr>')
    return (f'<div class="ph"><h1>Mi Flota</h1><p>{len(vehs)} vehículos registrados</p></div>'
            f'<div class="card"><table class="ft">'
            f'<thead><tr><th>Vehículo</th><th>Tipo</th><th>Progreso</th><th>Estado</th></tr></thead>'
            f'<tbody>{rows or "<tr><td colspan=4 class=empty>Sin vehículos</td></tr>"}</tbody>'
            f'</table></div>')


def _vw_ordenes(ord_act):
    if not ord_act:
        return '<div class="ph"><h1>Órdenes Activas</h1></div><div class="card"><div class="empty">No hay órdenes activas en este momento.</div></div>'
    cards = ''.join(_orden_card(o) for o in ord_act)
    return f'<div class="ph"><h1>Órdenes Activas</h1><p>{len(ord_act)} en proceso</p></div>{cards}'


def _vw_historial(ords):
    completadas = [o for o in ords if _is_completed(o)]
    cards = ''.join(_orden_card(o) for o in completadas)
    total = sum(_grand_total(o) for o in completadas)
    resumen = (f'<div class="card" style="margin-bottom:20px;background:linear-gradient(135deg,#f0fdf4,#dcfce7);border-color:#bbf7d0">'
               f'<div style="font-size:13px;font-weight:700;color:#166534">{len(completadas)} servicios completados · Total invertido: S/ {total:,.2f}</div></div>') if completadas else ''
    return (f'<div class="ph"><h1>Historial de Servicios</h1>'
            f'<p>{len(completadas)} servicios completados</p></div>'
            f'{resumen}'
            f'{cards or "<div class=card><div class=empty>Sin historial de servicios.</div></div>"}')


def _vw_citas(citas_all):
    ahora = datetime.now().strftime('%Y-%m-%d')
    fut   = [c for c in citas_all if str(c.fecha_cita or '')[:10] >= ahora]
    pas   = [c for c in citas_all if str(c.fecha_cita or '')[:10] < ahora]
    fut_html = ''.join(_cita_row(c) for c in fut) or '<div class="empty">Sin citas próximas</div>'
    pas_html = ''.join(_cita_row(c) for c in pas[:6]) or '<div class="empty">Sin citas anteriores</div>'
    return (f'<div class="ph"><h1>Citas Programadas</h1><p>{len(fut)} próximas · {len(pas)} anteriores</p></div>'
            f'<div class="card" style="margin-bottom:20px"><div class="shd"><span class="st">Próximas citas</span></div>{fut_html}</div>'
            f'<div class="card"><div class="shd"><span class="st">Anteriores</span></div>{pas_html}</div>')


def _vw_empresa(cli, vehs, ords):
    nombre = cli.nombre or ''
    email  = getattr(cli,'email','') or ''
    tel    = getattr(cli,'telefono','') or ''
    init   = ''.join(p[0].upper() for p in nombre.split()[:2]) or 'E'
    return (f'<div class="ph"><h1>Mi Empresa</h1></div>'
            f'<div style="background:linear-gradient(135deg,#eff6ff,#f0f9ff);border:1px solid #bfdbfe;border-radius:14px;padding:24px;margin-bottom:24px;display:flex;align-items:center;gap:20px">'
            f'<div style="width:64px;height:64px;background:#2563eb;border-radius:16px;display:flex;align-items:center;justify-content:center;font-size:24px;font-weight:800;color:#fff;flex-shrink:0;box-shadow:0 4px 12px rgba(37,99,235,.3)">{init}</div>'
            f'<div><div style="font-size:20px;font-weight:800;color:#0f172a">{_esc(nombre)}</div>'
            f'<div style="font-size:13px;color:#64748b;margin-top:3px">RUC {_esc(str(cli.id))}{" · "+_esc(email) if email else ""}{" · "+_esc(tel) if tel else ""}</div></div></div>'
            f'{_inversion_html(ords)}')


# ─── Entry point ─────────────────────────────────────────────────────────────

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
        citas_all   = db.query(Cita).filter_by(cliente_id=cli.id).order_by(Cita.fecha_cita).all()
        ahora       = datetime.now().strftime('%Y-%m-%d')
        citas_fut   = [c for c in citas_all if str(c.fecha_cita or '')[:10] >= ahora]
        ord_act     = [o for o in ords if not _is_completed(o)]
        nombre_disp = cli.nombre if es_empresa else f"{cli.nombre} {cli.apellidos or ''}".strip()
        initials    = ''.join(p[0].upper() for p in nombre_disp.split()[:2]) or 'C'
        en_t        = sum(1 for o in ord_act if _fase_idx(o.estado) < 5)
        lst         = sum(1 for o in ord_act if _fase_idx(o.estado) in (5,6))

        # Sidebar empresa card
        emp_card = ''
        if es_empresa:
            emp_card = (f'<div class="sb-emp"><div class="sb-emp-lbl">Mi empresa</div>'
                        f'<div class="sb-emp-nm">{_esc(cli.nombre)}</div>'
                        f'<div class="sb-emp-ruc">RUC {_esc(str(cli.id))}</div>'
                        f'<div class="sb-emp-fl">'
                        f'<div class="sb-stat"><div class="sb-stat-n">{len(vehs)}</div><div class="sb-stat-l">Vehículos</div></div>'
                        f'<div class="sb-stat"><div class="sb-stat-n" style="color:#d97706">{en_t}</div><div class="sb-stat-l">En taller</div></div>'
                        f'<div class="sb-stat"><div class="sb-stat-n" style="color:#16a34a">{lst}</div><div class="sb-stat-l">Listos</div></div>'
                        f'</div></div>')

        b_ord = f'<span class="nb red">{len(ord_act)}</span>' if ord_act else ''
        b_veh = f'<span class="nb">{len(vehs)}</span>' if len(vehs) > 1 else ''
        emp_nav  = (f'<div class="sb-sec">Empresa</div>'
                    f'<div class="ni" onclick="sv(\'empresa\')" id="n-empresa">{SVG["bldg"]}<span class="nl">Mi Empresa</span></div>') if es_empresa else ''
        emp_view = f'<div class="view" id="v-empresa">{_vw_empresa(cli, vehs, ords)}</div>' if es_empresa else ''

        html = f'''<div id="pr">
<style>{CSS}</style>

<div class="tb">
  <div class="tb-l">
    <div class="logo">S</div>
    <div><div class="bn">Mecánica Sandoval</div><div class="bs">Portal del Cliente</div></div>
  </div>
  <div class="tb-r">
    <div class="uc">
      <div class="ua">{initials}</div>
      <div><div class="un">{_esc(nombre_disp)}</div><div class="ur">{"Cliente Corporativo" if es_empresa else "Cliente"}</div></div>
    </div>
    <button class="logout" onclick="location.href='/portal-logout'">Cerrar sesión</button>
  </div>
</div>

<div class="ly">
  <nav class="sb">
    {emp_card}
    <div class="sb-sec">Principal</div>
    {_ni('dashboard','dash','Dashboard','dashboard',active='dashboard')}
    {_ni('flota','car','Mi Flota','flota',badge=str(len(vehs)) if len(vehs)>1 else None)}
    <div class="sb-sec">Servicios</div>
    {_ni('ordenes','ord','Órdenes Activas','ordenes',badge=str(len(ord_act)) if ord_act else None,red=True)}
    {_ni('historial','hist','Historial','historial')}
    {_ni('citas','cal','Citas','citas')}
    {emp_nav}
    <div class="sb-sec">Cuenta</div>
    {_ni('perfil','user','Mi Perfil','perfil')}
  </nav>

  <main class="mn">
    <div class="view on" id="v-dashboard">{_vw_dashboard(cli,vehs,ords,ord_act,citas_fut,es_empresa)}</div>
    <div class="view" id="v-flota">{_vw_flota(vehs,ord_act)}</div>
    <div class="view" id="v-ordenes">{_vw_ordenes(ord_act)}</div>
    <div class="view" id="v-historial">{_vw_historial(ords)}</div>
    <div class="view" id="v-citas">{_vw_citas(citas_all)}</div>
    {emp_view}
    <div class="view" id="v-perfil">
      <div class="ph"><h1>Mi Perfil</h1></div>
      <div class="card">
        <div style="font-size:15px;font-weight:700;color:#0f172a;margin-bottom:6px">{_esc(nombre_disp)}</div>
        <div style="font-size:13px;color:#64748b">{"RUC " if es_empresa else "DNI "}{_esc(str(cli.id))}</div>
      </div>
    </div>
  </main>
</div>

<div id="lb" onclick="closeLb()">
  <span id="lb-x">✕</span>
  <div id="lb-c"></div>
</div>

<script>
function sv(name) {{
  document.querySelectorAll('.view').forEach(function(v){{v.classList.remove('on')}});
  document.querySelectorAll('.ni').forEach(function(n){{n.classList.remove('on')}});
  var el = document.getElementById('v-' + name);
  if (el) el.classList.add('on');
  var nav = document.getElementById('n-' + name);
  if (nav) nav.classList.add('on');
  window.scrollTo(0,0);
}}
function openLb(el, isVid) {{
  var src = isVid ? el.querySelector('video').src : el.querySelector('img').src;
  document.getElementById('lb-c').innerHTML = isVid
    ? '<video src="'+src+'" controls autoplay style="max-width:90vw;max-height:90vh;border-radius:12px"></video>'
    : '<img src="'+src+'" style="max-width:90vw;max-height:90vh;border-radius:12px;object-fit:contain"/>';
  document.getElementById('lb').classList.add('on');
}}
function closeLb() {{
  document.getElementById('lb').classList.remove('on');
  document.getElementById('lb-c').innerHTML='';
}}
document.addEventListener('keydown',function(e){{if(e.key==='Escape')closeLb();}});
</script>
</div>'''

        ui.add_body_html(html)

    finally:
        db.close()


def show_portal(_container=None):
    """Fallback desde frame admin — redirige al portal dedicado."""
    ui.navigate.to('/portal')

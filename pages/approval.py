"""
SANDOVAL Dashboard - Página de Aprobación Pública
El cliente puede ver su orden y aprobar/rechazar sin login.
Acceso: GET  /aprobacion/{token}
        POST /api/aprobacion/{token}/respond  (JSON: {status, comentario})

Se renderiza como HTML puro (fuera del stack NiceGUI/Quasar) para que el
cliente vea el documento tipo presupuesto con estilos profesionales sin
interferencias del framework.
"""

from datetime import datetime
import html as _html
import os

from utils.models import get_db, Orden, Cliente, Vehiculo, log_actividad
from utils.pdf_generator import generate_pdf


# ═════════════════════════ helpers ═════════════════════════
def _esc(s):
    if s is None:
        return '—'
    return _html.escape(str(s))


def _fmt_money(n):
    try:
        return "{:,.2f}".format(float(n or 0))
    except Exception:
        return "0.00"


def _safe_int(v, default=0):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default


_CSS = """
:root {
  --primary:#274495; --primary-dark:#1e3475;
  --accent:#d97706; --emerald:#059669; --red:#dc2626;
  --slate-900:#0f172a; --slate-700:#334155; --slate-500:#64748b;
  --slate-300:#cbd5e1; --slate-100:#f1f5f9; --slate-50:#f8fafc;
  --paper:#ffffff; --bg:#eef2f7;
}
*,*::before,*::after{box-sizing:border-box;}
html,body{margin:0;padding:0;}
body{
  background:var(--bg); color:var(--slate-900);
  font-family:'Inter','Segoe UI',system-ui,sans-serif;
  font-size:14px; line-height:1.55;
  -webkit-font-smoothing:antialiased;
}
h1,h2,h3,h4,p{margin:0;padding:0;}
.doc-wrap{max-width:960px;margin:0 auto;padding:28px 16px 140px;}
.doc{
  background:var(--paper); border-radius:6px;
  box-shadow:0 6px 40px rgba(15,23,42,.08),0 0 0 1px rgba(15,23,42,.04);
  overflow:hidden;
}
/* ── Header corporativo ─────────────────────────── */
.doc-head{
  display:grid; grid-template-columns:96px 1fr auto; gap:22px;
  padding:30px 38px;
  background:linear-gradient(135deg,var(--primary) 0%,var(--primary-dark) 100%);
  color:#fff; align-items:center;
}
.doc-head .logo{
  width:86px;height:86px;border-radius:14px;background:#fff;padding:8px;
  box-shadow:0 10px 30px rgba(0,0,0,.2); object-fit:contain; display:block;
}
.doc-head .co-name{
  font-size:22px; font-weight:800; letter-spacing:-.4px; margin:0 0 4px;
  line-height:1.15;
}
.doc-head .co-sub{font-size:11.5px; opacity:.9; margin:0; letter-spacing:.3px;}
.doc-head .co-sub.m{opacity:.7;margin-top:3px;}
.doc-head .doc-id{
  background:rgba(255,255,255,.12); border:1px solid rgba(255,255,255,.25);
  padding:12px 18px; border-radius:10px; text-align:right; min-width:240px;
}
.doc-head .doc-id .lbl{font-size:9px;letter-spacing:2.4px;text-transform:uppercase;
  opacity:.8;font-weight:700;}
.doc-head .doc-id .num{font-size:19px;font-weight:800;margin:3px 0;}
.doc-head .doc-id .date{font-size:11px;opacity:.85;}
/* ── Sección ─────────────────────────────────────── */
.sec{padding:26px 38px;border-top:1px solid var(--slate-100);}
.sec h2{
  font-size:12px;font-weight:800;text-transform:uppercase;letter-spacing:2.4px;
  color:var(--primary); margin:0 0 16px; padding:0 0 10px;
  border-bottom:2px solid var(--primary);
  display:inline-flex; align-items:center; gap:10px;
}
.sec h2 .num{
  display:inline-flex;align-items:center;justify-content:center;
  width:22px;height:22px;border-radius:50%;
  background:var(--primary); color:#fff; font-size:11px; font-weight:800;
}
/* ── Tablas de datos ─────────────────────────────── */
.table-scroll{
  -webkit-overflow-scrolling:touch;
  overflow-x:auto;
  border-radius:8px;
  position:relative;
}
.table-scroll::-webkit-scrollbar{height:6px;}
.table-scroll::-webkit-scrollbar-thumb{background:#cbd5e1;border-radius:4px;}
.info-table{width:100%;border-collapse:collapse;font-size:13px;}
.info-table th,.info-table td{
  padding:10px 14px;text-align:left;vertical-align:top;
  border:1px solid var(--slate-100);
}
.info-table th{
  background:var(--slate-50); color:var(--slate-500);
  font-weight:700; font-size:10.5px;
  letter-spacing:1px; text-transform:uppercase; width:26%;
}
.info-table td{color:var(--slate-900); font-weight:600; background:#fff;}
/* ── Diagnóstico ─────────────────────────────────── */
.diag-block{display:grid;grid-template-columns:1fr;gap:14px;}
.diag-row{
  border-left:4px solid var(--primary); background:var(--slate-50);
  padding:16px 20px; border-radius:0 8px 8px 0;
}
.diag-row.sol{border-left-color:var(--emerald);background:#ecfdf5;}
.diag-row.mot{border-left-color:var(--accent);background:#fffbeb;}
.diag-row .diag-lbl{
  font-size:10px;font-weight:800;text-transform:uppercase;letter-spacing:1.4px;
  color:var(--primary);margin-bottom:6px;
}
.diag-row.sol .diag-lbl{color:var(--emerald);}
.diag-row.mot .diag-lbl{color:var(--accent);}
.diag-row .diag-txt{
  font-size:14px;color:var(--slate-700);line-height:1.65;
  font-weight:500;white-space:pre-line;
}
/* ── Escáner ─────────────────────────────────────── */
.scanner-card{
  background:#ecfdf5;border:1px solid #a7f3d0;border-radius:10px;
  padding:22px;margin-top:14px;
}
.scanner-card .scan-ttl{
  font-size:13px;font-weight:800;color:#064e3b;margin-bottom:10px;
  display:flex;align-items:center;gap:8px;
}
.scanner-card iframe{
  width:100%;height:480px;border:1px solid #bbf7d0;
  border-radius:8px;background:#fff;
}
.scanner-card .scan-actions{margin-top:12px;display:flex;gap:10px;flex-wrap:wrap;}
.scanner-card .scan-actions a{
  flex:1;min-width:160px;text-align:center;text-decoration:none;
  background:var(--emerald);color:#fff;padding:10px 16px;border-radius:8px;
  font-weight:700;font-size:12px;letter-spacing:.5px;
}
.scanner-card .scan-actions a.alt{background:var(--slate-900);}
/* ── Galería ─────────────────────────────────────── */
.gallery{
  display:grid;grid-template-columns:repeat(auto-fill,minmax(170px,1fr));
  gap:12px;
}
.gallery a{
  display:block;aspect-ratio:1/1;border-radius:8px;overflow:hidden;
  border:1px solid var(--slate-100);background:var(--slate-50);
  transition:transform .15s ease,box-shadow .15s ease;
}
.gallery a:hover{transform:translateY(-2px);box-shadow:0 10px 25px rgba(0,0,0,.08);}
.gallery img{width:100%;height:100%;object-fit:cover;display:block;}
.gallery .video-item{
  background:#000;aspect-ratio:16/9;grid-column:span 2;
  border-radius:8px;overflow:hidden;
}
.gallery .video-item video{width:100%;height:100%;display:block;}
.no-evidence{
  padding:18px;border:1px dashed var(--slate-300);border-radius:8px;
  color:var(--slate-500);font-size:13px;text-align:center;background:var(--slate-50);
}
.fase-group{margin-bottom:18px;}
.fase-group:last-child{margin-bottom:0;}
.fase-head{
  display:flex;align-items:center;justify-content:space-between;
  margin-bottom:10px;padding:6px 12px;border-radius:6px;
  background:var(--slate-100);
}
.fase-tag{
  font-size:10.5px;font-weight:800;color:var(--primary);
  text-transform:uppercase;letter-spacing:1.4px;
}
.fase-count{font-size:11px;color:var(--slate-500);font-weight:600;}
/* ── Cuentas bancarias ───────────────────────────── */
.bank-intro{
  color:var(--slate-700);font-size:12.5px;margin:0 0 16px;line-height:1.6;
}
.bank-grid{
  display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));
  gap:14px;
}
.bank-card{
  border:1px solid var(--slate-300);border-radius:8px;overflow:hidden;
  background:#fff;box-shadow:0 2px 6px rgba(15,23,42,.04);
}
.bank-name{
  background:linear-gradient(135deg,var(--primary) 0%,var(--primary-dark) 100%);
  color:#fff;padding:10px 14px;font-size:13.5px;font-weight:800;
  letter-spacing:.4px;
}
.bank-table{width:100%;border-collapse:collapse;font-size:12.5px;}
.bank-table th{
  text-align:left;padding:7px 12px;background:var(--slate-50);
  color:var(--slate-500);font-weight:700;font-size:10.5px;
  text-transform:uppercase;letter-spacing:1px;width:34%;border-bottom:1px solid var(--slate-100);
}
.bank-table td{
  padding:7px 12px;color:var(--slate-900);font-weight:600;border-bottom:1px solid var(--slate-100);
}
.bank-table tr:last-child th,.bank-table tr:last-child td{border-bottom:0;}
.bank-table code{
  font-family:'SFMono-Regular',Consolas,monospace;background:#f1f5f9;
  padding:2px 6px;border-radius:4px;font-size:12px;color:var(--primary-dark);
  letter-spacing:.3px;
}
/* ── Tabla presupuesto ───────────────────────────── */
.items-table{width:100%;border-collapse:collapse;font-size:13px;}
.items-table thead th{
  background:var(--slate-900);color:#fff;
  padding:12px 14px;font-size:10.5px;font-weight:700;
  letter-spacing:1.2px;text-transform:uppercase;text-align:left;
}
.items-table thead th.num{text-align:right;}
.items-table tbody td{
  padding:12px 14px;border-bottom:1px solid var(--slate-100);
  background:#fff;vertical-align:top;
}
.items-table tbody tr:nth-child(even) td{background:var(--slate-50);}
.items-table tbody td.num{text-align:right;font-variant-numeric:tabular-nums;font-weight:600;}
.items-table .cat-badge{
  display:inline-block;font-size:9px;font-weight:800;
  padding:3px 8px;border-radius:20px;
  text-transform:uppercase;letter-spacing:.8px;
}
.items-table .cat-serv{background:#dbeafe;color:#1e40af;}
.items-table .cat-rep{background:#fef3c7;color:#92400e;}
.items-table tfoot td{
  padding:10px 14px;border-top:1px solid #e2e8f0;font-weight:700;
}
.items-table tfoot td.lbl{
  text-align:right;color:var(--slate-500);font-size:11.5px;
  text-transform:uppercase;letter-spacing:1px;
}
.items-table tfoot td.val{
  text-align:right;font-variant-numeric:tabular-nums;color:var(--slate-900);font-size:14px;
}
.items-table tfoot tr.total td{background:var(--primary);color:#fff;padding:14px;font-size:16px;}
.items-table tfoot tr.total td.lbl{color:rgba(255,255,255,.9);font-size:11.5px;}
.items-table tfoot tr.total td.val{font-size:22px;font-weight:800;}
/* ── Términos ─────────────────────────────────────── */
.terms-list{margin:0;padding-left:20px;color:var(--slate-700);font-size:12.5px;line-height:1.75;}
.terms-list li{margin-bottom:4px;}
/* ── Autorización ─────────────────────────────────── */
.auth-sec{
  background:linear-gradient(180deg,#f8fafc 0%,#ffffff 100%);
  padding:36px 38px; border-top:3px solid var(--primary);
}
.auth-ttl{
  text-align:center;font-size:20px;font-weight:800;color:var(--slate-900);margin:0 0 6px;
}
.auth-sub{text-align:center;color:var(--slate-500);font-size:13px;margin:0 0 22px;}
.sign-grid{display:grid;grid-template-columns:1fr 1fr;gap:24px;margin:18px 0 24px;}
.sign-box{
  border:1px dashed var(--slate-300);border-radius:8px;padding:14px 18px;background:#fff;
}
.sign-box .lbl{
  font-size:9.5px;letter-spacing:1.2px;text-transform:uppercase;
  color:var(--slate-500);font-weight:800;margin-bottom:8px;
}
.sign-box .val{font-size:15px;font-weight:800;color:var(--slate-900);}
.sign-box .sub{font-size:11.5px;color:var(--slate-500);margin-top:2px;}
.note-inp{
  width:100%;min-height:84px;padding:12px 14px;font-family:inherit;font-size:13.5px;
  border:1px solid var(--slate-300);border-radius:8px;background:#fff;
  color:var(--slate-900);resize:vertical;margin-bottom:18px;outline:none;
}
.note-inp:focus{border-color:var(--primary);box-shadow:0 0 0 3px rgba(39,68,149,.12);}
.btn-row{display:flex;gap:14px;flex-wrap:wrap;justify-content:center;margin-top:4px;}
.btn{
  display:inline-flex;align-items:center;justify-content:center;gap:8px;
  padding:14px 28px;border-radius:10px;font-weight:800;font-size:13px;
  letter-spacing:.5px;text-transform:uppercase;cursor:pointer;
  border:1px solid transparent;transition:all .15s ease; min-width:200px;
}
.btn:hover{transform:translateY(-1px);}
.btn:active{transform:translateY(0);}
.btn:disabled{opacity:.55;cursor:wait;transform:none;}
.btn-approve{background:var(--emerald);color:#fff;box-shadow:0 10px 30px rgba(5,150,105,.35);}
.btn-approve:hover{background:#047857;box-shadow:0 14px 34px rgba(5,150,105,.45);}
.btn-reject{background:#fff;color:var(--slate-500);border-color:var(--slate-300);}
.btn-reject:hover{background:var(--slate-50);color:var(--slate-700);}
.disclaimer{
  margin-top:20px;font-size:11.5px;color:var(--slate-500);
  text-align:center;line-height:1.6;
}
.doc-foot{
  padding:18px 38px;background:var(--slate-900);color:rgba(255,255,255,.75);
  font-size:11px;letter-spacing:.5px;
  display:flex;justify-content:space-between;flex-wrap:wrap;gap:10px;
}
.support-float{
  position:fixed;bottom:22px;right:22px;background:#25d366;color:#fff;
  padding:12px 20px;border-radius:100px;text-decoration:none;
  display:inline-flex;align-items:center;gap:8px;
  font-weight:700;font-size:13px;letter-spacing:.5px;
  box-shadow:0 14px 34px rgba(37,211,102,.42);z-index:1000;
}
.pdf-float{
  position:fixed;bottom:22px;left:22px;background:var(--primary);color:#fff;
  padding:12px 20px;border-radius:100px;border:0;text-decoration:none;
  display:inline-flex;align-items:center;gap:8px;cursor:pointer;
  font-weight:700;font-size:13px;letter-spacing:.5px;font-family:inherit;
  box-shadow:0 14px 34px rgba(39,68,149,.42);z-index:1000;
}
.pdf-float:disabled{opacity:.6;cursor:wait;}
.thanks-icon{
  width:88px;height:88px;background:#d1fae5;border:3px solid #059669;
  border-radius:50%;display:inline-flex;align-items:center;justify-content:center;
  font-size:46px;color:#059669;font-weight:900;margin:0 auto 16px;
}
.toast-ok{
  position:fixed;top:20px;left:50%;transform:translateX(-50%);
  background:#059669;color:#fff;padding:14px 22px;border-radius:10px;
  font-weight:700;font-size:14px;box-shadow:0 10px 30px rgba(5,150,105,.4);
  z-index:2000;opacity:0;pointer-events:none;transition:opacity .25s ease;
}
.toast-ok.show{opacity:1;}
.table-hint{display:none;}
@media print{
  body{background:#fff;}
  .support-float,.pdf-float,.scan-actions{display:none!important;}
  .doc{box-shadow:none;}
}
"""


_STATUS_PAGE_TPL = """<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=1024, user-scalable=yes, maximum-scale=5, minimum-scale=0.3">
<title>{title} · Sandoval</title>
<style>{css}</style>
</head><body>
<div class="doc-wrap">
  <div class="doc" style="padding:64px 32px;text-align:center;">
    <div style="width:84px;height:84px;border-radius:50%;background:{bg};
         color:{color};font-size:42px;font-weight:900;display:inline-flex;
         align-items:center;justify-content:center;margin-bottom:22px;
         border:3px solid {color};">{icon}</div>
    <h2 style="font-size:28px;margin:0 0 8px;color:{color};letter-spacing:-.4px;">{title}</h2>
    <div style="font-size:12px;color:#64748b;letter-spacing:1.6px;
         text-transform:uppercase;font-weight:800;margin-bottom:24px;">{subtitle}</div>
    <p style="color:#334155;font-size:14.5px;line-height:1.7;max-width:520px;margin:0 auto 28px;">{message}</p>
    <div style="margin-top:18px;">{actions}</div>
  </div>
</div>
</body></html>"""


def render_error_html(title: str, message: str) -> str:
    return _STATUS_PAGE_TPL.format(
        title=_esc(title), subtitle='Enlace no disponible',
        message=_esc(message),
        bg='#fef2f2', color='#dc2626', icon='⚠',
        css=_CSS,
        actions=('<a href="https://wa.me/51924980586" style="display:inline-block;'
                 'background:#25d366;color:#fff;padding:12px 26px;border-radius:100px;'
                 'text-decoration:none;font-weight:700;">Contactar al taller</a>'),
    )


def render_already_responded_html(order) -> str:
    approved = (order.approval_status or '').lower() == 'aprobado'
    color = '#059669' if approved else '#dc2626'
    bg = '#ecfdf5' if approved else '#fef2f2'
    icon = '✓' if approved else '✕'
    title = 'Presupuesto autorizado' if approved else 'Respuesta registrada'
    msg = ('Recibimos su autorización. Estamos iniciando los trabajos. Le informaremos '
           'sobre el avance del vehículo por WhatsApp.') if approved else \
          ('Hemos recibido su decisión. Un asesor se pondrá en contacto con usted a la brevedad.')
    actions = ''
    if approved and getattr(order, 'pdf_cotizacion', None):
        actions += (f'<a href="/{_esc(order.pdf_cotizacion)}" target="_blank" '
                    'style="display:inline-block;background:#059669;color:#fff;'
                    'padding:12px 26px;border-radius:100px;text-decoration:none;'
                    'font-weight:700;margin-right:8px;">Descargar presupuesto PDF</a>')
    actions += ('<a href="https://wa.me/51924980586" style="display:inline-block;'
                'background:#0f172a;color:#fff;padding:12px 26px;border-radius:100px;'
                'text-decoration:none;font-weight:700;">Contactar por WhatsApp</a>')
    return _STATUS_PAGE_TPL.format(
        title=_esc(title),
        subtitle=f'Orden {_esc(order.consecutivo or "")}',
        message=_esc(msg),
        bg=bg, color=color, icon=icon,
        css=_CSS, actions=actions,
    )


def _render_diag_block(order):
    diag_form = (order.checklist_reparacion or {}).get('diagnosis_form', {}) or {}
    parts = []
    if order.motivo:
        parts.append(
            f'<div class="diag-row mot">'
            f'<div class="diag-lbl">📋 Motivo de Ingreso</div>'
            f'<div class="diag-txt">{_esc(order.motivo)}</div></div>'
        )
    if diag_form.get('analysis'):
        parts.append(
            f'<div class="diag-row">'
            f'<div class="diag-lbl">🔬 Análisis del Especialista</div>'
            f'<div class="diag-txt">{_esc(diag_form["analysis"])}</div></div>'
        )
    if diag_form.get('solution'):
        parts.append(
            f'<div class="diag-row sol">'
            f'<div class="diag-lbl">✅ Solución Recomendada</div>'
            f'<div class="diag-txt">{_esc(diag_form["solution"])}</div></div>'
        )
    if not diag_form and order.diagnostico:
        parts.append(
            f'<div class="diag-row">'
            f'<div class="diag-lbl">🔧 Diagnóstico</div>'
            f'<div class="diag-txt">{_esc(order.diagnostico)}</div></div>'
        )
    if len(parts) == (1 if order.motivo else 0):
        # solo motivo o nada → mensaje
        parts.append('<div class="no-evidence">Análisis técnico pendiente de consolidación.</div>')
    return ''.join(parts)


def _render_scanner(order):
    sc_path = ((order.checklist_reparacion or {}).get('diagnostic_details', {}) or {}).get('scanner_path')
    if not sc_path:
        return ''
    sp = _esc(sc_path)
    return (
        '<div class="scanner-card">'
        '<div class="scan-ttl">📊 Reporte Electrónico OBD-II</div>'
        '<p style="font-size:12.5px;color:#065f46;margin:0 0 12px;opacity:.9;">'
        'Prueba de salud electrónica: parámetros en tiempo real de los módulos de control.</p>'
        f'<iframe src="/{sp}"></iframe>'
        '<div class="scan-actions">'
        f'<a href="/{sp}" target="_blank">VER PANTALLA COMPLETA</a>'
        f'<a href="/{sp}" download class="alt">DESCARGAR PDF</a>'
        '</div></div>'
    )


_FASE_ORDER = ['RECEPCION', 'DIAGNOSTICO', 'REPARACION', 'CONTROL CALIDAD', 'ENTREGA', 'OTROS']
_FASE_LABELS = {
    'RECEPCION': 'Recepción',
    'DIAGNOSTICO': 'Diagnóstico',
    'REPARACION': 'Reparación',
    'CONTROL CALIDAD': 'Control de Calidad',
    'ENTREGA': 'Entrega',
    'OTROS': 'Otros',
}
_VIDEO_EXT = ('.mp4', '.mov', '.avi', '.webm', '.mkv')
_IMG_EXT = ('.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.heic', '.heif')


def _strip_accents(s):
    import unicodedata
    return ''.join(c for c in unicodedata.normalize('NFD', str(s))
                   if unicodedata.category(c) != 'Mn')


def _canon_fase(fase):
    """Normaliza RECEPCIÓN/recepcion/Recepción → 'RECEPCION'."""
    if not fase:
        return 'OTROS'
    s = _strip_accents(str(fase)).upper().strip().replace('_', ' ')
    mapping = {
        'RECEPCION': 'RECEPCION', 'RECEPCIÓN': 'RECEPCION',
        'DIAGNOSTICO': 'DIAGNOSTICO', 'DIAGNÓSTICO': 'DIAGNOSTICO',
        'REPARACION': 'REPARACION', 'REPARACIÓN': 'REPARACION',
        'CONTROL CALIDAD': 'CONTROL CALIDAD', 'CONTROL': 'CONTROL CALIDAD',
        'CALIDAD': 'CONTROL CALIDAD',
        'ENTREGA': 'ENTREGA', 'LISTO PARA ENTREGA': 'ENTREGA', 'LISTO': 'ENTREGA',
    }
    return mapping.get(s, s if s in _FASE_ORDER else 'OTROS')


def _fix_url(path):
    """Normaliza path a URL accesible públicamente. La carpeta /evidencia/ tiene
    permisos restrictivos (nginx da 403), pero /static/evidencia/ pasa por el
    app Python que sí puede leerla.
    """
    if not path:
        return ''
    p = str(path).strip()
    # Ya es URL externa
    if p.startswith('http://') or p.startswith('https://'):
        return p
    # Quitar prefijo absoluto del VPS si viniera
    p = p.replace('/var/www/sandoval/', '/').replace('//', '/')
    # /evidencia/xxx → /static/evidencia/xxx
    if p.startswith('/evidencia/'):
        return '/static' + p
    # evidencia/xxx (sin slash) → /static/evidencia/xxx
    if p.startswith('evidencia/'):
        return '/static/' + p
    # static/evidencia/xxx → /static/evidencia/xxx
    if p.startswith('static/'):
        return '/' + p
    # Path relativo sin prefijo conocido
    if not p.startswith('/'):
        return '/static/evidencia/' + p
    return p


def _normalize_evidencia(raw):
    """Convierte fotos_evidencia a lista de {path,fase} con URL arreglada y fase canónica."""
    out = []
    for p in (raw or []):
        if isinstance(p, str):
            out.append({'path': _fix_url(p), 'fase': 'OTROS'})
        elif isinstance(p, dict):
            raw_path = p.get('path') or p.get('url') or p.get('src') or ''
            if not raw_path:
                continue
            out.append({
                'path': _fix_url(raw_path),
                'fase': _canon_fase(p.get('fase')),
            })
    seen = set()
    uniq = []
    for m in out:
        key = (m['path'], m['fase'])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(m)
    return uniq


def _is_image(path):
    low = path.lower()
    # Strip query string si hay
    if '?' in low:
        low = low.split('?', 1)[0]
    return low.endswith(_IMG_EXT)


def _is_video(path):
    low = path.lower()
    if '?' in low:
        low = low.split('?', 1)[0]
    return low.endswith(_VIDEO_EXT)


def _render_gallery(order):
    medios = _normalize_evidencia(order.fotos_evidencia)
    # Filtrar solo imagen o video (ignorar PDFs auto-importados históricos)
    medios = [m for m in medios if _is_image(m['path']) or _is_video(m['path'])]
    if not medios:
        return '<div class="no-evidence">Sin evidencias fotográficas registradas para esta orden.</div>'

    grupos = {}
    for m in medios:
        grupos.setdefault(m['fase'], []).append(m['path'])

    blocks = []
    rendered = set()
    for fase in _FASE_ORDER:
        items = grupos.get(fase)
        if not items:
            continue
        rendered.add(fase)
        parts = []
        for path in items:
            src = _esc(path)
            if _is_video(path):
                parts.append(f'<div class="video-item"><video src="{src}" controls preload="metadata"></video></div>')
            else:
                parts.append(f'<a href="{src}" target="_blank"><img src="{src}" loading="lazy" onerror="this.parentElement.style.display=\'none\'"/></a>')
        label = _FASE_LABELS.get(fase, fase.title())
        count = len(items)
        blocks.append(
            f'<div class="fase-group">'
            f'<div class="fase-head"><span class="fase-tag">{_esc(label)}</span>'
            f'<span class="fase-count">{count} archivo{"s" if count != 1 else ""}</span></div>'
            f'<div class="gallery">{"".join(parts)}</div>'
            f'</div>'
        )
    # Fases desconocidas que quedaron fuera de _FASE_ORDER
    for fase, items in grupos.items():
        if fase in rendered:
            continue
        parts = []
        for path in items:
            src = _esc(path)
            if _is_video(path):
                parts.append(f'<div class="video-item"><video src="{src}" controls preload="metadata"></video></div>')
            else:
                parts.append(f'<a href="{src}" target="_blank"><img src="{src}" loading="lazy" onerror="this.parentElement.style.display=\'none\'"/></a>')
        count = len(items)
        blocks.append(
            f'<div class="fase-group">'
            f'<div class="fase-head"><span class="fase-tag">{_esc(fase.title())}</span>'
            f'<span class="fase-count">{count} archivo{"s" if count != 1 else ""}</span></div>'
            f'<div class="gallery">{"".join(parts)}</div>'
            f'</div>'
        )
    return ''.join(blocks) if blocks else '<div class="no-evidence">Sin evidencias fotográficas registradas para esta orden.</div>'


def _render_cuentas_bancarias(taller_id):
    """Devuelve HTML con tabla de cuentas activas del taller. Vacío si no hay."""
    from sqlalchemy import text as _sa_text
    from utils.models import get_db as _gd
    db = _gd()
    try:
        rows = db.execute(_sa_text(
            "SELECT banco, titular, numero_cuenta, cci, tipo, moneda, "
            "COALESCE(telefono, '') "
            "FROM cuentas_bancarias WHERE taller_id=:t AND activa=TRUE "
            "ORDER BY orden ASC, id ASC"
        ), {"t": taller_id}).fetchall()
    finally:
        db.close()
    if not rows:
        return ''
    items = []
    for r in rows:
        banco, titular, num, cci, tipo, moneda, telefono = r
        is_wallet = (banco or '').strip().lower() in ('yape', 'plin')
        if is_wallet:
            body = (
                f'<tr><th>Titular</th><td>{_esc(titular or "—")}</td></tr>'
                f'<tr><th>Teléfono</th><td><code>{_esc(telefono or "—")}</code></td></tr>'
                f'<tr><th>Tipo</th><td>Billetera digital</td></tr>'
            )
        else:
            body = (
                f'<tr><th>Titular</th><td>{_esc(titular or "—")}</td></tr>'
                f'<tr><th>Tipo</th><td>{_esc((tipo or "Ahorros"))} · {_esc(moneda or "PEN")}</td></tr>'
                f'<tr><th>N° de cuenta</th><td><code>{_esc(num or "—")}</code></td></tr>'
                f'<tr><th>CCI</th><td><code>{_esc(cci or "—")}</code></td></tr>'
            )
        items.append(
            '<div class="bank-card">'
            f'<div class="bank-name">{_esc(banco)}</div>'
            f'<table class="bank-table">{body}</table></div>'
        )
    return (
        '<div class="sec">'
        '<h2><span class="num">8</span> Cuentas para Pagos</h2>'
        '<p class="bank-intro">Puede realizar el pago o adelanto a cualquiera de las siguientes cuentas. '
        'Envíenos el comprobante por WhatsApp para confirmar la transferencia.</p>'
        f'<div class="bank-grid">{"".join(items)}</div>'
        '</div>'
    )


def _render_items(items):
    subtotal = 0.0
    rows = []
    for i, it in enumerate(items, 1):
        nombre = _esc(it.get('nombre') or 'Ítem')
        cant = it.get('cantidad', 1) or 1
        pu = float(it.get('precio_unitario', 0) or 0)
        sub = float(it.get('total', it.get('subtotal', pu * (cant or 1))) or 0)
        subtotal += sub
        cat = (it.get('categoria') or 'Servicio').strip()
        cat_cls = 'cat-serv' if cat.lower().startswith('serv') else 'cat-rep'
        rows.append(
            '<tr>'
            f'<td style="width:34px;text-align:center;color:#94a3b8;font-weight:700;">{i:02d}</td>'
            f'<td><div style="font-weight:700;color:#0f172a;">{nombre}</div></td>'
            f'<td class="col-cat"><span class="cat-badge {cat_cls}">{_esc(cat)}</span></td>'
            f'<td class="num">{cant}</td>'
            f'<td class="num">S/ {_fmt_money(pu)}</td>'
            f'<td class="num">S/ {_fmt_money(sub)}</td>'
            '</tr>'
        )
    if not rows:
        rows.append(
            '<tr><td colspan="6" style="padding:30px;text-align:center;'
            'color:#94a3b8;font-style:italic;">Presupuesto en proceso de consolidación.</td></tr>'
        )
    igv = round(subtotal * 18 / 118, 2)
    base = round(subtotal - igv, 2)
    return ''.join(rows), base, igv, subtotal


DEFAULT_TERMINOS = [
    'La aprobación de este presupuesto autoriza al taller a iniciar los trabajos detallados.',
    'Los precios incluyen IGV. La mano de obra y repuestos tienen garantía por escrito tras la entrega.',
    'Para asegurar el stock de repuestos, se solicita coordinar el adelanto con administración.',
    'Cualquier trabajo adicional no contemplado será comunicado antes de su ejecución.',
    'El plazo de entrega se confirmará una vez aprobado el presupuesto y asegurado el stock.',
    'Este presupuesto tiene una vigencia de 2 días calendario desde su emisión. Pasado ese plazo, los precios y la disponibilidad de repuestos pueden variar sin previo aviso.',
]


def _load_terminos(taller_id):
    """Lee términos personalizados del taller desde config_sistema (clave=terminos_aprobacion).
    Si está vacío, devuelve los términos por defecto.
    """
    import json as _json
    from sqlalchemy import text as _sa_text
    from utils.models import get_db as _gd
    db = _gd()
    try:
        row = db.execute(_sa_text(
            "SELECT valor FROM config_sistema WHERE taller_id=:t AND clave='terminos_aprobacion'"
        ), {"t": taller_id}).fetchone()
    finally:
        db.close()
    if not row or not row[0]:
        return DEFAULT_TERMINOS
    try:
        data = _json.loads(row[0])
        if isinstance(data, list) and data:
            return [str(x).strip() for x in data if str(x).strip()]
    except Exception:
        pass
    return DEFAULT_TERMINOS


def _render_terminos(taller_id):
    terms = _load_terminos(taller_id)
    lis = ''.join(f'<li>{_esc(t)}</li>' for t in terms)
    return f'<ol class="terms-list">{lis}</ol>'


def _render_approval_html(order, client, vehicle, token: str) -> str:
    items = order.items_cotizacion or []
    rows_html, base, igv, total = _render_items(items)
    taller_id = getattr(order, 'taller_id', 1) or 1
    # cache-buster firma: usa mtime del archivo (cambia cuando se actualiza)
    import os as _os_fc
    _firma_path = '/var/www/sandoval/assets/firma/taller_' + str(taller_id) + '.png'
    firma_v = str(int(_os_fc.path.getmtime(_firma_path))) if _os_fc.path.isfile(_firma_path) else '0' 
    cuentas_html = _render_cuentas_bancarias(taller_id)
    terminos_html = _render_terminos(taller_id)

    if client:
        nom = (client.nombre or '').strip()
        ape = (getattr(client, 'apellidos', '') or '').strip()
        cliente_nombre = f"{nom} {ape}".strip() or '—'
        cliente_doc = (getattr(client, 'documento', '') or '').strip() or '—'
        cliente_tel = (client.telefono or '').strip() or '—'
        cliente_email = (getattr(client, 'email', '') or '').strip() or '—'
        cliente_dir_raw = (getattr(client, 'direccion', '') or '').strip()
        ciudad = (getattr(client, 'ciudad', '') or '').strip()
        cliente_dir = f"{cliente_dir_raw}{', ' + ciudad if ciudad and cliente_dir_raw else ciudad}" or '—'
    else:
        cliente_nombre = cliente_doc = cliente_tel = cliente_email = cliente_dir = '—'

    placa = (vehicle.placa if vehicle else (order.vehiculo_placa or '—'))
    marca = (vehicle.marca if vehicle else '—')
    modelo = (vehicle.modelo if vehicle else '—')
    anio = (getattr(vehicle, 'año', '') or getattr(vehicle, 'ano', '') or '—') if vehicle else '—'
    color_v = (getattr(vehicle, 'color', '') or '—') if vehicle else '—'
    km_int = _safe_int(order.km)
    km = f"{km_int:,}" if km_int else '—'

    fecha_ing = (order.fecha or '')[:10] or datetime.now().strftime('%Y-%m-%d')
    fecha_emision = datetime.now().strftime('%d/%m/%Y')

    diag_html = _render_diag_block(order)
    scanner_html = _render_scanner(order)
    evidence_html = _render_gallery(order)

    return f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=1024, user-scalable=yes, maximum-scale=5, minimum-scale=0.3">
<meta name="robots" content="noindex,nofollow">
<title>Presupuesto {_esc(order.consecutivo)} · Sandoval</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
<style>{_CSS}</style>
</head><body>
<div id="toast" class="toast-ok"></div>
<div class="doc-wrap">
  <div class="doc">

    <div class="doc-head">
      <img class="logo" src="/assets/logo_sandoval.jpg" alt="Logo Sandoval" onerror="this.style.display='none'">
      <div>
        <h1 class="co-name">MECÁNICA Y REPUESTOS SANDOVAL E.I.R.L.</h1>
        <p class="co-sub">RUC 20601234567 &nbsp;•&nbsp; Tel. 924 980 586 &nbsp;•&nbsp; Servicio especializado</p>
        <p class="co-sub m">Documento digital con validez para autorización de trabajos</p>
      </div>
      <div class="doc-id">
        <div class="lbl">Presupuesto de servicio</div>
        <div class="num">{_esc(order.consecutivo)}</div>
        <div class="date">Emitido: {fecha_emision}</div>
      </div>
    </div>

    <div class="sec">
      <h2><span class="num">1</span> Datos del Cliente</h2>
      <div class="table-hint">Deslizá para ver todo</div>
      <div class="table-scroll">
      <table class="info-table">
        <tr><th>Nombre / Razón Social</th><td>{_esc(cliente_nombre)}</td>
            <th>Documento</th><td>{_esc(cliente_doc)}</td></tr>
        <tr><th>Teléfono</th><td>{_esc(cliente_tel)}</td>
            <th>Correo electrónico</th><td>{_esc(cliente_email)}</td></tr>
        <tr><th>Dirección</th><td colspan="3">{_esc(cliente_dir)}</td></tr>
      </table>
      </div>
    </div>

    <div class="sec">
      <h2><span class="num">2</span> Datos del Vehículo</h2>
      <div class="table-hint">Deslizá para ver todo</div>
      <div class="table-scroll">
      <table class="info-table">
        <tr><th>Placa / Matrícula</th><td><b>{_esc(placa)}</b></td>
            <th>Marca</th><td>{_esc(marca)}</td></tr>
        <tr><th>Modelo</th><td>{_esc(modelo)}</td>
            <th>Año</th><td>{_esc(anio)}</td></tr>
        <tr><th>Color</th><td>{_esc(color_v)}</td>
            <th>Kilometraje al ingreso</th><td>{_esc(km)} km</td></tr>
      </table>
      </div>
    </div>

    <div class="sec">
      <h2><span class="num">3</span> Información de la Orden</h2>
      <div class="table-hint">Deslizá para ver todo</div>
      <div class="table-scroll">
      <table class="info-table">
        <tr><th>N° de Orden</th><td><b>{_esc(order.consecutivo)}</b></td>
            <th>Fecha de ingreso</th><td>{_esc(fecha_ing)}</td></tr>
        <tr><th>Tipo de servicio</th><td>{_esc(order.tipo or '—')}</td>
            <th>Técnico responsable</th><td>{_esc(order.tecnico or '—')}</td></tr>
      </table>
      </div>
    </div>

    <div class="sec">
      <h2><span class="num">4</span> Diagnóstico Técnico</h2>
      <div class="diag-block">{diag_html}</div>
      {scanner_html}
    </div>

    <div class="sec">
      <h2><span class="num">5</span> Evidencias Fotográficas</h2>
      {evidence_html}
    </div>

    <div class="sec">
      <h2><span class="num">6</span> Desglose del Presupuesto</h2>
      <div class="table-hint">Deslizá para ver todo</div>
      <div class="table-scroll">
      <table class="items-table">
        <thead><tr>
          <th style="width:34px;text-align:center;">#</th>
          <th>Descripción del trabajo / repuesto</th>
          <th class="col-cat">Categoría</th>
          <th class="num" style="width:60px;">Cant.</th>
          <th class="num" style="width:120px;">P. Unit. (S/)</th>
          <th class="num" style="width:140px;">Subtotal (S/)</th>
        </tr></thead>
        <tbody>{rows_html}</tbody>
        <tfoot>
          <tr><td class="lbl" colspan="5">Base imponible</td><td class="val">S/ {_fmt_money(base)}</td></tr>
          <tr><td class="lbl" colspan="5">IGV (18%)</td><td class="val">S/ {_fmt_money(igv)}</td></tr>
          <tr class="total"><td class="lbl" colspan="5">TOTAL A PAGAR</td><td class="val">S/ {_fmt_money(total)}</td></tr>
        </tfoot>
      </table>
      </div>
    </div>

    <div class="sec">
      <h2><span class="num">7</span> Términos y Condiciones</h2>
      {terminos_html}
    </div>

    {cuentas_html}

    <div class="auth-sec">
      <h2 class="auth-ttl">Autorización del Cliente</h2>
      <p class="auth-sub">Su firma digital autoriza el inicio inmediato de los trabajos.</p>
      <!-- FIRMA + SELLO DIGITALIZADO (imagen procesada con fondo transparente) -->
      <div style="margin-top:28px;padding-top:22px;border-top:1px dashed #cbd5e1;text-align:center">
        <img src="/assets/firma/taller_{taller_id}.png?v={firma_v}" style="max-width:340px;max-height:200px;object-fit:contain;display:inline-block" onerror="this.style.display='none'">
      </div>

      <div class="sign-grid">
        <div class="sign-box">
          <div class="lbl">Cliente / Titular</div>
          <div class="val">{_esc(cliente_nombre)}</div>
          <div class="sub">{_esc(cliente_doc)}</div>
        </div>
        <div class="sign-box">
          <div class="lbl">Vehículo</div>
          <div class="val">{_esc(placa)}</div>
          <div class="sub">{_esc(marca)} {_esc(modelo)} &nbsp;•&nbsp; {_esc(str(anio))}</div>
        </div>
      </div>

      <div style="font-size:12px;color:#64748b;margin:0 0 8px;font-weight:700;">
        Observación o consulta para el técnico (opcional)
      </div>
      <textarea id="note-inp" class="note-inp" placeholder="Ej: confirmar si el cambio de aceite incluye filtro..."></textarea>

      <div class="btn-row">
        <button type="button" class="btn btn-reject" id="btn-reject">Rechazar / Consultar</button>
        <button type="button" class="btn btn-approve" id="btn-approve">✔ Aprobar e iniciar trabajos</button>
      </div>

      <div class="disclaimer">
        Al aprobar, confirma que revisó el diagnóstico, las evidencias y el detalle del presupuesto por
        <b>S/ {_fmt_money(total)}</b>.<br>
        La orden pasará automáticamente a etapa de <b>REPARACIÓN</b> y recibirá actualizaciones por WhatsApp.
      </div>
    </div>

    <div class="doc-foot">
      <div>Mecánica y Repuestos Sandoval E.I.R.L. &nbsp;•&nbsp; RUC 20601234567</div>
      <div>Documento digital generado el {fecha_emision}</div>
    </div>
  </div>
</div>

<a href="https://wa.me/51924980586" class="support-float">💬 Apoyo en línea</a>
<button type="button" class="pdf-float" id="pdf-float">📥 Descargar PDF</button>

<script>
(function(){{
  var TOKEN = "{_esc(token)}";
  var CONSEC = "{_esc(order.consecutivo or '')}";
  var PDF_NAME = 'presupuesto_' + (CONSEC || 'sandoval').replace(/[^\\w.-]/g,'_') + '.pdf';
  var ENDPOINT = '/api/aprobacion/' + TOKEN + '/respond';
  var toast = document.getElementById('toast');
  var note = document.getElementById('note-inp');
  var btnA = document.getElementById('btn-approve');
  var btnR = document.getElementById('btn-reject');
  var btnDL = document.getElementById('pdf-float');
  var btnDLOrig = btnDL ? btnDL.innerHTML : '';
  function showToast(msg, color){{
    toast.textContent = msg;
    toast.style.background = color || '#059669';
    toast.classList.add('show');
    setTimeout(function(){{toast.classList.remove('show');}}, 3500);
  }}
  function loadPdfLib(cb){{
    if (window.html2pdf) return cb();
    var s = document.createElement('script');
    s.src = 'https://cdnjs.cloudflare.com/ajax/libs/html2pdf.js/0.10.2/html2pdf.bundle.min.js';
    s.onload = cb;
    s.onerror = function(){{
      showToast('No se pudo cargar el generador de PDF', '#dc2626');
      if (btnDL){{ btnDL.disabled = false; btnDL.innerHTML = btnDLOrig; }}
    }};
    document.head.appendChild(s);
  }}
  function descargarPDF(targetBtn){{
    var b = targetBtn || btnDL;
    if (b){{ b.disabled = true; var orig = b.innerHTML; b.innerHTML = '⏳ Cargando…'; }}
    loadPdfLib(function(){{
      if (b) b.innerHTML = '⏳ Generando…';
      var el = document.querySelector('.doc');
      html2pdf().set({{
        margin: [6, 5, 6, 5],
        filename: PDF_NAME,
        image: {{type: 'jpeg', quality: 0.95}},
        html2canvas: {{scale: 2, useCORS: true, backgroundColor: '#ffffff', logging: false}},
        jsPDF: {{unit: 'mm', format: 'a4', orientation: 'portrait'}},
        pagebreak: {{mode: ['avoid-all', 'css']}}
      }}).from(el).save().then(function(){{
        if (b){{ b.disabled = false; b.innerHTML = orig || btnDLOrig; }}
      }}).catch(function(e){{
        showToast('Error generando PDF', '#dc2626');
        if (b){{ b.disabled = false; b.innerHTML = orig || btnDLOrig; }}
      }});
    }});
  }}
  if (btnDL) btnDL.addEventListener('click', function(){{ descargarPDF(btnDL); }});

  function mostrarGracias(){{
    var authSec = document.querySelector('.auth-sec');
    if (!authSec) return;
    authSec.innerHTML = ''
      + '<div style="text-align:center;padding:14px 0">'
      + '  <div class="thanks-icon">✓</div>'
      + '  <h2 class="auth-ttl">¡Gracias por confiar en nosotros!</h2>'
      + '  <p class="auth-sub">Su presupuesto ha sido autorizado. La orden pasó a etapa de <b>REPARACIÓN</b>.<br>Ahora puede descargar una copia en PDF con toda la información para sus registros.</p>'
      + '  <div class="btn-row" style="margin-top:22px">'
      + '    <button type="button" class="btn btn-approve" id="ty-dl">📥 Descargar PDF</button>'
      + '    <button type="button" class="btn btn-reject" id="ty-wa">💬 Escribir al taller</button>'
      + '  </div>'
      + '  <div class="disclaimer" style="margin-top:22px">Le mantendremos informado por WhatsApp sobre el avance de la reparación.</div>'
      + '</div>';
    document.getElementById('ty-dl').addEventListener('click', function(){{
      descargarPDF(document.getElementById('ty-dl'));
    }});
    document.getElementById('ty-wa').addEventListener('click', function(){{
      window.open('https://wa.me/51924980586?text=' + encodeURIComponent('Hola, acabo de aprobar mi presupuesto de la orden ' + CONSEC), '_blank');
    }});
    authSec.scrollIntoView({{behavior: 'smooth', block: 'start'}});
  }}

  async function submit(status){{
    btnA.disabled = true; btnR.disabled = true;
    var label = status === 'aprobado' ? 'Aprobando…' : 'Registrando…';
    (status === 'aprobado' ? btnA : btnR).textContent = label;
    try {{
      var r = await fetch(ENDPOINT, {{
        method: 'POST',
        headers: {{'Content-Type': 'application/json'}},
        body: JSON.stringify({{status: status, comentario: note.value || ''}})
      }});
      var d = await r.json();
      if (!r.ok || !d.ok) throw new Error(d.error || 'Error');
      if (status === 'aprobado') {{
        showToast('✓ Presupuesto autorizado');
        mostrarGracias();
      }} else {{
        showToast('Respuesta registrada. Un asesor le contactará.');
        setTimeout(function(){{location.reload();}}, 1500);
      }}
    }} catch(err){{
      showToast('Error: ' + (err.message || 'intente nuevamente'), '#dc2626');
      btnA.disabled = false; btnR.disabled = false;
      btnA.textContent = '✔ Aprobar e iniciar trabajos';
      btnR.textContent = 'Rechazar / Consultar';
    }}
  }}
  btnA.addEventListener('click', function(){{
    if (!confirm('¿Confirma que aprueba el presupuesto por S/ {_fmt_money(total)}?')) return;
    submit('aprobado');
  }});
  btnR.addEventListener('click', function(){{
    if (!confirm('¿Desea rechazar o posponer este presupuesto?')) return;
    submit('rechazado');
  }});
}})();
</script>
</body></html>"""


def approval_html(token: str) -> str:
    """Punto de entrada: devuelve HTML del flujo de aprobación."""
    db = get_db()
    try:
        order = db.query(Orden).filter_by(approval_token=token).first()
        if not order:
            return render_error_html('Enlace inválido',
                                     'Este enlace de aprobación no es válido o ha expirado.')

        # Expiración (48h tras respuesta previa)
        if order.approval_date:
            try:
                created = datetime.strptime(order.approval_date[:16], '%Y-%m-%d %H:%M')
                if (datetime.now() - created).total_seconds() > 172800:
                    return render_error_html(
                        'Enlace expirado',
                        'Este enlace de aprobación ha expirado. Contacte al taller para obtener uno nuevo.')
            except Exception:
                pass

        if (order.approval_status or '').lower() in ('aprobado', 'rechazado'):
            return render_already_responded_html(order)

        client = db.query(Cliente).filter_by(id=order.cliente_id).first()
        vehicle = db.query(Vehiculo).filter_by(placa=order.vehiculo_placa).first()
        return _render_approval_html(order, client, vehicle, token)
    finally:
        db.close()


def process_approval_response(token: str, status: str, comentario: str = '') -> dict:
    """Procesa la decisión del cliente. Devuelve dict con {ok, error?}."""
    if status not in ('aprobado', 'rechazado'):
        return {'ok': False, 'error': 'Estado inválido'}

    db = get_db()
    try:
        o = db.query(Orden).filter_by(approval_token=token).first()
        if not o:
            return {'ok': False, 'error': 'Token inválido o ya utilizado'}

        o.approval_status = status
        o.approval_date = datetime.now().strftime('%Y-%m-%d %H:%M')
        if hasattr(o, 'comentario_cliente'):
            o.comentario_cliente = (comentario or '')[:500]

        if status == 'aprobado':
            o.estado = 'REPARACIÓN'
            try:
                c = db.query(Cliente).filter_by(id=o.cliente_id).first()
                v = db.query(Vehiculo).filter_by(placa=o.vehiculo_placa).first()
                o_dict = {col.name: getattr(o, col.name) for col in o.__table__.columns}
                c_dict = {col.name: getattr(c, col.name) for col in c.__table__.columns} if c else {}
                v_dict = {col.name: getattr(v, col.name) for col in v.__table__.columns} if v else {}
                o_dict['fotos_evidencia'] = o.fotos_evidencia
                os.makedirs('pdfs', exist_ok=True)
                pdf_p = f"pdfs/Cotizacion_{(o.consecutivo or '').replace('#','')}.pdf"
                generate_pdf(o_dict, c_dict, v_dict, 'cotizacion', pdf_p)
                o.pdf_cotizacion = pdf_p
            except Exception as e:
                print(f"[approval] Error generando PDF: {e}")

        try:
            log_actividad(f'Orden {o.consecutivo} {status} via web', 'ordenes')
        except Exception:
            pass

        import secrets as _sec
        o.approval_token = 'USED_' + _sec.token_hex(8)
        db.commit()
        return {'ok': True, 'consecutivo': o.consecutivo, 'estado': o.estado}
    except Exception as e:
        db.rollback()
        return {'ok': False, 'error': str(e)}
    finally:
        db.close()


# ─── Compat: mantener approval_page() para main.py antiguo si se re-usara ───
def approval_page(token: str):
    """Fallback NiceGUI (no recomendado). Usar app.get/app.post en main.py."""
    from nicegui import ui
    html = approval_html(token)
    ui.add_body_html(html)

"""
utils/api_extensions.py — Endpoints complementarios móvil SANDOVAL PRO v22.

Contenido:
  - Notas de venta: detalle, abonar, PDF (HTML imprimible estilo aprobación)
  - Cotizaciones: detalle, crear, actualizar, PDF, convertir a orden
  - Créditos: crear (list/abono ya están en api_mobile_admin)
  - Clientes: búsqueda por documento RUC/DNI (cache local antes de CODART)

Diseño: SQL directo con text(), reusa helpers/auth de api_service y
api_mobile_admin. Multi-tenant estricto (taller_id del JWT).
"""
import json
import os as _os
import re as _re
import base64 as _b64
import html as _html
from datetime import datetime, date as _date

from sqlalchemy import text
from starlette.requests import Request
from starlette.responses import JSONResponse, HTMLResponse

from utils.api_service import (_require_auth, _require_admin, json_ok, json_err)
from utils.api_mobile_admin import _auth_tenant, _safe_date, _parse_json
from utils.models import get_db


# ═════════════════════════ helpers ═════════════════════════

def _esc(s):
    if s is None: return ''
    return _html.escape(str(s))

def _fmt_money(n):
    try: return "S/ {:,.2f}".format(float(n or 0))
    except Exception: return "S/ 0.00"

def _fmt_fecha(raw, with_time=False):
    if not raw: return ''
    s = str(raw)[:19]
    try:
        d = datetime.strptime(s[:10], "%Y-%m-%d")
        if with_time and len(s) >= 16:
            return d.strftime("%d/%m/%Y") + ' ' + s[11:16]
        return d.strftime("%d/%m/%Y")
    except Exception:
        return s[:10]

_LOGO_DATA_URI_CACHE = {"uri": None}

def _logo_data_uri():
    """Lee assets/logo_sandoval.jpg y lo devuelve como data URI base64 (cacheado)."""
    if _LOGO_DATA_URI_CACHE["uri"] is not None:
        return _LOGO_DATA_URI_CACHE["uri"]
    candidates = [
        "/var/www/sandoval/assets/logo_sandoval.jpg",
        _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),
                      "assets", "logo_sandoval.jpg"),
        "assets/logo_sandoval.jpg",
    ]
    for p in candidates:
        try:
            with open(p, "rb") as f:
                b64 = _b64.b64encode(f.read()).decode("ascii")
            uri = f"data:image/jpeg;base64,{b64}"
            _LOGO_DATA_URI_CACHE["uri"] = uri
            return uri
        except Exception:
            continue
    _LOGO_DATA_URI_CACHE["uri"] = ""
    return ""


def _taller_info(db, taller_id):
    default_logo = _logo_data_uri() or "/assets/logo_sandoval.jpg"
    # Rollback por si la transacción quedó en estado fallido por queries previas
    try: db.rollback()
    except Exception: pass
    try:
        row = db.execute(text(
            "SELECT COALESCE(NULLIF(empresa_nombre,''), nombre), "
            "COALESCE(NULLIF(empresa_direccion,''), direccion, ''), "
            "COALESCE(NULLIF(empresa_telefono,''), telefono, ''), "
            "COALESCE(NULLIF(empresa_ruc,''), ruc, '') "
            "FROM talleres WHERE id=:t"
        ), {"t": taller_id}).fetchone()
        if row:
            return {"nombre": row[0] or "MECÁNICA Y REPUESTOS SANDOVAL E.I.R.L.",
                    "direccion": row[1] or "", "telefono": row[2] or "",
                    "ruc": row[3] or "", "logo": default_logo}
    except Exception:
        try: db.rollback()
        except Exception: pass
    return {"nombre": "MECÁNICA Y REPUESTOS SANDOVAL E.I.R.L.",
            "direccion": "Piura, Perú", "telefono": "",
            "ruc": "", "logo": default_logo}


# ═════════════════════════ CSS del documento (replica approval) ═════════════════════════

_DOC_CSS = """
:root{
  --primary:#274495; --primary-dark:#1e3475;
  --accent:#d97706; --emerald:#059669; --red:#dc2626;
  --slate-900:#0f172a; --slate-700:#334155; --slate-500:#64748b;
  --slate-300:#cbd5e1; --slate-100:#f1f5f9; --slate-50:#f8fafc;
  --paper:#ffffff; --bg:#eef2f7;
}
*,*::before,*::after{box-sizing:border-box;}
html,body{margin:0;padding:0;}
body{background:var(--bg);color:var(--slate-900);
  font-family:'Inter','Segoe UI',system-ui,sans-serif;
  font-size:14px;line-height:1.55;-webkit-font-smoothing:antialiased;}
h1,h2,h3,h4,p{margin:0;padding:0;}
.doc-wrap{max-width:960px;margin:0 auto;padding:28px 16px 100px;}
.doc{background:var(--paper);border-radius:6px;
  box-shadow:0 6px 40px rgba(15,23,42,.08),0 0 0 1px rgba(15,23,42,.04);
  overflow:hidden;}
.doc-head{display:grid;grid-template-columns:96px 1fr auto;gap:22px;padding:30px 38px;
  background:linear-gradient(135deg,var(--primary) 0%,var(--primary-dark) 100%);
  color:#fff;align-items:center;}
.doc-head .logo{width:86px;height:86px;border-radius:14px;background:#fff;padding:8px;
  box-shadow:0 10px 30px rgba(0,0,0,.2);object-fit:contain;display:block;}
.doc-head .co-name{font-size:22px;font-weight:800;letter-spacing:-.4px;margin:0 0 4px;line-height:1.15;}
.doc-head .co-sub{font-size:11.5px;opacity:.9;margin:0;letter-spacing:.3px;}
.doc-head .co-sub.m{opacity:.7;margin-top:3px;}
.doc-head .doc-id{background:rgba(255,255,255,.12);border:1px solid rgba(255,255,255,.25);
  padding:12px 18px;border-radius:10px;text-align:right;min-width:240px;}
.doc-head .doc-id .lbl{font-size:9px;letter-spacing:2.4px;text-transform:uppercase;
  opacity:.8;font-weight:700;}
.doc-head .doc-id .num{font-size:19px;font-weight:800;margin:3px 0;}
.doc-head .doc-id .date{font-size:11px;opacity:.85;}
.sec{padding:26px 38px;border-top:1px solid var(--slate-100);}
.sec h2{font-size:12px;font-weight:800;text-transform:uppercase;letter-spacing:2.4px;
  color:var(--primary);margin:0 0 16px;padding:0 0 10px;
  border-bottom:2px solid var(--primary);display:inline-flex;align-items:center;gap:10px;}
.sec h2 .num{display:inline-flex;align-items:center;justify-content:center;
  width:22px;height:22px;border-radius:50%;background:var(--primary);color:#fff;font-size:11px;font-weight:800;}
.info-table{width:100%;border-collapse:collapse;font-size:13px;}
.info-table th,.info-table td{padding:10px 14px;text-align:left;vertical-align:top;
  border:1px solid var(--slate-100);}
.info-table th{background:var(--slate-50);color:var(--slate-500);font-weight:700;font-size:10.5px;
  letter-spacing:1px;text-transform:uppercase;width:26%;}
.info-table td{color:var(--slate-900);font-weight:600;background:#fff;}
.items-table{width:100%;border-collapse:collapse;font-size:13px;}
.items-table thead th{background:var(--slate-900);color:#fff;padding:12px 14px;font-size:10.5px;
  font-weight:700;letter-spacing:1.2px;text-transform:uppercase;text-align:left;}
.items-table thead th.num{text-align:right;}
.items-table tbody td{padding:12px 14px;border-bottom:1px solid var(--slate-100);
  background:#fff;vertical-align:top;}
.items-table tbody tr:nth-child(even) td{background:var(--slate-50);}
.items-table tbody td.num{text-align:right;font-variant-numeric:tabular-nums;font-weight:600;}
.items-table .cat-badge{display:inline-block;font-size:9px;font-weight:800;
  padding:3px 8px;border-radius:20px;text-transform:uppercase;letter-spacing:.8px;}
.items-table .cat-serv{background:#dbeafe;color:#1e40af;}
.items-table .cat-rep{background:#fef3c7;color:#92400e;}
.items-table tfoot td{padding:10px 14px;border-top:1px solid #e2e8f0;font-weight:700;}
.items-table tfoot td.lbl{text-align:right;color:var(--slate-500);font-size:11.5px;
  text-transform:uppercase;letter-spacing:1px;}
.items-table tfoot td.val{text-align:right;font-variant-numeric:tabular-nums;color:var(--slate-900);font-size:14px;}
.items-table tfoot tr.total td{background:var(--primary);color:#fff;padding:14px;font-size:16px;}
.items-table tfoot tr.total td.lbl{color:rgba(255,255,255,.9);font-size:11.5px;}
.items-table tfoot tr.total td.val{font-size:22px;font-weight:800;}
.stamp{display:inline-block;padding:6px 14px;border-radius:100px;font-size:10.5px;
  font-weight:800;letter-spacing:1.2px;text-transform:uppercase;}
.stamp-ok{background:#d1fae5;color:#065f46;border:1px solid #6ee7b7;}
.stamp-warn{background:#fef3c7;color:#92400e;border:1px solid #fcd34d;}
.stamp-red{background:#fee2e2;color:#991b1b;border:1px solid #fca5a5;}
.pay-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:12px;}
.pay-card{border:1px solid var(--slate-300);border-radius:8px;padding:14px 18px;background:#fff;}
.pay-card .pay-lbl{font-size:10px;letter-spacing:1.2px;text-transform:uppercase;
  color:var(--slate-500);font-weight:800;margin-bottom:6px;}
.pay-card .pay-val{font-size:18px;font-weight:800;color:var(--slate-900);font-variant-numeric:tabular-nums;}
.pay-card.saldo .pay-val{color:var(--red);}
.pay-card.pagado .pay-val{color:var(--emerald);}
.terms-list{margin:0;padding-left:20px;color:var(--slate-700);font-size:12.5px;line-height:1.75;}
.terms-list li{margin-bottom:4px;}
.doc-foot{padding:18px 38px;background:var(--slate-900);color:rgba(255,255,255,.75);font-size:11px;
  letter-spacing:.5px;display:flex;justify-content:space-between;flex-wrap:wrap;gap:10px;}
.doc-actions{max-width:960px;margin:16px auto 24px;padding:0 16px;display:flex;gap:10px;flex-wrap:wrap;justify-content:flex-end;}
.doc-actions button{background:var(--primary);color:#fff;border:0;padding:11px 22px;border-radius:10px;
  font-weight:700;font-size:13px;cursor:pointer;display:inline-flex;align-items:center;gap:6px;}
.doc-actions button.alt{background:#25d366;}
.doc-actions button.alt2{background:var(--slate-700);}
.doc-actions button:hover{filter:brightness(1.05);}
.doc-actions button:disabled{opacity:.6;cursor:wait;}
.abonos-table{width:100%;border-collapse:collapse;font-size:12.5px;margin-top:8px;}
.abonos-table th{background:var(--slate-50);color:var(--slate-500);padding:8px 12px;
  font-size:10px;text-transform:uppercase;letter-spacing:1px;font-weight:700;text-align:left;}
.abonos-table td{padding:8px 12px;border-bottom:1px solid var(--slate-100);}
.abonos-table tr:last-child td{border-bottom:0;}
@media print{
  body{background:#fff;}
  .doc-actions{display:none!important;}
  .doc{box-shadow:none;}
}
"""


# ═════════════════════════ Render plantilla común ═════════════════════════

def _render_doc_html(*, titulo, subtitulo, numero, fecha, taller,
                     cliente_nombre, cliente_doc, cliente_tel, cliente_email,
                     items, subtotal, igv, total, pagado=None, saldo=None,
                     estado=None, estado_color='warn', metodo_pago=None,
                     abonos=None, nota=None, terminos=None,
                     whatsapp_msg=None, whatsapp_to=None):
    """Devuelve HTML imprimible estilo aprobación para nota/cotización."""

    def _logo_html():
        # El logo viene como data-URI (base64) embebido en el HTML, así no
        # depende de caché/CDN/permisos. visibility:hidden preserva el ancho
        # de la celda del grid aunque falle.
        src = taller.get('logo') or ''
        if not src:
            return '<div class="logo" style="visibility:hidden"></div>'
        return (f'<img class="logo" src="{_esc(src)}" alt="Logo" '
                f'onerror="this.style.visibility=\'hidden\'">')

    rows_items = []
    for i, it in enumerate(items or [], start=1):
        nombre = it.get('nombre') or it.get('descripcion') or '—'
        cat = str(it.get('tipo') or it.get('categoria') or '').lower()
        is_serv = 'serv' in cat or 'mano' in cat or 'labor' in cat
        cat_badge = ('<span class="cat-badge cat-serv">Mano de obra</span>'
                     if is_serv else '<span class="cat-badge cat-rep">Repuesto</span>')
        cod = it.get('codigo') or it.get('referencia') or ''
        cant = it.get('cantidad', 1)
        pu = it.get('precio_unitario', it.get('precio', 0))
        sub = it.get('subtotal', it.get('total', 0))
        rows_items.append(f"""
          <tr>
            <td class="num">{i}</td>
            <td>{cat_badge}</td>
            <td><b>{_esc(nombre)}</b>{f'<div style="font-size:11px;color:var(--slate-500);margin-top:2px">Cód: {_esc(cod)}</div>' if cod else ''}</td>
            <td class="num">{_esc(cant)}</td>
            <td class="num">{_fmt_money(pu)}</td>
            <td class="num"><b>{_fmt_money(sub)}</b></td>
          </tr>""")
    items_html = ''.join(rows_items) or (
        '<tr><td colspan="6" style="text-align:center;color:var(--slate-500);padding:20px">'
        'Sin ítems</td></tr>')

    pago_html = ''
    if pagado is not None and saldo is not None:
        clase_est = 'stamp-ok' if (saldo or 0) <= 0.005 else 'stamp-warn'
        pago_html = f"""
        <div class="sec">
          <h2><span class="num">3</span>Estado de Pago</h2>
          <div class="pay-grid">
            <div class="pay-card">
              <div class="pay-lbl">Total</div>
              <div class="pay-val">{_fmt_money(total)}</div>
            </div>
            <div class="pay-card pagado">
              <div class="pay-lbl">Pagado</div>
              <div class="pay-val">{_fmt_money(pagado)}</div>
            </div>
            <div class="pay-card saldo">
              <div class="pay-lbl">Saldo</div>
              <div class="pay-val">{_fmt_money(saldo)}</div>
            </div>
            <div class="pay-card">
              <div class="pay-lbl">Método</div>
              <div class="pay-val" style="font-size:14px">{_esc(metodo_pago or '—')}</div>
            </div>
          </div>
          <div style="margin-top:14px;text-align:center">
            <span class="stamp {clase_est}">
              {'PAGADO' if (saldo or 0) <= 0.005 else 'SALDO PENDIENTE'}
            </span>
          </div>
        </div>"""

    abonos_html = ''
    if abonos:
        rows_ab = ''.join(
            f"<tr><td>{_fmt_fecha(a.get('fecha'))}</td>"
            f"<td>{_esc(a.get('metodo') or a.get('metodo_pago') or '—')}</td>"
            f"<td>{_esc(a.get('nota') or '')}</td>"
            f"<td style='text-align:right;font-weight:700'>{_fmt_money(a.get('monto', 0))}</td></tr>"
            for a in abonos
        )
        abonos_html = f"""
        <div class="sec">
          <h2><span class="num">4</span>Historial de Abonos</h2>
          <table class="abonos-table">
            <thead><tr><th>Fecha</th><th>Método</th><th>Nota</th><th style="text-align:right">Monto</th></tr></thead>
            <tbody>{rows_ab}</tbody>
          </table>
        </div>"""

    nota_html = ''
    if nota:
        nota_html = f"""
        <div class="sec">
          <h2><span class="num">5</span>Observaciones</h2>
          <p style="color:var(--slate-700);line-height:1.7;white-space:pre-line">{_esc(nota)}</p>
        </div>"""

    terminos_html = ''
    if terminos:
        lis = ''.join(f'<li>{_esc(t)}</li>' for t in terminos)
        terminos_html = f"""
        <div class="sec">
          <h2><span class="num">6</span>Términos y Condiciones</h2>
          <ul class="terms-list">{lis}</ul>
        </div>"""

    wa_btn = ''
    if whatsapp_msg:
        import urllib.parse as _up
        msg_enc = _up.quote(whatsapp_msg)
        wa_url = (f"https://wa.me/{_esc(whatsapp_to)}?text={msg_enc}"
                  if whatsapp_to else f"https://wa.me/?text={msg_enc}")
        wa_btn = (f'<button class="alt" onclick="window.open(\'{wa_url}\', \'_blank\')">'
                  f'Enviar por WhatsApp</button>')

    estado_chip = ''
    if estado:
        mapa = {'warn': 'stamp-warn', 'ok': 'stamp-ok', 'red': 'stamp-red'}
        estado_chip = f'<div style="margin-top:6px"><span class="stamp {mapa.get(estado_color, "stamp-warn")}">{_esc(estado)}</span></div>'

    pdf_filename = _re.sub(r'[^\w.-]', '_', f"{titulo}_{numero}").strip('_') + '.pdf'

    return f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=1024, user-scalable=yes, maximum-scale=5, minimum-scale=0.3">
<title>{_esc(titulo)} {_esc(numero)} · {_esc(taller.get('nombre', 'SANDOVAL'))}</title>
<style>{_DOC_CSS}</style>
</head><body>
<div class="doc-actions">
  <button id="btn-pdf">📥 Descargar PDF</button>
  <button onclick="window.print()" class="alt2">🖨️ Imprimir</button>
  {wa_btn}
</div>
<div class="doc-wrap">
  <div class="doc">
    <div class="doc-head">
      {_logo_html()}
      <div>
        <h1 class="co-name">{_esc(taller.get('nombre', 'MECÁNICA Y REPUESTOS SANDOVAL E.I.R.L.'))}</h1>
        <p class="co-sub">{('RUC ' + _esc(taller.get('ruc',''))) if taller.get('ruc') else ''}{' &nbsp;•&nbsp; ' if taller.get('ruc') and taller.get('telefono') else ''}{('Tel. ' + _esc(taller.get('telefono',''))) if taller.get('telefono') else ''}</p>
        <p class="co-sub m">{_esc(taller.get('direccion', ''))}</p>
      </div>
      <div class="doc-id">
        <div class="lbl">{_esc(subtitulo)}</div>
        <div class="num">{_esc(numero)}</div>
        <div class="date">{_fmt_fecha(fecha, with_time=True)}</div>
        {estado_chip}
      </div>
    </div>

    <div class="sec">
      <h2><span class="num">1</span>Cliente</h2>
      <table class="info-table">
        <tr><th>Nombre</th><td>{_esc(cliente_nombre or 'Mostrador')}</td></tr>
        {f'<tr><th>Documento</th><td>{_esc(cliente_doc)}</td></tr>' if cliente_doc else ''}
        {f'<tr><th>Teléfono</th><td>{_esc(cliente_tel)}</td></tr>' if cliente_tel else ''}
        {f'<tr><th>Correo</th><td>{_esc(cliente_email)}</td></tr>' if cliente_email else ''}
      </table>
    </div>

    <div class="sec">
      <h2><span class="num">2</span>Detalle</h2>
      <table class="items-table">
        <thead>
          <tr>
            <th class="num" style="width:38px">#</th>
            <th style="width:120px">Tipo</th>
            <th>Descripción</th>
            <th class="num" style="width:72px">Cant.</th>
            <th class="num" style="width:110px">P. Unit.</th>
            <th class="num" style="width:120px">Subtotal</th>
          </tr>
        </thead>
        <tbody>{items_html}</tbody>
        <tfoot>
          <tr><td colspan="5" class="lbl">Subtotal (sin IGV)</td><td class="val">{_fmt_money(subtotal)}</td></tr>
          <tr><td colspan="5" class="lbl">IGV (18%)</td><td class="val">{_fmt_money(igv)}</td></tr>
          <tr class="total"><td colspan="5" class="lbl">Total a pagar</td><td class="val">{_fmt_money(total)}</td></tr>
        </tfoot>
      </table>
    </div>

    {pago_html}
    {abonos_html}
    {nota_html}
    {terminos_html}

    <div class="doc-foot">
      <span>Documento generado el {_fmt_fecha(datetime.now(), with_time=True)}</span>
      <span>{_esc(taller.get('nombre', 'MECÁNICA Y REPUESTOS SANDOVAL E.I.R.L.'))} · sandoval.pe</span>
    </div>
  </div>
</div>
<script>
(function(){{
  var btn = document.getElementById('btn-pdf');
  if (!btn) return;
  var PDF_NAME = {json.dumps(pdf_filename)};
  var origHTML = btn.innerHTML;
  function loadLib(cb){{
    if (window.html2pdf) return cb();
    var s = document.createElement('script');
    s.src = 'https://cdnjs.cloudflare.com/ajax/libs/html2pdf.js/0.10.2/html2pdf.bundle.min.js';
    s.onload = cb;
    s.onerror = function(){{
      alert('No se pudo cargar el generador de PDF. Revise su conexión.');
      btn.disabled = false; btn.innerHTML = origHTML;
    }};
    document.head.appendChild(s);
  }}
  btn.addEventListener('click', function(){{
    btn.disabled = true;
    btn.innerHTML = '⏳ Cargando…';
    loadLib(function(){{
      btn.innerHTML = '⏳ Generando PDF…';
      var el = document.querySelector('.doc');
      var opt = {{
        margin: [6, 5, 6, 5],
        filename: PDF_NAME,
        image: {{type: 'jpeg', quality: 0.95}},
        html2canvas: {{scale: 2, useCORS: true, backgroundColor: '#ffffff', logging: false}},
        jsPDF: {{unit: 'mm', format: 'a4', orientation: 'portrait'}},
        pagebreak: {{mode: ['avoid-all', 'css']}}
      }};
      html2pdf().set(opt).from(el).save().then(function(){{
        btn.disabled = false; btn.innerHTML = origHTML;
      }}).catch(function(e){{
        alert('Error generando PDF: ' + (e && e.message ? e.message : 'inténtelo de nuevo'));
        btn.disabled = false; btn.innerHTML = origHTML;
      }});
    }});
  }});
}})();
</script>
</body></html>"""


# ═════════════════════════ NOTAS DE VENTA ═════════════════════════

async def api_nota_detail(request: Request) -> JSONResponse:
    """GET /api/notas-venta/{nid} — detalle con items, monto_pagado, abonos."""
    auth = _auth_tenant(request)
    if isinstance(auth, JSONResponse): return auth
    _user, tid, db = auth
    try:
        nid = request.path_params.get('nid') or request.path_params.get('id') or ''
        try: nid = int(nid)
        except: return json_err('ID inválido')
        row = db.execute(text("""
            SELECT id, numero, fecha, cliente_id, cliente_nombre,
                   subtotal, igv, total, estado, metodo_pago, items,
                   COALESCE(monto_pagado,0), COALESCE(notas,'')
              FROM notas_venta
             WHERE id=:nid AND taller_id=:t
        """), {"nid": nid, "t": tid}).fetchone()
        if not row: return json_err('Nota no encontrada', 404)
        items = _parse_json(row[10])
        total = float(row[7] or 0)
        pagado = float(row[11] or 0)
        saldo = max(0.0, round(total - pagado, 2))
        abonos = []
        try:
            rows_ab = db.execute(text(
                "SELECT monto, metodo_pago, nota, fecha FROM abonos_nota "
                "WHERE nota_id=:nid AND taller_id=:t ORDER BY id"
            ), {"nid": nid, "t": tid}).fetchall()
            abonos = [{"monto": float(a[0] or 0), "metodo": a[1] or '',
                       "nota": a[2] or '', "fecha": str(a[3] or '')[:10]}
                      for a in rows_ab]
        except Exception:
            abonos = []
        cli_doc = cli_tel = cli_email = ''
        if row[3]:
            try:
                cr = db.execute(text(
                    "SELECT COALESCE(id,''), COALESCE(telefono,''), COALESCE(email,'') "
                    "FROM clientes WHERE id=:cid AND taller_id=:t"
                ), {"cid": row[3], "t": tid}).fetchone()
                if cr:
                    cli_doc, cli_tel, cli_email = cr[0] or '', cr[1] or '', cr[2] or ''
            except Exception:
                pass
        return json_ok({
            "id": row[0], "numero": row[1], "fecha": str(row[2] or ''),
            "cliente_id": row[3], "cliente_nombre": row[4] or 'Mostrador',
            "cliente_doc": cli_doc, "cliente_tel": cli_tel, "cliente_email": cli_email,
            "subtotal": float(row[5] or 0), "igv": float(row[6] or 0),
            "total": total, "estado": row[8] or '', "metodo_pago": row[9] or '',
            "items": items if isinstance(items, list) else [],
            "monto_pagado": pagado, "saldo": saldo,
            "notas": row[12] or '', "abonos": abonos,
        })
    finally:
        db.close()


async def api_nota_abonar(request: Request) -> JSONResponse:
    """POST /api/notas-venta/{nid}/abonar {monto, metodo_pago, nota, fecha}."""
    auth = _auth_tenant(request)
    if isinstance(auth, JSONResponse): return auth
    _user, tid, db = auth
    try:
        nid = request.path_params.get('nid') or request.path_params.get('id') or ''
        try: nid = int(nid)
        except: return json_err('ID inválido')
        try: body = await request.json()
        except: return json_err('Body inválido')
        try: monto = float(body.get('monto') or 0)
        except: return json_err('Monto inválido')
        if monto <= 0: return json_err('Monto debe ser > 0')
        fecha = _safe_date(body.get('fecha')) or datetime.now().strftime('%Y-%m-%d')
        # Asegurar tabla abonos_nota
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS abonos_nota (
                id SERIAL PRIMARY KEY,
                taller_id INTEGER NOT NULL,
                nota_id INTEGER NOT NULL,
                monto NUMERIC(12,2) NOT NULL,
                metodo_pago VARCHAR(40),
                nota TEXT,
                fecha DATE,
                creado_at TIMESTAMP DEFAULT NOW()
            )
        """))
        row = db.execute(text(
            "SELECT total, COALESCE(monto_pagado,0) FROM notas_venta "
            "WHERE id=:nid AND taller_id=:t FOR UPDATE"
        ), {"nid": nid, "t": tid}).fetchone()
        if not row:
            db.rollback()
            return json_err('Nota no encontrada', 404)
        total = float(row[0] or 0)
        pagado = float(row[1] or 0)
        nuevo_pagado = min(round(pagado + monto, 2), total)
        nuevo_estado = 'pagada' if nuevo_pagado >= total - 0.005 else 'abono'
        db.execute(text(
            "UPDATE notas_venta SET monto_pagado=:mp, estado=:est "
            "WHERE id=:nid AND taller_id=:t"
        ), {"mp": nuevo_pagado, "est": nuevo_estado, "nid": nid, "t": tid})
        db.execute(text("""
            INSERT INTO abonos_nota (taller_id, nota_id, monto, metodo_pago, nota, fecha)
            VALUES (:t, :nid, :m, :mp, :nt, CAST(:f AS date))
        """), {"t": tid, "nid": nid, "m": monto,
               "mp": body.get('metodo_pago') or 'efectivo',
               "nt": body.get('nota') or '', "f": fecha})
        db.commit()
        return json_ok({"ok": True, "monto_pagado": nuevo_pagado,
                        "estado": nuevo_estado,
                        "saldo": round(total - nuevo_pagado, 2),
                        "fecha": fecha})
    except Exception as e:
        db.rollback()
        return json_err(str(e))
    finally:
        db.close()


async def api_nota_pdf(request: Request):
    """GET /api/notas-venta/{nid}/pdf — HTML imprimible estilo aprobación."""
    auth = _auth_tenant(request)
    if isinstance(auth, JSONResponse): return auth
    _user, tid, db = auth
    try:
        nid = request.path_params.get('nid') or request.path_params.get('id') or ''
        try: nid = int(nid)
        except:
            return HTMLResponse('<h1>ID inválido</h1>', status_code=400)
        row = db.execute(text("""
            SELECT id, numero, fecha, cliente_id, cliente_nombre, subtotal, igv,
                   total, estado, metodo_pago, items, COALESCE(monto_pagado,0),
                   COALESCE(notas,'')
              FROM notas_venta WHERE id=:nid AND taller_id=:t
        """), {"nid": nid, "t": tid}).fetchone()
        if not row:
            return HTMLResponse('<h1>Nota no encontrada</h1>', status_code=404)
        items = _parse_json(row[10]) or []
        total = float(row[7] or 0)
        pagado = float(row[11] or 0)
        saldo = max(0.0, round(total - pagado, 2))
        cli_doc = cli_tel = cli_email = ''
        if row[3]:
            try:
                cr = db.execute(text(
                    "SELECT COALESCE(id,''), COALESCE(telefono,''), COALESCE(email,'') "
                    "FROM clientes WHERE id=:cid AND taller_id=:t"
                ), {"cid": row[3], "t": tid}).fetchone()
                if cr:
                    cli_doc, cli_tel, cli_email = cr[0] or '', cr[1] or '', cr[2] or ''
            except Exception:
                pass
        abonos = []
        try:
            rows_ab = db.execute(text(
                "SELECT monto, metodo_pago, nota, fecha FROM abonos_nota "
                "WHERE nota_id=:nid AND taller_id=:t ORDER BY id"
            ), {"nid": nid, "t": tid}).fetchall()
            abonos = [{"monto": float(a[0] or 0), "metodo": a[1] or '',
                       "nota": a[2] or '', "fecha": str(a[3] or '')[:10]}
                      for a in rows_ab]
        except Exception:
            abonos = []
        estado = 'PAGADA' if saldo <= 0.005 else ('ABONADA' if pagado > 0 else 'PENDIENTE')
        taller = _taller_info(db, tid)
        wa_msg = (f"Hola, le comparto la nota de venta {row[1]} "
                  f"por {_fmt_money(total)} emitida el {_fmt_fecha(row[2])}.")
        html = _render_doc_html(
            titulo="Nota de Venta", subtitulo="Nota de Venta",
            numero=row[1] or f"NV-{nid}", fecha=row[2],
            taller=taller,
            cliente_nombre=row[4], cliente_doc=cli_doc,
            cliente_tel=cli_tel, cliente_email=cli_email,
            items=items,
            subtotal=float(row[5] or 0), igv=float(row[6] or 0),
            total=total, pagado=pagado, saldo=saldo,
            estado=estado,
            estado_color='ok' if saldo <= 0.005 else 'warn',
            metodo_pago=row[9] or '', abonos=abonos,
            nota=row[12] or None,
            terminos=["Este documento es un comprobante interno de venta.",
                     "Los productos vendidos no tienen devolución salvo falla de fábrica.",
                     "El saldo pendiente, si existe, debe regularizarse en los términos acordados."],
            whatsapp_msg=wa_msg, whatsapp_to=cli_tel.replace('+', '').replace(' ', '') if cli_tel else '',
        )
        return HTMLResponse(html)
    finally:
        db.close()


# ═════════════════════════ COTIZACIONES (extensión) ═════════════════════════

async def api_cotizacion_detail(request: Request) -> JSONResponse:
    auth = _auth_tenant(request)
    if isinstance(auth, JSONResponse): return auth
    _user, tid, db = auth
    try:
        cid = int(request.path_params.get('cid') or request.path_params.get('id') or 0)
        row = db.execute(text("""
            SELECT id, numero, fecha_creacion, cliente_id, nombre_cliente,
                   estado, total, COALESCE(nota,'')
              FROM cotizaciones WHERE id=:id AND taller_id=:t
        """), {"id": cid, "t": tid}).fetchone()
        if not row: return json_err('Cotización no encontrada', 404)
        items = db.execute(text(
            "SELECT descripcion, tipo, cantidad, precio_unitario, subtotal "
            "FROM cotizacion_items WHERE cotizacion_id=:id ORDER BY id"
        ), {"id": cid}).fetchall()
        items_list = [{"nombre": i[0], "descripcion": i[0], "tipo": i[1] or 'repuesto',
                       "cantidad": float(i[2] or 0),
                       "precio_unitario": float(i[3] or 0),
                       "subtotal": float(i[4] or 0),
                       "total": float(i[4] or 0)} for i in items]
        return json_ok({"id": row[0], "numero": row[1],
                        "fecha": str(row[2] or ''),
                        "cliente_id": row[3], "nombre_cliente": row[4],
                        "cliente_nombre": row[4],
                        "estado": row[5], "total": float(row[6] or 0),
                        "nota": row[7], "items": items_list})
    finally:
        db.close()


def _cot_numero_nuevo(db, tid, fecha_dia):
    count = db.execute(text(
        "SELECT COUNT(*) FROM cotizaciones WHERE taller_id=:t "
        "AND CAST(fecha_creacion AS date)=CAST(:d AS date)"
    ), {"t": tid, "d": fecha_dia}).fetchone()[0]
    return f"COT-{fecha_dia.replace('-', '')}-{str(count + 1).zfill(3)}"


async def api_cotizacion_create(request: Request) -> JSONResponse:
    auth = _auth_tenant(request)
    if isinstance(auth, JSONResponse): return auth
    user, tid, db = auth
    try:
        body = await request.json()
        fecha = _safe_date(body.get('fecha')) or datetime.now().strftime('%Y-%m-%d')
        items = body.get('items') or []
        total = round(sum(float(i.get('subtotal') or i.get('total') or 0) for i in items), 2)
        numero = _cot_numero_nuevo(db, tid, fecha)
        cli_id = body.get('cliente_id')
        nombre_cliente = body.get('nombre_cliente') or body.get('cliente_nombre') or ''
        if not nombre_cliente and cli_id:
            cr = db.execute(text(
                "SELECT COALESCE(nombre,'')||' '||COALESCE(apellidos,'') "
                "FROM clientes WHERE id=:cid AND taller_id=:t"
            ), {"cid": cli_id, "t": tid}).fetchone()
            if cr: nombre_cliente = (cr[0] or '').strip()
        cot_id = db.execute(text("""
            INSERT INTO cotizaciones (taller_id, numero, fecha, cliente_id, nombre_cliente,
                estado, total, nota, creado_por, fecha_creacion)
            VALUES (:t, :n, CAST(:fc AS timestamp), :c, :cn, 'PENDIENTE',
                    :tot, :nota, :cp, CAST(:fc AS timestamp))
            RETURNING id
        """), {"t": tid, "n": numero, "fc": fecha + ' 12:00:00',
               "c": cli_id, "cn": nombre_cliente,
               "tot": total, "nota": body.get('nota') or body.get('observaciones') or '',
               "cp": user.get('nombre') or 'admin'}).fetchone()[0]
        for it in items:
            db.execute(text("""
                INSERT INTO cotizacion_items
                    (cotizacion_id, descripcion, tipo, cantidad, precio_unitario, subtotal)
                VALUES (:id, :desc, :tipo, :cant, :pu, :sub)
            """), {
                "id": cot_id,
                "desc": it.get('nombre') or it.get('descripcion') or '',
                "tipo": (it.get('tipo') or ('servicio' if 'servicio' in str(it.get('categoria', '')).lower() or 'mano' in str(it.get('categoria', '')).lower() else 'repuesto')),
                "cant": float(it.get('cantidad') or 1),
                "pu": float(it.get('precio_unitario') or 0),
                "sub": float(it.get('subtotal') or it.get('total') or 0),
            })
        db.commit()
        return json_ok({"ok": True, "id": int(cot_id), "numero": numero, "total": total})
    except Exception as e:
        db.rollback()
        return json_err(str(e))
    finally:
        db.close()


async def api_cotizacion_update(request: Request) -> JSONResponse:
    auth = _auth_tenant(request)
    if isinstance(auth, JSONResponse): return auth
    _user, tid, db = auth
    try:
        cid = int(request.path_params.get('cid') or request.path_params.get('id') or 0)
        body = await request.json()
        items = body.get('items') or []
        total = round(sum(float(i.get('subtotal') or i.get('total') or 0) for i in items), 2)
        fecha = _safe_date(body.get('fecha'))
        if fecha:
            db.execute(text("""
                UPDATE cotizaciones SET nombre_cliente=:cn, estado=:est, total=:tot,
                    nota=:nota, fecha_creacion=CAST(:fc AS timestamp),
                    fecha=CAST(:fc AS timestamp)
                WHERE id=:id AND taller_id=:t
            """), {"cn": body.get('nombre_cliente') or body.get('cliente_nombre') or '',
                   "est": body.get('estado') or 'PENDIENTE', "tot": total,
                   "nota": body.get('nota') or body.get('observaciones') or '',
                   "fc": fecha + ' 12:00:00', "id": cid, "t": tid})
        else:
            db.execute(text("""
                UPDATE cotizaciones SET nombre_cliente=:cn, estado=:est, total=:tot, nota=:nota
                WHERE id=:id AND taller_id=:t
            """), {"cn": body.get('nombre_cliente') or body.get('cliente_nombre') or '',
                   "est": body.get('estado') or 'PENDIENTE', "tot": total,
                   "nota": body.get('nota') or body.get('observaciones') or '',
                   "id": cid, "t": tid})
        db.execute(text("DELETE FROM cotizacion_items WHERE cotizacion_id=:id"), {"id": cid})
        for it in items:
            db.execute(text("""
                INSERT INTO cotizacion_items
                    (cotizacion_id, descripcion, tipo, cantidad, precio_unitario, subtotal)
                VALUES (:id, :desc, :tipo, :cant, :pu, :sub)
            """), {
                "id": cid,
                "desc": it.get('nombre') or it.get('descripcion') or '',
                "tipo": it.get('tipo') or 'repuesto',
                "cant": float(it.get('cantidad') or 1),
                "pu": float(it.get('precio_unitario') or 0),
                "sub": float(it.get('subtotal') or it.get('total') or 0),
            })
        db.commit()
        return json_ok({"ok": True, "total": total})
    except Exception as e:
        db.rollback()
        return json_err(str(e))
    finally:
        db.close()


async def api_cotizacion_pdf(request: Request):
    auth = _auth_tenant(request)
    if isinstance(auth, JSONResponse): return auth
    _user, tid, db = auth
    try:
        cid = int(request.path_params.get('cid') or request.path_params.get('id') or 0)
        row = db.execute(text("""
            SELECT id, numero, fecha_creacion, cliente_id, nombre_cliente,
                   estado, total, COALESCE(nota,'')
              FROM cotizaciones WHERE id=:id AND taller_id=:t
        """), {"id": cid, "t": tid}).fetchone()
        if not row:
            return HTMLResponse('<h1>Cotización no encontrada</h1>', status_code=404)
        items_rows = db.execute(text(
            "SELECT descripcion, tipo, cantidad, precio_unitario, subtotal "
            "FROM cotizacion_items WHERE cotizacion_id=:id ORDER BY id"
        ), {"id": cid}).fetchall()
        items = [{"nombre": i[0], "tipo": i[1] or 'repuesto',
                  "cantidad": float(i[2] or 0),
                  "precio_unitario": float(i[3] or 0),
                  "subtotal": float(i[4] or 0)} for i in items_rows]
        total = float(row[6] or 0)
        igv = round(total * 18 / 118, 2)
        subtotal = round(total - igv, 2)
        cli_doc = cli_tel = cli_email = ''
        if row[3]:
            try:
                cr = db.execute(text(
                    "SELECT COALESCE(id,''), COALESCE(telefono,''), COALESCE(email,'') "
                    "FROM clientes WHERE id=:cid AND taller_id=:t"
                ), {"cid": row[3], "t": tid}).fetchone()
                if cr:
                    cli_doc, cli_tel, cli_email = cr[0] or '', cr[1] or '', cr[2] or ''
            except Exception:
                pass
        estado = (row[5] or 'PENDIENTE').upper()
        color_est = 'ok' if estado in ('APROBADA', 'ACEPTADA') else ('red' if estado in ('RECHAZADA', 'VENCIDA') else 'warn')
        taller = _taller_info(db, tid)
        wa_msg = (f"Hola, le comparto la cotización {row[1]} "
                  f"por {_fmt_money(total)} emitida el {_fmt_fecha(row[2])}. "
                  f"Valida por 15 días.")
        html = _render_doc_html(
            titulo="Cotización", subtitulo="Cotización",
            numero=row[1] or f"COT-{cid}", fecha=row[2],
            taller=taller,
            cliente_nombre=row[4], cliente_doc=cli_doc,
            cliente_tel=cli_tel, cliente_email=cli_email,
            items=items, subtotal=subtotal, igv=igv, total=total,
            estado=estado, estado_color=color_est,
            nota=row[7] or None,
            terminos=["Cotización válida por 15 días desde la fecha de emisión.",
                     "Los precios incluyen IGV (18%).",
                     "Trabajos inician al recibir aprobación del cliente.",
                     "Los repuestos están sujetos a disponibilidad al momento de la compra."],
            whatsapp_msg=wa_msg,
            whatsapp_to=cli_tel.replace('+', '').replace(' ', '') if cli_tel else '',
        )
        return HTMLResponse(html)
    finally:
        db.close()


async def api_cotizacion_convertir(request: Request) -> JSONResponse:
    """POST /api/cotizaciones/{cid}/convertir — crea orden desde cotización."""
    auth = _auth_tenant(request)
    if isinstance(auth, JSONResponse): return auth
    user, tid, db = auth
    try:
        cid = int(request.path_params.get('cid') or request.path_params.get('id') or 0)
        cot = db.execute(text(
            "SELECT id, numero, cliente_id, nombre_cliente, total, COALESCE(nota,'') "
            "FROM cotizaciones WHERE id=:id AND taller_id=:t"
        ), {"id": cid, "t": tid}).fetchone()
        if not cot:
            return json_err('Cotización no encontrada', 404)
        items_rows = db.execute(text(
            "SELECT descripcion, tipo, cantidad, precio_unitario, subtotal "
            "FROM cotizacion_items WHERE cotizacion_id=:id ORDER BY id"
        ), {"id": cid}).fetchall()
        items = [{"nombre": i[0], "tipo": i[1] or 'repuesto',
                  "categoria": ('servicio' if (i[1] or '').lower().startswith('serv') or 'mano' in (i[1] or '').lower() else 'repuesto'),
                  "cantidad": float(i[2] or 0),
                  "precio_unitario": float(i[3] or 0),
                  "subtotal": float(i[4] or 0),
                  "total": float(i[4] or 0)} for i in items_rows]
        hoy = datetime.now()
        seq = db.execute(text(
            "SELECT COUNT(*) FROM ordenes WHERE taller_id=:t "
            "AND CAST(fecha AS date)=CAST(:d AS date)"
        ), {"t": tid, "d": hoy.strftime('%Y-%m-%d')}).fetchone()[0]
        consecutivo = f"OS-{hoy.strftime('%Y%m%d')}-{str(seq + 1).zfill(3)}"
        vehiculo_placa = ''
        if cot[2]:
            vr = db.execute(text(
                "SELECT placa FROM vehiculos WHERE cliente_id=:cid AND taller_id=:t "
                "ORDER BY id DESC LIMIT 1"
            ), {"cid": cot[2], "t": tid}).fetchone()
            if vr: vehiculo_placa = vr[0] or ''
        db.execute(text("""
            INSERT INTO ordenes (taller_id, consecutivo, fecha, cliente_id,
                vehiculo_placa, estado, items_cotizacion, notas, creado_por)
            VALUES (:t, :cons, :f, :cli, :pl, 'RECEPCIÓN', :it, :nota, :cp)
        """), {"t": tid, "cons": consecutivo, "f": hoy, "cli": cot[2],
               "pl": vehiculo_placa, "it": json.dumps(items),
               "nota": (cot[5] or '') + (f"\nGenerada desde cotización {cot[1]}" if cot[1] else ''),
               "cp": user.get('nombre') or 'admin'})
        db.execute(text(
            "UPDATE cotizaciones SET estado='CONVERTIDA' WHERE id=:id AND taller_id=:t"
        ), {"id": cid, "t": tid})
        db.commit()
        return json_ok({"ok": True, "consecutivo": consecutivo})
    except Exception as e:
        db.rollback()
        return json_err(str(e))
    finally:
        db.close()


# ═════════════════════════ CRÉDITOS (crear) ═════════════════════════

async def api_credito_create(request: Request) -> JSONResponse:
    """POST /api/creditos/nuevo — crea un crédito fiado."""
    auth = _auth_tenant(request)
    if isinstance(auth, JSONResponse): return auth
    user, tid, db = auth
    try:
        body = await request.json()
        nombre = (body.get('cliente_nombre') or body.get('cliente') or '').strip()
        if not nombre: return json_err('Cliente requerido')
        try: total = float(body.get('total') or 0)
        except: return json_err('Total inválido')
        if total <= 0: return json_err('Total debe ser > 0')
        fecha = _safe_date(body.get('fecha') or body.get('fecha_venta')) or datetime.now().strftime('%Y-%m-%d')
        vencimiento = _safe_date(body.get('fecha_amortizacion') or body.get('vencimiento'))
        items = body.get('items') or []
        if vencimiento:
            nid = db.execute(text("""
                INSERT INTO creditos (taller_id, cliente_nombre, telefono, descripcion,
                    items_json, total, pendiente, estado, nota, fecha_venta,
                    fecha_venta_dt, fecha_amortizacion, creado_por)
                VALUES (:t, :cn, :tel, :desc, :items, :tot, :tot, 'PENDIENTE',
                        :nota, :fv, CAST(:fv AS date), CAST(:fa AS date), :cp)
                RETURNING id
            """), {"t": tid, "cn": nombre,
                   "tel": body.get('telefono') or '',
                   "desc": body.get('descripcion') or '',
                   "items": json.dumps(items), "tot": total,
                   "nota": body.get('nota') or '', "fv": fecha,
                   "fa": vencimiento, "cp": user.get('nombre') or 'admin'}).fetchone()[0]
        else:
            nid = db.execute(text("""
                INSERT INTO creditos (taller_id, cliente_nombre, telefono, descripcion,
                    items_json, total, pendiente, estado, nota, fecha_venta,
                    fecha_venta_dt, creado_por)
                VALUES (:t, :cn, :tel, :desc, :items, :tot, :tot, 'PENDIENTE',
                        :nota, :fv, CAST(:fv AS date), :cp)
                RETURNING id
            """), {"t": tid, "cn": nombre,
                   "tel": body.get('telefono') or '',
                   "desc": body.get('descripcion') or '',
                   "items": json.dumps(items), "tot": total,
                   "nota": body.get('nota') or '', "fv": fecha,
                   "cp": user.get('nombre') or 'admin'}).fetchone()[0]
        db.commit()
        return json_ok({"ok": True, "id": int(nid), "fecha_venta": fecha})
    except Exception as e:
        db.rollback()
        return json_err(str(e))
    finally:
        db.close()


# ═════════════════════════ CLIENTES por documento (local-first) ═════════════════════════

async def api_cliente_por_doc(request: Request) -> JSONResponse:
    """GET /api/clientes/buscar-doc/{doc} — busca cliente en BD local por RUC/DNI.

    Si lo encuentra, devuelve {ok:true, origen:'local', ...}.
    Si no existe en local, devuelve {ok:false, origen:'local'} (el cliente
    decide si consultar /api/lookup/ruc o /api/lookup/dni a CODART)."""
    auth = _auth_tenant(request)
    if isinstance(auth, JSONResponse): return auth
    _user, tid, db = auth
    try:
        doc = (request.path_params.get('doc') or '').strip()
        if not doc.isdigit() or len(doc) not in (8, 11):
            return json_err('Documento inválido (DNI 8 o RUC 11 dígitos)', 400)
        # Schema real: clientes tiene `documento` (no ruc/dni) y `tipo` (persona/empresa)
        row = db.execute(text("""
            SELECT id, COALESCE(nombre,''), COALESCE(apellidos,''),
                   COALESCE(telefono,''), COALESCE(email,''),
                   COALESCE(direccion,''), COALESCE(tipo,''),
                   COALESCE(documento,'')
              FROM clientes
             WHERE taller_id=:t
               AND (documento=:d OR id=:d)
             LIMIT 1
        """), {"t": tid, "d": doc}).fetchone()
        if row:
            nombre = f"{row[1] or ''} {row[2] or ''}".strip() or row[1] or '—'
            return json_ok({"ok": True, "found": True, "origen": "local",
                            "id": row[0], "nombre": nombre,
                            "razon_social": nombre,
                            "telefono": row[3], "email": row[4],
                            "direccion": row[5], "tipo": row[6],
                            "documento": row[7]})
        return json_ok({"ok": False, "found": False, "origen": "local",
                        "detail": "No encontrado en clientes locales"})
    finally:
        db.close()


# ═════════════════════════ Registro de rutas ═════════════════════════

def register_extensions_routes(app):
    """Registra los endpoints de extensiones v22 en la app FastAPI."""
    # Notas de venta
    app.add_api_route('/api/notas-venta/{nid}',         api_nota_detail,
                      methods=['GET', 'OPTIONS'])
    app.add_api_route('/api/notas-venta/{nid}/abonar',  api_nota_abonar,
                      methods=['POST', 'OPTIONS'])
    app.add_api_route('/api/notas-venta/{nid}/pdf',     api_nota_pdf,
                      methods=['GET', 'OPTIONS'])

    # Cotizaciones (extensión — list y create ya existen en otros módulos,
    # pero aquí agregamos detail/create-v2/update/pdf/convertir)
    app.add_api_route('/api/cotizaciones/{cid}',            api_cotizacion_detail,
                      methods=['GET', 'OPTIONS'])
    app.add_api_route('/api/cotizaciones/{cid}',            api_cotizacion_update,
                      methods=['PUT', 'OPTIONS'])
    app.add_api_route('/api/cotizaciones/nueva',            api_cotizacion_create,
                      methods=['POST', 'OPTIONS'])
    app.add_api_route('/api/cotizaciones/{cid}/pdf',        api_cotizacion_pdf,
                      methods=['GET', 'OPTIONS'])
    app.add_api_route('/api/cotizaciones/{cid}/convertir',  api_cotizacion_convertir,
                      methods=['POST', 'OPTIONS'])

    # Créditos (create)
    app.add_api_route('/api/creditos/nuevo',  api_credito_create,
                      methods=['POST', 'OPTIONS'])

    # Clientes — búsqueda local por documento
    app.add_api_route('/api/clientes/buscar-doc/{doc}',  api_cliente_por_doc,
                      methods=['GET', 'OPTIONS'])

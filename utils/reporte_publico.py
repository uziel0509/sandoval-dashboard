"""
SANDOVAL Dashboard — Reporte Público de Servicio (HTML puro, sin NiceGUI).

Endpoint: GET /reporte/{token}
- Sin login. Acceso por `report_token` único de la orden.
- Pensado para enviar al cliente vía WhatsApp.
- Responsive, imprimible, marca de agua corporativa, botón a PDF.
"""
from __future__ import annotations

import html as _html
import json as _json
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text as _sa_text

from utils.models import get_db, Orden, Cliente, Vehiculo


# Etiquetas legibles para checklist de control de calidad (canónico + legacy).
QC_LABELS = {
    'repair_done':   'Reparación completada',
    'parts_ok':      'Repuestos instalados',
    'no_leaks':      'Sin fugas',
    'fluids_level':  'Niveles de fluidos',
    'engine_start':  'Motor arranca',
    'brakes_test':   'Prueba de frenos',
    'bodywork_ok':   'Carrocería',
    'interior_ok':   'Cabina limpia',
    'glass_ok':      'Vidrios',
    'lights_ok':     'Alumbrado',
    'tires_ok':      'Neumáticos',
    'tools_removed': 'Herramientas retiradas',
    'evidence_ok':   'Evidencia fotográfica',
    'order_signed':  'Orden firmada',
    'warranty_given':'Garantía entregada',
    'payment_ok':    'Pago / factura',
    # Aliases de la PWA antigua
    'funcional':     'Pruebas funcionales',
    'ruido':         'Sin ruidos anormales',
    'fugas':         'Sin fugas de fluidos',
    'scanner':       'Scanner sin códigos',
    'ruta':          'Prueba de ruta',
    'limpieza':      'Vehículo limpio',
}


def _esc(s: Any) -> str:
    """Escapa para uso en HTML."""
    return _html.escape(str(s) if s is not None else '', quote=True)


def _parse_json(raw: Any) -> Any:
    if raw is None or raw == '':
        return None
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return _json.loads(raw)
    except (TypeError, ValueError):
        return None


def _money(v: Any) -> str:
    try:
        return f"S/ {float(v or 0):,.2f}"
    except (TypeError, ValueError):
        return "S/ 0.00"


def _qc_normalize(qc_raw: Any) -> List[Dict[str, str]]:
    """Devuelve lista [{key,label,status}] desde:
    - Nuevo formato: [{key,label,ok}, ...]
    - Dict legacy: {repair_done: {status:'ok',note:''}, ...}
    - Dict simple: {key: bool}
    - None / vacío.
    """
    out: List[Dict[str, str]] = []
    if not qc_raw:
        return out
    if isinstance(qc_raw, list):
        for it in qc_raw:
            if not isinstance(it, dict):
                continue
            key = str(it.get('key') or '')
            label = it.get('label') or QC_LABELS.get(key, key.replace('_', ' ').title())
            status = 'ok' if (it.get('ok') is True) else (
                'obs' if str(it.get('estado','')).lower() in ('obs','observacion') else 'none'
            )
            note = (it.get('note') or it.get('observacion') or '').strip()
            out.append({'label': label, 'status': status, 'note': note})
        return out
    if isinstance(qc_raw, dict):
        for k, v in qc_raw.items():
            label = QC_LABELS.get(k, k.replace('_', ' ').title())
            if isinstance(v, dict):
                st = (v.get('status') or '').lower()
                note = (v.get('note') or '').strip()
                if st not in ('ok', 'obs'):
                    st = 'none'
            elif v is True:
                st, note = 'ok', ''
            elif v is False:
                st, note = 'none', ''
            else:
                st, note = 'none', str(v) if v else ''
            out.append({'label': label, 'status': st, 'note': note})
    return out


def _extract_qc(checklist: Dict[str, Any]) -> List[Dict[str, str]]:
    """Encuentra el control de calidad en cualquier ubicación conocida."""
    if not isinstance(checklist, dict):
        return []
    for key in ('control_calidad', 'calidad', 'quality_control', 'qc'):
        v = checklist.get(key)
        if isinstance(v, dict):
            inner = v.get('checklist') or v.get('items') or v.get('tareas')
            if inner:
                return _qc_normalize(inner)
            # dict directo legacy
            return _qc_normalize(v)
        if isinstance(v, list) and v:
            return _qc_normalize(v)
    return []


def _extract_repair_logs(checklist: Dict[str, Any]) -> List[Dict[str, str]]:
    """Lista de actividades de reparación (compatibilidad con varios formatos)."""
    if not isinstance(checklist, dict):
        return []
    # Nuevo: ck.reparacion.items = [{tarea, completado, hora}]
    rep = checklist.get('reparacion')
    if isinstance(rep, dict):
        for k in ('items', 'actividades', 'tareas'):
            v = rep.get(k)
            if isinstance(v, list) and v:
                return [
                    {'falla': it.get('tarea') or it.get('falla') or '—',
                     'solucion': '✓ Completado' if it.get('completado') else '',
                     'hora': str(it.get('hora') or '')}
                    for it in v if isinstance(it, dict)
                ]
    # Legacy NiceGUI: ck.repair_logs = [{falla, solucion}]
    legacy = checklist.get('repair_logs')
    if isinstance(legacy, list) and legacy:
        return [
            {'falla': it.get('falla', '—'),
             'solucion': it.get('solucion', ''),
             'hora': str(it.get('hora') or '')}
            for it in legacy if isinstance(it, dict)
        ]
    return []


def _extract_evidence(checklist: Dict[str, Any], fotos_evidencia: Any,
                      consecutivo: str) -> Dict[str, List[str]]:
    """Devuelve {categoria: [urls...]} unificando los dos formatos:
    - Legacy: ck.evidence_cats = {recepcion_antes: ['file.jpg', ...]}
    - Nuevo: o.fotos_evidencia = [{url:'/static/evidencia/...', fase:'reparacion', tipo:'foto'}, ...]
    Se omiten PDFs (se enlazan aparte).
    """
    out: Dict[str, List[str]] = {}
    # Legacy evidence_cats
    if isinstance(checklist, dict):
        ev_cats = checklist.get('evidence_cats') or {}
        if isinstance(ev_cats, dict):
            for cat, files in ev_cats.items():
                if not isinstance(files, list):
                    continue
                urls = [f'/evidencia/{consecutivo}/{cat}/{fn}' for fn in files if fn]
                if urls:
                    out.setdefault(cat, []).extend(urls)
    # Nuevo formato con paths absolutos
    if isinstance(fotos_evidencia, list):
        for it in fotos_evidencia:
            if not isinstance(it, dict):
                continue
            url = it.get('url') or it.get('path') or ''
            tipo = (it.get('tipo') or '').lower()
            if not url or tipo == 'pdf':
                continue
            cat = (it.get('fase') or 'general').lower()
            out.setdefault(cat, []).append(url)
    return out


def _extract_pdfs(fotos_evidencia: Any) -> List[Dict[str, str]]:
    """Devuelve PDFs adjuntos del scanner: [{url, nombre, fase}]."""
    out = []
    if isinstance(fotos_evidencia, list):
        for it in fotos_evidencia:
            if not isinstance(it, dict):
                continue
            tipo = (it.get('tipo') or '').lower()
            url = it.get('url') or it.get('path') or ''
            if tipo == 'pdf' and url:
                out.append({
                    'url': url,
                    'nombre': it.get('nombre') or url.rsplit('/', 1)[-1],
                    'fase': (it.get('fase') or '').upper(),
                })
    return out


def _fetch_order_data(token: str) -> Optional[Dict[str, Any]]:
    """Devuelve dict listo para renderizar, o None si el token no existe.

    En modo RLS STRICT, antes de hacer queries normales necesitamos
    descubrir el `taller_id` del token (vía función SECURITY DEFINER) y
    luego abrir el get_db dentro de `with_taller(...)` para que las
    policies dejen pasar las queries sobre clientes/vehículos.
    """
    info = _lookup_by_report_token(token)
    if not info:
        return None
    try:
        from utils.rls_session import with_taller
    except Exception:
        # Sin RLS configurado: no envolver
        from contextlib import nullcontext
        with_taller = lambda _x: nullcontext()  # noqa: E731
    with with_taller(info["taller_id"]):
        db = get_db()
        try:
            order = db.query(Orden).filter_by(report_token=token).first()
            if not order:
                return None
            client = (db.query(Cliente).filter_by(id=order.cliente_id).first()
                      if order.cliente_id else None)
            vehicle = (db.query(Vehiculo).filter_by(placa=order.vehiculo_placa).first()
                       if order.vehiculo_placa else None)
            checklist = _parse_json(order.checklist_reparacion) or {}
            items = _parse_json(order.items_cotizacion) or []
            if not isinstance(items, list):
                items = []
            fotos_ev = _parse_json(order.fotos_evidencia) or []

            # Cálculos
            try:
                total_rep = sum(float(i.get('total') or 0) for i in items if isinstance(i, dict))
            except (TypeError, ValueError):
                total_rep = 0.0

            return {
                'consecutivo': order.consecutivo,
                'fecha': (order.fecha or '')[:16],
                'motivo': order.motivo or '',
                'diagnostico': order.diagnostico or '',
                'tecnico': order.tecnico or '',
                'km': order.km or '',
                'estado': order.estado or '',
                'cliente_nombre': (
                    f"{client.nombre} {(client.apellidos or '').strip()}".strip()
                    if client else '—'
                ),
                'cliente_telefono': (client.telefono if client else '') or '—',
                'cliente_documento': (getattr(client, 'documento', '') if client else '') or '—',
                'vehiculo_marca': (vehicle.marca if vehicle else '') or '',
                'vehiculo_modelo': (vehicle.modelo if vehicle else '') or '',
                'vehiculo_anio': (
                    getattr(vehicle, 'año', None) or getattr(vehicle, 'anio', None) or ''
                ) if vehicle else '',
                'vehiculo_placa': (vehicle.placa if vehicle else '') or '—',
                'vehiculo_vin': (getattr(vehicle, 'vin', '') if vehicle else '') or '—',
                'items': items,
                'total_rep': total_rep,
                'qc_list': _extract_qc(checklist),
                'repair_logs': _extract_repair_logs(checklist),
                'evidencia': _extract_evidence(checklist, fotos_ev, order.consecutivo),
                'pdfs': _extract_pdfs(fotos_ev),
            }
        finally:
            db.close()


# ─────────────────────────────────────────────────────────────────
# Render HTML
# ─────────────────────────────────────────────────────────────────
def _render_not_found() -> str:
    return """<!doctype html>
<html lang="es"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Reporte no encontrado — SANDOVAL</title>
<meta name="robots" content="noindex, nofollow">
<style>
  body{font-family:system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;
       background:#f4f6f9;color:#64748b;min-height:100vh;
       display:flex;flex-direction:column;align-items:center;justify-content:center;
       padding:20px;text-align:center;gap:12px;margin:0}
  .ico{font-size:64px}
  h1{font-size:22px;color:#1e293b;margin:0}
  p{font-size:14px;max-width:420px;line-height:1.5}
  a{color:#1d4ed8;text-decoration:none;font-weight:600;margin-top:12px}
</style>
</head><body>
<div class="ico">🔍</div>
<h1>Reporte no encontrado</h1>
<p>El enlace que abriste no es válido o ha expirado. Si recibiste este link
por WhatsApp, contacta al taller para que te envíen uno nuevo.</p>
<a href="https://sandoval.pe">sandoval.pe</a>
</body></html>"""


def _render_report(d: Dict[str, Any], token: str) -> str:
    e = _esc

    # ── Cabecera de info-cards ───────────────────────────────────
    veh_str = ' '.join(s for s in [d['vehiculo_marca'], d['vehiculo_modelo'],
                                    str(d['vehiculo_anio'] or '').strip()] if s)
    info_cliente = [
        ('Nombre',    d['cliente_nombre']),
        ('Teléfono',  d['cliente_telefono']),
        ('Documento', d['cliente_documento']),
    ]
    info_vehiculo = [
        ('Vehículo',   veh_str or '—'),
        ('Placa',      d['vehiculo_placa']),
        ('VIN',        d['vehiculo_vin']),
        ('Técnico',    d['tecnico'] or '—'),
        ('Ingreso',    d['fecha'] or '—'),
        ('Kilómetros', str(d['km']) if d['km'] else '—'),
    ]

    # ── Tabla de repuestos ───────────────────────────────────────
    items_html = ''
    if d['items']:
        rows = []
        for it in d['items']:
            if not isinstance(it, dict):
                continue
            desc = it.get('nombre') or it.get('descripcion') or '—'
            cant = it.get('cantidad') or 1
            pu   = float(it.get('precio_unitario') or it.get('precio') or 0)
            tot  = float(it.get('total') or pu * float(cant or 1))
            rows.append(f'''<tr>
                <td style="font-weight:600;color:#1e293b">{e(desc)}</td>
                <td class="td-num" style="color:#64748b">x{e(cant)}</td>
                <td class="td-num" style="color:#64748b">{e(_money(pu))}</td>
                <td class="td-num" style="font-weight:700;color:#1e293b">{e(_money(tot))}</td>
            </tr>''')
        items_html = f'''
        <section class="card">
          <header class="card-hdr">
            <span class="ico" style="background:#f0fdf4">🔩</span>
            <div><h2>Repuestos e Insumos</h2>
                 <p>{len(d['items'])} ítem(s) utilizados en la reparación</p></div>
          </header>
          <table class="rep-table">
            <thead><tr>
              <th>Descripción del ítem</th>
              <th style="text-align:right">Cant.</th>
              <th style="text-align:right">Unit.</th>
              <th style="text-align:right">Total</th>
            </tr></thead>
            <tbody>{''.join(rows)}</tbody>
          </table>
          <div class="rep-total">
            <div>
              <span class="rt-tag">INVERSIÓN EN REPUESTOS</span>
              <span class="rt-lbl">TOTAL GENERAL</span>
            </div>
            <span class="rt-val">{e(_money(d['total_rep']))}</span>
          </div>
        </section>'''

    # ── Bitácora reparación ──────────────────────────────────────
    repair_html = ''
    if d['repair_logs']:
        logs = []
        for i, log in enumerate(d['repair_logs'], 1):
            sol = log.get('solucion', '')
            hora = log.get('hora', '')
            sol_html = f'<div class="log-sol">{e(sol)}</div>' if sol else ''
            hora_html = f'<div class="log-hora">⏱ {e(hora)}</div>' if hora else ''
            logs.append(f'''<div class="log-item">
                <div class="log-num">Intervención #{i}</div>
                <div class="log-falla">{e(log.get('falla','—'))}</div>
                {sol_html}{hora_html}
            </div>''')
        repair_html = f'''
        <section class="card">
          <header class="card-hdr">
            <span class="ico" style="background:#fff7ed">🔧</span>
            <div><h2>Trabajo de Reparación</h2>
                 <p>{len(d['repair_logs'])} intervención(es) registrada(s)</p></div>
          </header>
          {''.join(logs)}
        </section>'''

    # ── Evidencia fotográfica ────────────────────────────────────
    ev_html = ''
    total_fotos = sum(len(v) for v in d['evidencia'].values())
    if total_fotos > 0:
        cats = []
        for cat, urls in d['evidencia'].items():
            if not urls:
                continue
            cat_label = cat.replace('_', ' ').title()
            imgs = ''.join(
                f'<a href="{e(u)}" target="_blank" rel="noopener"><img src="{e(u)}" '
                f'class="ev-img" loading="lazy" alt="Evidencia {e(cat_label)}" '
                f'onerror="this.style.display=\'none\'"></a>'
                for u in urls
            )
            cats.append(
                f'<div class="ev-cat-title">{e(cat_label)} ({len(urls)} foto(s))</div>'
                f'<div class="ev-grid">{imgs}</div>'
            )
        ev_html = f'''
        <section class="card">
          <header class="card-hdr">
            <span class="ico" style="background:#fdf4ff">📷</span>
            <div><h2>Evidencia Fotográfica</h2>
                 <p>{total_fotos} foto(s) registrada(s) durante el servicio</p></div>
          </header>
          {''.join(cats)}
        </section>'''

    # ── PDFs adjuntos del scanner ────────────────────────────────
    pdf_html = ''
    if d['pdfs']:
        chips = ''.join(
            f'<a class="pdf-chip" href="{e(p["url"])}" target="_blank" rel="noopener">'
            f'<span class="pdf-ico">📄</span><span>{e(p["nombre"])}</span>'
            f'{f"<small>{e(p[chr(34)+chr(102)+chr(97)+chr(115)+chr(101)+chr(34)])}</small>" if p.get("fase") else ""}</a>'
            for p in d['pdfs']
        )
        # Versión más simple del chip (la f-string anterior tenía escapes raros)
        chips = ''.join(
            f'<a class="pdf-chip" href="{e(p["url"])}" target="_blank" rel="noopener">'
            f'<span class="pdf-ico">📄</span>'
            f'<span class="pdf-name">{e(p["nombre"])}</span>'
            + (f'<span class="pdf-fase">{e(p["fase"])}</span>' if p.get('fase') else '')
            + '</a>'
            for p in d['pdfs']
        )
        pdf_html = f'''
        <section class="card">
          <header class="card-hdr">
            <span class="ico" style="background:#fef2f2">📑</span>
            <div><h2>Reportes del Scanner</h2>
                 <p>{len(d['pdfs'])} archivo(s) PDF adjunto(s)</p></div>
          </header>
          <div class="pdf-list">{chips}</div>
        </section>'''

    # ── Control de calidad ───────────────────────────────────────
    qc_html = ''
    if d['qc_list']:
        items = ''
        for q in d['qc_list']:
            st = q.get('status', 'none')
            ico = '✓' if st == 'ok' else ('⚠' if st == 'obs' else '–')
            note = (f' <em>({e(q["note"])})</em>' if q.get('note') else '')
            items += f'<div class="qc-item {st}">{ico} {e(q["label"])}{note}</div>'
        qc_html = f'''
        <section class="card">
          <header class="card-hdr">
            <span class="ico" style="background:#f0fdf4">✅</span>
            <div><h2>Control de Calidad — Inspección Final</h2>
                 <p>Verificación previa a la entrega del vehículo</p></div>
          </header>
          <div class="qc-grid">{items}</div>
        </section>'''

    # ── Render final ─────────────────────────────────────────────
    info_cliente_html = ''.join(
        f'<div class="info-row"><span class="info-lbl">{e(l)}</span>'
        f'<span class="info-val">{e(v)}</span></div>'
        for l, v in info_cliente
    )
    info_vehiculo_html = ''.join(
        f'<div class="info-row"><span class="info-lbl">{e(l)}</span>'
        f'<span class="info-val">{e(v)}</span></div>'
        for l, v in info_vehiculo
    )

    gen_date = datetime.now().strftime('%d/%m/%Y %H:%M')
    pdf_url = f'/api/reporte/{e(token)}/pdf'

    return f'''<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<meta name="theme-color" content="#1e5c3a">
<title>Reporte de Servicio {e(d['consecutivo'])} — SANDOVAL</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
<style>
  *,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
  html,body{{font-family:'Inter',system-ui,sans-serif;background:#f4f6f9;color:#1e293b;min-height:100vh;line-height:1.5}}
  body::before{{content:'';position:fixed;top:50%;left:50%;transform:translate(-50%,-50%);
    width:520px;height:520px;background:url('/assets/logo_sandoval.jpg') center/contain no-repeat;
    opacity:.045;pointer-events:none;z-index:0}}
  .wrap{{position:relative;z-index:1;max-width:880px;margin:0 auto;padding:28px 18px 90px}}

  /* Cabecera */
  .hdr{{background:#fff;border-radius:18px;padding:24px 28px;margin-bottom:22px;
       display:flex;align-items:center;gap:22px;box-shadow:0 2px 12px rgba(0,0,0,.07)}}
  .hdr-logo{{width:74px;height:74px;object-fit:contain;flex-shrink:0;border-radius:12px;background:#fff}}
  .hdr-info{{flex:1;min-width:0}}
  .hdr-co{{font-size:18px;font-weight:800;color:#1e5c3a;letter-spacing:.02em}}
  .hdr-sub{{font-size:11.5px;color:#64748b;margin-top:3px}}
  .hdr-badge{{background:linear-gradient(135deg,#1d4ed8,#3b82f6);color:#fff;border-radius:12px;
    padding:9px 18px;text-align:center;font-weight:700;font-size:13px;flex-shrink:0;
    box-shadow:0 4px 14px rgba(59,130,246,.35)}}
  .hdr-badge small{{display:block;font-size:9px;font-weight:400;opacity:.85;margin-top:2px}}
  @media (max-width:580px){{.hdr{{flex-wrap:wrap;padding:18px 20px}} .hdr-badge{{order:3;width:100%;margin-top:6px}}}}

  /* Grid info */
  .info-grid{{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:22px}}
  @media (max-width:600px){{.info-grid{{grid-template-columns:1fr}}}}
  .info-card{{background:#fff;border-radius:14px;padding:18px;box-shadow:0 1px 6px rgba(0,0,0,.06);
    border:1px solid #e8edf2}}
  .info-card-title{{font-size:9px;font-weight:800;color:#94a3b8;text-transform:uppercase;
    letter-spacing:.14em;margin-bottom:11px;padding-bottom:8px;border-bottom:1px solid #f1f5f9}}
  .info-row{{display:flex;justify-content:space-between;padding:5px 0;gap:8px}}
  .info-lbl{{font-size:11.5px;color:#64748b;flex-shrink:0}}
  .info-val{{font-size:12.5px;font-weight:600;color:#1e293b;text-align:right;
    overflow-wrap:anywhere;min-width:0}}

  /* Cards */
  .card{{background:#fff;border-radius:14px;padding:22px;margin-bottom:18px;
    box-shadow:0 1px 6px rgba(0,0,0,.06);border:1px solid #e8edf2}}
  .card-hdr{{display:flex;align-items:center;gap:11px;margin-bottom:14px;
    padding-bottom:11px;border-bottom:1px solid #f1f5f9}}
  .card-hdr .ico{{width:34px;height:34px;border-radius:10px;display:flex;align-items:center;
    justify-content:center;font-size:17px;flex-shrink:0}}
  .card-hdr h2{{font-size:14.5px;font-weight:700;color:#1e293b}}
  .card-hdr p{{font-size:11px;color:#64748b;margin-top:2px}}

  /* Diagnóstico */
  .diag-block{{margin-bottom:16px}}
  .diag-tag-cli{{font-size:10px;font-weight:800;color:#3b82f6;text-transform:uppercase;
    letter-spacing:.08em;margin-bottom:7px;display:inline-block}}
  .diag-tag-tec{{font-size:10px;font-weight:800;color:#059669;text-transform:uppercase;
    letter-spacing:.08em;margin-bottom:7px;display:inline-block}}
  .diag-box{{padding:14px 16px;border-radius:11px;font-size:13px;line-height:1.6;
    border-left:4px solid;white-space:pre-wrap;word-wrap:break-word}}
  .diag-cli{{background:#f8fafc;border:1px solid #e2e8f0;color:#475569;border-left-color:#3b82f6}}
  .diag-tec{{background:#f0fdf4;border:1px solid #bbf7d0;color:#166534;border-left-color:#10b981;font-weight:500}}

  /* Tabla repuestos */
  .rep-table{{width:100%;border-collapse:collapse}}
  .rep-table th{{background:#f8fafc;font-size:10px;font-weight:700;color:#94a3b8;
    text-transform:uppercase;letter-spacing:.08em;padding:9px 12px;text-align:left;
    border-bottom:1px solid #e2e8f0}}
  .rep-table td{{padding:11px 12px;font-size:12.5px;color:#374151;border-bottom:1px solid #f1f5f9}}
  .rep-table tr:last-child td{{border-bottom:none}}
  .rep-table .td-num{{text-align:right;font-weight:600;font-variant-numeric:tabular-nums}}
  .rep-total{{background:#f0fdf4;border:1px solid #bbf7d0;border-radius:11px;
    padding:13px 16px;margin-top:12px;display:flex;justify-content:space-between;align-items:center}}
  .rt-tag{{font-size:9.5px;font-weight:800;color:#166534;opacity:.7;text-transform:uppercase;display:block}}
  .rt-lbl{{font-size:13px;font-weight:700;color:#166534;display:block;margin-top:2px}}
  .rt-val{{font-size:19px;font-weight:800;color:#166534;font-variant-numeric:tabular-nums}}

  /* Logs */
  .log-item{{background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;
    padding:13px 15px;margin-bottom:9px}}
  .log-num{{font-size:10px;font-weight:800;color:#3b82f6;text-transform:uppercase;
    letter-spacing:.08em;margin-bottom:4px}}
  .log-falla{{font-size:13px;font-weight:700;color:#1e293b}}
  .log-sol{{font-size:12px;color:#10b981;margin-top:6px;font-weight:500}}
  .log-sol::before{{content:'↳ ';font-weight:700}}
  .log-hora{{font-size:10.5px;color:#94a3b8;margin-top:4px}}

  /* Evidencia */
  .ev-cat-title{{font-size:10px;font-weight:800;color:#64748b;text-transform:uppercase;
    letter-spacing:.1em;margin:14px 0 9px}}
  .ev-cat-title:first-child{{margin-top:0}}
  .ev-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:9px}}
  .ev-img{{width:100%;aspect-ratio:4/3;object-fit:cover;border-radius:10px;
    border:1px solid #e2e8f0;box-shadow:0 1px 4px rgba(0,0,0,.08);cursor:zoom-in;transition:transform .15s}}
  .ev-img:hover{{transform:scale(1.02);box-shadow:0 4px 14px rgba(0,0,0,.12)}}

  /* PDFs */
  .pdf-list{{display:flex;flex-wrap:wrap;gap:8px}}
  .pdf-chip{{display:inline-flex;align-items:center;gap:8px;background:#fef2f2;
    border:1px solid #fecaca;color:#991b1b;padding:8px 12px;border-radius:10px;
    text-decoration:none;font-size:12px;font-weight:600;max-width:100%;transition:all .15s}}
  .pdf-chip:hover{{background:#fee2e2;border-color:#fca5a5;transform:translateY(-1px)}}
  .pdf-ico{{font-size:16px}}
  .pdf-name{{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:200px}}
  .pdf-fase{{font-size:9.5px;background:#991b1b;color:#fff;padding:2px 7px;border-radius:5px;
    font-weight:800;letter-spacing:.04em}}

  /* Quality control */
  .qc-grid{{display:grid;grid-template-columns:1fr 1fr;gap:8px}}
  @media (max-width:520px){{.qc-grid{{grid-template-columns:1fr}}}}
  .qc-item{{display:flex;align-items:center;gap:8px;padding:9px 12px;border-radius:9px;
    font-size:12.5px;font-weight:500;border:1px solid}}
  .qc-item.ok{{background:#f0fdf4;color:#166534;border-color:#bbf7d0}}
  .qc-item.obs{{background:#fffbeb;color:#92400e;border-color:#fde68a}}
  .qc-item.none{{background:#f1f5f9;color:#64748b;border-color:#e2e8f0}}

  /* Footer */
  .footer{{background:#1e5c3a;border-radius:14px;padding:22px 26px;color:#fff;text-align:center;
    margin-top:24px;box-shadow:0 4px 16px rgba(30,92,58,.3)}}
  .footer-title{{font-size:14px;font-weight:800;letter-spacing:.04em}}
  .footer-sub{{font-size:11px;opacity:.78;margin-top:4px}}
  .footer-mini{{font-size:10.5px;opacity:.55;margin-top:10px;line-height:1.5}}

  /* Action bar (botones flotantes) */
  .action-bar{{position:fixed;bottom:18px;right:18px;z-index:99;display:flex;flex-direction:column;gap:10px}}
  .btn{{border:none;border-radius:50px;padding:13px 22px;font-size:13px;font-weight:700;
    cursor:pointer;font-family:inherit;letter-spacing:.02em;display:inline-flex;align-items:center;
    gap:8px;transition:all .2s;text-decoration:none;justify-content:center}}
  .btn-pdf{{background:linear-gradient(135deg,#dc2626,#ef4444);color:#fff;box-shadow:0 6px 20px rgba(220,38,38,.4)}}
  .btn-pdf:hover{{box-shadow:0 8px 28px rgba(220,38,38,.55);transform:translateY(-2px)}}
  .btn-print{{background:linear-gradient(135deg,#1d4ed8,#3b82f6);color:#fff;box-shadow:0 6px 20px rgba(59,130,246,.4)}}
  .btn-print:hover{{box-shadow:0 8px 28px rgba(59,130,246,.55);transform:translateY(-2px)}}
  @media (max-width:520px){{.action-bar{{left:18px;right:18px;bottom:14px;flex-direction:row}}
    .btn{{flex:1}}}}

  @media print{{
    .action-bar{{display:none!important}}
    body::before{{opacity:.06!important}}
    body{{background:#fff}}
    .wrap{{max-width:100%;padding:14px}}
    .card,.info-card,.hdr{{box-shadow:none;border:1px solid #e2e8f0;break-inside:avoid}}
    .ev-grid{{grid-template-columns:repeat(3,1fr)}}
  }}
</style>
</head>
<body>
<div class="wrap">

  <!-- Cabecera -->
  <header class="hdr">
    <img src="/assets/logo_sandoval.jpg" class="hdr-logo" alt="Logo SANDOVAL"
         onerror="this.style.display='none'">
    <div class="hdr-info">
      <div class="hdr-co">MECÁNICA Y REPUESTOS SANDOVAL</div>
      <div class="hdr-sub">Reporte de servicio completo · {e(d['fecha'] or gen_date)}</div>
    </div>
    <div class="hdr-badge">
      {e(d['consecutivo'])}<small>REPORTE DE ENTREGA</small>
    </div>
  </header>

  <!-- Info cliente + vehículo -->
  <div class="info-grid">
    <div class="info-card">
      <div class="info-card-title">👤 Datos del cliente</div>
      {info_cliente_html}
    </div>
    <div class="info-card">
      <div class="info-card-title">🚗 Datos del vehículo</div>
      {info_vehiculo_html}
    </div>
  </div>

  <!-- Diagnóstico -->
  <section class="card">
    <header class="card-hdr">
      <span class="ico" style="background:#eff6ff">🔍</span>
      <div><h2>Diagnóstico Técnico</h2>
           <p>Evaluación profesional del vehículo</p></div>
    </header>
    <div class="diag-block">
      <span class="diag-tag-cli">● Reporte del cliente</span>
      <div class="diag-box diag-cli">{e(d['motivo'] or 'Sin motivo registrado.')}</div>
    </div>
    <div>
      <span class="diag-tag-tec">● Hallazgos del especialista</span>
      <div class="diag-box diag-tec">{e(d['diagnostico'] or 'Diagnóstico aún no registrado.')}</div>
    </div>
  </section>

  {items_html}
  {repair_html}
  {ev_html}
  {pdf_html}
  {qc_html}

  <!-- Footer -->
  <div class="footer">
    <div class="footer-title">MECÁNICA Y REPUESTOS SANDOVAL EIRL</div>
    <div class="footer-sub">RUC 20608755111 · Piura, Perú</div>
    <div class="footer-mini">Reporte generado el {gen_date}<br>
      Este documento es válido como comprobante del servicio prestado.</div>
  </div>
</div>

<!-- Acciones flotantes -->
<div class="action-bar">
  <a class="btn btn-pdf" href="{pdf_url}" target="_blank" rel="noopener">
    📄 Descargar PDF
  </a>
  <button class="btn btn-print" onclick="window.print()">
    🖨️ Imprimir
  </button>
</div>

</body></html>'''


# ─────────────────────────────────────────────────────────────────
# Handlers para registrar como rutas
# ─────────────────────────────────────────────────────────────────
def render_reporte_publico(token: str) -> Tuple[str, int]:
    """Devuelve (html, status_code). Útil para FastAPI handlers."""
    data = _fetch_order_data(token)
    if not data:
        return _render_not_found(), 404
    return _render_report(data, token), 200


def _lookup_by_report_token(token: str):
    """Bypasea RLS via función SECURITY DEFINER en PG.
    Devuelve dict {taller_id, consecutivo} o None.
    """
    if not token or len(token) < 16:
        return None
    db = get_db()
    try:
        try:
            row = db.execute(_sa_text(
                "SELECT taller_id, consecutivo FROM lookup_taller_by_report_token(:t)"
            ), {"t": token}).fetchone()
            if not row:
                return None
            return {"taller_id": int(row[0]), "consecutivo": row[1]}
        except Exception:
            # Fallback: BD sin la función SECURITY DEFINER (SQLite dev) o
            # antes de la migración. La policy permisiva de RLS deja pasar.
            row = db.execute(_sa_text(
                "SELECT taller_id, consecutivo FROM ordenes WHERE report_token=:t LIMIT 1"
            ), {"t": token}).fetchone()
            if not row:
                return None
            return {"taller_id": int(row[0]), "consecutivo": row[1]}
    finally:
        db.close()


def get_taller_id_by_token(token: str) -> Optional[int]:
    """Devuelve taller_id de la orden con ese report_token, o None."""
    info = _lookup_by_report_token(token)
    return info["taller_id"] if info else None


def get_consecutivo_by_token(token: str) -> Optional[str]:
    """Devuelve consecutivo de la orden con ese report_token, o None."""
    info = _lookup_by_report_token(token)
    return info["consecutivo"] if info else None

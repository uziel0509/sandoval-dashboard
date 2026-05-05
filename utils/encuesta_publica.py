"""
SANDOVAL Dashboard — Encuesta de satisfacción pública (HTML puro, sin NiceGUI).

Endpoints:
  GET  /encuesta/{token}           → HTML del formulario (o agradecimiento si ya respondió)
  POST /api/encuesta/{token}/submit → guarda la respuesta en orden.encuesta

Acceso público con `report_token` (mismo que /reporte/{token}).
"""
from __future__ import annotations

import html as _html
import json as _json
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

from utils.models import get_db, Orden, Cliente


def _esc(s: Any) -> str:
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


# ─────────────────────────────────────────────────────────────────
# Lookup
# ─────────────────────────────────────────────────────────────────
def _lookup_taller(token: str):
    """Bypasea RLS via función SECURITY DEFINER. Devuelve dict o None."""
    if not token or len(token) < 16:
        return None
    from sqlalchemy import text as _t
    db = get_db()
    try:
        try:
            row = db.execute(_t(
                "SELECT taller_id, consecutivo FROM lookup_taller_by_report_token(:t)"
            ), {"t": token}).fetchone()
        except Exception:
            row = db.execute(_t(
                "SELECT taller_id, consecutivo FROM ordenes WHERE report_token=:t LIMIT 1"
            ), {"t": token}).fetchone()
        if not row:
            return None
        return {"taller_id": int(row[0]), "consecutivo": row[1]}
    finally:
        db.close()


def _fetch(token: str) -> Optional[Dict[str, Any]]:
    info = _lookup_taller(token)
    if not info:
        return None
    try:
        from utils.rls_session import with_taller
    except Exception:
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
            encuesta = _parse_json(order.encuesta) or {}
            return {
                'consecutivo': order.consecutivo,
                'cliente_nombre': (client.nombre if client else 'estimado cliente').strip() or 'estimado cliente',
                'completada': bool(encuesta.get('completada')),
                'encuesta_actual': encuesta,
            }
        finally:
            db.close()


# ─────────────────────────────────────────────────────────────────
# Renderers
# ─────────────────────────────────────────────────────────────────
_NOT_FOUND_HTML = """<!doctype html>
<html lang="es"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Encuesta no válida — SANDOVAL</title>
<meta name="robots" content="noindex,nofollow">
<style>
  body{font-family:system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;
       background:#f8fafc;color:#64748b;min-height:100vh;
       display:flex;flex-direction:column;align-items:center;justify-content:center;
       padding:20px;text-align:center;gap:14px;margin:0}
  .ico{font-size:64px;color:#cbd5e1}
  h1{font-size:22px;color:#1e293b;margin:0}
  p{font-size:14px;max-width:420px;line-height:1.5}
</style>
</head><body>
<div class="ico">⚠️</div>
<h1>Encuesta no válida</h1>
<p>El link ha expirado o no existe. Si recibiste este link por WhatsApp,
por favor contacta al taller para que te envíen uno nuevo.</p>
</body></html>"""


def _render_thanks(d: Dict[str, Any]) -> str:
    return f"""<!doctype html>
<html lang="es"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>¡Gracias! — SANDOVAL</title>
<meta name="robots" content="noindex,nofollow">
<meta name="theme-color" content="#10b981">
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:'Inter',system-ui,sans-serif;background:#f8fafc;color:#0f172a;
       min-height:100vh;display:flex;flex-direction:column;align-items:center;
       justify-content:center;padding:20px;text-align:center;gap:18px}}
  .ico{{width:96px;height:96px;border-radius:50%;background:linear-gradient(135deg,#10b981,#059669);
       color:#fff;font-size:54px;display:flex;align-items:center;justify-content:center;
       box-shadow:0 8px 24px rgba(16,185,129,.35)}}
  h1{{font-size:26px;font-weight:900;color:#0f172a}}
  p{{font-size:14.5px;color:#475569;max-width:440px;line-height:1.6}}
  .footer{{font-size:11px;color:#94a3b8;letter-spacing:.12em;text-transform:uppercase;margin-top:24px}}
</style>
</head><body>
<div class="ico">✓</div>
<h1>¡Muchas gracias por tu tiempo!</h1>
<p>Tu opinión ha sido registrada exitosamente. Nos ayuda a seguir brindándote
el mejor servicio técnico de la región.</p>
<div class="footer">MECÁNICA Y REPUESTOS SANDOVAL</div>
</body></html>"""


def _render_form(d: Dict[str, Any], token: str) -> str:
    name = _esc(d['cliente_nombre'])
    cons = _esc(d['consecutivo'])
    return f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<meta name="theme-color" content="#1e40af">
<title>Encuesta de satisfacción · {cons} — SANDOVAL</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800;900&display=swap" rel="stylesheet">
<style>
  *,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
  html,body{{font-family:'Inter',system-ui,sans-serif;background:#f8fafc;color:#0f172a;
            min-height:100vh;line-height:1.5}}
  .hero{{background:linear-gradient(135deg,#1e40af,#3b82f6);padding:36px 20px 60px;color:#fff;
       text-align:center;border-radius:0 0 28px 28px;box-shadow:0 6px 20px rgba(30,64,175,.25)}}
  .hero img{{width:72px;height:72px;border-radius:14px;background:#fff;padding:6px;margin-bottom:14px;
            box-shadow:0 4px 12px rgba(0,0,0,.18)}}
  .hero h1{{font-size:24px;font-weight:900;letter-spacing:.01em}}
  .hero p{{opacity:.9;font-size:13.5px;margin-top:6px;max-width:480px;margin-left:auto;margin-right:auto}}
  .wrap{{max-width:540px;margin:-46px auto 30px;padding:0 16px}}
  .card{{background:#fff;border-radius:18px;padding:24px;box-shadow:0 10px 30px rgba(0,0,0,.06);
        border:1px solid #e8edf2}}
  .card h2{{font-size:16px;font-weight:800;color:#0f172a;text-align:center;margin-bottom:6px}}
  .card .order-tag{{display:block;font-size:11px;color:#64748b;text-align:center;margin-bottom:18px}}
  .q{{margin-top:18px}}
  .q-title{{font-size:13px;font-weight:700;color:#475569;margin-bottom:9px;display:block;line-height:1.4}}
  .ratings{{display:flex;gap:6px}}
  .rating-btn{{flex:1;padding:10px 4px;border-radius:11px;border:2px solid #e2e8f0;background:#fff;
              cursor:pointer;text-align:center;transition:all .15s;font-family:inherit}}
  .rating-btn:hover{{border-color:#3b82f6;background:#eff6ff}}
  .rating-btn.active{{background:#3b82f6;border-color:#1d4ed8;color:#fff;
                     box-shadow:0 4px 12px rgba(59,130,246,.32)}}
  .rating-btn .ico{{font-size:22px;line-height:1;display:block}}
  .rating-btn .num{{font-size:10px;font-weight:800;display:block;margin-top:3px;letter-spacing:.04em}}
  .ratings .b1 .ico{{color:#ef4444}} .ratings .b2 .ico{{color:#f97316}}
  .ratings .b3 .ico{{color:#eab308}} .ratings .b4 .ico{{color:#84cc16}}
  .ratings .b5 .ico{{color:#10b981}}
  .rating-btn.active .ico{{color:#fff!important}}
  .slider-wrap{{padding:6px 4px 0}}
  .slider-row{{display:flex;justify-content:space-between;font-size:10.5px;color:#94a3b8;
              font-weight:700;letter-spacing:.04em;margin-bottom:4px}}
  input[type=range]{{width:100%;height:8px;border-radius:5px;background:#e2e8f0;
                    -webkit-appearance:none;appearance:none;outline:none}}
  input[type=range]::-webkit-slider-thumb{{-webkit-appearance:none;appearance:none;width:24px;height:24px;
    border-radius:50%;background:#10b981;cursor:pointer;box-shadow:0 4px 10px rgba(16,185,129,.45);border:3px solid #fff}}
  input[type=range]::-moz-range-thumb{{width:24px;height:24px;border-radius:50%;background:#10b981;
    cursor:pointer;box-shadow:0 4px 10px rgba(16,185,129,.45);border:3px solid #fff}}
  .slider-val{{font-size:14px;font-weight:800;color:#10b981;text-align:center;margin-top:6px}}
  textarea{{width:100%;border:1.5px solid #e2e8f0;border-radius:11px;padding:10px 12px;
          font-family:inherit;font-size:13.5px;resize:vertical;min-height:80px;background:#f8fafc;
          color:#0f172a;outline:none;transition:border-color .15s}}
  textarea:focus{{border-color:#3b82f6;background:#fff}}
  .submit{{width:100%;background:linear-gradient(135deg,#10b981,#059669);color:#fff;font-weight:800;
          padding:16px;border-radius:14px;border:none;cursor:pointer;margin-top:20px;font-size:14px;
          letter-spacing:.04em;font-family:inherit;transition:all .15s;
          box-shadow:0 6px 18px rgba(16,185,129,.35)}}
  .submit:hover{{transform:translateY(-1px);box-shadow:0 10px 22px rgba(16,185,129,.45)}}
  .submit:disabled{{opacity:.6;cursor:not-allowed;transform:none;box-shadow:none}}
  .footer{{text-align:center;padding:18px 20px 32px;color:#94a3b8;font-size:10.5px;
          letter-spacing:.14em;font-weight:700;text-transform:uppercase}}
  .footer-sub{{font-style:italic;font-weight:400;text-transform:none;font-size:11px;
              opacity:.75;margin-top:3px;letter-spacing:0}}
  .err-msg{{background:#fef2f2;border:1px solid #fecaca;color:#991b1b;font-size:12.5px;font-weight:600;
          padding:10px 14px;border-radius:10px;margin-top:14px;text-align:center;display:none}}
  .err-msg.show{{display:block}}
</style>
</head>
<body>

<div class="hero">
  <img src="/assets/logo_sandoval.jpg" alt="SANDOVAL" onerror="this.style.display='none'">
  <h1>¡Tu opinión nos importa!</h1>
  <p>Hola {name}, ayúdanos a mejorar nuestra calidad de servicio.</p>
</div>

<div class="wrap">
  <form id="enc-form" class="card" onsubmit="return false">
    <h2>Califica nuestra atención</h2>
    <span class="order-tag">Orden {cons}</span>

    <div class="q">
      <span class="q-title">¿Qué tan satisfecho estás con el trabajo técnico?</span>
      <div class="ratings" data-key="calidad_trabajo">
        {''.join(_rating_buttons('calidad_trabajo'))}
      </div>
    </div>
    <div class="q">
      <span class="q-title">¿Qué te pareció el tiempo de entrega?</span>
      <div class="ratings" data-key="tiempo_entrega">
        {''.join(_rating_buttons('tiempo_entrega'))}
      </div>
    </div>
    <div class="q">
      <span class="q-title">¿Cómo calificarías la atención del personal?</span>
      <div class="ratings" data-key="atencion_cliente">
        {''.join(_rating_buttons('atencion_cliente'))}
      </div>
    </div>
    <div class="q">
      <span class="q-title">¿Consideras que el precio fue justo?</span>
      <div class="ratings" data-key="precio_justo">
        {''.join(_rating_buttons('precio_justo'))}
      </div>
    </div>
    <div class="q">
      <span class="q-title">¿Cómo encontraste la limpieza de tu vehículo?</span>
      <div class="ratings" data-key="limpieza_vehiculo">
        {''.join(_rating_buttons('limpieza_vehiculo'))}
      </div>
    </div>

    <div class="q">
      <span class="q-title" style="text-align:center">¿Nos recomendarías con amigos o familiares?</span>
      <div class="slider-wrap">
        <div class="slider-row"><span>Nada probable</span><span>Muy probable</span></div>
        <input type="range" id="recomendacion" min="0" max="10" value="10" step="1">
        <div class="slider-val"><span id="recom-val">10</span> / 10</div>
      </div>
    </div>

    <div class="q">
      <span class="q-title">¿Tienes algún comentario o sugerencia?</span>
      <textarea id="comentarios" maxlength="800" placeholder="Escríbenos lo que quieras compartir…"></textarea>
    </div>

    <div class="err-msg" id="err">Por favor, califica todos los puntos antes de enviar.</div>

    <button type="submit" class="submit" id="btn-submit">ENVIAR MI CALIFICACIÓN</button>
  </form>

  <div class="footer">
    MECÁNICA Y REPUESTOS SANDOVAL
    <div class="footer-sub">Pasión por el detalle técnico ✨</div>
  </div>
</div>

<script>
(function(){{
  const TOKEN = {_json.dumps(token)};
  const ratings = {{}};
  document.querySelectorAll('.ratings').forEach(group => {{
    const key = group.dataset.key;
    ratings[key] = null;
    group.querySelectorAll('.rating-btn').forEach(btn => {{
      btn.addEventListener('click', () => {{
        const v = parseInt(btn.dataset.val, 10);
        ratings[key] = v;
        group.querySelectorAll('.rating-btn').forEach(b => b.classList.toggle('active', b === btn));
      }});
    }});
  }});

  const recom = document.getElementById('recomendacion');
  const recomVal = document.getElementById('recom-val');
  const updateRecom = () => recomVal.textContent = recom.value;
  recom.addEventListener('input', updateRecom);
  updateRecom();

  const errEl = document.getElementById('err');
  const btn = document.getElementById('btn-submit');
  document.getElementById('enc-form').addEventListener('submit', async () => {{
    if (Object.values(ratings).some(v => v === null)) {{
      errEl.classList.add('show');
      window.scrollTo({{top: errEl.offsetTop - 20, behavior: 'smooth'}});
      return;
    }}
    errEl.classList.remove('show');
    btn.disabled = true;
    btn.textContent = 'ENVIANDO…';
    const payload = Object.assign({{}}, ratings, {{
      recomendacion: parseInt(recom.value, 10) || 0,
      comentarios: document.getElementById('comentarios').value.trim(),
    }});
    try {{
      const res = await fetch('/api/encuesta/' + encodeURIComponent(TOKEN) + '/submit', {{
        method: 'POST',
        headers: {{'Content-Type': 'application/json'}},
        body: JSON.stringify(payload),
      }});
      if (!res.ok) throw new Error('http ' + res.status);
      window.location.reload();
    }} catch (e) {{
      btn.disabled = false;
      btn.textContent = 'ENVIAR MI CALIFICACIÓN';
      errEl.textContent = 'No pudimos guardar tu respuesta. Verifica tu conexión e inténtalo de nuevo.';
      errEl.classList.add('show');
    }}
  }});
}})();
</script>

</body></html>"""


def _rating_buttons(key: str):
    icons = ['😞', '🙁', '😐', '🙂', '😄']
    for i in range(1, 6):
        ico = icons[i - 1]
        yield (
            f'<button type="button" class="rating-btn b{i}" data-val="{i}">'
            f'<span class="ico">{ico}</span><span class="num">{i}</span>'
            f'</button>'
        )


# ─────────────────────────────────────────────────────────────────
# API pública
# ─────────────────────────────────────────────────────────────────
def render_encuesta_publica(token: str) -> Tuple[str, int]:
    data = _fetch(token)
    if not data:
        return _NOT_FOUND_HTML, 404
    if data['completada']:
        return _render_thanks(data), 200
    return _render_form(data, token), 200


def submit_encuesta(token: str, body: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    if not isinstance(body, dict):
        return {'ok': False, 'error': 'Cuerpo inválido'}, 400
    info = _lookup_taller(token)
    if not info:
        return {'ok': False, 'error': 'Token inválido'}, 404
    try:
        from utils.rls_session import with_taller
    except Exception:
        from contextlib import nullcontext
        with_taller = lambda _x: nullcontext()  # noqa: E731
    with with_taller(info["taller_id"]):
        return _submit_encuesta_inner(token, body)


def _submit_encuesta_inner(token: str, body: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    db = get_db()
    try:
        order = db.query(Orden).filter_by(report_token=token).first()
        if not order:
            return {'ok': False, 'error': 'Token inválido'}, 404
        existing = _parse_json(order.encuesta) or {}
        if existing.get('completada'):
            return {'ok': True, 'already': True}, 200

        # Validar y normalizar
        def _i(v, lo, hi, default=None):
            try:
                n = int(v)
                if lo <= n <= hi:
                    return n
            except (TypeError, ValueError):
                pass
            return default

        respuesta = {
            'calidad_trabajo':   _i(body.get('calidad_trabajo'),   1, 5),
            'tiempo_entrega':    _i(body.get('tiempo_entrega'),    1, 5),
            'atencion_cliente':  _i(body.get('atencion_cliente'),  1, 5),
            'precio_justo':      _i(body.get('precio_justo'),      1, 5),
            'limpieza_vehiculo': _i(body.get('limpieza_vehiculo'), 1, 5),
            'recomendacion':     _i(body.get('recomendacion'),     0, 10, default=10),
            'comentarios':       (str(body.get('comentarios') or '').strip())[:800],
            'completada':        True,
            'fecha_encuesta':    datetime.now().strftime('%Y-%m-%d %H:%M'),
        }
        # Bloquear envío si falta alguna calificación
        missing = [k for k in ('calidad_trabajo','tiempo_entrega','atencion_cliente',
                                'precio_justo','limpieza_vehiculo')
                   if respuesta[k] is None]
        if missing:
            return {'ok': False, 'error': 'Faltan calificaciones', 'missing': missing}, 422

        # Promedio para estrellas (lo usa el portal cliente)
        try:
            ratings = [respuesta[k] for k in ('calidad_trabajo','tiempo_entrega',
                                               'atencion_cliente','precio_justo','limpieza_vehiculo')]
            respuesta['estrellas'] = round(sum(ratings) / len(ratings))
            respuesta['comentario'] = respuesta['comentarios']
            respuesta['fecha_calificacion'] = respuesta['fecha_encuesta']
        except Exception:
            pass

        order.encuesta = respuesta
        db.commit()
        return {'ok': True}, 200
    except Exception as e:
        db.rollback()
        return {'ok': False, 'error': str(e)}, 500
    finally:
        db.close()

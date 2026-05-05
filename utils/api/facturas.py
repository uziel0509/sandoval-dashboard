"""utils.api.facturas — facturas mobile (Bot Telegram OCR)."""
from __future__ import annotations
import os
import json
import secrets
from datetime import datetime
from starlette.requests import Request
from starlette.responses import JSONResponse
from sqlalchemy import text as _sa_text
from utils.models import get_db, ItemInventario
from utils.api.common import _require_auth, _require_admin, json_ok, json_err
from utils.api.tenant import _setup_flota_ctx
from utils.upload_validator import validate_upload_bytes, safe_extension


# === IMPORTS_LEGACY ===
import secrets
import hashlib
import hmac
import os
import json
import sqlite3
import threading as _threading
from collections import defaultdict as _defaultdict
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from starlette.requests import Request
from starlette.responses import JSONResponse, FileResponse, RedirectResponse
from sqlalchemy import text, text as _sa_text
from utils.models import (
    get_db, Usuario, Cliente, Vehiculo, ItemInventario,
    Orden, Cita, NotaVenta, Proveedor, log_actividad,
    verify_password, hash_password,
)
from utils.security_events import track_login_failure as _track_login_fail
from utils.auth_cookies import (
    get_token_from_request, set_token_cookie, clear_token_cookie,
    COOKIE_CLIENT_NAME, COOKIE_ADMIN_NAME,
)
from utils.upload_validator import validate_upload_bytes, safe_extension
# === FIN IMPORTS_LEGACY ===

async def api_mobile_facturas_ocr(request: Request) -> JSONResponse:
    """POST /api/mobile/facturas/ocr {imagen_base64, media_type}
    Usa Groq vision (LLaMA 4 Maverick) para extraer datos estructurados.
    Devuelve proveedor, ruc, numero, fecha, items, subtotal, igv, total."""
    import re as _re
    user = _require_admin(request)
    if isinstance(user, JSONResponse):
        return user
    try:
        body = await request.json()
    except Exception:
        return json_err('Body inválido')
    imagen_b64 = body.get('imagen_base64') or ''
    # El frontend puede mandar 'mime' o 'media_type' indistintamente.
    media_type = body.get('media_type') or body.get('mime') or 'image/jpeg'
    if not imagen_b64:
        return json_err('Sin imagen')
    # ── HARDENING anti-DoS: límite tamaño imagen base64 (~8MB raw = ~10.7MB b64) ──
    _MAX_B64 = 12 * 1024 * 1024  # 12MB limit
    if len(imagen_b64) > _MAX_B64:
        return json_err('Imagen demasiado grande (max ~8MB)', 413)
    # ── HARDENING anti-injection: whitelist media_type ──
    _ALLOWED_MEDIA = {'image/jpeg', 'image/jpg', 'image/png', 'image/webp', 'image/gif'}
    media_type = (media_type or '').strip().lower().split(';')[0]
    if media_type not in _ALLOWED_MEDIA:
        media_type = 'image/jpeg'
    # Normalizar: si viene como data URL completo (canvas.toDataURL()), extraer
    # SOLO la parte base64; si no, dejarlo tal cual. Groq rechaza data URLs
    # anidados ("invalid base64 url") si lo envolvemos dos veces.
    if imagen_b64.startswith('data:'):
        _head, _, _b64 = imagen_b64.partition(',')
        if _b64:
            # Detectar media_type del propio data URL
            _m = _re.match(r'data:([^;]+);base64', _head)
            if _m:
                media_type = _m.group(1)
            imagen_b64 = _b64
    # Eliminar espacios, saltos de línea que pudieran haber venido.
    imagen_b64 = imagen_b64.replace('\n', '').replace('\r', '').replace(' ', '')
    # FIX SYNC-03: eliminar fallback `or 1` (multi-tenancy hardening, regla 5.1 CLAUDE.md)
    _tid_raw = user.get('taller_id')
    if _tid_raw is None:
        return json_err('Token sin taller_id (sesión inválida)', 403)
    taller_id = int(_tid_raw)

    from sqlalchemy import text as _sql_text
    db = get_db()
    try:
        row = db.execute(_sql_text(
            "SELECT valor FROM config_sistema WHERE taller_id=:t AND clave='groq_api_key'"
        ), {'t': taller_id}).fetchone()
    finally:
        db.close()
    if not row or not row[0]:
        return json_err('No hay API key Groq configurada', 400)
    groq_key = row[0].strip()

    try:
        from groq import Groq as _Groq
    except ImportError:
        return json_err('Librería groq no instalada', 500)

    # RUC del taller (comprador) — hay que IGNORARLO al extraer, porque el
    # campo "ruc" del JSON debe ser el del PROVEEDOR (emisor de la factura).
    _mi_ruc = os.getenv('TALLER_RUC', '20608755111')
    _mi_nombre = os.getenv('TALLER_NOMBRE', 'MECANICA Y REPUESTOS SANDOVAL EIRL')
    _prompt = (
        "Eres un contador peruano experto en SUNAT. Lee la factura/boleta de ARRIBA hacia ABAJO sin saltarte NADA. "
        "Si hay 50 ítems, devuelve los 50.\n\n"
        "════════════════════════════════════════════════════════════\n"
        "🎯 PASO 1 — RUCs (LECTURA EXHAUSTIVA, no elijas tú)\n"
        "════════════════════════════════════════════════════════════\n"
        "🔍 LEE CON MÁXIMA PRECISIÓN cada dígito del RUC, uno por uno.\n"
        "   Los RUCs peruanos tienen EXACTAMENTE 11 DÍGITOS. Cuenta dos veces antes de responder.\n"
        "   Si dudas entre 0/8, 6/8, 1/7, 3/8, 5/6 — RELEE el dígito ampliando mentalmente.\n\n"
        "📋 Devuelve en 'rucs_detectados' un ARRAY con TODOS los RUCs que veas en la imagen,\n"
        "   en el orden que aparecen (de arriba hacia abajo). Cada uno como string de 11 dígitos.\n"
        "   Ejemplo: \"rucs_detectados\": [\"20100123456\", \"20608755111\", \"10405068301\"]\n\n"
        "📌 Adicionalmente, en 'ruc' pon el primer RUC del array que NO sea " f"{_mi_ruc} (mío).\n"
        f"   En 'proveedor' pon la razón social que aparece junto a ese RUC (NO '{_mi_nombre}').\n"
        f"   Si todos los RUCs son {_mi_ruc} o no encuentras ninguno, deja ruc='' y proveedor=''.\n\n"
        "⚠️ Si NO ves ningún RUC con claridad, deja 'rucs_detectados': [] y 'ruc': ''.\n"
        "   NO INVENTES dígitos. Es mejor vacío que incorrecto.\n\n"
        "════════════════════════════════════════════════════════════\n"
        "🔢 PASO 2 — ÍTEMS (lee TODOS, sin omitir)\n"
        "════════════════════════════════════════════════════════════\n"
        "Tabla típica: CANT | DESCRIPCIÓN | P.UNIT | IMPORTE.\n"
        "Para CADA fila de la tabla:\n"
        "  • nombre = descripción completa (no recortes ni resumas).\n"
        "  • cantidad = número de la columna CANT (puede tener decimales: 1, 2, 0.5, 1.25, 2.75).\n"
        "  • precio_unitario = P.UNIT (precio por una unidad CON IGV incluido).\n"
        "    👉 LEE HASTA 4 DECIMALES si la factura los tiene (ej: '12.7458', '0.5085').\n"
        "    👉 NO redondees a 2 decimales — preserva la precisión que ves impresa.\n"
        "  • total = IMPORTE de esa fila. Verifica: total ≈ cantidad × precio_unitario.\n"
        "  • Si dice 'GRATIS'/'OBSEQUIO'/'BONIFICACIÓN' o el precio es 0 → es_gratis=true, precio_unitario=0, total=0.\n\n"
        "🧮 VERIFICACIÓN ARITMÉTICA por ítem:\n"
        "  Calcula cantidad × precio_unitario. Compáralo con el total impreso.\n"
        "  Si no cuadra (>S/.0.10 de diferencia), RELEE la fila — el OCR pudo confundir un dígito.\n\n"
        "🧮 VERIFICACIÓN ARITMÉTICA total:\n"
        "  La SUMA de los 'total' de TODOS los ítems debe ser ≈ total_con_igv.\n"
        "  Si no cuadra, revisa los ítems antes de responder.\n\n"
        "════════════════════════════════════════════════════════════\n"
        "💰 PASO 3 — TOTALES (TOTAL FINAL = verdad absoluta)\n"
        "════════════════════════════════════════════════════════════\n"
        "1. En Perú, precios de facturas YA INCLUYEN IGV (18%). NO sumes IGV adicional.\n"
        "2. TOTAL FINAL impreso (etiquetas: 'TOTAL', 'IMPORTE TOTAL', 'TOTAL A PAGAR') = verdad absoluta.\n"
        "3. Fórmula:  IGV = Total × 18 / 118  |  Subtotal = Total − IGV.\n"
        "4. Moneda: 'S/.' o 'SOLES' → 'PEN'; '$' → 'USD'; default 'PEN'.\n"
        "5. numero_factura: copia EXACTO ('F001-12345', 'B001-67890', 'FU01-000961', etc.).\n"
        "6. Fecha: YYYY-MM-DD. Si ves DD/MM/YYYY, conviértela.\n\n"
        "════════════════════════════════════════════════════════════\n"
        "📋 PASO 4 — JSON estricto (sin markdown, sin ```, sin texto extra)\n"
        "════════════════════════════════════════════════════════════\n"
        '{"proveedor":"","ruc":"","rucs_detectados":[],"numero_factura":"","fecha":"YYYY-MM-DD","moneda":"PEN",'
        '"items":[{"nombre":"","cantidad":1,"precio_unitario":0.0000,"total":0.00,"es_gratis":false}],'
        '"subtotal_sin_igv":0.00,"igv_monto":0.00,"total_con_igv":0.00,'
        '"notas":"","confianza":"alta|media|baja"}'
    )

    # Modelos de visión de Groq en orden de preferencia. Si Groq descontinúa
    # uno, caemos al siguiente automáticamente en vez de devolver 500.
    _vision_models = [
        'meta-llama/llama-4-scout-17b-16e-instruct',
        'meta-llama/llama-4-maverick-17b-128e-instruct',
        'llama-3.2-90b-vision-preview',
        'llama-3.2-11b-vision-preview',
    ]
    resp = None
    last_err = None
    try:
        from groq import NotFoundError as _GroqNotFound, AuthenticationError as _GroqAuth
    except Exception:
        _GroqNotFound = Exception
        _GroqAuth = Exception
    try:
        client = _Groq(api_key=groq_key)
        for _model in _vision_models:
            try:
                resp = client.chat.completions.create(
                    model=_model,
                    messages=[{'role': 'user', 'content': [
                        {'type': 'text', 'text': _prompt},
                        {'type': 'image_url', 'image_url': {'url': f'data:{media_type};base64,{imagen_b64}'}},
                    ]}],
                    temperature=0, max_tokens=2000,
                )
                break  # éxito
            except _GroqNotFound as e:
                last_err = e
                continue  # probar siguiente modelo
            except _GroqAuth as e:
                # API key inválida/expirada: no tiene sentido probar otros modelos.
                return json_err(
                    'API key de Groq inválida o expirada. Renuévala en https://console.groq.com/keys '
                    'y actualiza GROQ_API_KEY en /var/www/sandoval/.env',
                    503,
                )
        if resp is None:
            raise last_err or RuntimeError('Ningún modelo de visión Groq disponible')
    except Exception:
        import traceback; traceback.print_exc()
        return json_err('Error al procesar imagen con OCR', 500)

    raw = (resp.choices[0].message.content or '').strip()
    raw = _re.sub(r'^```(?:json)?\s*', '', raw)
    raw = _re.sub(r'\s*```$', '', raw)
    m = _re.search(r'\{[\s\S]+\}', raw)
    if not m:
        return json_err('OCR no devolvió JSON válido', 500)
    try:
        import json as _json
        data = _json.loads(m.group(0))
    except Exception:
        return json_err('JSON malformado desde OCR', 500)

    # ─────────────────────────────────────────────────────────────
    # RECONCILIACIÓN ARITMÉTICA con Decimal (precisión exacta)
    # • precio_unitario: hasta 4 decimales (facturas peruanas usan 4 decimales)
    # • total ítem, IGV, subtotal, total_factura: 2 decimales (formato impreso)
    # ─────────────────────────────────────────────────────────────
    from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
    _Q2 = Decimal('0.01')
    _Q4 = Decimal('0.0001')
    def _D(v, q=_Q2):
        try:
            return Decimal(str(v if v not in (None, '') else 0)).quantize(q, rounding=ROUND_HALF_UP)
        except (InvalidOperation, ValueError, TypeError):
            return Decimal('0.00') if q == _Q2 else Decimal('0.0000')

    _warnings = []
    items = data.get('items') or []
    items_sum = Decimal('0.00')
    items_recalc_count = 0
    for it in items:
        if it.get('es_gratis'):
            it['precio_unitario'] = 0.0
            it['total'] = 0.0
            continue
        qty = _D(it.get('cantidad') or 1, _Q4)  # cantidad puede ser 0.5, 1.25, etc.
        if qty <= 0:
            qty = Decimal('1.0000')
        pu = _D(it.get('precio_unitario'), _Q4)  # precio_unitario hasta 4 decimales
        declared_total = _D(it.get('total'), _Q2)
        computed_total = (qty * pu).quantize(_Q2, rounding=ROUND_HALF_UP)
        # Si la IA puso un total inconsistente (>S/.0.05 de diff) → confiar en cantidad×PU
        if abs(declared_total - computed_total) > Decimal('0.05'):
            it['total'] = float(computed_total)
            items_recalc_count += 1
        else:
            it['total'] = float(declared_total)
        it['cantidad'] = float(qty)
        it['precio_unitario'] = float(pu)  # preserva 4 decimales en serializado JSON
        items_sum += _D(it['total'], _Q2)

    # Total final: la verdad absoluta es el TOTAL impreso. Si la IA no lo extrajo
    # pero sí los ítems, derivar total = suma items.
    total_factura = _D(data.get('total_con_igv'), _Q2)
    if total_factura <= 0 and items_sum > 0:
        total_factura = items_sum
        _warnings.append(
            f"Total no detectado en cabecera; se usó suma de ítems S/{items_sum}."
        )

    # IGV y subtotal: SIEMPRE recalculados desde total final (Perú: precio incluye IGV 18%).
    if total_factura > 0:
        igv = (total_factura * Decimal('18') / Decimal('118')).quantize(_Q2, rounding=ROUND_HALF_UP)
        subtotal = (total_factura - igv).quantize(_Q2, rounding=ROUND_HALF_UP)
        data['total_con_igv'] = float(total_factura)
        data['igv_monto'] = float(igv)
        data['subtotal_sin_igv'] = float(subtotal)

    # Reconciliación: si suma de items difiere del total >S/.0.10, avisar.
    if total_factura > 0 and items_sum > 0:
        diff = abs(items_sum - total_factura)
        if diff > Decimal('0.10'):
            _warnings.append(
                f"⚠️ Suma de ítems S/{items_sum} difiere del total S/{total_factura} "
                f"(diferencia S/{diff}). Revisa los ítems antes de guardar."
            )
    if items_recalc_count > 0:
        _warnings.append(
            f"Se recalcularon {items_recalc_count} ítem(s) por inconsistencia "
            f"entre cantidad×precio y total declarado."
        )

    # ─────────────────────────────────────────────────────────────
    # SELECCIÓN INTELIGENTE DE RUC EMISOR (3 capas de validación)
    #   Capa 1: Filtrar el mío (20608755111) y los con nombre 'SANDOVAL'.
    #   Capa 2: Validar checksum SUNAT (algoritmo dígito verificador).
    #   Capa 3: Confirmar contra CODART/SUNAT (existe + obtiene razón social).
    # Resultado: el primer RUC que pase las 3 capas, con razón social oficial.
    # ─────────────────────────────────────────────────────────────

    def _ruc_checksum_ok(ruc: str) -> bool:
        """Valida dígito verificador del RUC peruano (algoritmo SUNAT)."""
        if not (ruc and len(ruc) == 11 and ruc.isdigit()):
            return False
        if ruc[:2] not in ('10', '15', '17', '20'):
            return False
        # Multiplicadores oficiales SUNAT
        mult = [5, 4, 3, 2, 7, 6, 5, 4, 3, 2]
        s = sum(int(ruc[i]) * mult[i] for i in range(10))
        resto = s % 11
        dig = (11 - resto) % 10
        # SUNAT: si el resto da 0 o 1, el dígito esperado es 0 o (11-resto)%10
        # La fórmula (11-resto)%10 cubre ambos casos correctamente.
        return dig == int(ruc[10])

    def _consultar_codart(ruc: str, timeout: float = 3.0):
        """Consulta CODART/SUNAT para validar RUC y obtener razón social.
        Retorna dict con 'ok','nombre','direccion','estado' o None si falla/timeout.
        URL correcta: /api/v1/consultas/sunat/ruc/{ruc}"""
        try:
            import requests as _rq  # type: ignore
        except Exception:
            return None
        token = (os.environ.get('CODART_TOKEN') or '').strip()
        if not token:
            return None
        try:
            r = _rq.get(
                f'https://api-codart.cgrt.org/api/v1/consultas/sunat/ruc/{ruc}',
                headers={
                    'Authorization': f'Bearer {token}',
                    'Accept': 'application/json',
                    'Content-Type': 'application/json',
                },
                timeout=timeout,
            )
        except Exception:
            return None
        if r.status_code != 200:
            return None
        try:
            jd = r.json()
        except Exception:
            return None
        if not jd.get('success') or not jd.get('result'):
            return None
        res = jd['result']
        return {
            'ok': True,
            'ruc': res.get('numero_documento') or ruc,
            'nombre': (res.get('razon_social') or '').strip(),
            'direccion': (res.get('direccion') or '').strip(),
            'estado': res.get('estado') or '',
            'condicion': res.get('condicion') or '',
        }

    # Normalizar mi nombre (quitar E.I.R.L./EIRL/SAC/SA) para comparar startswith
    _mi_nombre_base = _re.sub(r'\b(E\.?I\.?R\.?L\.?|S\.?A\.?C\.?|S\.?A\.?|S\.?R\.?L\.?)\b', '',
                              _mi_nombre.upper()).strip().rstrip('.,').strip()

    # Construir lista candidata: rucs_detectados[] + el ruc principal por si la IA
    # no llenó el array. Deduplicar preservando orden.
    _raw_rucs = list(data.get('rucs_detectados') or [])
    _ruc_principal = (str(data.get('ruc') or '')).strip().replace(' ', '').replace('-', '')
    if _ruc_principal and _ruc_principal not in _raw_rucs:
        _raw_rucs.insert(0, _ruc_principal)

    # Limpiar formato (solo dígitos) y deduplicar
    _candidatos = []
    _seen = set()
    for r in _raw_rucs:
        rn = _re.sub(r'[^0-9]', '', str(r or ''))
        if rn and rn not in _seen:
            _seen.add(rn)
            _candidatos.append(rn)

    # Capa 1: descartar mi RUC
    _candidatos_otro = [r for r in _candidatos if r != _mi_ruc]

    # Capa 2: separar checksum válido vs inválido
    _checksum_ok = [r for r in _candidatos_otro if _ruc_checksum_ok(r)]
    _checksum_bad = [r for r in _candidatos_otro if not _ruc_checksum_ok(r)]

    # Capa 3: probar CODART/SUNAT en los que pasaron checksum (cap a 3 para DoS)
    _ruc_final = ''
    _nombre_final = ''
    _codart_data = None
    for r in _checksum_ok[:3]:
        _codart_data = _consultar_codart(r)
        if _codart_data and _codart_data.get('ok'):
            _ruc_final = r
            _nombre_final = _codart_data.get('nombre') or ''
            break

    # Fallback: si CODART falló (sin token, timeout, o todos rechazados),
    # usa el primer RUC con checksum válido SIN datos oficiales.
    if not _ruc_final and _checksum_ok:
        _ruc_final = _checksum_ok[0]
        _warnings.append(
            f"RUC '{_ruc_final}' tiene checksum válido pero no pude confirmar con SUNAT "
            "(sin token CODART o timeout). Verifica razón social manualmente."
        )

    # Si nada pasó checksum pero hay candidatos, advertir fuerte
    if not _ruc_final and _checksum_bad:
        _ruc_final = _checksum_bad[0]
        _warnings.append(
            f"⚠️ RUC detectado '{_ruc_final}' tiene checksum SUNAT INVÁLIDO. "
            f"Probablemente la IA leyó mal un dígito. Por favor verifica número por número."
        )

    # Si no hay candidatos, devolver vacío con aviso
    if not _ruc_final:
        if _candidatos and _mi_ruc in _candidatos and len(_candidatos) == 1:
            _warnings.append(
                f'Solo se detectó tu propio RUC ({_mi_ruc}). El RUC del emisor '
                'no es visible o no se leyó. Ingrésalo manualmente.'
            )
        else:
            _warnings.append('No se detectó ningún RUC válido en la imagen. Ingrésalo manualmente.')
        data['ruc'] = ''
        data['proveedor'] = ''
    else:
        # Si CODART confirmó, usar nombre oficial. Si no, intentar conservar el de OCR
        # SALVO que sea Sandoval o vacío.
        data['ruc'] = _ruc_final
        _prov_ocr = (str(data.get('proveedor') or '')).upper().strip()
        _es_mi_empresa_ocr = (
            _mi_nombre_base and _prov_ocr.startswith(_mi_nombre_base)
        )
        if _nombre_final:
            data['proveedor'] = _nombre_final  # razón social oficial SUNAT
            data['_codart'] = _codart_data  # extra: dirección, estado, etc.
        elif not _prov_ocr or _es_mi_empresa_ocr:
            data['proveedor'] = ''
            _warnings.append(
                'Razón social del proveedor no identificada. Ingrésala manualmente.'
            )
        # else: conservar lo que la IA leyó

    # Exponer la lista de RUCs detectados al frontend (debug + transparencia)
    data['rucs_detectados'] = _candidatos

    if _warnings:
        data['_warnings'] = _warnings
    return json_ok(data)


async def api_mobile_facturas_crear(request: Request) -> JSONResponse:
    """POST /api/mobile/facturas/crear
    Body: {proveedor, ruc, numero, fecha, subtotal, igv, total, items, moneda, notas, imagen_base64?, media_type?}
    Crea la factura + guarda imagen si se envía."""
    import base64 as _b64, os as _os, secrets as _secrets, json as _json
    from sqlalchemy import text as _sql_text
    user = _require_admin(request)
    if isinstance(user, JSONResponse):
        return user
    try:
        body = await request.json()
    except Exception:
        return json_err('Body inválido')
    taller_id = int(user.get('taller_id') or 1)

    imagen_path = ''
    if body.get('imagen_base64'):
        try:
            media = (body.get('media_type') or 'image/jpeg').strip().lower().split(';')[0]
            # FIX security #4: whitelist estricta de tipos + extensiones
            _MEDIA_TO_EXT = {'image/jpeg': '.jpg', 'image/jpg': '.jpg',
                             'image/png': '.png', 'image/webp': '.webp', 'image/gif': '.gif'}
            ext = _MEDIA_TO_EXT.get(media, '.jpg')
            save_dir = '/var/www/sandoval/static/facturas'
            _os.makedirs(save_dir, exist_ok=True)
            fname = f"factura_m_{int(datetime.now().timestamp())}_{_secrets.token_hex(3)}{ext}"
            _fpath = _os.path.join(save_dir, fname)
            _b64data = body['imagen_base64']
            if isinstance(_b64data, str) and ',' in _b64data and _b64data.startswith('data:'):
                _b64data = _b64data.split(',', 1)[1]
            _raw_bytes = _b64.b64decode(_b64data)
            # FIX security #4: validar magic bytes antes de escribir (anti file-upload-as-script)
            try:
                _ok, _kind = validate_upload_bytes(_raw_bytes, ext)
            except Exception:
                _ok, _kind = (True, 'unknown')
            if not _ok:
                imagen_path = ''
                # log warning pero continuar (la factura se guarda sin imagen)
                import logging
                logging.getLogger('sandoval.factura').warning(
                    "Imagen factura rechazada: magic=%s vs ext=%s", _kind, ext)
            else:
                with open(_fpath, 'wb') as f:
                    f.write(_raw_bytes)
                try: _os.chmod(_fpath, 0o644)
                except Exception: pass
                imagen_path = f'/facturas/{fname}'
        except Exception:
            imagen_path = ''

    db = get_db()
    try:
        fecha = body.get('fecha') or datetime.now().strftime('%Y-%m-%d')
        # FIX P0 (finance-auditor): si total<=0 pero hay items, derivar de sum(items.total)
        # Antes: el endpoint confiaba ciegamente en `body.get('total') or 0` → 9 facturas
        # quedaron con S/0 cuando la IA solo lleno items pero el frontend mando total=0.
        _items = body.get('items', []) or []
        _tot = float(body.get('total') or 0)
        _sub = float(body.get('subtotal') or 0)
        _igv = float(body.get('igv') or 0)
        if _tot <= 0 and _items:
            try:
                _tot = round(sum(float(i.get('total') or 0) for i in _items if not i.get('es_gratis')), 2)
            except Exception:
                _tot = 0.0
            if _tot > 0 and _sub <= 0:
                _igv = round(_tot * 18 / 118, 2)
                _sub = round(_tot - _igv, 2)
        new_id = db.execute(_sql_text("""
            INSERT INTO facturas (taller_id, tipo, subtipo_gasto, proveedor, ruc_proveedor,
                numero_factura, fecha, subtotal, igv, total, estado, notas,
                items_json, moneda, imagen_path, fecha_registro)
            VALUES (:t, :tipo, '', :prov, :ruc, :num, :fecha, :sub, :igv, :tot,
                    'procesada', :notas, :items, :moneda, :img, NOW())
            RETURNING id
        """), {
            't': taller_id,
            'tipo': body.get('tipo', 'mercaderia'),
            'prov': (body.get('proveedor') or '').strip(),
            'ruc': (body.get('ruc') or body.get('ruc_proveedor') or '').strip(),
            'num': (body.get('numero') or body.get('numero_factura') or '').strip(),
            'fecha': fecha,
            'sub': _sub,
            'igv': _igv,
            'tot': _tot,
            'notas': body.get('notas', ''),
            'items': _json.dumps(_items),
            'moneda': body.get('moneda', 'PEN'),
            'img': imagen_path,
        }).scalar()
        db.commit()
        return json_ok({'ok': True, 'id': int(new_id), 'imagen_path': imagen_path})
    except Exception:
        db.rollback()
        import traceback; traceback.print_exc()
        return json_err('Error al guardar factura', 500)
    finally:
        db.close()


async def api_mobile_factura_agregar_stock(request: Request) -> JSONResponse:
    """POST /api/mobile/facturas/{fid}/agregar-stock
    Suma los items de la factura al inventario con match fuzzy."""
    import unicodedata as _u
    from sqlalchemy import text as _sql_text
    def _norm(s):
        s = _u.normalize('NFKD', s or '').encode('ASCII', 'ignore').decode()
        return ''.join(c if (c.isalnum() or c == ' ') else ' ' for c in s.lower()).strip()[:150]

    user = _require_admin(request)
    if isinstance(user, JSONResponse):
        return user
    fid_raw = request.path_params.get('fid', '')
    try:
        fid = int(fid_raw)
    except Exception:
        return json_err('ID inválido', 400)
    taller_id = int(user.get('taller_id') or 1)
    db = get_db()
    try:
        row = db.execute(_sql_text(
            "SELECT items_json, proveedor, ruc_proveedor FROM facturas "
            "WHERE id=:id AND taller_id=:t"
        ), {'id': fid, 't': taller_id}).fetchone()
        if not row:
            return json_err('Factura no encontrada', 404)
        import json as _json
        items = _json.loads(row[0] or '[]')
        proveedor = row[1] or ''
        ruc = row[2] or ''
        added = 0; updated = 0; skipped = []
        hoy = datetime.now().strftime('%Y-%m-%d')
        for it in items:
            nombre = (it.get('nombre') or '').strip()
            if not nombre:
                skipped.append(it); continue
            upe = int(it.get('unidades_por_empaque') or 1)
            if upe < 1: upe = 1
            qty = float(it.get('cantidad') or 1)
            qty_stock = qty * upe
            precio_emp = float(it.get('precio_unitario') or 0)
            costo_unit = round(precio_emp / upe, 4) if upe else precio_emp
            # Margen/rentabilidad: si el item lo trae (desde el review), úsalo;
            # si no, default 40% que era el viejo hardcoded *1.4.
            try:
                margen_pct = float(it.get('rentabilidad') or it.get('margen') or 40)
            except (ValueError, TypeError):
                margen_pct = 40.0
            if margen_pct < 0: margen_pct = 0.0
            precio_venta = round(costo_unit * (1 + margen_pct/100), 2)
            nombre_norm = _norm(nombre)
            codigo_provided = (it.get('codigo') or '').strip()
            codigo_barras = (it.get('codigo_barras') or '').strip()
            categoria = (it.get('categoria') or 'Repuesto').strip() or 'Repuesto'
            match = None
            # Prioridad de match: codigo_barras > codigo interno > nombre+ruc > nombre
            if codigo_barras:
                match = db.execute(_sql_text(
                    "SELECT codigo FROM inventario WHERE codigo_barras=:cb AND taller_id=:t"
                ), {'cb': codigo_barras, 't': taller_id}).fetchone()
            if not match and codigo_provided:
                match = db.execute(_sql_text(
                    "SELECT codigo FROM inventario WHERE codigo=:c AND taller_id=:t"
                ), {'c': codigo_provided, 't': taller_id}).fetchone()
            if not match and ruc:
                match = db.execute(_sql_text(
                    "SELECT codigo FROM inventario WHERE nombre_norm=:nn AND ruc_proveedor=:r AND taller_id=:t LIMIT 1"
                ), {'nn': nombre_norm, 'r': ruc, 't': taller_id}).fetchone()
            if not match:
                match = db.execute(_sql_text(
                    "SELECT codigo FROM inventario WHERE nombre_norm=:nn AND taller_id=:t LIMIT 1"
                ), {'nn': nombre_norm, 't': taller_id}).fetchone()
            if match:
                # Existe: sumar stock + actualizar costo/proveedor. NO tocamos precio
                # ni rentabilidad (conservan lo que el admin configuró antes).
                # Si viene codigo_barras y el producto no lo tenía, asignarlo.
                db.execute(_sql_text("""
                    UPDATE inventario SET stock = COALESCE(stock,0) + :q, costo = :cv,
                        proveedor = CASE WHEN :pv<>'' THEN :pv ELSE proveedor END,
                        ruc_proveedor = CASE WHEN :r<>'' THEN :r ELSE ruc_proveedor END,
                        codigo_barras = CASE WHEN :cb<>'' AND (codigo_barras IS NULL OR codigo_barras='')
                                              THEN :cb ELSE codigo_barras END,
                        unidades_por_empaque = :upe, fecha_ultimo_ingreso = CAST(:h AS date)
                    WHERE codigo=:c AND taller_id=:t
                """), {'q': qty_stock, 'cv': costo_unit, 'pv': proveedor, 'r': ruc,
                       'cb': codigo_barras, 'upe': upe, 'h': hoy, 'c': match[0], 't': taller_id})
                updated += 1
            else:
                codigo_new = codigo_provided or nombre[:12].upper().replace(' ', '_')[:20]
                existing = db.execute(_sql_text(
                    "SELECT 1 FROM inventario WHERE codigo=:c AND taller_id=:t"
                ), {'c': codigo_new, 't': taller_id}).fetchone()
                if existing:
                    import time as _t
                    codigo_new = (codigo_new[:15] + '_' + str(int(_t.time()) % 10000))[:20]
                db.execute(_sql_text("""
                    INSERT INTO inventario (codigo, codigo_barras, nombre, nombre_norm, categoria,
                        precio, costo, rentabilidad, stock, proveedor, ruc_proveedor,
                        unidades_por_empaque, fecha_ultimo_ingreso, taller_id)
                    VALUES (:cod, :cb, :nom, :nn, :cat, :pv, :cv, :rent, :st, :prov, :r, :upe,
                            CAST(:h AS date), :t)
                """), {'cod': codigo_new, 'cb': codigo_barras, 'nom': nombre, 'nn': nombre_norm,
                       'cat': categoria, 'pv': precio_venta, 'cv': costo_unit, 'rent': margen_pct,
                       'st': qty_stock, 'prov': proveedor, 'r': ruc, 'upe': upe, 'h': hoy, 't': taller_id})
                added += 1
        estado_agr = 1 if not skipped else 2
        db.execute(_sql_text(
            "UPDATE facturas SET agregado_inventario=:e WHERE id=:id AND taller_id=:t"
        ), {'e': estado_agr, 'id': fid, 't': taller_id})
        db.commit()
        return json_ok({'ok': True, 'items_added': added, 'items_updated': updated,
                        'items_skipped': len(skipped), 'parcial': bool(skipped)})
    except Exception:
        db.rollback()
        import traceback; traceback.print_exc()
        return json_err('Error al agregar items al inventario', 500)
    finally:
        db.close()


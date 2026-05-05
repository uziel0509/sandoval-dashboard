"""
routers/facturas.py — Facturas, OCR y gastos operacionales (multi-tenant).

Refactor 2026-04-21:
  * taller_id del JWT via _tenant_id (antes TALLER_ID global).
  * create_factura usa RETURNING id en lugar de currval() (más seguro bajo
    concurrencia: currval depende del estado de la secuencia en la sesión y
    podía devolver el id de otro INSERT reciente si la conexión se reutiliza).
  * list_facturas y list_gastos con limit validado (Query bounds).
"""
from utils.upload_validator import validate_upload_bytes, safe_extension
from routers._common import (
    router, ADMIN_HTML,
    _auth, _get_db, _require_admin, _require_staff, _safe_date,
    _img_to_url, _parse_json_field, _make_token, _tenant_id,
    os, json, datetime, timedelta, Path,
    Request, HTTPException, UploadFile, File, List, HTMLResponse, text,
)
from fastapi import Query


@router.get("/api/facturas")
async def list_facturas(
    request: Request,
    tipo: str | None = None,
    limit: int = Query(100, ge=1, le=500),
):
    tok = _auth(request)
    _require_staff(tok)
    taller_id = _tenant_id(tok)
    db = _get_db()
    try:
        sql = ("SELECT id, tipo, proveedor, ruc_proveedor, numero_factura, fecha, "
               "subtotal, igv, total, estado, notas, items_json, imagen_path, "
               "subtipo_gasto, agregado_inventario, COALESCE(moneda,'PEN') "
               "FROM facturas WHERE taller_id=:t")
        params = {"t": taller_id, "lim": limit}
        if tipo:
            sql += " AND tipo=:tipo"; params["tipo"] = tipo
        sql += " ORDER BY id DESC LIMIT :lim"
        rows = db.execute(text(sql), params).fetchall()
        return [{"id": r[0], "tipo": r[1], "proveedor": r[2], "ruc_proveedor": r[3],
                 "numero_factura": r[4], "fecha": r[5], "subtotal": float(r[6] or 0),
                 "igv": float(r[7] or 0), "total": float(r[8] or 0),
                 "estado": r[9], "notas": r[10], "items_json": r[11],
                 "imagen_path": _img_to_url(r[12]), "subtipo_gasto": r[13],
                 "agregado_inventario": r[14], "moneda": r[15]} for r in rows]
    finally:
        db.close()


@router.post("/api/facturas")
async def create_factura(request: Request):
    tok = _auth(request)
    _require_admin(tok)
    taller_id = _tenant_id(tok)
    body = await request.json()
    # 2026-05-04 FASE1.2: validacion Pydantic V2 con FacturaPayload
    # NOTA: solo valida campos obligatorios. tipo/subtipo/notas/items siguen siendo
    # opcionales con defaults (no en el schema para mantener flexibilidad existente).
    try:
        from utils.schemas import FacturaPayload
        _p = FacturaPayload.model_validate({
            "proveedor":      body.get("proveedor", ""),
            "numero_factura": body.get("numero_factura", ""),
            "fecha":          body.get("fecha") or datetime.now().strftime("%Y-%m-%d"),
            "subtotal":       body.get("subtotal", 0),
            "igv":            body.get("igv", 0),
            "total":          body.get("total", 0),
            "ruc_proveedor":  body.get("ruc_proveedor", "") or "",
            "tipo":           body.get("tipo", "gasto"),
            "notas":          body.get("notas") or None,
        })
    except Exception as _ve:
        raise HTTPException(422, f"Datos de factura invalidos: {str(_ve)[:200]}")
    db = _get_db()
    try:
        new_id = db.execute(text("""
            INSERT INTO facturas (taller_id, tipo, subtipo_gasto, proveedor, ruc_proveedor,
                numero_factura, fecha, subtotal, igv, total, estado, notas,
                items_json, moneda, fecha_registro)
            VALUES (:t, :tipo, :st, :prov, :ruc, :num, :fecha, :sub, :igv, :tot, 'PENDIENTE',
                   :notas, :items, :moneda, NOW())
            RETURNING id
        """), {
            "t":     taller_id,
            "tipo":  _p.tipo, "st": body.get("subtipo_gasto", ""),
            "prov":  _p.proveedor, "ruc": _p.ruc_proveedor,
            "num":   _p.numero_factura,
            "fecha": _p.fecha,
            "sub":   float(_p.subtotal), "igv": float(_p.igv),
            "tot":   float(_p.total),    "notas": _p.notas or "",
            "items": json.dumps(body.get("items", [])),
            "moneda": body.get("moneda", "PEN"),
        }).scalar()
        db.commit()
        # Hook contabilidad: asiento fail-safe
        try:
            from utils.contabilidad_engine import generar_asiento_factura_compra
            generar_asiento_factura_compra(db, taller_id, int(new_id))
        except Exception as _ce:
            import logging
            logging.getLogger("sandoval.contabilidad").warning(
                "Hook factura asiento fallido id=%s: %s", new_id, _ce
            )
        return {"ok": True, "id": int(new_id)}
    finally:
        db.close()


@router.put("/api/facturas/{fid}")
async def update_factura(fid: int, request: Request):
    tok = _auth(request)
    _require_admin(tok)
    taller_id = _tenant_id(tok)
    body = await request.json()
    db = _get_db()
    try:
        db.execute(text("""
            UPDATE facturas SET tipo=:tipo, subtipo_gasto=:st, proveedor=:prov, ruc_proveedor=:ruc,
            numero_factura=:num, fecha=:fecha, subtotal=:sub, igv=:igv, total=:tot,
            estado=:estado, notas=:notas, items_json=:items, moneda=:moneda
            WHERE id=:id AND taller_id=:t
        """), {
            "id": fid, "t": taller_id,
            "tipo": body.get("tipo", "gasto"), "st": body.get("subtipo_gasto", ""),
            "prov": body.get("proveedor", ""), "ruc": body.get("ruc_proveedor", ""),
            "num": body.get("numero_factura", ""),
            "fecha": body.get("fecha", ""), "sub": float(body.get("subtotal", 0)),
            "igv": float(body.get("igv", 0)), "tot": float(body.get("total", 0)),
            "estado": body.get("estado", "procesada"), "notas": body.get("notas", ""),
            "items": json.dumps(body.get("items", [])),
            "moneda": body.get("moneda", "PEN"),
        })
        db.commit()
        return {"ok": True}
    finally:
        db.close()


@router.post("/api/facturas/{fid}/imagen")
async def upload_factura_imagen(fid: int, request: Request, file: UploadFile = File(...)):
    tok = _auth(request)
    _require_staff(tok)
    taller_id = _tenant_id(tok)
    import shutil, time as _time
    db = _get_db()
    try:
        # Verificar pertenencia antes de escribir archivo (evita orphans en cross-tenant)
        owner = db.execute(text(
            "SELECT 1 FROM facturas WHERE id=:id AND taller_id=:t"
        ), {"id": fid, "t": taller_id}).fetchone()
        if not owner:
            raise HTTPException(404, "Factura no encontrada")
        save_dir = "/var/www/sandoval/static/facturas"
        os.makedirs(save_dir, exist_ok=True)
        ext = safe_extension(file.filename or "", ".jpg")
        if ext not in {".jpg",".jpeg",".png",".webp",".pdf"}:
            raise HTTPException(400, "Tipo de archivo no permitido para factura")
        content = await file.read()
        ok, kind = validate_upload_bytes(content, ext)
        if not ok:
            raise HTTPException(400, f"Contenido invalido (esperaba {ext}, magic={kind})")
        fname = f"factura_{fid}_{int(_time.time())}{ext}"
        fpath = os.path.join(save_dir, fname)
        with open(fpath, "wb") as out:
            out.write(content)
        # 2026-04-30 fix: chmod 644 para que nginx (www-data) pueda servir la imagen
        try: os.chmod(fpath, 0o644)
        except Exception: pass
        db.execute(text("UPDATE facturas SET imagen_path=:p WHERE id=:id AND taller_id=:t"),
                   {"p": f"/facturas/{fname}", "id": fid, "t": taller_id})
        db.commit()
        return {"ok": True, "imagen_path": f"/facturas/{fname}"}
    finally:
        db.close()


@router.post("/api/facturas/leer-imagen")
async def leer_factura_imagen(request: Request):
    """OCR factura/boleta peruana con Groq vision + checksum SUNAT + CODART.
    Usa exactamente el mismo flujo que api_mobile_facturas_ocr para mantener
    paridad admin/mobile (sincronización 2026-05-01)."""
    import re as _re
    from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
    tok = _auth(request)
    _require_staff(tok)
    taller_id = _tenant_id(tok)
    # 2026-05-04 FASE2.3: rate limit 20/min por IP (Groq vision API + costo)
    from utils.api.ratelimit import enforce_endpoint_rate_limit as _rl_ocr
    _rl_ocr(request, "factura_ocr", max_per_min=20)
    body = await request.json()
    imagen_b64 = body.get("imagen_base64", "")
    media_type = body.get("media_type") or body.get("mime") or "image/jpeg"
    if not imagen_b64:
        raise HTTPException(400, "No se recibió imagen")
    # FIX security #1: límite tamaño anti-DoS (~8MB raw = ~12MB base64)
    if len(imagen_b64) > 12 * 1024 * 1024:
        raise HTTPException(413, "Imagen demasiado grande (max ~8MB)")
    # FIX security #2: whitelist media_type anti header injection
    _ALLOWED = {'image/jpeg', 'image/jpg', 'image/png', 'image/webp', 'image/gif'}
    media_type = (media_type or '').strip().lower().split(';')[0]
    if media_type not in _ALLOWED:
        media_type = 'image/jpeg'
    # Normalizar data URL si llega con prefijo data:image/...;base64,
    if isinstance(imagen_b64, str) and imagen_b64.startswith('data:'):
        _head, _, _b64 = imagen_b64.partition(',')
        if _b64:
            _m = _re.match(r'data:([^;]+);base64', _head)
            if _m:
                media_type = _m.group(1)
            imagen_b64 = _b64
    imagen_b64 = imagen_b64.replace('\n', '').replace('\r', '').replace(' ', '')

    db = _get_db()
    try:
        row = db.execute(
            text("SELECT valor FROM config_sistema WHERE taller_id=:t AND clave='groq_api_key'"),
            {"t": taller_id}
        ).fetchone()
        if not row or not row[0]:
            raise HTTPException(400, "No hay API key de Groq configurada en el sistema")
        groq_key = row[0].strip()
    finally:
        db.close()

    try:
        from groq import Groq as _Groq
    except ImportError:
        raise HTTPException(500, "Librería groq no instalada en el servidor")

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
        f"📌 Adicionalmente, en 'ruc' pon el primer RUC del array que NO sea {_mi_ruc} (mío).\n"
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

    # Modelos en orden de preferencia (fallback automático)
    _vision_models = [
        'meta-llama/llama-4-scout-17b-16e-instruct',
        'meta-llama/llama-4-maverick-17b-128e-instruct',
        'llama-3.2-90b-vision-preview',
        'llama-3.2-11b-vision-preview',
    ]
    try:
        from groq import NotFoundError as _GroqNotFound, AuthenticationError as _GroqAuth
    except Exception:
        _GroqNotFound = Exception
        _GroqAuth = Exception
    resp = None
    last_err = None
    try:
        client = _Groq(api_key=groq_key)
        for _model in _vision_models:
            try:
                resp = client.chat.completions.create(
                    model=_model,
                    messages=[{
                        "role": "user",
                        "content": [
                            {"type": "text", "text": _prompt},
                            {"type": "image_url", "image_url": {
                                "url": f"data:{media_type};base64,{imagen_b64}"
                            }}
                        ]
                    }],
                    temperature=0,
                    max_tokens=2000,
                )
                break
            except _GroqNotFound as e:
                last_err = e
                continue
            except _GroqAuth:
                raise HTTPException(503, "API key Groq inválida o expirada. Renueva en https://console.groq.com/keys.")
        if resp is None:
            raise last_err or RuntimeError('Ningún modelo de visión Groq disponible')
    except HTTPException:
        raise
    except Exception:
        import traceback; traceback.print_exc()
        raise HTTPException(500, "Error al procesar imagen con OCR")

    raw = resp.choices[0].message.content.strip()
    raw = _re.sub(r'^```(?:json)?\s*', '', raw)
    raw = _re.sub(r'\s*```$', '', raw)
    m = _re.search(r'\{[\s\S]+\}', raw)
    if not m:
        raise HTTPException(500, "No se pudo extraer JSON de la respuesta IA")
    try:
        data = json.loads(m.group(0))
    except Exception:
        raise HTTPException(500, "Error parseando respuesta IA - intenta de nuevo")

    # ── Reconciliación aritmética con Decimal ──
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
            it['precio_unitario'] = 0.0; it['total'] = 0.0; continue
        qty = _D(it.get('cantidad') or 1, _Q4)
        if qty <= 0: qty = Decimal('1.0000')
        pu = _D(it.get('precio_unitario'), _Q4)
        declared_total = _D(it.get('total'), _Q2)
        computed_total = (qty * pu).quantize(_Q2, rounding=ROUND_HALF_UP)
        if abs(declared_total - computed_total) > Decimal('0.05'):
            it['total'] = float(computed_total); items_recalc_count += 1
        else:
            it['total'] = float(declared_total)
        it['cantidad'] = float(qty)
        it['precio_unitario'] = float(pu)
        items_sum += _D(it['total'], _Q2)

    total_factura = _D(data.get('total_con_igv'), _Q2)
    if total_factura <= 0 and items_sum > 0:
        total_factura = items_sum
        _warnings.append(f"Total no detectado en cabecera; se usó suma de ítems S/{items_sum}.")

    if total_factura > 0:
        igv = (total_factura * Decimal('18') / Decimal('118')).quantize(_Q2, rounding=ROUND_HALF_UP)
        subtotal = (total_factura - igv).quantize(_Q2, rounding=ROUND_HALF_UP)
        data['total_con_igv'] = float(total_factura)
        data['igv_monto'] = float(igv)
        data['subtotal_sin_igv'] = float(subtotal)

    if total_factura > 0 and items_sum > 0:
        diff = abs(items_sum - total_factura)
        if diff > Decimal('0.10'):
            _warnings.append(
                f"⚠️ Suma de ítems S/{items_sum} difiere del total S/{total_factura} "
                f"(diferencia S/{diff}). Revisa los ítems antes de guardar."
            )
    if items_recalc_count > 0:
        _warnings.append(
            f"Se recalcularon {items_recalc_count} ítem(s) por inconsistencia."
        )

    # ── Selección RUC con checksum SUNAT + CODART ──
    def _ruc_checksum_ok(ruc):
        if not (ruc and len(ruc) == 11 and ruc.isdigit()): return False
        if ruc[:2] not in ('10', '15', '17', '20'): return False
        mult = [5, 4, 3, 2, 7, 6, 5, 4, 3, 2]
        s = sum(int(ruc[i]) * mult[i] for i in range(10))
        return (11 - s % 11) % 10 == int(ruc[10])

    def _consultar_codart(ruc, timeout=3.0):
        try:
            import requests as _rq  # type: ignore
        except Exception:
            return None
        token = (os.environ.get('CODART_TOKEN') or '').strip()
        if not token: return None
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
        if r.status_code != 200: return None
        try: jd = r.json()
        except Exception: return None
        if not jd.get('success') or not jd.get('result'): return None
        res = jd['result']
        return {
            'ok': True, 'ruc': res.get('numero_documento') or ruc,
            'nombre': (res.get('razon_social') or '').strip(),
            'direccion': (res.get('direccion') or '').strip(),
            'estado': res.get('estado') or '', 'condicion': res.get('condicion') or '',
        }

    _mi_nombre_base = _re.sub(r'\b(E\.?I\.?R\.?L\.?|S\.?A\.?C\.?|S\.?A\.?|S\.?R\.?L\.?)\b', '',
                              _mi_nombre.upper()).strip().rstrip('.,').strip()

    _raw_rucs = list(data.get('rucs_detectados') or [])
    _ruc_principal = (str(data.get('ruc') or '')).strip().replace(' ', '').replace('-', '')
    if _ruc_principal and _ruc_principal not in _raw_rucs:
        _raw_rucs.insert(0, _ruc_principal)
    _candidatos = []; _seen = set()
    for r in _raw_rucs:
        rn = _re.sub(r'[^0-9]', '', str(r or ''))
        if rn and rn not in _seen:
            _seen.add(rn); _candidatos.append(rn)
    _candidatos_otro = [r for r in _candidatos if r != _mi_ruc]
    _checksum_ok = [r for r in _candidatos_otro if _ruc_checksum_ok(r)]
    _checksum_bad = [r for r in _candidatos_otro if not _ruc_checksum_ok(r)]

    _ruc_final = ''; _nombre_final = ''; _codart_data = None
    # FIX security #5: cap 3 candidatos CODART (anti DoS por OCR con 30+ RUCs)
    for r in _checksum_ok[:3]:
        _codart_data = _consultar_codart(r)
        if _codart_data and _codart_data.get('ok'):
            _ruc_final = r; _nombre_final = _codart_data.get('nombre') or ''
            break
    if not _ruc_final and _checksum_ok:
        _ruc_final = _checksum_ok[0]
        _warnings.append(
            f"RUC '{_ruc_final}' tiene checksum válido pero no pude confirmar con SUNAT "
            "(token CODART o timeout). Verifica razón social manualmente."
        )
    if not _ruc_final and _checksum_bad:
        _ruc_final = _checksum_bad[0]
        _warnings.append(
            f"⚠️ RUC detectado '{_ruc_final}' tiene checksum SUNAT INVÁLIDO. "
            "Probablemente la IA leyó mal un dígito. Verifica número por número."
        )
    if not _ruc_final:
        if _candidatos and _mi_ruc in _candidatos and len(_candidatos) == 1:
            _warnings.append(
                f'Solo se detectó tu propio RUC ({_mi_ruc}). El RUC del emisor no es visible.'
            )
        else:
            _warnings.append('No se detectó ningún RUC válido en la imagen.')
        data['ruc'] = ''; data['proveedor'] = ''
    else:
        data['ruc'] = _ruc_final
        _prov_ocr = (str(data.get('proveedor') or '')).upper().strip()
        _es_mi_empresa_ocr = (_mi_nombre_base and _prov_ocr.startswith(_mi_nombre_base))
        if _nombre_final:
            data['proveedor'] = _nombre_final
            data['_codart'] = _codart_data
        elif not _prov_ocr or _es_mi_empresa_ocr:
            data['proveedor'] = ''
            _warnings.append('Razón social del proveedor no identificada. Ingrésala manualmente.')

    data['rucs_detectados'] = _candidatos
    if _warnings:
        data['_warnings'] = _warnings
    return data


@router.post("/api/facturas/{fid}/agregar-inventario")
async def agregar_factura_inventario(fid: int, request: Request):
    """
    Agrega ítems de factura al inventario con dedup fuzzy:
      1) Match por codigo+taller_id
      2) Match por nombre_norm+ruc_proveedor+taller_id (mismo proveedor)
      3) Match por nombre_norm+taller_id (cualquier proveedor)
      4) INSERT nuevo
    Soporta empaques: si item tiene unidades_por_empaque>1, stock += cant*upe
    """
    import unicodedata as _u
    def _norm(s):
        s = _u.normalize('NFKD', s or '').encode('ASCII', 'ignore').decode()
        return ''.join(c if (c.isalnum() or c == ' ') else ' ' for c in s.lower()).strip()[:150]

    tok = _auth(request); _require_admin(tok)
    taller_id = _tenant_id(tok)
    db = _get_db()
    try:
        row = db.execute(text(
            "SELECT items_json, proveedor, ruc_proveedor FROM facturas "
            "WHERE id=:id AND taller_id=:t"
        ), {"id": fid, "t": taller_id}).fetchone()
        if not row:
            raise HTTPException(404, "Factura no encontrada")
        items = json.loads(row[0] or "[]")
        proveedor = row[1] or ""
        ruc = row[2] or ""
        added = 0; updated = 0; skipped = []
        from datetime import date as _d
        hoy = _d.today().strftime("%Y-%m-%d")
        for it in items:
            nombre = (it.get("nombre") or "").strip()
            if not nombre:
                skipped.append(it); continue
            upe = int(it.get("unidades_por_empaque") or 1)
            if upe < 1: upe = 1
            qty_factura = float(it.get("cantidad") or 1)
            qty_stock = qty_factura * upe
            precio_empaque = float(it.get("precio_unitario") or 0)
            costo_unit = round(precio_empaque / upe, 4) if upe else precio_empaque
            precio_venta = round(costo_unit * 1.4, 2)
            nombre_norm = _norm(nombre)

            match = None
            codigo_provided = (it.get("codigo") or "").strip()
            if codigo_provided:
                match = db.execute(text(
                    "SELECT codigo FROM inventario WHERE codigo=:c AND taller_id=:t"
                ), {"c": codigo_provided, "t": taller_id}).fetchone()
            if not match and ruc:
                match = db.execute(text(
                    "SELECT codigo FROM inventario "
                    "WHERE nombre_norm=:nn AND ruc_proveedor=:r AND taller_id=:t LIMIT 1"
                ), {"nn": nombre_norm, "r": ruc, "t": taller_id}).fetchone()
            if not match:
                match = db.execute(text(
                    "SELECT codigo FROM inventario "
                    "WHERE nombre_norm=:nn AND taller_id=:t LIMIT 1"
                ), {"nn": nombre_norm, "t": taller_id}).fetchone()

            if match:
                cod = match[0]
                db.execute(text("""
                    UPDATE inventario
                    SET stock = COALESCE(stock,0) + :q,
                        costo = :cv,
                        proveedor = CASE WHEN :pv<>'' THEN :pv ELSE proveedor END,
                        ruc_proveedor = CASE WHEN :r<>'' THEN :r ELSE ruc_proveedor END,
                        unidades_por_empaque = :upe,
                        fecha_ultimo_ingreso = :h::date
                    WHERE codigo=:c AND taller_id=:t
                """), {"q": qty_stock, "cv": costo_unit, "pv": proveedor, "r": ruc,
                       "upe": upe, "h": hoy, "c": cod, "t": taller_id})
                updated += 1
            else:
                codigo_new = codigo_provided or nombre[:12].upper().replace(" ", "_")[:20]
                existing = db.execute(text(
                    "SELECT 1 FROM inventario WHERE codigo=:c AND taller_id=:t"
                ), {"c": codigo_new, "t": taller_id}).fetchone()
                if existing:
                    import time as _t
                    codigo_new = (codigo_new[:15] + "_" + str(int(_t.time()) % 10000))[:20]
                db.execute(text("""
                    INSERT INTO inventario (codigo, nombre, nombre_norm, categoria, precio, costo,
                        stock, proveedor, ruc_proveedor, unidades_por_empaque,
                        fecha_ultimo_ingreso, taller_id)
                    VALUES (:cod, :nom, :nn, 'Repuesto', :pv, :cv, :st, :prov, :r, :upe, :h::date, :t)
                """), {"cod": codigo_new, "nom": nombre, "nn": nombre_norm,
                       "pv": precio_venta, "cv": costo_unit, "st": qty_stock,
                       "prov": proveedor, "r": ruc, "upe": upe, "h": hoy, "t": taller_id})
                added += 1

        estado_agr = 1 if not skipped else 2
        db.execute(text("UPDATE facturas SET agregado_inventario=:e WHERE id=:id AND taller_id=:t"),
                   {"e": estado_agr, "id": fid, "t": taller_id})
        db.commit()
        return {
            "ok": True,
            "items_added": added,
            "items_updated": updated,
            "items_skipped": len(skipped),
            "skipped": skipped,
            "parcial": len(skipped) > 0,
        }
    except HTTPException:
        raise
    except Exception:
        db.rollback()
        import traceback; traceback.print_exc()
        raise HTTPException(500, "Error al agregar items al inventario")
    finally:
        db.close()


@router.get('/api/gastos_operacionales')
async def list_gastos(
    request: Request,
    limit: int = Query(500, ge=1, le=2000),
):
    tok = _auth(request); _require_staff(tok)
    taller_id = _tenant_id(tok)
    db = _get_db()
    try:
        rows = db.execute(text(
            "SELECT id, fecha, descripcion, codigo_inventario, nombre_item, cantidad, "
            "costo_unitario, costo_total, registrado_por, notas "
            "FROM gastos_operacionales WHERE taller_id=:t ORDER BY id DESC LIMIT :lim"
        ), {'t': taller_id, 'lim': limit}).fetchall()
        gastos = [{'id': r[0], 'fecha': str(r[1]), 'descripcion': r[2],
                   'codigo_inventario': r[3], 'nombre_item': r[4],
                   'cantidad': r[5], 'costo_unitario': r[6], 'costo_total': r[7],
                   'registrado_por': r[8], 'notas': r[9]} for r in rows]
        inicio_mes = datetime.now().replace(day=1).strftime('%Y-%m-%d')
        tot = db.execute(text(
            'SELECT COALESCE(SUM(costo_total),0) FROM gastos_operacionales '
            'WHERE taller_id=:t AND fecha>=:inicio'
        ), {'t': taller_id, 'inicio': inicio_mes}).fetchone()[0]
        return {'gastos': gastos, 'total_mes': tot}
    finally:
        db.close()


@router.post('/api/gastos_operacionales')
async def create_gasto(request: Request):
    tok = _auth(request); _require_staff(tok)
    taller_id = _tenant_id(tok)
    body = await request.json()
    db = _get_db()
    try:
        q = float(body.get('cantidad') or 1)
        cu = float(body.get('costo_unitario') or 0)
        ct = q * cu
        db.execute(text('''
            INSERT INTO gastos_operacionales (taller_id, fecha, descripcion, codigo_inventario,
                nombre_item, cantidad, costo_unitario, costo_total, registrado_por, notas)
            VALUES (:t, :f, :d, :ci, :ni, :cant, :cu, :ct, :rp, :notas)
        '''), {
            't': taller_id, 'f': body.get('fecha') or datetime.now().strftime('%Y-%m-%d'),
            'd': body.get('descripcion', ''), 'ci': body.get('codigo_inventario', ''),
            'ni': body.get('nombre_item', ''), 'cant': q, 'cu': cu, 'ct': ct,
            'rp': tok.get('nombre', ''), 'notas': body.get('notas', '')
        })
        if body.get('codigo_inventario'):
            db.execute(text(
                'UPDATE inventario SET stock = stock - :q WHERE codigo=:c AND taller_id=:t'
            ), {'q': q, 'c': body.get('codigo_inventario'), 't': taller_id})
        db.commit()
        # Hook contabilidad: asiento gasto fail-safe
        try:
            gasto_row = db.execute(text(
                'SELECT id FROM gastos_operacionales WHERE taller_id=:t ORDER BY id DESC LIMIT 1'
            ), {'t': taller_id}).fetchone()
            if gasto_row:
                from utils.contabilidad_engine import generar_asiento_gasto
                generar_asiento_gasto(db, taller_id, gasto_row[0])
        except Exception as _ce:
            import logging
            logging.getLogger('sandoval.contabilidad').warning(
                'Hook gasto asiento fallido: %s', _ce
            )
        return {'ok': True}
    finally:
        db.close()


@router.delete('/api/gastos_operacionales/{gid}')
async def delete_gasto(gid: int, request: Request):
    tok = _auth(request); _require_admin(tok)
    taller_id = _tenant_id(tok)
    db = _get_db()
    try:
        row = db.execute(text(
            'SELECT codigo_inventario, cantidad FROM gastos_operacionales '
            'WHERE id=:id AND taller_id=:t'
        ), {'id': gid, 't': taller_id}).fetchone()
        if row and row[0]:
            db.execute(text(
                'UPDATE inventario SET stock = stock + :q WHERE codigo=:c AND taller_id=:t'
            ), {'q': row[1], 'c': row[0], 't': taller_id})
        db.execute(text(
            'DELETE FROM gastos_operacionales WHERE id=:id AND taller_id=:t'
        ), {'id': gid, 't': taller_id})
        db.commit()
        return {'ok': True}
    finally:
        db.close()

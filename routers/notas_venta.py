"""
routers/notas_venta.py - Notas de Venta (ventas directas de repuestos/servicios).
Fixes:
  - _normalize_fecha: bug ljust(19, ":00") corregido (fillchar debe ser 1 char).
  - DELETE: restaurado _require_admin (regresion de seguridad introducida por edicion previa).
"""
from routers._common import (
    router, ADMIN_HTML,
    _auth, _get_db, _require_admin, _require_staff, _safe_date,
    _img_to_url, _parse_json_field, _make_token, _tenant_id,
    os, json, datetime, timedelta, Path,
    Request, HTTPException, UploadFile, File, List, HTMLResponse, text,
)
from fastapi import Query


def _normalize_fecha(raw) -> str | None:
    """
    Convierte cualquier formato de fecha entrante a 'YYYY-MM-DD HH:MM:SS'.
    Acepta: 'YYYY-MM-DD', 'YYYY-MM-DDTHH:MM', 'YYYY-MM-DD HH:MM:SS', None.
    Retorna None si no hay valor.
    """
    if not raw:
        return None
    s = str(raw).strip()
    # Solo fecha YYYY-MM-DD (viene del <input type="date">)
    if len(s) == 10 and s[4] == "-":
        return s + " 00:00:00"
    # YYYY-MM-DDTHH:MM (formato del input datetime-local)
    if "T" in s:
        s = s.replace("T", " ")
    # Asegurar HH:MM:SS completo
    s = s[:19]
    if len(s) == 16:        # YYYY-MM-DD HH:MM
        s += ":00"
    elif len(s) == 13:      # YYYY-MM-DD HH
        s += ":00:00"
    elif len(s) == 10:      # YYYY-MM-DD
        s += " 00:00:00"
    return s if len(s) == 19 else None


@router.get("/api/notas_venta")
@router.get("/api/notas-venta")  # alias frontend admin SPA
async def list_notas(request: Request, limit: int = Query(100, ge=1, le=500)):
    tok = _auth(request)
    _require_staff(tok)
    taller_id = _tenant_id(tok)
    db = _get_db()
    try:
        rows = db.execute(text("""
            SELECT id, numero, fecha, cliente_nombre, subtotal, igv, total, estado, metodo_pago,
                   COALESCE(monto_pagado, 0)
            FROM notas_venta
            WHERE taller_id=:t
            ORDER BY id DESC
            LIMIT :lim
        """), {"t": taller_id, "lim": limit}).fetchall()
        return [
            {
                "id": r[0], "numero": r[1], "fecha": _safe_date(r[2]),
                "cliente": r[3], "subtotal": r[4], "igv": r[5],
                "total": r[6], "estado": r[7], "metodo_pago": r[8],
                "monto_pagado": float(r[9] or 0),
                "saldo": round(float(r[6] or 0) - float(r[9] or 0), 2),
            }
            for r in rows
        ]
    finally:
        db.close()


@router.get("/api/notas_venta/{nota_id}")
async def get_nota_detail(nota_id: int, request: Request):
    tok = _auth(request)
    _require_staff(tok)
    taller_id = _tenant_id(tok)
    db = _get_db()
    try:
        row = db.execute(text("""
            SELECT id, numero, fecha, cliente_nombre, subtotal, igv, total,
                   estado, metodo_pago, items, COALESCE(monto_pagado, 0), notas, pagos
            FROM notas_venta
            WHERE id=:nid AND taller_id=:t
        """), {"nid": nota_id, "t": taller_id}).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Nota no encontrada")
        items = row[9]
        if isinstance(items, str):
            try:
                items = json.loads(items)
            except Exception:
                items = []
        if items is None:
            items = []
        pagos = row[12]
        if isinstance(pagos, str):
            try:
                pagos = json.loads(pagos)
            except Exception:
                pagos = []
        if not isinstance(pagos, list):
            pagos = []
        return {
            "id": row[0], "numero": row[1], "fecha": _safe_date(row[2]),
            "cliente": row[3], "cliente_nombre": row[3],
            "subtotal": row[4], "igv": row[5], "total": row[6],
            "estado": row[7], "metodo_pago": row[8],
            "items": items,
            "monto_pagado": float(row[10] or 0),
            "notas": row[11] or "",
            "pagos": pagos,
        }
    finally:
        db.close()


@router.post("/api/notas_venta")
async def create_nota(request: Request):
    tok = _auth(request)
    _require_staff(tok)
    taller_id = _tenant_id(tok)
    body = await request.json()
    db = _get_db()
    try:
        fecha_custom = _normalize_fecha(body.get("fecha"))
        # Numeracion basada en la fecha efectiva (consecutivo del dia)
        fecha_dia = fecha_custom[:10] if fecha_custom else datetime.now().strftime("%Y-%m-%d")
        count = db.execute(text(
            "SELECT COUNT(*) FROM notas_venta WHERE taller_id=:t AND CAST(fecha AS date)=CAST(:d AS date)"
        ), {"t": taller_id, "d": fecha_dia}).fetchone()[0]
        numero = f"NV-{fecha_dia.replace('-', '')}-{str(count + 1).zfill(3)}"

        items = body.get("items", [])
        # El precio de cada item YA incluye IGV (precio final al publico)
        total    = round(sum(float(i.get("subtotal", 0)) for i in items), 2)
        igv      = round(total * 18 / 118, 2)
        subtotal = round(total - igv, 2)

        fecha_insert = fecha_custom or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # monto_pagado: si el frontend NO lo manda, asumimos cobro al instante (= total).
        # Si manda 0 o un parcial explícito (crédito/abono), se respeta.
        # PRD §4.2: integridad financiera. Validar 0 <= monto_pagado <= total.
        try:
            mp_raw = body.get("monto_pagado")
            monto_pagado = float(mp_raw) if mp_raw is not None else float(total)
        except (TypeError, ValueError):
            monto_pagado = float(total)
        if monto_pagado < 0:
            raise HTTPException(400, "monto_pagado no puede ser negativo")
        if monto_pagado > float(total) + 0.01:
            raise HTTPException(400, f"monto_pagado ({monto_pagado:.2f}) excede el total ({float(total):.2f})")
        # Clamp defensivo (centavos por redondeo)
        monto_pagado = round(min(monto_pagado, float(total)), 2)
        db.execute(text("""
            INSERT INTO notas_venta
                (taller_id, numero, fecha, cliente_id, cliente_nombre,
                 subtotal, igv, total, monto_pagado, estado, notas, metodo_pago, items)
            VALUES
                (:t, :n, CAST(:fc AS timestamp), :cli, :cn, :sub, :igv, :tot, :mpag,
                 'ACTIVA', :notas, :mp, :items)
        """), {
            "t": taller_id, "n": numero, "fc": fecha_insert,
            "cli": body.get("cliente_id"),
            "cn": body.get("cliente_nombre", "Consumidor Final"),
            "sub": subtotal, "igv": igv, "tot": total, "mpag": monto_pagado,
            "notas": body.get("notas", ""),
            "mp": body.get("metodo_pago", "Efectivo"),
            "items": json.dumps(items),
        })

        # Descontar stock de inventario para items con codigo
        for item in items:
            if item.get("codigo"):
                db.execute(text(
                    "UPDATE inventario SET stock = GREATEST(stock - :q, 0) "
                    "WHERE codigo=:c AND taller_id=:t"
                ), {"q": item.get("cantidad", 1), "c": item["codigo"], "t": taller_id})

        db.commit()
        # Hook contabilidad: asiento fail-safe
        try:
            nv_row = db.execute(text(
                "SELECT id FROM notas_venta WHERE taller_id=:t AND numero=:n"
            ), {"t": taller_id, "n": numero}).fetchone()
            if nv_row:
                from utils.contabilidad_engine import generar_asiento_nota_venta
                generar_asiento_nota_venta(db, taller_id, nv_row[0])
        except Exception as _ce:
            import logging
            logging.getLogger("sandoval.contabilidad").warning(
                "Hook nota_venta asiento fallido id=%s: %s", numero, _ce
            )
        return {"numero": numero, "total": total, "fecha": fecha_insert}
    finally:
        db.close()


@router.put("/api/notas_venta/{nid}")
async def update_nota_venta(nid: int, request: Request):
    """
    Edita una nota de venta existente.
    Si se cambia la fecha, se actualiza la fecha de la nota (para historial correcto).
    El numero NO cambia al editar.
    """
    tok = _auth(request)
    _require_staff(tok)
    taller_id = _tenant_id(tok)
    body = await request.json()
    db = _get_db()
    try:
        items = body.get("items", [])
        # Los items vienen con el precio final (incluye IGV)
        total    = round(sum(float(i.get("subtotal", i.get("total", 0))) for i in items), 2)
        igv      = round(total * 18 / 118, 2)
        subtotal = round(total - igv, 2)

        fecha_custom = _normalize_fecha(body.get("fecha"))

        params = {
            "cn": body.get("cliente_nombre", "Consumidor Final"),
            "sub": subtotal, "igv": igv, "tot": total,
            "notas": body.get("notas", ""),
            "mp": body.get("metodo_pago", "Efectivo"),
            "items": json.dumps(items),
            "id": nid,
            "t": taller_id,
        }

        if fecha_custom:
            params["fc"] = fecha_custom
            db.execute(text("""
                UPDATE notas_venta
                SET cliente_nombre=:cn,
                    subtotal=:sub, igv=:igv, total=:tot,
                    notas=:notas, metodo_pago=:mp,
                    items=:items,
                    fecha=CAST(:fc AS timestamp)
                WHERE id=:id AND taller_id=:t
            """), params)
        else:
            db.execute(text("""
                UPDATE notas_venta
                SET cliente_nombre=:cn,
                    subtotal=:sub, igv=:igv, total=:tot,
                    notas=:notas, metodo_pago=:mp,
                    items=:items
                WHERE id=:id AND taller_id=:t
            """), params)

        db.commit()
        return {"ok": True, "total": total, "fecha": fecha_custom}
    except Exception as e:
        import traceback; traceback.print_exc()
        raise HTTPException(500, "Error al actualizar nota")
    finally:
        db.close()


@router.delete("/api/notas_venta/{nid}")
async def delete_nota_venta(nid: int, request: Request):
    """
    Elimina una nota de venta y REVIERTE el stock de inventario que se descontó al crearla.
    PRD §4.3 (auditabilidad) y §4.2 (integridad financiera): no podemos perder stock al borrar.
    """
    tok = _auth(request)
    _require_admin(tok)
    taller_id = _tenant_id(tok)
    db = _get_db()
    try:
        # Lock + leer items antes de borrar para revertir stock
        row = db.execute(text(
            "SELECT items FROM notas_venta WHERE id=:id AND taller_id=:t FOR UPDATE"
        ), {"id": nid, "t": taller_id}).fetchone()
        if not row:
            raise HTTPException(404, "Nota no encontrada")
        items_raw = row[0]
        items = items_raw if isinstance(items_raw, list) else (json.loads(items_raw) if items_raw else [])
        # Revertir stock SOLO de items con codigo (los servicios no afectan inventario)
        for item in items or []:
            cod = (item.get("codigo") or "").strip()
            qty = float(item.get("cantidad", 0) or 0)
            if cod and qty > 0:
                db.execute(text(
                    "UPDATE inventario SET stock = stock + :q "
                    "WHERE codigo=:c AND taller_id=:t"
                ), {"q": qty, "c": cod, "t": taller_id})
        db.execute(text("DELETE FROM notas_venta WHERE id=:id AND taller_id=:t"),
                   {"id": nid, "t": taller_id})
        db.commit()
        return {"ok": True, "items_revertidos": sum(1 for it in (items or []) if it.get("codigo"))}
    finally:
        db.close()


@router.post("/api/notas_venta/_fix_fechas_abonos")
async def fix_fechas_abonos_utc(request: Request):
    """
    Corrige el bug de fechas en abonos: cuando el frontend usaba
    `new Date().toISOString().slice(0,10)` (fecha UTC), abonos hechos despues
    de las 19:00 hora Lima quedaban con fecha del dia siguiente.

    Detecta notas creadas HOY (zona Lima) cuyos pagos tienen fecha > hoy_lima
    y los corrige a hoy_lima manteniendo la hora.

    Query param:
      - dry_run=true (default): NO modifica, solo lista lo que cambiaria.
      - dry_run=false: aplica los cambios.

    Solo admin.
    """
    tok = _auth(request)
    _require_admin(tok)
    taller_id = _tenant_id(tok)
    dry_run = request.query_params.get("dry_run", "true").lower() != "false"

    # Hoy en Lima (UTC-5). datetime.now() del server puede no ser Lima,
    # asi que usamos un offset hardcoded como fallback seguro.
    from datetime import timezone
    now_utc = datetime.now(timezone.utc)
    hoy_lima = (now_utc - timedelta(hours=5)).date()
    manana_lima = hoy_lima + timedelta(days=1)

    db = _get_db()
    try:
        # Notas creadas HOY en zona Lima (con conversion explicita)
        rows = db.execute(text("""
            SELECT id, numero, fecha, pagos, monto_pagado, total
              FROM notas_venta
             WHERE taller_id = :t
               AND (fecha AT TIME ZONE 'UTC' AT TIME ZONE 'America/Lima')::date = :hoy
             ORDER BY id DESC
        """), {"t": taller_id, "hoy": hoy_lima}).fetchall()

        cambios = []
        notas_afectadas = 0
        pagos_corregidos = 0

        for r in rows:
            nid, numero, fecha_nota, pagos_raw, monto_pagado, total = r
            pagos = pagos_raw
            if isinstance(pagos, str):
                try: pagos = json.loads(pagos)
                except Exception: pagos = []
            if not isinstance(pagos, list) or not pagos:
                continue

            modificado = False
            pagos_nuevos = []
            cambios_nota = []
            for i, p in enumerate(pagos):
                fpago = (p.get("fecha") or "").strip()
                fecha_solo = fpago[:10]
                # Si la fecha del pago es "mañana" o posterior respecto al dia de Lima
                # → corregir a hoy_lima (manteniendo la hora HH:MM)
                if fecha_solo and fecha_solo >= manana_lima.isoformat():
                    nueva_fecha = hoy_lima.isoformat() + fpago[10:]
                    if not fpago[10:]:
                        nueva_fecha = hoy_lima.isoformat() + " 12:00"
                    cambios_nota.append({
                        "indice": i,
                        "monto": p.get("monto"),
                        "fecha_antes": fpago,
                        "fecha_despues": nueva_fecha,
                    })
                    p2 = dict(p); p2["fecha"] = nueva_fecha
                    pagos_nuevos.append(p2)
                    modificado = True
                    pagos_corregidos += 1
                else:
                    pagos_nuevos.append(p)

            if modificado:
                notas_afectadas += 1
                cambios.append({
                    "nota_id": nid,
                    "numero": numero,
                    "monto_pagado": float(monto_pagado or 0),
                    "total": float(total or 0),
                    "pagos_corregidos": cambios_nota,
                })
                if not dry_run:
                    db.execute(text("""
                        UPDATE notas_venta
                           SET pagos = CAST(:pagos AS jsonb)
                         WHERE id = :id AND taller_id = :t
                    """), {
                        "pagos": json.dumps(pagos_nuevos),
                        "id": nid, "t": taller_id,
                    })

        if not dry_run:
            db.commit()

        return {
            "modo":              "dry_run" if dry_run else "aplicado",
            "hoy_lima":          hoy_lima.isoformat(),
            "notas_revisadas":   len(rows),
            "notas_afectadas":   notas_afectadas,
            "pagos_corregidos":  pagos_corregidos,
            "cambios":           cambios,
            "siguiente_paso":    "Repite con ?dry_run=false para aplicar" if dry_run and notas_afectadas else None,
        }
    finally:
        db.close()


@router.post("/api/notas_venta/{nid}/abonar")
async def abonar_nota_venta(nid: int, request: Request):
    tok = _auth(request)
    _require_staff(tok)
    taller_id = _tenant_id(tok)
    body = await request.json()
    monto = float(body.get("monto", 0))
    if monto <= 0:
        raise HTTPException(400, "Monto invalido")
    metodo = (body.get("metodo_pago") or "Efectivo").strip() or "Efectivo"
    observacion = (body.get("observacion") or "").strip()
    # Fecha opcional (backdating) para que la caja cuadre con ingresos reales
    raw_fecha = (body.get("fecha") or "").strip()
    now = datetime.now()
    if raw_fecha:
        base = raw_fecha.replace("T", " ")
        try:
            if len(base) <= 10:
                d = datetime.strptime(base[:10], "%Y-%m-%d").replace(
                    hour=now.hour, minute=now.minute, second=now.second)
            else:
                d = datetime.strptime(base[:19], "%Y-%m-%d %H:%M:%S") if len(base) >= 19 else datetime.strptime(base[:16], "%Y-%m-%d %H:%M")
            fecha_pago = d.strftime("%Y-%m-%d %H:%M")
        except ValueError:
            fecha_pago = now.strftime("%Y-%m-%d %H:%M")
    else:
        fecha_pago = now.strftime("%Y-%m-%d %H:%M")
    db = _get_db()
    try:
        # Lock de fila hasta commit para evitar race cuando dos requests
        # concurrentes intentan abonar la misma nota (sobrepago).
        row = db.execute(text(
            "SELECT total, COALESCE(monto_pagado, 0), pagos FROM notas_venta "
            "WHERE id=:id AND taller_id=:t FOR UPDATE"
        ), {"id": nid, "t": taller_id}).fetchone()
        if not row:
            raise HTTPException(404, "Nota no encontrada")
        total_nv  = float(row[0] or 0)
        ya_pagado = float(row[1] or 0)
        saldo_prev = round(total_nv - ya_pagado, 2)
        if saldo_prev <= 0:
            raise HTTPException(400, "La nota ya está pagada")
        if monto > saldo_prev + 0.01:
            raise HTTPException(400, f"El monto excede el saldo pendiente (S/ {saldo_prev:.2f})")
        pagos_prev = row[2]
        if isinstance(pagos_prev, str):
            try: pagos_prev = json.loads(pagos_prev)
            except Exception: pagos_prev = []
        if not isinstance(pagos_prev, list):
            pagos_prev = []
        pagos_prev.append({
            "monto": round(monto, 2),
            "metodo": metodo,
            "fecha": fecha_pago,
            "observacion": observacion,
            "usuario": tok.get("nombre", ""),
        })
        nuevo_pagado = min(ya_pagado + monto, total_nv)
        nuevo_estado = "PAGADO" if nuevo_pagado >= total_nv else "ABONO"
        db.execute(text("""
            UPDATE notas_venta
               SET monto_pagado=:mp, estado=:est, metodo_pago=:mt, pagos=CAST(:pagos AS jsonb)
             WHERE id=:id AND taller_id=:t
        """), {"mp": nuevo_pagado, "est": nuevo_estado, "mt": metodo,
               "pagos": json.dumps(pagos_prev), "id": nid, "t": taller_id})
        db.commit()
        return {
            "ok": True,
            "monto_pagado": nuevo_pagado,
            "estado": nuevo_estado,
            "saldo": round(total_nv - nuevo_pagado, 2),
            "fecha_pago": fecha_pago,
        }
    finally:
        db.close()

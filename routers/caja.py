"""
routers/caja.py — Apertura/cierre de caja y consolidado diario (multi-tenant).

Refactor 2026-04-21:
  * taller_id del JWT via _tenant_id (antes TALLER_ID global).
  * caja_historial acepta dias validado (Query bounds).
  * cerrar_caja: UPDATE también scopeado por taller_id (defense-in-depth).
"""
from routers._common import (
    router, ADMIN_HTML,
    _auth, _get_db, _require_admin, _require_staff, _safe_date,
    _img_to_url, _parse_json_field, _make_token, _tenant_id,
    os, json, datetime, timedelta, Path,
    Request, HTTPException, UploadFile, File, List, HTMLResponse, text,
)
from fastapi import Query

# CTE compartido: pagos unificados (JSON pagos[] + legacy fallback fecha_dt)
_CTE_PAGOS = """
WITH pagos_jsonb AS (
  SELECT
    o.consecutivo, o.taller_id, o.cliente_id, o.vehiculo_placa, o.estado,
    (p->>'fecha')::date AS dia,
    (p->>'monto')::numeric AS monto,
    COALESCE(NULLIF(p->>'metodo',''), 'Efectivo') AS metodo,
    COALESCE(p->>'nota','') AS nota,
    COALESCE(p->>'usuario','') AS usuario
  FROM ordenes o
  CROSS JOIN LATERAL json_array_elements(COALESCE(o.pagos, '[]'::json)) AS p
  WHERE o.taller_id = :t
    AND o.pagos IS NOT NULL
    AND COALESCE(json_array_length(o.pagos), 0) > 0
),
pagos_legacy AS (
  SELECT
    o.consecutivo, o.taller_id, o.cliente_id, o.vehiculo_placa, o.estado,
    o.fecha_dt::date AS dia,
    COALESCE(o.monto_cobrado, 0)::numeric AS monto,
    COALESCE(o.metodo_pago, 'Efectivo') AS metodo,
    ''::text AS nota, ''::text AS usuario
  FROM ordenes o
  WHERE o.taller_id = :t
    AND COALESCE(o.monto_cobrado, 0) > 0
    AND (o.pagos IS NULL OR COALESCE(json_array_length(o.pagos), 0) = 0)
),
pagos_orden AS (
  SELECT * FROM pagos_jsonb UNION ALL SELECT * FROM pagos_legacy
)
"""



@router.get("/api/caja")
async def get_caja(request: Request):
    tok = _auth(request)
    _require_staff(tok)
    taller_id = _tenant_id(tok)
    db = _get_db()
    try:
        from datetime import date as dt_date
        hoy = dt_date.today().strftime("%Y-%m-%d")
        caja = db.execute(text(
            "SELECT id, fecha, apertura_hora, saldo_apertura, estado, usuario_apertura, notas_operador "
            "FROM cierres_caja WHERE taller_id=:t AND fecha=:f ORDER BY id DESC LIMIT 1"
        ), {"t": taller_id, "f": hoy}).fetchone()
        if not caja:
            return {"estado": "sin_apertura", "fecha": hoy}
        # ÓRDENES: pagos JSON (fecha real del abono que configuró el usuario).
        # Fallback legacy a fecha_dt si una orden tiene monto_cobrado>0 pero pagos vacío.
        tot = db.execute(text(_CTE_PAGOS + """
            SELECT
                COALESCE(SUM(monto) FILTER (WHERE metodo='Efectivo'), 0) AS ef,
                COALESCE(SUM(monto) FILTER (WHERE metodo IN ('Yape','Plin')), 0) AS yp,
                COALESCE(SUM(monto) FILTER (WHERE metodo='Transferencia'), 0) AS tr,
                COALESCE(SUM(monto) FILTER (WHERE metodo='Tarjeta'), 0) AS ta,
                COUNT(DISTINCT consecutivo) FILTER (WHERE monto > 0) AS n_ord
            FROM pagos_orden
            WHERE dia = CURRENT_DATE
        """), {"t": taller_id}).fetchone()
        nv_m = db.execute(text("""
            SELECT
                COALESCE(SUM(CASE WHEN COALESCE(monto_pagado,0) > 0 THEN monto_pagado ELSE total END)
                  FILTER (WHERE metodo_pago='Efectivo'), 0) as ef,
                COALESCE(SUM(CASE WHEN COALESCE(monto_pagado,0) > 0 THEN monto_pagado ELSE total END)
                  FILTER (WHERE metodo_pago IN ('Yape','Plin')), 0) as yp,
                COALESCE(SUM(CASE WHEN COALESCE(monto_pagado,0) > 0 THEN monto_pagado ELSE total END)
                  FILTER (WHERE metodo_pago='Transferencia'), 0) as tr,
                COALESCE(SUM(CASE WHEN COALESCE(monto_pagado,0) > 0 THEN monto_pagado ELSE total END)
                  FILTER (WHERE metodo_pago='Tarjeta'), 0) as ta,
                COALESCE(SUM(total), 0) as nv_tot
            FROM notas_venta WHERE taller_id=:t AND fecha::date=CURRENT_DATE
              AND COALESCE(estado,'ACTIVA') NOT IN ('ANULADA','CANCELADA')
        """), {"t": taller_id}).fetchone()
        ab_m = db.execute(text("""
            SELECT
                COALESCE(SUM(monto) FILTER (WHERE metodo_pago='Efectivo'), 0) as ef,
                COALESCE(SUM(monto) FILTER (WHERE metodo_pago IN ('Yape','Plin')), 0) as yp,
                COALESCE(SUM(monto) FILTER (WHERE metodo_pago='Transferencia'), 0) as tr,
                COALESCE(SUM(monto) FILTER (WHERE metodo_pago='Tarjeta'), 0) as ta
            FROM abonos_credito WHERE taller_id=:t AND fecha_dt::date=CURRENT_DATE
        """), {"t": taller_id}).fetchone()
        ef = round(float(tot[0]) + float(nv_m[0]) + float(ab_m[0]), 2)
        yp = round(float(tot[1]) + float(nv_m[1]) + float(ab_m[1]), 2)
        tr = round(float(tot[2]) + float(nv_m[2]) + float(ab_m[2]), 2)
        ta = round(float(tot[3]) + float(nv_m[3]) + float(ab_m[3]), 2)
        nv = round(float(nv_m[4]), 2)
        total_dia = ef + yp + tr + ta
        return {
            "id": caja[0], "fecha": caja[1], "apertura_hora": caja[2],
            "saldo_apertura": caja[3], "estado": caja[4],
            "usuario_apertura": caja[5], "notas": caja[6],
            "totales": {
                "efectivo": ef, "yape": yp,
                "transferencia": tr, "tarjeta": ta,
                "notas_venta": nv,
                "total": round(total_dia, 2), "n_ordenes": int(tot[4] or 0),
            }
        }
    finally:
        db.close()


@router.post("/api/caja/abrir")
async def abrir_caja(request: Request):
    tok = _auth(request)
    _require_staff(tok)
    taller_id = _tenant_id(tok)
    body = await request.json()
    db = _get_db()
    try:
        from datetime import date as dt_date
        hoy = dt_date.today().strftime("%Y-%m-%d")
        exists = db.execute(text(
            "SELECT id FROM cierres_caja WHERE taller_id=:t AND fecha=:f"
        ), {"t": taller_id, "f": hoy}).fetchone()
        if exists:
            raise HTTPException(409, "Ya existe una caja abierta para hoy")
        db.execute(text("""
            INSERT INTO cierres_caja (taller_id, fecha, apertura_hora, saldo_apertura,
                estado, usuario_apertura, notas_operador)
            VALUES (:t, :f, :h, :sa, 'abierto', :u, :n)
        """), {
            "t": taller_id, "f": hoy,
            "h": datetime.now().strftime("%H:%M"),
            "sa": float(body.get("saldo_apertura", 0)),
            "u": tok.get("nombre", ""), "n": body.get("notas", ""),
        })
        db.commit()
        return {"ok": True}
    finally:
        db.close()


@router.post("/api/caja/cerrar")
@router.post("/api/caja/{cid}/cerrar")
async def cerrar_caja(request: Request, cid: int | None = None):
    tok = _auth(request)
    _require_admin(tok)
    taller_id = _tenant_id(tok)
    body = await request.json()
    db = _get_db()
    try:
        from datetime import date as dt_date
        hoy = dt_date.today().strftime("%Y-%m-%d")
        if cid:
            caja = db.execute(text(
                "SELECT id FROM cierres_caja WHERE id=:id AND taller_id=:t"
            ), {"id": cid, "t": taller_id}).fetchone()
        else:
            caja = db.execute(text(
                "SELECT id FROM cierres_caja WHERE taller_id=:t AND fecha=:f AND estado='abierto'"
            ), {"t": taller_id, "f": hoy}).fetchone()
        if not caja:
            raise HTTPException(404, "No hay caja abierta para cerrar")
        db.execute(text("""
            UPDATE cierres_caja SET estado='CERRADA', cierre_hora=:h,
                saldo_cierre=:sc, notas_operador=:n, usuario_cierre=:u
            WHERE id=:id AND taller_id=:t
        """), {
            "h": datetime.now().strftime("%H:%M"),
            "sc": float(body.get("saldo_cierre", 0)),
            "n": body.get("notas", ""), "u": tok.get("nombre", ""),
            "id": caja[0], "t": taller_id,
        })
        db.commit()
        return {"ok": True}
    finally:
        db.close()


@router.get("/api/caja/historial")
async def caja_historial(
    request: Request,
    dias: int = Query(30, ge=1, le=365),
):
    """Desglose diario de ingresos en los últimos N días.

    Usa pagos JSON (fecha real del abono configurada por el usuario) para órdenes,
    fallback legacy a fecha_dt si la orden tiene monto_cobrado>0 pero pagos vacío.
    """
    tok = _auth(request); _require_admin(tok)
    taller_id = _tenant_id(tok)
    db = _get_db()
    try:
        rows = db.execute(text(_CTE_PAGOS + """
            SELECT dia,
                   SUM(efectivo)      AS efectivo,
                   SUM(yape)          AS yape,
                   SUM(transferencia) AS transferencia,
                   SUM(tarjeta)       AS tarjeta,
                   SUM(notas_venta)   AS notas_venta
            FROM (
                SELECT
                    dia,
                    CASE WHEN metodo='Efectivo' THEN monto ELSE 0 END AS efectivo,
                    CASE WHEN metodo IN ('Yape','Plin') THEN monto ELSE 0 END AS yape,
                    CASE WHEN metodo='Transferencia' THEN monto ELSE 0 END AS transferencia,
                    CASE WHEN metodo='Tarjeta' THEN monto ELSE 0 END AS tarjeta,
                    0::numeric AS notas_venta
                FROM pagos_orden
                WHERE dia >= CURRENT_DATE - (:dias - 1) * INTERVAL '1 day'
                UNION ALL
                SELECT
                    fecha::date AS dia,
                    CASE WHEN COALESCE(metodo_pago,'Efectivo') IN ('Efectivo') THEN (CASE WHEN COALESCE(monto_pagado,0) > 0 THEN monto_pagado ELSE total END) ELSE 0 END AS efectivo,
                    CASE WHEN COALESCE(metodo_pago,'Efectivo') IN ('Yape','Plin') THEN (CASE WHEN COALESCE(monto_pagado,0) > 0 THEN monto_pagado ELSE total END) ELSE 0 END AS yape,
                    CASE WHEN COALESCE(metodo_pago,'Efectivo') IN ('Transferencia') THEN (CASE WHEN COALESCE(monto_pagado,0) > 0 THEN monto_pagado ELSE total END) ELSE 0 END AS transferencia,
                    CASE WHEN COALESCE(metodo_pago,'Efectivo') IN ('Tarjeta') THEN (CASE WHEN COALESCE(monto_pagado,0) > 0 THEN monto_pagado ELSE total END) ELSE 0 END AS tarjeta,
                    COALESCE(total,0)::numeric AS notas_venta
                FROM notas_venta
                WHERE taller_id = :t
                  AND fecha::date >= CURRENT_DATE - (:dias - 1) * INTERVAL '1 day'
                  AND COALESCE(estado,'ACTIVA') NOT IN ('ANULADA','CANCELADA')
                UNION ALL
                SELECT
                    fecha_dt::date AS dia,
                    CASE WHEN COALESCE(metodo_pago,'Efectivo') IN ('Efectivo') THEN COALESCE(monto,0) ELSE 0 END AS efectivo,
                    CASE WHEN COALESCE(metodo_pago,'Efectivo') IN ('Yape','Plin') THEN COALESCE(monto,0) ELSE 0 END AS yape,
                    CASE WHEN COALESCE(metodo_pago,'Efectivo') IN ('Transferencia') THEN COALESCE(monto,0) ELSE 0 END AS transferencia,
                    CASE WHEN COALESCE(metodo_pago,'Efectivo') IN ('Tarjeta') THEN COALESCE(monto,0) ELSE 0 END AS tarjeta,
                    0::numeric AS notas_venta
                FROM abonos_credito
                WHERE taller_id = :t
                  AND fecha_dt::date >= CURRENT_DATE - (:dias - 1) * INTERVAL '1 day'
            ) sub
            GROUP BY dia
            ORDER BY dia
        """), {"t": taller_id, "dias": dias}).fetchall()
        historial = []
        for r in rows:
            ef = round(float(r[1] or 0), 2)
            yp = round(float(r[2] or 0), 2)
            tr = round(float(r[3] or 0), 2)
            ta = round(float(r[4] or 0), 2)
            nv = round(float(r[5] or 0), 2)
            tot = round(ef + yp + tr + ta, 2)
            historial.append({
                "fecha": str(r[0]),
                "efectivo": ef, "yape": yp,
                "transferencia": tr, "tarjeta": ta,
                "notas_venta": nv, "total": tot,
            })
        return {"historial": historial, "dias": dias}
    finally:
        db.close()


@router.get("/api/caja/detalle/{fecha}")
async def caja_detalle_dia(fecha: str, request: Request):
    """Desglose de movimientos de un día. Usa pagos JSON (fecha real del abono)."""
    tok = _auth(request)
    _require_staff(tok)
    taller_id = _tenant_id(tok)
    try:
        datetime.strptime(fecha, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(400, "Fecha inválida, usar YYYY-MM-DD")
    db = _get_db()
    try:
        ordenes = db.execute(text(_CTE_PAGOS + """
            SELECT po.consecutivo,
                   COALESCE(NULLIF(TRIM(c.nombre || ' ' || COALESCE(c.apellidos,'')), ''),
                            po.cliente_id, '(sin cliente)') AS cliente,
                   po.vehiculo_placa,
                   po.monto,
                   po.metodo,
                   po.estado,
                   po.nota,
                   po.usuario
              FROM pagos_orden po
              LEFT JOIN clientes c ON c.id = po.cliente_id AND c.taller_id = po.taller_id
             WHERE po.dia = :f AND po.monto > 0
             ORDER BY po.consecutivo
        """), {"t": taller_id, "f": fecha}).fetchall()
        notas = db.execute(text("""
            SELECT numero, cliente_nombre, total,
                   COALESCE(monto_pagado, 0) AS pagado,
                   COALESCE(metodo_pago, 'Efectivo') AS metodo,
                   estado
              FROM notas_venta
             WHERE taller_id = :t AND fecha::date = :f
             ORDER BY numero
        """), {"t": taller_id, "f": fecha}).fetchall()
        abonos = db.execute(text("""
            SELECT ac.credito_id, cr.cliente_nombre, ac.monto,
                   COALESCE(ac.metodo_pago, 'Efectivo') AS metodo,
                   ac.nota
              FROM abonos_credito ac
              JOIN creditos cr ON cr.id = ac.credito_id
             WHERE ac.taller_id = :t AND ac.fecha_dt::date = :f
             ORDER BY ac.id
        """), {"t": taller_id, "f": fecha}).fetchall()
        totales = {"Efectivo": 0.0, "Yape": 0.0, "Plin": 0.0,
                   "Transferencia": 0.0, "Tarjeta": 0.0, "Otros": 0.0}
        def _bucket(metodo: str) -> str:
            mt = (metodo or "Efectivo").strip()
            if mt in totales: return mt
            if mt.lower() in ("yape", "plin"): return "Yape"
            return "Otros"
        movimientos = []
        for r in ordenes:
            b = _bucket(r[4])
            totales[b] = round(totales[b] + float(r[3] or 0), 2)
            movimientos.append({
                "tipo": "Orden",
                "referencia": r[0],
                "cliente": r[1],
                "placa": r[2] or "",
                "monto": round(float(r[3] or 0), 2),
                "metodo": r[4],
                "estado": r[5] or "",
                "nota": r[6] or "",
                "usuario": r[7] or "",
            })
        for r in notas:
            pagado = float(r[3] or 0) if float(r[3] or 0) > 0 else float(r[2] or 0)
            b = _bucket(r[4])
            totales[b] = round(totales[b] + pagado, 2)
            movimientos.append({
                "tipo": "Nota Venta",
                "referencia": r[0],
                "cliente": r[1] or "",
                "placa": "",
                "monto": round(pagado, 2),
                "monto_total_nv": round(float(r[2] or 0), 2),
                "metodo": r[4],
                "estado": r[5] or "",
            })
        for r in abonos:
            b = _bucket(r[3])
            totales[b] = round(totales[b] + float(r[2] or 0), 2)
            movimientos.append({
                "tipo": "Abono Crédito",
                "referencia": f"CR-{r[0]}",
                "cliente": r[1] or "",
                "placa": "",
                "monto": round(float(r[2] or 0), 2),
                "metodo": r[3],
                "nota": r[4] or "",
            })
        return {
            "fecha": fecha,
            "totales_por_metodo": totales,
            "total_dia": round(sum(totales.values()), 2),
            "movimientos": movimientos,
            "resumen": {
                "ordenes_cobradas": len(ordenes),
                "notas_emitidas": len(notas),
                "abonos_credito": len(abonos),
            },
        }
    finally:
        db.close()

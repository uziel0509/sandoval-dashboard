"""
routers/finanzas.py — Centro Financiero ejecutivo (multi-tenant).

Refactor 2026-04-25:
  * Mantiene endpoints legacy: GET /api/finanzas, GET /api/finanzas/historico
  * NUEVO: GET /api/finanzas/dashboard?periodo=mes
      Endpoint consolidado con:
        - KPIs actuales + deltas vs periodo anterior
        - Sparklines (últimos 7 puntos por KPI)
        - Mix de ingresos (mano_obra, repuesto_margen, notas, abonos)
        - Top categorías de gasto
        - Proyección a 30 días (regresión lineal últimos 14 días)
        - Insights ejecutivos auto-generados (texto en español)

Refactor 2026-04-21: taller_id del JWT via _tenant_id (antes TALLER_ID global).
"""
from routers._common import (
    router, ADMIN_HTML,
    _auth, _get_db, _require_admin, _safe_date,
    _img_to_url, _parse_json_field, _make_token, _tenant_id,
    os, json, datetime, timedelta, Path,
    Request, HTTPException, UploadFile, File, List, HTMLResponse, text,
)


# ── Helpers locales de ganancia ────────────────────────────────────────────────

def _items_from_raw(raw) -> list:
    """Convierte items_cotizacion / items de notas_venta a lista Python."""
    if raw is None:
        return []
    if isinstance(raw, list):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw) or []
        except Exception:
            return []
    return []


_REP_CATS = ("repuesto", "general")
_MO_CATS  = ("servicio", "mano de obra", "mano_obra")

# Cache de inventario por taller_id, vive durante 1 request (db connection scope).
# Evita N+1: antes hacia 1 query por item; ahora 1 query total cuando se llama por
# primera vez en el request. Se invalida al cerrar la conexion.
def _get_inv_costo_map(db, taller_id: int) -> dict:
    """Mapa codigo->costo del inventario del taller. Cachea en el objeto db."""
    cache_attr = f"_inv_costo_map_t{taller_id}"
    cached = getattr(db, cache_attr, None)
    if cached is not None:
        return cached
    rows = db.execute(text(
        "SELECT codigo, COALESCE(costo, 0) FROM inventario WHERE taller_id=:t"
    ), {"t": taller_id}).fetchall()
    m = {r[0]: float(r[1] or 0) for r in rows if r[0]}
    setattr(db, cache_attr, m)
    return m


_COSTO_FALLBACK_RATIO = 0.6  # si no hay costo en inventario, asumir 60% del precio venta

# NOTA CONTABLE (PRD §4.2 - integridad financiera):
# El margen actualmente se calcula sobre precio_unitario que INCLUYE IGV (boletas).
# El costo de inventario es NETO. Esto puede inflar el margen ~18% en notas con IGV.
# Decision pendiente: dividir precio entre 1.18 antes de calcular margen?
# Riesgo: cambiar retroactivamente todos los reportes historicos.
# Excepcion: ventas a consumidor final < S/700 NO llevan IGV.
# Status: monitorear con auditoria contable trimestral. Si se aprueba el cambio,
#         agregar columna 'aplica_igv' a notas_venta y dividir condicionalmente.

def _ganancia_items(db, items: list, taller_id: int):
    """
    Calcula (mo, rep_venta, rep_costo, total) de una lista de items.
    Refactor 2026-04-25: pre-carga inv_map (una sola query) en lugar de N queries.
    """
    inv_map = _get_inv_costo_map(db, taller_id)
    mo = rep_venta = rep_costo = total = 0.0
    for item in items:
        cat = str(item.get("categoria", "")).lower().strip()
        try:
            qty = float(item.get("cantidad", 1) or 1)
            pu  = float(item.get("precio_unitario", 0) or 0)
            tot = float(item.get("total", item.get("subtotal", qty * pu)) or 0)
        except (TypeError, ValueError):
            continue  # item con datos invalidos, lo saltamos en lugar de crashear

        if any(k in cat for k in _MO_CATS):
            mo += tot
        elif any(k in cat for k in _REP_CATS) or cat == "":
            rep_venta += tot
            codigo = item.get("referencia") or item.get("codigo") or ""
            costo_unit = inv_map.get(codigo, 0.0) if codigo else 0.0
            if costo_unit <= 0:
                costo_unit = pu * _COSTO_FALLBACK_RATIO
            rep_costo += costo_unit * qty
        total += tot
    return round(mo, 2), round(rep_venta, 2), round(rep_costo, 2), round(total, 2)


_PERIODO_CONFIG = {
    "dia":    ("day",   "14 days",   "CURRENT_DATE",                         "day",   "1 day"),
    "semana": ("week",  "8 weeks",   "date_trunc('week', NOW())::date",       "week",  "7 days"),
    "mes":    ("month", "12 months", "date_trunc('month', NOW())::date",      "month", "1 month"),
    "anio":   ("year",  "5 years",   "date_trunc('year', NOW())::date",       "year",  "1 year"),
}

def _periodo_params(periodo: str):
    return _PERIODO_CONFIG.get(periodo, _PERIODO_CONFIG["mes"])


# ═══════════════════════════════════════════════════════════════════════════════
# ENDPOINT: GET /api/finanzas (legacy, devuelve KPIs del MES)
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/api/finanzas")
async def get_finanzas(request: Request):
    """Centro Financiero con ganancias reales (MO 100% + rep precio-costo)."""
    tok = _auth(request)
    _require_admin(tok)
    taller_id = _tenant_id(tok)
    db = _get_db()
    try:
        ing = db.execute(text("""
            SELECT metodo_pago, COALESCE(SUM(monto_cobrado), 0)
            FROM ordenes
            WHERE taller_id=:t AND COALESCE(monto_cobrado,0) > 0
              AND fecha_dt::date >= date_trunc('month', NOW())::date
            GROUP BY metodo_pago
        """), {"t": taller_id}).fetchall()
        ingresos_metodo: dict = {}
        for metodo, monto in ing:
            key = (metodo or "").strip() or "Efectivo"
            ingresos_metodo[key] = round(ingresos_metodo.get(key, 0.0) + float(monto or 0), 2)
        total_ordenes = round(sum(ingresos_metodo.values()), 2)

        nv_mes = db.execute(text(
            "SELECT COALESCE(SUM(COALESCE(monto_pagado, total)), 0) FROM notas_venta "
            "WHERE taller_id=:t AND fecha >= date_trunc('month', NOW())"
        ), {"t": taller_id}).fetchone()[0] or 0

        ac_mes = db.execute(text(
            "SELECT COALESCE(SUM(monto), 0) FROM abonos_credito "
            "WHERE taller_id=:t AND fecha_dt >= date_trunc('month', NOW())::date"
        ), {"t": taller_id}).fetchone()[0] or 0

        inicio_mes_str = datetime.now().strftime("%Y-%m-01")
        gastos_fact = db.execute(text("""
            SELECT COALESCE(SUM(total), 0) FROM facturas
            WHERE taller_id=:t AND tipo='gasto'
              AND CASE
                    WHEN fecha ~ '^[0-9]{2}/[0-9]{2}/[0-9]{4}$' THEN TO_DATE(fecha, 'DD/MM/YYYY')
                    WHEN fecha ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}'  THEN TO_DATE(substring(fecha,1,10), 'YYYY-MM-DD')
                    ELSE NULL::date
                  END >= CAST(:inicio AS date)
        """), {"t": taller_id, "inicio": inicio_mes_str}).fetchone()[0] or 0

        gastos_nomina = db.execute(text(
            "SELECT COALESCE(SUM(monto), 0) FROM pagos_trabajadores "
            "WHERE taller_id=:t AND fecha >= date_trunc('month', NOW())::date"
        ), {"t": taller_id}).fetchone()[0] or 0
        gastos = float(gastos_fact) + float(gastos_nomina)

        mo_o = rep_v_o = rep_c_o = 0.0
        for (items_raw, cobrado_o, total_jsonb) in db.execute(text(
            "SELECT items_cotizacion, COALESCE(monto_cobrado,0), "
            "       COALESCE(COALESCE(orden_total(items_cotizacion)::float, 0), 0) "
            "  FROM ordenes "
            " WHERE taller_id=:t AND COALESCE(monto_cobrado,0) > 0 "
            "   AND fecha_dt::date >= date_trunc('month', NOW())::date"
        ), {"t": taller_id}).fetchall():
            m, rv, rc, tot = _ganancia_items(db, _items_from_raw(items_raw), taller_id)
            base = float(total_jsonb) or tot
            pct = min(float(cobrado_o)/base, 1.0) if base > 0 else 1.0
            mo_o += m*pct; rep_v_o += rv*pct; rep_c_o += rc*pct

        mo_n = rep_v_n = rep_c_n = 0.0
        for (items_raw, pagado_n, total_n) in db.execute(text(
            "SELECT items, COALESCE(monto_pagado, total, 0), COALESCE(total, 0) "
            "  FROM notas_venta "
            " WHERE taller_id=:t AND fecha >= date_trunc('month', NOW())"
        ), {"t": taller_id}).fetchall():
            m, rv, rc, _ = _ganancia_items(db, _items_from_raw(items_raw), taller_id)
            pct = min(float(pagado_n)/float(total_n), 1.0) if total_n and total_n > 0 else 1.0
            mo_n += m*pct; rep_v_n += rv*pct; rep_c_n += rc*pct

        mo_c = rep_v_c = rep_c_c = 0.0
        cr_rows = db.execute(text("""
            SELECT c.items_json, c.total,
                   COALESCE(SUM(a.monto) FILTER (
                       WHERE a.fecha_dt >= date_trunc('month', NOW())::date), 0) AS cobrado_mes
            FROM creditos c
            LEFT JOIN abonos_credito a ON a.credito_id = c.id AND a.taller_id = c.taller_id
            WHERE c.taller_id = :t
            GROUP BY c.id, c.items_json, c.total
            HAVING COALESCE(SUM(a.monto) FILTER (
                WHERE a.fecha_dt >= date_trunc('month', NOW())::date), 0) > 0
        """), {"t": taller_id}).fetchall()
        for items_raw, total_c, cobrado in cr_rows:
            m, rv, rc, _ = _ganancia_items(db, _items_from_raw(items_raw), taller_id)
            pct = float(cobrado or 0) / float(total_c) if total_c else 0
            mo_c += m * pct; rep_v_c += rv * pct; rep_c_c += rc * pct

        mo_total     = round(mo_o + mo_n + mo_c, 2)
        rep_venta    = round(rep_v_o + rep_v_n + rep_v_c, 2)
        rep_costo    = round(rep_c_o + rep_c_n + rep_c_c, 2)
        rep_ganancia = round(rep_venta - rep_costo, 2)
        ganancia_bruta = round(mo_total + rep_ganancia, 2)
        ganancia_neta  = round(ganancia_bruta - float(gastos), 2)

        pago_stats = db.execute(text("""
            SELECT
                COUNT(*) FILTER (WHERE monto_cobrado >= orden_total(items_cotizacion)::float
                    AND items_cotizacion IS NOT NULL AND items_cotizacion::text != 'null') AS pagadas,
                COUNT(*) FILTER (WHERE monto_cobrado < orden_total(items_cotizacion)::float
                    AND monto_cobrado > 0
                    AND items_cotizacion IS NOT NULL AND items_cotizacion::text != 'null') AS parciales,
                COUNT(*) FILTER (WHERE (monto_cobrado IS NULL OR monto_cobrado = 0)) AS pendientes,
                COALESCE(SUM(orden_total(items_cotizacion)::float - monto_cobrado), 0) AS deuda_total
            FROM ordenes
            WHERE taller_id=:t
              AND items_cotizacion IS NOT NULL AND items_cotizacion::text != 'null'
        """), {"t": taller_id}).fetchone()

        return {
            "ingresos_mes": round(total_ordenes, 2),
            "notas_venta_mes": round(float(nv_mes), 2),
            "creditos_cobrados_mes": round(float(ac_mes), 2),
            "gastos_mes": round(float(gastos), 2),
            "utilidad_mes": round(total_ordenes + float(nv_mes) + float(ac_mes) - float(gastos), 2),
            "por_metodo": ingresos_metodo,
            "ganancias": {
                "mano_obra_100pct": mo_total,
                "repuesto_venta": rep_venta,
                "repuesto_costo": rep_costo,
                "repuesto_ganancia": rep_ganancia,
                "ganancia_bruta": ganancia_bruta,
                "ganancia_neta": ganancia_neta,
                "desglose": {
                    "ordenes":           {"mo": round(mo_o, 2), "rep_venta": round(rep_v_o, 2), "rep_costo": round(rep_c_o, 2)},
                    "notas_venta":       {"mo": round(mo_n, 2), "rep_venta": round(rep_v_n, 2), "rep_costo": round(rep_c_n, 2)},
                    "creditos_cobrados": {"mo": round(mo_c, 2), "rep_venta": round(rep_v_c, 2), "rep_costo": round(rep_c_c, 2)},
                }
            },
            "pago_stats": {
                "pagadas":     int(pago_stats[0] or 0),
                "parciales":   int(pago_stats[1] or 0),
                "pendientes":  int(pago_stats[2] or 0),
                "deuda_total": round(float(pago_stats[3] or 0), 2),
            }
        }
    except HTTPException:
        raise
    except Exception:
        import traceback; traceback.print_exc()
        raise HTTPException(500, "Error en finanzas")
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════════
# ENDPOINT: GET /api/finanzas/historico (legacy)
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/api/finanzas/historico")
async def get_finanzas_historico(request: Request, periodo: str = "mes"):
    tok = _auth(request)
    _require_admin(tok)
    taller_id = _tenant_id(tok)
    db = _get_db()
    try:
        trunc, interval, inicio_sql, _trunc_res, _int_res = _periodo_params(periodo)
        dc = "fecha_dt::date"

        cobrado_r = db.execute(text(f"""
            SELECT p, SUM(monto) FROM (
              SELECT date_trunc('{trunc}', {dc})::date AS p, COALESCE(monto_cobrado, 0) AS monto
                FROM ordenes
               WHERE taller_id=:t AND COALESCE(monto_cobrado,0) > 0
                 AND {dc} >= NOW() - interval '{interval}'
              UNION ALL
              SELECT date_trunc('{trunc}', fecha::timestamp)::date AS p,
                     COALESCE(monto_pagado, total, 0) AS monto
                FROM notas_venta
               WHERE taller_id=:t
                 AND fecha::timestamp >= NOW() - interval '{interval}'
              UNION ALL
              SELECT date_trunc('{trunc}', fecha_dt::timestamp)::date AS p, COALESCE(monto, 0) AS monto
                FROM abonos_credito
               WHERE taller_id=:t
                 AND fecha_dt::date >= NOW() - interval '{interval}'
            ) u
            GROUP BY p ORDER BY p
        """), {"t": taller_id}).fetchall()

        rep_r = db.execute(text(
            f"SELECT date_trunc('{trunc}', {dc})::date AS p, "
            f"  COALESCE(SUM(COALESCE(NULLIF(item->>'cantidad','')::float, 0) * GREATEST("
            f"    COALESCE(NULLIF(item->>'precio_unitario','')::float, 0) - COALESCE(inv.costo, COALESCE(NULLIF(item->>'precio_unitario','')::float, 0)*0.6)"
            f"  , 0) "
            f"  * LEAST(o.monto_cobrado / NULLIF(COALESCE(orden_total(o.items_cotizacion)::float, 0), 0), 1.0)"
            f"  ), 0) "
            f"FROM ordenes o "
            f"CROSS JOIN jsonb_array_elements(COALESCE(o.items_cotizacion::jsonb, '[]'::jsonb)) item "
            f"LEFT JOIN inventario inv ON inv.codigo = item->>'referencia' AND inv.taller_id = o.taller_id "
            f"WHERE o.taller_id=:t AND COALESCE(o.monto_cobrado,0) > 0 "
            f"  AND item->>'categoria' IN ('Repuesto','Repuesto Histórico','Repuestos','General') "
            f"  AND {dc} >= NOW() - interval '{interval}' "
            f"GROUP BY 1 ORDER BY 1"
        ), {"t": taller_id}).fetchall()

        mdo_r = db.execute(text(
            f"SELECT date_trunc('{trunc}', {dc})::date AS p, "
            f"  COALESCE(SUM(COALESCE(NULLIF(item->>'total','')::float, 0) "
            f"    * LEAST(o.monto_cobrado / NULLIF(COALESCE(orden_total(o.items_cotizacion)::float, 0), 0), 1.0)"
            f"  ), 0) "
            f"FROM ordenes o "
            f"CROSS JOIN jsonb_array_elements(COALESCE(o.items_cotizacion::jsonb, '[]'::jsonb)) item "
            f"WHERE o.taller_id=:t AND COALESCE(o.monto_cobrado,0) > 0 "
            f"  AND item->>'categoria' IN ('Servicio','Mano de obra') "
            f"  AND {dc} >= NOW() - interval '{interval}' "
            f"GROUP BY 1 ORDER BY 1"
        ), {"t": taller_id}).fetchall()

        nv_r = db.execute(text(
            f"SELECT date_trunc('{trunc}', fecha::timestamp)::date AS p, "
            f"  COALESCE(SUM(COALESCE(monto_pagado, total, 0)), 0) "
            f"FROM notas_venta "
            f"WHERE taller_id=:t AND fecha::timestamp >= NOW() - interval '{interval}' "
            f"GROUP BY 1 ORDER BY 1"
        ), {"t": taller_id}).fetchall()

        gastos_r = db.execute(text(f"""
            SELECT p, SUM(total) FROM (
              SELECT date_trunc('{trunc}', f_parsed)::date AS p, total
                FROM (
                  SELECT total,
                         CASE
                           WHEN fecha ~ '^[0-9]{{2}}/[0-9]{{2}}/[0-9]{{4}}$' THEN TO_DATE(fecha, 'DD/MM/YYYY')
                           WHEN fecha ~ '^[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}'  THEN TO_DATE(substring(fecha,1,10), 'YYYY-MM-DD')
                           ELSE NULL::date
                         END AS f_parsed
                    FROM facturas
                   WHERE taller_id=:t AND tipo='gasto'
                ) x
               WHERE f_parsed IS NOT NULL
                 AND f_parsed >= (NOW() - interval '{interval}')::date
              UNION ALL
              SELECT date_trunc('{trunc}', fecha::timestamp)::date AS p,
                     COALESCE(monto, 0) AS total
                FROM pagos_trabajadores
               WHERE taller_id=:t AND fecha >= (NOW() - interval '{interval}')::date
            ) u
            GROUP BY p ORDER BY p
        """), {"t": taller_id}).fetchall()

        data: dict = {}
        for rows, key in [(cobrado_r, "cobrado"), (rep_r, "ganancia_repuesto"),
                          (mdo_r, "mano_obra"), (nv_r, "nv"), (gastos_r, "gastos")]:
            for r in rows:
                k = str(r[0])
                data.setdefault(k, {"periodo": k, "cobrado": 0, "ganancia_repuesto": 0,
                                    "mano_obra": 0, "nv": 0, "gastos": 0})
                data[k][key] = round(float(r[1]), 2)
        historico = sorted(
            [{**d,
              "ganancia_bruta": round(d["ganancia_repuesto"] + d["mano_obra"] + d["nv"], 2),
              "ganancia_neta":  round(d["ganancia_repuesto"] + d["mano_obra"] + d["nv"] - d["gastos"], 2)}
             for d in data.values()],
            key=lambda x: x["periodo"]
        )

        _rep_cats = "('Repuesto','Repuesto Histórico','Repuestos','General')"
        _mo_cats  = "('Servicio','Mano de obra')"
        res = db.execute(text(
            f"SELECT COALESCE(SUM(mdo), 0), COALESCE(SUM(rep_venta), 0), "
            f"       COALESCE(SUM(rep_costo), 0), COALESCE(SUM(cobrado), 0), COUNT(*) "
            f"FROM ("
            f"  SELECT o.consecutivo,"
            f"    MAX(o.monto_cobrado) AS cobrado,"
            f"    LEAST(MAX(o.monto_cobrado) / NULLIF(MAX(COALESCE(orden_total(o.items_cotizacion)::float, 0)), 0), 1.0) AS pct,"
            f"    SUM(CASE WHEN item->>'categoria' IN {_mo_cats} "
            f"             THEN COALESCE(NULLIF(item->>'total','')::float, 0) ELSE 0 END) AS mdo_nominal,"
            f"    SUM(CASE WHEN item->>'categoria' IN {_rep_cats} "
            f"             THEN COALESCE(NULLIF(item->>'total','')::float, 0) ELSE 0 END) AS rep_venta_nominal,"
            f"    SUM(CASE WHEN item->>'categoria' IN {_rep_cats} "
            f"             THEN COALESCE(NULLIF(item->>'cantidad','')::float, 0) * COALESCE(inv.costo, COALESCE(NULLIF(item->>'precio_unitario','')::float, 0)*0.6) "
            f"             ELSE 0 END) AS rep_costo_nominal,"
            f"    SUM(CASE WHEN item->>'categoria' IN {_mo_cats} "
            f"             THEN COALESCE(NULLIF(item->>'total','')::float, 0) ELSE 0 END) "
            f"    * COALESCE(LEAST(MAX(o.monto_cobrado) / NULLIF(MAX(COALESCE(orden_total(o.items_cotizacion)::float, 0)), 0), 1.0), 1.0) AS mdo,"
            f"    SUM(CASE WHEN item->>'categoria' IN {_rep_cats} "
            f"             THEN COALESCE(NULLIF(item->>'total','')::float, 0) ELSE 0 END) "
            f"    * COALESCE(LEAST(MAX(o.monto_cobrado) / NULLIF(MAX(COALESCE(orden_total(o.items_cotizacion)::float, 0)), 0), 1.0), 1.0) AS rep_venta,"
            f"    SUM(CASE WHEN item->>'categoria' IN {_rep_cats} "
            f"             THEN COALESCE(NULLIF(item->>'cantidad','')::float, 0) * COALESCE(inv.costo, COALESCE(NULLIF(item->>'precio_unitario','')::float, 0)*0.6) "
            f"             ELSE 0 END) "
            f"    * COALESCE(LEAST(MAX(o.monto_cobrado) / NULLIF(MAX(COALESCE(orden_total(o.items_cotizacion)::float, 0)), 0), 1.0), 1.0) AS rep_costo"
            f"  FROM ordenes o"
            f"  CROSS JOIN jsonb_array_elements(COALESCE(o.items_cotizacion::jsonb, '[]'::jsonb)) item"
            f"  LEFT JOIN inventario inv ON inv.codigo = item->>'referencia' AND inv.taller_id = o.taller_id"
            f"  WHERE o.taller_id=:t AND COALESCE(o.monto_cobrado,0) > 0"
            f"    AND {dc} >= {inicio_sql}"
            f"  GROUP BY o.consecutivo"
            f") sub"
        ), {"t": taller_id}).fetchone()

        nv_periodo = db.execute(text(
            f"SELECT COALESCE(SUM(COALESCE(monto_pagado, total, 0)), 0) FROM notas_venta "
            f"WHERE taller_id=:t AND fecha::date >= {inicio_sql}"
        ), {"t": taller_id}).fetchone()[0] or 0

        if periodo == "dia":
            inicio_gastos_str = datetime.now().strftime("%Y-%m-%d")
        elif periodo == "semana":
            hoy = datetime.now()
            inicio_gastos_str = (hoy - timedelta(days=hoy.weekday())).strftime("%Y-%m-%d")
        elif periodo == "anio":
            inicio_gastos_str = datetime.now().strftime("%Y-01-01")
        else:
            inicio_gastos_str = datetime.now().strftime("%Y-%m-01")

        gastos_fact_p = db.execute(text("""
            SELECT COALESCE(SUM(total), 0) FROM facturas
            WHERE taller_id=:t AND tipo='gasto'
              AND CASE
                    WHEN fecha ~ '^[0-9]{2}/[0-9]{2}/[0-9]{4}$' THEN TO_DATE(fecha, 'DD/MM/YYYY')
                    WHEN fecha ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}'  THEN TO_DATE(substring(fecha,1,10), 'YYYY-MM-DD')
                    ELSE NULL::date
                  END >= CAST(:inicio AS date)
        """), {"t": taller_id, "inicio": inicio_gastos_str}).fetchone()[0] or 0
        gastos_nom_p = db.execute(text(
            "SELECT COALESCE(SUM(monto), 0) FROM pagos_trabajadores "
            "WHERE taller_id=:t AND fecha >= CAST(:inicio AS date)"
        ), {"t": taller_id, "inicio": inicio_gastos_str}).fetchone()[0] or 0
        gastos_periodo = float(gastos_fact_p) + float(gastos_nom_p)

        mdo_p     = round(float(res[0] or 0), 2)
        rv_p      = round(float(res[1] or 0), 2)
        rc_p      = round(float(res[2] or 0), 2)
        cobrado_p = round(float(res[3] or 0), 2)
        n_ord_p   = int(res[4] or 0)
        nv_p      = round(float(nv_periodo), 2)
        gastos_p  = round(float(gastos_periodo), 2)

        rep_ganancia_p   = round(rv_p - rc_p, 2)
        ganancia_bruta_p = round(mdo_p + rep_ganancia_p + nv_p, 2)
        ganancia_neta_p  = round(ganancia_bruta_p - gastos_p, 2)

        resumen = {
            "mdo_mes":          mdo_p,
            "rep_venta_mes":    rv_p,
            "rep_costo_mes":    rc_p,
            "rep_ganancia_mes": rep_ganancia_p,
            "cobrado_mes":      cobrado_p,
            "total_ordenes_mes": n_ord_p,
            "ticket_promedio":  round(cobrado_p / max(n_ord_p, 1), 2),
            "nv_mes":           nv_p,
            "gastos_mes":       gastos_p,
            "ganancia_bruta_mes": ganancia_bruta_p,
            "ganancia_neta_mes":  ganancia_neta_p,
            "periodo_label":    {"dia": "Hoy", "semana": "Esta semana", "mes": "Este mes", "anio": "Este año"}.get(periodo, "Este mes"),
        }

        return {"historico": historico, "resumen": resumen}

    except HTTPException:
        raise
    except Exception:
        # PRD §4.3: errores deben quedar en logs, NO retornar 200 con datos vacios.
        import traceback; traceback.print_exc()
        raise HTTPException(500, "Error en finanzas/historico (revisar logs)")
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════════
# NUEVO: GET /api/finanzas/dashboard?periodo=mes
# Endpoint ejecutivo consolidado (KPIs + deltas + sparklines + insights + proyecc)
# ═══════════════════════════════════════════════════════════════════════════════

# Rangos: actual y anterior
_PERIODO_RANGOS_SQL = {
    "dia": {
        "actual_inicio":   "CURRENT_DATE",
        "actual_fin":      "CURRENT_DATE + interval '1 day'",
        "anterior_inicio": "CURRENT_DATE - interval '1 day'",
        "anterior_fin":    "CURRENT_DATE",
        "label":           "Hoy",
        "label_anterior":  "Ayer",
    },
    "semana": {
        "actual_inicio":   "date_trunc('week', NOW())::date",
        "actual_fin":      "date_trunc('week', NOW())::date + interval '7 days'",
        "anterior_inicio": "date_trunc('week', NOW())::date - interval '7 days'",
        "anterior_fin":    "date_trunc('week', NOW())::date",
        "label":           "Esta semana",
        "label_anterior":  "Semana anterior",
    },
    "quincena": {
        "actual_inicio":   "(CURRENT_DATE - interval '14 days')::date",
        "actual_fin":      "(CURRENT_DATE + interval '1 day')::date",
        "anterior_inicio": "(CURRENT_DATE - interval '28 days')::date",
        "anterior_fin":    "(CURRENT_DATE - interval '14 days')::date",
        "label":           "Últimos 15 días",
        "label_anterior":  "15 días previos",
    },
    "mes": {
        "actual_inicio":   "date_trunc('month', NOW())::date",
        "actual_fin":      "(date_trunc('month', NOW()) + interval '1 month')::date",
        "anterior_inicio": "(date_trunc('month', NOW()) - interval '1 month')::date",
        "anterior_fin":    "date_trunc('month', NOW())::date",
        "label":           "Este mes",
        "label_anterior":  "Mes anterior",
    },
    "anio": {
        "actual_inicio":   "date_trunc('year', NOW())::date",
        "actual_fin":      "(date_trunc('year', NOW()) + interval '1 year')::date",
        "anterior_inicio": "(date_trunc('year', NOW()) - interval '1 year')::date",
        "anterior_fin":    "date_trunc('year', NOW())::date",
        "label":           "Este año",
        "label_anterior":  "Año anterior",
    },
}


def _kpis_rango(db, taller_id: int, ini_sql: str, fin_sql: str) -> dict:
    """Calcula KPIs entre [ini_sql, fin_sql). Retorna dict con todas las métricas."""
    # Cobrado de órdenes (suma monto_cobrado en órdenes con fecha_dt en el rango)
    cobrado_ord = db.execute(text(f"""
        SELECT COALESCE(SUM(monto_cobrado), 0), COUNT(*) FILTER (WHERE COALESCE(monto_cobrado,0)>0)
          FROM ordenes
         WHERE taller_id=:t AND fecha_dt::date >= ({ini_sql})
           AND fecha_dt::date < ({fin_sql})
    """), {"t": taller_id}).fetchone()
    cobrado_o = float(cobrado_ord[0] or 0)
    n_ord     = int(cobrado_ord[1] or 0)

    # Cobrado notas_venta
    cobrado_nv = db.execute(text(f"""
        SELECT COALESCE(SUM(COALESCE(monto_pagado, 0)), 0),
               COALESCE(SUM(COALESCE(total, 0)), 0)
          FROM notas_venta
         WHERE taller_id=:t AND fecha::date >= ({ini_sql})
           AND fecha::date < ({fin_sql})
           AND COALESCE(estado,'ACTIVA') NOT IN ('ANULADA','CANCELADA')
    """), {"t": taller_id}).fetchone()
    nv_pagado = float(cobrado_nv[0] or 0)
    nv_total  = float(cobrado_nv[1] or 0)

    # Cobrado abonos_credito
    cobrado_ab = db.execute(text(f"""
        SELECT COALESCE(SUM(monto), 0)
          FROM abonos_credito
         WHERE taller_id=:t AND fecha_dt::date >= ({ini_sql})
           AND fecha_dt::date < ({fin_sql})
    """), {"t": taller_id}).fetchone()
    ab = float(cobrado_ab[0] or 0)

    # Mano de obra y repuestos prorrateados (órdenes con cobranza en rango)
    _rep_cats = "('Repuesto','Repuesto Histórico','Repuestos','General')"
    _mo_cats  = "('Servicio','Mano de obra')"
    res_o = db.execute(text(f"""
        SELECT COALESCE(SUM(mdo), 0), COALESCE(SUM(rep_venta), 0),
               COALESCE(SUM(rep_costo), 0)
          FROM (
            SELECT o.consecutivo,
              SUM(CASE WHEN item->>'categoria' IN {_mo_cats}
                       THEN COALESCE(NULLIF(item->>'total','')::float, 0) ELSE 0 END)
              * COALESCE(LEAST(MAX(o.monto_cobrado) / NULLIF(MAX(COALESCE(orden_total(o.items_cotizacion)::float, 0)), 0), 1.0), 1.0) AS mdo,
              SUM(CASE WHEN item->>'categoria' IN {_rep_cats}
                       THEN COALESCE(NULLIF(item->>'total','')::float, 0) ELSE 0 END)
              * COALESCE(LEAST(MAX(o.monto_cobrado) / NULLIF(MAX(COALESCE(orden_total(o.items_cotizacion)::float, 0)), 0), 1.0), 1.0) AS rep_venta,
              SUM(CASE WHEN item->>'categoria' IN {_rep_cats}
                       THEN COALESCE(NULLIF(item->>'cantidad','')::float, 0) * COALESCE(inv.costo, COALESCE(NULLIF(item->>'precio_unitario','')::float, 0)*0.6)
                       ELSE 0 END)
              * COALESCE(LEAST(MAX(o.monto_cobrado) / NULLIF(MAX(COALESCE(orden_total(o.items_cotizacion)::float, 0)), 0), 1.0), 1.0) AS rep_costo
            FROM ordenes o
            CROSS JOIN jsonb_array_elements(COALESCE(o.items_cotizacion::jsonb, '[]'::jsonb)) item
            LEFT JOIN inventario inv ON inv.codigo = item->>'referencia' AND inv.taller_id = o.taller_id
            WHERE o.taller_id=:t AND COALESCE(o.monto_cobrado,0) > 0
              AND o.fecha_dt::date >= ({ini_sql}) AND o.fecha_dt::date < ({fin_sql})
            GROUP BY o.consecutivo
          ) sub
    """), {"t": taller_id}).fetchone()
    mdo_o   = float(res_o[0] or 0)
    rv_o    = float(res_o[1] or 0)
    rc_o    = float(res_o[2] or 0)

    # ── Mano de obra y repuestos prorrateados de NOTAS DE VENTA ──
    # Cada nota tiene items con categoria 'Repuesto' o 'Servicio'.
    # MO = 100% ganancia · Repuesto = precio venta - costo de inventario.
    # Prorrateamos por monto_pagado/total para que notas a credito o parciales
    # cuenten solo la fraccion realmente cobrada.
    mdo_n = rv_n = rc_n = 0.0
    nv_rows = db.execute(text(f"""
        SELECT items, COALESCE(monto_pagado, 0), COALESCE(total, 0)
          FROM notas_venta
         WHERE taller_id=:t
           AND fecha::date >= ({ini_sql}) AND fecha::date < ({fin_sql})
           AND COALESCE(estado,'ACTIVA') NOT IN ('ANULADA','CANCELADA')
    """), {"t": taller_id}).fetchall()
    for items_raw, pagado_n, total_n in nv_rows:
        m, rv, rc, _ = _ganancia_items(db, _items_from_raw(items_raw), taller_id)
        pct = min(float(pagado_n)/float(total_n), 1.0) if total_n and float(total_n) > 0 else 0.0
        mdo_n += m * pct
        rv_n  += rv * pct
        rc_n  += rc * pct

    # ── Mano de obra y repuestos prorrateados de ABONOS DE CREDITO ──
    # Cada credito tiene items_json. Calculamos su composicion MO/Repuesto/costo
    # y prorrateamos por (monto cobrado en el rango / total del credito).
    mdo_c = rv_c = rc_c = 0.0
    cr_rows = db.execute(text(f"""
        SELECT c.items_json, COALESCE(c.total, 0),
               COALESCE(SUM(a.monto) FILTER (
                   WHERE a.fecha_dt::date >= ({ini_sql})
                     AND a.fecha_dt::date < ({fin_sql})
               ), 0) AS cobrado_periodo
          FROM creditos c
          LEFT JOIN abonos_credito a ON a.credito_id = c.id AND a.taller_id = c.taller_id
         WHERE c.taller_id = :t
         GROUP BY c.id, c.items_json, c.total
         HAVING COALESCE(SUM(a.monto) FILTER (
             WHERE a.fecha_dt::date >= ({ini_sql})
               AND a.fecha_dt::date < ({fin_sql})
         ), 0) > 0
    """), {"t": taller_id}).fetchall()
    for items_raw, total_c, cobrado_p in cr_rows:
        m, rv, rc, _ = _ganancia_items(db, _items_from_raw(items_raw), taller_id)
        pct = float(cobrado_p or 0) / float(total_c) if total_c and float(total_c) > 0 else 0.0
        pct = min(pct, 1.0)
        mdo_c += m * pct
        rv_c  += rv * pct
        rc_c  += rc * pct

    # Totales agregados (ordenes + notas + creditos)
    mdo_total = mdo_o + mdo_n + mdo_c
    rv_total  = rv_o  + rv_n  + rv_c
    rc_total  = rc_o  + rc_n  + rc_c

    # Gastos: facturas + nómina
    gastos_fact = db.execute(text(f"""
        SELECT COALESCE(SUM(total), 0) FROM facturas
         WHERE taller_id=:t AND tipo='gasto'
           AND CASE
                 WHEN fecha ~ '^[0-9]{{2}}/[0-9]{{2}}/[0-9]{{4}}$' THEN TO_DATE(fecha, 'DD/MM/YYYY')
                 WHEN fecha ~ '^[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}'  THEN TO_DATE(substring(fecha,1,10), 'YYYY-MM-DD')
                 ELSE NULL::date
               END >= ({ini_sql})
           AND CASE
                 WHEN fecha ~ '^[0-9]{{2}}/[0-9]{{2}}/[0-9]{{4}}$' THEN TO_DATE(fecha, 'DD/MM/YYYY')
                 WHEN fecha ~ '^[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}'  THEN TO_DATE(substring(fecha,1,10), 'YYYY-MM-DD')
                 ELSE NULL::date
               END < ({fin_sql})
    """), {"t": taller_id}).fetchone()[0] or 0
    gastos_nom = db.execute(text(f"""
        SELECT COALESCE(SUM(monto), 0) FROM pagos_trabajadores
         WHERE taller_id=:t AND fecha >= ({ini_sql}) AND fecha < ({fin_sql})
    """), {"t": taller_id}).fetchone()[0] or 0
    gastos = float(gastos_fact) + float(gastos_nom)

    # Cash flow real: cuanto entro de plata (sin restar costos)
    cobrado_total = round(cobrado_o + nv_pagado + ab, 2)

    # Ganancia REAL: MO 100% + (precio venta repuestos - costo inventario)
    # Suma SOLO ganancias reales de ordenes + notas + creditos.
    # Antes el bug: sumaba nv_pagado y ab planos como si fueran 100% ganancia.
    rep_ganancia  = round(rv_total - rc_total, 2)
    ganancia_bruta = round(mdo_total + rep_ganancia, 2)
    ganancia_neta  = round(ganancia_bruta - gastos, 2)
    margen_pct     = round((ganancia_neta / cobrado_total * 100), 1) if cobrado_total > 0 else 0.0
    ticket_prom    = round(cobrado_total / n_ord, 2) if n_ord > 0 else 0.0

    return {
        "cobrado":         cobrado_total,
        "cobrado_ordenes": round(cobrado_o, 2),
        "cobrado_nv":      round(nv_pagado, 2),
        "nv_emitido":      round(nv_total, 2),
        "cobrado_abonos":  round(ab, 2),
        # MO = todas las fuentes (ordenes + notas + abonos creditos)
        "mdo":             round(mdo_total, 2),
        "mdo_ordenes":     round(mdo_o, 2),
        "mdo_notas":       round(mdo_n, 2),
        "mdo_creditos":    round(mdo_c, 2),
        # Repuestos = todas las fuentes
        "rep_venta":       round(rv_total, 2),
        "rep_costo":       round(rc_total, 2),
        "rep_ganancia":    rep_ganancia,
        "rep_venta_ordenes": round(rv_o, 2),
        "rep_venta_notas":   round(rv_n, 2),
        "rep_venta_creditos":round(rv_c, 2),
        "rep_costo_ordenes": round(rc_o, 2),
        "rep_costo_notas":   round(rc_n, 2),
        "rep_costo_creditos":round(rc_c, 2),
        "gastos":          round(gastos, 2),
        "gastos_facturas": round(float(gastos_fact), 2),
        "gastos_nomina":   round(float(gastos_nom), 2),
        "ganancia_bruta":  ganancia_bruta,
        "ganancia_neta":   ganancia_neta,
        "margen_pct":      margen_pct,
        "n_ordenes":       n_ord,
        "ticket_promedio": ticket_prom,
    }


def _delta(actual: float, anterior: float) -> dict:
    if anterior == 0 and actual == 0:
        return {"abs": 0.0, "pct": 0.0, "dir": "flat"}
    if anterior == 0:
        return {"abs": round(actual, 2), "pct": 100.0, "dir": "up"}
    pct = round(((actual - anterior) / abs(anterior)) * 100, 1)
    return {
        "abs": round(actual - anterior, 2),
        "pct": pct,
        "dir": "up" if actual > anterior else ("down" if actual < anterior else "flat"),
    }


def _sparkline_diaria(db, taller_id: int, dias: int = 7) -> dict:
    """Retorna {fechas:[7], cobrado:[7], ganancia:[7], gastos:[7]}."""
    rows = db.execute(text(f"""
        SELECT d::date AS dia,
          COALESCE((
            SELECT SUM(COALESCE(monto_cobrado,0)) FROM ordenes
             WHERE taller_id=:t AND fecha_dt::date = d::date
          ),0)
          + COALESCE((
            SELECT SUM(COALESCE(monto_pagado,0)) FROM notas_venta
             WHERE taller_id=:t AND fecha::date = d::date
               AND COALESCE(estado,'ACTIVA') NOT IN ('ANULADA','CANCELADA')
          ),0)
          + COALESCE((
            SELECT SUM(monto) FROM abonos_credito
             WHERE taller_id=:t AND fecha_dt::date = d::date
          ),0) AS cobrado,
          COALESCE((
            SELECT SUM(total) FROM facturas
             WHERE taller_id=:t AND tipo='gasto'
               AND CASE
                     WHEN fecha ~ '^[0-9]{{2}}/[0-9]{{2}}/[0-9]{{4}}$' THEN TO_DATE(fecha, 'DD/MM/YYYY')
                     WHEN fecha ~ '^[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}'  THEN TO_DATE(substring(fecha,1,10), 'YYYY-MM-DD')
                     ELSE NULL::date
                   END = d::date
          ),0)
          + COALESCE((
            SELECT SUM(monto) FROM pagos_trabajadores
             WHERE taller_id=:t AND fecha = d::date
          ),0) AS gastos
        FROM generate_series(CURRENT_DATE - interval '{dias-1} days', CURRENT_DATE, interval '1 day') d
        ORDER BY d
    """), {"t": taller_id}).fetchall()
    fechas, cobrado, ganancia, gastos = [], [], [], []
    for r in rows:
        fechas.append(str(r[0]))
        cob = float(r[1] or 0)
        gas = float(r[2] or 0)
        cobrado.append(round(cob, 2))
        gastos.append(round(gas, 2))
        # Aproximación rápida ganancia diaria = cobrado*0.45 - gastos (ratio típico)
        # Usaremos histórico real para gráfico principal; sparkline es indicador visual.
        ganancia.append(round(cob * 0.45 - gas, 2))
    return {"fechas": fechas, "cobrado": cobrado, "ganancia": ganancia, "gastos": gastos}


def _historico_diario(db, taller_id: int, dias: int = 30) -> list:
    """
    Historico con KPIs reales por dia.
    Refactor 2026-04-25: de 240+ queries (loop _kpis_rango) a 1 sola con
    generate_series + LEFT JOIN agregados. Ganancia se aproxima por:
      mdo_dia + (rep_venta_dia - rep_costo_dia) prorrateado por monto_cobrado/total.
    Para reconciliacion exacta del rango completo, usar _kpis_rango (no aggregable).
    """
    _rep_cats = "('Repuesto','Repuesto Histórico','Repuestos','General')"
    _mo_cats  = "('Servicio','Mano de obra')"

    rows = db.execute(text(f"""
        WITH dias AS (
          SELECT d::date AS dia FROM generate_series(
            CURRENT_DATE - interval '{dias-1} days', CURRENT_DATE, interval '1 day'
          ) d
        ),
        ord_agg AS (
          SELECT o.fecha_dt::date AS dia,
                 SUM(COALESCE(o.monto_cobrado,0)) AS cobrado_o,
                 COUNT(*) FILTER (WHERE COALESCE(o.monto_cobrado,0)>0) AS n_ord,
                 SUM(CASE WHEN item->>'categoria' IN {_mo_cats}
                          THEN COALESCE(NULLIF(item->>'total','')::float, 0) ELSE 0 END
                     * COALESCE(LEAST(o.monto_cobrado / NULLIF(COALESCE(orden_total(o.items_cotizacion)::float, 0),0), 1.0), 1.0)
                 ) AS mdo,
                 SUM(CASE WHEN item->>'categoria' IN {_rep_cats}
                          THEN COALESCE(NULLIF(item->>'total','')::float, 0) ELSE 0 END
                     * COALESCE(LEAST(o.monto_cobrado / NULLIF(COALESCE(orden_total(o.items_cotizacion)::float, 0),0), 1.0), 1.0)
                 ) AS rep_v,
                 SUM(CASE WHEN item->>'categoria' IN {_rep_cats}
                          THEN COALESCE(NULLIF(item->>'cantidad','')::float, 0)
                               * COALESCE(inv.costo, COALESCE(NULLIF(item->>'precio_unitario','')::float,0)*0.6)
                          ELSE 0 END
                     * COALESCE(LEAST(o.monto_cobrado / NULLIF(COALESCE(orden_total(o.items_cotizacion)::float, 0),0), 1.0), 1.0)
                 ) AS rep_c
            FROM ordenes o
            CROSS JOIN LATERAL jsonb_array_elements(COALESCE(o.items_cotizacion::jsonb, '[]'::jsonb)) item
            LEFT JOIN inventario inv ON inv.codigo = item->>'referencia' AND inv.taller_id = o.taller_id
           WHERE o.taller_id=:t AND COALESCE(o.monto_cobrado,0) > 0
             AND o.fecha_dt::date >= CURRENT_DATE - interval '{dias-1} days'
           GROUP BY o.fecha_dt::date
        ),
        nv_agg AS (
          SELECT fecha::date AS dia,
                 SUM(COALESCE(monto_pagado,0)) AS cobrado_nv
            FROM notas_venta
           WHERE taller_id=:t AND fecha::date >= CURRENT_DATE - interval '{dias-1} days'
             AND COALESCE(estado,'ACTIVA') NOT IN ('ANULADA','CANCELADA')
           GROUP BY fecha::date
        ),
        ab_agg AS (
          SELECT fecha_dt::date AS dia,
                 SUM(COALESCE(monto,0)) AS cobrado_ab
            FROM abonos_credito
           WHERE taller_id=:t AND fecha_dt::date >= CURRENT_DATE - interval '{dias-1} days'
           GROUP BY fecha_dt::date
        ),
        gas_agg AS (
          SELECT dia, SUM(monto) AS gastos FROM (
            SELECT CASE
                     WHEN fecha ~ '^[0-9]{{2}}/[0-9]{{2}}/[0-9]{{4}}$' THEN TO_DATE(fecha, 'DD/MM/YYYY')
                     WHEN fecha ~ '^[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}'  THEN TO_DATE(substring(fecha,1,10), 'YYYY-MM-DD')
                     ELSE NULL::date
                   END AS dia,
                   COALESCE(total,0) AS monto
              FROM facturas
             WHERE taller_id=:t AND tipo='gasto'
            UNION ALL
            SELECT fecha::date AS dia, COALESCE(monto,0) AS monto
              FROM pagos_trabajadores
             WHERE taller_id=:t
          ) u
          WHERE dia IS NOT NULL AND dia >= CURRENT_DATE - interval '{dias-1} days'
          GROUP BY dia
        )
        SELECT
          d.dia::text AS fecha,
          COALESCE(o.cobrado_o,0) + COALESCE(n.cobrado_nv,0) + COALESCE(a.cobrado_ab,0) AS cobrado,
          COALESCE(o.mdo,0)   AS mdo,
          COALESCE(o.rep_v,0) - COALESCE(o.rep_c,0) AS rep_ganancia,
          COALESCE(n.cobrado_nv,0) AS nv,
          COALESCE(g.gastos,0) AS gastos,
          COALESCE(o.n_ord,0)  AS n_ordenes
          FROM dias d
          LEFT JOIN ord_agg o ON o.dia = d.dia
          LEFT JOIN nv_agg  n ON n.dia = d.dia
          LEFT JOIN ab_agg  a ON a.dia = d.dia
          LEFT JOIN gas_agg g ON g.dia = d.dia
          ORDER BY d.dia
    """), {"t": taller_id}).fetchall()

    out = []
    for r in rows:
        cobrado = float(r[1] or 0)
        mdo     = float(r[2] or 0)
        rep_g   = float(r[3] or 0)
        nv      = float(r[4] or 0)
        gastos  = float(r[5] or 0)
        bruta = round(mdo + rep_g, 2)
        out.append({
            "fecha":          str(r[0]),
            "cobrado":        round(cobrado, 2),
            "mdo":            round(mdo, 2),
            "rep_ganancia":   round(rep_g, 2),
            "nv":             round(nv, 2),
            "gastos":         round(gastos, 2),
            "ganancia_bruta": bruta,
            "ganancia_neta":  round(bruta - gastos, 2),
            "n_ordenes":      int(r[6] or 0),
        })
    return out


def _proyeccion(historico: list, dias_futuro: int = 30) -> dict:
    """Regresión lineal simple sobre últimos 14 puntos para proyectar 30 días."""
    if not historico:
        return {"fechas": [], "ganancia_neta": [], "cobrado": [], "ganancia_total_proyectada": 0.0}
    base = historico[-14:] if len(historico) >= 14 else historico
    n = len(base)
    if n < 2:
        avg_g = base[0]["ganancia_neta"] if base else 0
        avg_c = base[0]["cobrado"] if base else 0
        slope_g = slope_c = 0
    else:
        x = list(range(n))
        y_g = [d["ganancia_neta"] for d in base]
        y_c = [d["cobrado"] for d in base]
        mean_x = sum(x) / n
        mean_g = sum(y_g) / n
        mean_c = sum(y_c) / n
        var_x = sum((xi - mean_x) ** 2 for xi in x)
        if var_x == 0:
            slope_g = slope_c = 0
        else:
            slope_g = sum((x[i] - mean_x) * (y_g[i] - mean_g) for i in range(n)) / var_x
            slope_c = sum((x[i] - mean_x) * (y_c[i] - mean_c) for i in range(n)) / var_x
        avg_g = mean_g
        avg_c = mean_c
    fechas, gn_proy, c_proy = [], [], []
    base_date = datetime.now().date()
    total_gn = 0.0
    for i in range(1, dias_futuro + 1):
        f = base_date + timedelta(days=i)
        gn = max(round(avg_g + slope_g * (n + i), 2), 0.0)
        c  = max(round(avg_c + slope_c * (n + i), 2), 0.0)
        fechas.append(f.strftime("%Y-%m-%d"))
        gn_proy.append(gn)
        c_proy.append(c)
        total_gn += gn
    return {
        "fechas": fechas,
        "ganancia_neta": gn_proy,
        "cobrado": c_proy,
        "ganancia_total_proyectada": round(total_gn, 2),
        "promedio_diario_estimado": round(total_gn / dias_futuro, 2) if dias_futuro else 0,
    }


def _top_gastos(db, taller_id: int, ini_sql: str, fin_sql: str) -> list:
    """Top categorías de gasto. Como no hay 'categoria' en facturas, agrupa por proveedor."""
    rows_fact = db.execute(text(f"""
        SELECT COALESCE(NULLIF(TRIM(proveedor),''), 'Otros gastos') AS cat,
               COALESCE(SUM(total),0) AS monto, COUNT(*) AS n
          FROM facturas
         WHERE taller_id=:t AND tipo='gasto'
           AND CASE
                 WHEN fecha ~ '^[0-9]{{2}}/[0-9]{{2}}/[0-9]{{4}}$' THEN TO_DATE(fecha, 'DD/MM/YYYY')
                 WHEN fecha ~ '^[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}'  THEN TO_DATE(substring(fecha,1,10), 'YYYY-MM-DD')
                 ELSE NULL::date
               END >= ({ini_sql})
           AND CASE
                 WHEN fecha ~ '^[0-9]{{2}}/[0-9]{{2}}/[0-9]{{4}}$' THEN TO_DATE(fecha, 'DD/MM/YYYY')
                 WHEN fecha ~ '^[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}'  THEN TO_DATE(substring(fecha,1,10), 'YYYY-MM-DD')
                 ELSE NULL::date
               END < ({fin_sql})
         GROUP BY 1 ORDER BY monto DESC LIMIT 5
    """), {"t": taller_id}).fetchall()
    nomina = db.execute(text(f"""
        SELECT COALESCE(SUM(monto),0), COUNT(*)
          FROM pagos_trabajadores
         WHERE taller_id=:t AND fecha >= ({ini_sql}) AND fecha < ({fin_sql})
    """), {"t": taller_id}).fetchone()
    out = []
    if float(nomina[0] or 0) > 0:
        out.append({"categoria": "Nómina (trabajadores)", "monto": round(float(nomina[0]), 2), "n": int(nomina[1] or 0)})
    for r in rows_fact:
        out.append({"categoria": str(r[0]), "monto": round(float(r[1] or 0), 2), "n": int(r[2] or 0)})
    out.sort(key=lambda x: x["monto"], reverse=True)
    return out[:6]


def _desglose_items(db, taller_id: int, ini_sql: str, fin_sql: str) -> dict:
    """
    Devuelve desglose detallado item-por-item del periodo:
      - repuestos:    [{nombre, codigo, cantidad, venta_unit, costo_unit, venta_total, costo_total, ganancia_total, origen}]
      - mano_obra:    [{nombre, cantidad, precio_unit, total, origen}]
      - resumen:      {n_repuestos, n_mo, ganancia_repuestos, ganancia_mo, total_venta_rep, total_costo_rep}
    Origen: 'orden:CONSEC' o 'nota:NUM'. Lista hasta 200 items, ordenados por ganancia desc.
    """
    repuestos: list = []
    mano_obra: list = []

    # Inventario costos
    inv_rows = db.execute(text(
        "SELECT codigo, costo, nombre FROM inventario WHERE taller_id=:t"
    ), {"t": taller_id}).fetchall()
    inv_map = {r[0]: {"costo": float(r[1] or 0), "nombre": r[2] or ""} for r in inv_rows}

    # Items de ÓRDENES con monto_cobrado>0 en el período
    rows_ord = db.execute(text(f"""
        SELECT consecutivo, items_cotizacion
          FROM ordenes
         WHERE taller_id=:t AND COALESCE(monto_cobrado,0) > 0
           AND fecha_dt::date >= ({ini_sql}) AND fecha_dt::date < ({fin_sql})
    """), {"t": taller_id}).fetchall()
    for cons, items_raw in rows_ord:
        items = _items_from_raw(items_raw)
        for it in items:
            cat = str(it.get("categoria", "")).lower().strip()
            qty = float(it.get("cantidad", 1) or 1)
            pu  = float(it.get("precio_unitario", 0) or 0)
            tot = float(it.get("total", it.get("subtotal", qty * pu)) or 0)
            nombre = (it.get("nombre") or "Sin nombre").strip()

            if any(k in cat for k in _MO_CATS):
                mano_obra.append({
                    "nombre":      nombre,
                    "cantidad":    round(qty, 2),
                    "precio_unit": round(pu, 2),
                    "total":       round(tot, 2),
                    "origen":      f"orden:{cons}",
                })
            elif any(k in cat for k in _REP_CATS) or cat == "":
                codigo = it.get("referencia") or it.get("codigo") or ""
                inv = inv_map.get(codigo, {})
                costo_u = inv.get("costo", 0) or pu * 0.6
                costo_t = costo_u * qty
                ganancia = tot - costo_t
                repuestos.append({
                    "nombre":         nombre,
                    "codigo":         codigo or "—",
                    "cantidad":       round(qty, 2),
                    "venta_unit":     round(pu, 2),
                    "costo_unit":     round(costo_u, 2),
                    "venta_total":    round(tot, 2),
                    "costo_total":    round(costo_t, 2),
                    "ganancia_total": round(ganancia, 2),
                    "margen_pct":     round((ganancia/tot*100) if tot > 0 else 0, 1),
                    "origen":         f"orden:{cons}",
                })

    # Items de NOTAS DE VENTA del periodo
    rows_nv = db.execute(text(f"""
        SELECT numero, items
          FROM notas_venta
         WHERE taller_id=:t AND fecha::date >= ({ini_sql}) AND fecha::date < ({fin_sql})
           AND COALESCE(estado,'ACTIVA') NOT IN ('ANULADA','CANCELADA')
    """), {"t": taller_id}).fetchall()
    for num, items_raw in rows_nv:
        items = _items_from_raw(items_raw)
        for it in items:
            qty = float(it.get("cantidad", 1) or 1)
            pu  = float(it.get("precio", it.get("precio_unitario", 0)) or 0)
            tot = float(it.get("subtotal", qty * pu) or 0)
            nombre = (it.get("nombre") or "Sin nombre").strip()
            codigo = it.get("codigo") or ""
            inv = inv_map.get(codigo, {})
            costo_u = inv.get("costo", 0) or pu * 0.6
            costo_t = costo_u * qty
            ganancia = tot - costo_t
            repuestos.append({
                "nombre":         nombre,
                "codigo":         codigo or "—",
                "cantidad":       round(qty, 2),
                "venta_unit":     round(pu, 2),
                "costo_unit":     round(costo_u, 2),
                "venta_total":    round(tot, 2),
                "costo_total":    round(costo_t, 2),
                "ganancia_total": round(ganancia, 2),
                "margen_pct":     round((ganancia/tot*100) if tot > 0 else 0, 1),
                "origen":         f"nota:{num}",
            })

    # Agrupar repuestos por nombre+codigo (consolidar mismo SKU vendido en varias órdenes)
    grouped: dict = {}
    for r in repuestos:
        k = (r["codigo"], r["nombre"])
        if k not in grouped:
            grouped[k] = {**r, "ocurrencias": 1, "origenes": [r["origen"]]}
            del grouped[k]["origen"]
        else:
            g = grouped[k]
            g["cantidad"]       = round(g["cantidad"] + r["cantidad"], 2)
            g["venta_total"]    = round(g["venta_total"] + r["venta_total"], 2)
            g["costo_total"]    = round(g["costo_total"] + r["costo_total"], 2)
            g["ganancia_total"] = round(g["ganancia_total"] + r["ganancia_total"], 2)
            g["margen_pct"]     = round((g["ganancia_total"]/g["venta_total"]*100) if g["venta_total"] > 0 else 0, 1)
            g["ocurrencias"]   += 1
            g["origenes"].append(r["origen"])
    repuestos_g = sorted(grouped.values(), key=lambda x: x["ganancia_total"], reverse=True)[:50]

    # Agrupar mano de obra por nombre
    mo_g: dict = {}
    for m in mano_obra:
        k = m["nombre"]
        if k not in mo_g:
            mo_g[k] = {**m, "ocurrencias": 1, "origenes": [m["origen"]]}
            del mo_g[k]["origen"]
        else:
            g = mo_g[k]
            g["cantidad"]    = round(g["cantidad"] + m["cantidad"], 2)
            g["total"]       = round(g["total"] + m["total"], 2)
            g["ocurrencias"]+= 1
            g["origenes"].append(m["origen"])
    mo_list = sorted(mo_g.values(), key=lambda x: x["total"], reverse=True)[:30]

    total_venta_rep    = round(sum(r["venta_total"]    for r in repuestos), 2)
    total_costo_rep    = round(sum(r["costo_total"]    for r in repuestos), 2)
    total_ganancia_rep = round(sum(r["ganancia_total"] for r in repuestos), 2)
    total_mo           = round(sum(m["total"]          for m in mano_obra), 2)

    return {
        "repuestos": repuestos_g,
        "mano_obra": mo_list,
        "resumen": {
            "n_repuestos_unicos": len(grouped),
            "n_mo_unicos":        len(mo_g),
            "n_repuestos_lineas": len(repuestos),
            "n_mo_lineas":        len(mano_obra),
            "total_venta_rep":    total_venta_rep,
            "total_costo_rep":    total_costo_rep,
            "ganancia_repuestos": total_ganancia_rep,
            "ganancia_mo":        total_mo,
            "margen_promedio_rep": round((total_ganancia_rep/total_venta_rep*100) if total_venta_rep > 0 else 0, 1),
        }
    }


def _aging_cxc(db, taller_id: int) -> dict:
    """
    Aging de cuentas por cobrar: tres fuentes consolidadas.
      1. Ordenes con saldo (total cotizacion - monto_cobrado > 0)
      2. Notas de venta a credito o con abono parcial (total - monto_pagado > 0)
      3. Creditos sin amortizar completamente (total - SUM(abonos) > 0)
    Refactor 2026-04-25: extendido para incluir notas y creditos (antes solo ordenes).
    Tambien protege casts JSONB con NULLIF.
    """
    row = db.execute(text("""
        WITH cxc AS (
          -- Ordenes con saldo
          SELECT
            'orden'::text AS tipo,
            consecutivo::text AS ref,
            (COALESCE(orden_total(items_cotizacion), 0)
             - COALESCE(monto_cobrado,0))::float AS saldo,
            GREATEST(EXTRACT(DAY FROM (NOW() - fecha_dt))::int, 0) AS dias_atraso
          FROM ordenes
          WHERE taller_id=:t
            AND items_cotizacion IS NOT NULL AND items_cotizacion::text != 'null'
            AND COALESCE(orden_total(items_cotizacion), 0)
                > COALESCE(monto_cobrado,0)
          UNION ALL
          -- Notas de venta con saldo (credito o abono parcial)
          SELECT
            'nota'::text,
            numero::text,
            (COALESCE(total,0) - COALESCE(monto_pagado,0))::float,
            GREATEST(EXTRACT(DAY FROM (NOW() - fecha))::int, 0)
          FROM notas_venta
          WHERE taller_id=:t
            AND COALESCE(estado,'ACTIVA') NOT IN ('ANULADA','CANCELADA')
            AND COALESCE(total,0) > COALESCE(monto_pagado,0)
          UNION ALL
          -- Creditos sin amortizar completamente
          -- (fecha_venta_dt es DATE; si esta NULL usar NOW() para no inflar atraso)
          SELECT
            'credito'::text,
            c.id::text,
            (COALESCE(c.total,0) - COALESCE(SUM(a.monto),0))::float,
            GREATEST(EXTRACT(DAY FROM (NOW() - COALESCE(c.fecha_venta_dt::timestamp, NOW())))::int, 0)
          FROM creditos c
          LEFT JOIN abonos_credito a ON a.credito_id = c.id AND a.taller_id = c.taller_id
          WHERE c.taller_id=:t
            AND COALESCE(c.estado,'ACTIVO') NOT IN ('ANULADO','CANCELADO','PAGADO')
          GROUP BY c.id, c.total, c.fecha_venta_dt
          HAVING COALESCE(c.total,0) > COALESCE(SUM(a.monto),0)
        )
        SELECT
          COALESCE(SUM(CASE WHEN dias_atraso BETWEEN 0 AND 30 THEN saldo ELSE 0 END), 0) AS b1,
          COUNT(*) FILTER (WHERE dias_atraso BETWEEN 0 AND 30) AS n1,
          COALESCE(SUM(CASE WHEN dias_atraso BETWEEN 31 AND 60 THEN saldo ELSE 0 END), 0) AS b2,
          COUNT(*) FILTER (WHERE dias_atraso BETWEEN 31 AND 60) AS n2,
          COALESCE(SUM(CASE WHEN dias_atraso > 60 THEN saldo ELSE 0 END), 0) AS b3,
          COUNT(*) FILTER (WHERE dias_atraso > 60) AS n3,
          COALESCE(SUM(saldo), 0) AS total,
          COUNT(*) AS n_total,
          COUNT(*) FILTER (WHERE tipo='orden') AS n_ordenes,
          COUNT(*) FILTER (WHERE tipo='nota') AS n_notas,
          COUNT(*) FILTER (WHERE tipo='credito') AS n_creditos,
          COALESCE(SUM(saldo) FILTER (WHERE tipo='orden'), 0) AS s_ordenes,
          COALESCE(SUM(saldo) FILTER (WHERE tipo='nota'), 0) AS s_notas,
          COALESCE(SUM(saldo) FILTER (WHERE tipo='credito'), 0) AS s_creditos
        FROM cxc
    """), {"t": taller_id}).fetchone()
    return {
        "buckets": [
            {"rango": "0-30 días",  "monto": round(float(row[0] or 0), 2), "n": int(row[1] or 0)},
            {"rango": "31-60 días", "monto": round(float(row[2] or 0), 2), "n": int(row[3] or 0)},
            {"rango": "60+ días",   "monto": round(float(row[4] or 0), 2), "n": int(row[5] or 0)},
        ],
        "total":   round(float(row[6] or 0), 2),
        "n_total": int(row[7] or 0),
        "por_tipo": {
            "ordenes":  {"n": int(row[8] or 0),  "monto": round(float(row[11] or 0), 2)},
            "notas":    {"n": int(row[9] or 0),  "monto": round(float(row[12] or 0), 2)},
            "creditos": {"n": int(row[10] or 0), "monto": round(float(row[13] or 0), 2)},
        },
    }


def _generar_insights(actual: dict, anterior: dict, deltas: dict, top_gastos: list,
                      historico: list, aging: dict, periodo_label: str,
                      proyeccion: dict) -> list:
    """Insights ejecutivos en español, basados en datos reales."""
    insights = []
    # 1) Ingresos
    d_cob = deltas["cobrado"]
    if abs(d_cob["pct"]) >= 5:
        flecha = "↑" if d_cob["dir"] == "up" else "↓"
        color  = "positive" if d_cob["dir"] == "up" else "negative"
        insights.append({
            "icon": "trending_up" if d_cob["dir"] == "up" else "trending_down",
            "tipo": color,
            "titulo": f"Ingresos {flecha} {abs(d_cob['pct']):.1f}% vs período anterior",
            "texto": f"Cobraste S/ {actual['cobrado']:,.2f} ({periodo_label.lower()}) vs S/ {anterior['cobrado']:,.2f} antes. "
                     f"{'Excelente' if d_cob['dir']=='up' else 'Atención'}: variación de S/ {abs(d_cob['abs']):,.2f}.",
        })

    # 2) Margen
    if actual["margen_pct"] < 25 and actual["cobrado"] > 0:
        insights.append({
            "icon": "warning",
            "tipo": "negative",
            "titulo": f"Margen comprimido: {actual['margen_pct']:.1f}%",
            "texto": "Tu margen de ganancia neta está debajo del umbral saludable (25%). "
                     "Revisa precios de repuestos y costos operativos. Si el margen baja del 15%, el negocio "
                     "no genera utilidad después de gastos.",
        })
    elif actual["margen_pct"] >= 40:
        insights.append({
            "icon": "check_circle",
            "tipo": "positive",
            "titulo": f"Excelente margen: {actual['margen_pct']:.1f}%",
            "texto": f"Estás generando S/ {actual['ganancia_neta']:,.2f} de ganancia neta sobre S/ {actual['cobrado']:,.2f} cobrados. "
                     "Mantén esta proporción de servicios sobre repuestos.",
        })

    # 3) Mix MO vs Repuestos
    rep_g = actual["rep_ganancia"]
    mo    = actual["mdo"]
    if (rep_g + mo) > 0:
        pct_mo = (mo / (rep_g + mo)) * 100
        if pct_mo > 60:
            insights.append({
                "icon": "build",
                "tipo": "info",
                "titulo": f"Mano de obra domina ({pct_mo:.0f}% de la ganancia)",
                "texto": "El taller depende fuertemente de servicios. Considera ampliar venta de repuestos "
                         "(mayor rotación) para diversificar ingresos.",
            })
        elif pct_mo < 30:
            insights.append({
                "icon": "inventory_2",
                "tipo": "info",
                "titulo": f"Repuestos dominan ({100-pct_mo:.0f}% de la ganancia)",
                "texto": "La mayor parte de tu ganancia viene de venta de repuestos. Aumenta horas de mano de obra "
                         "(margen 100%) para mejorar rentabilidad.",
            })

    # 4) Ticket promedio
    d_t = deltas["ticket_promedio"]
    if abs(d_t["pct"]) >= 10 and actual["n_ordenes"] >= 3:
        flecha = "↑" if d_t["dir"] == "up" else "↓"
        insights.append({
            "icon": "confirmation_number",
            "tipo": "positive" if d_t["dir"] == "up" else "negative",
            "titulo": f"Ticket promedio {flecha} {abs(d_t['pct']):.1f}% (S/ {actual['ticket_promedio']:,.2f})",
            "texto": f"{'Subió' if d_t['dir']=='up' else 'Bajó'} respecto al período anterior (S/ {anterior['ticket_promedio']:,.2f}). "
                     f"{'Estás cobrando trabajos más completos.' if d_t['dir']=='up' else 'Las órdenes se están haciendo más pequeñas; revisa diagnósticos.'}",
        })

    # 5) Gastos
    if actual["gastos"] > actual["ganancia_bruta"] * 0.5 and actual["ganancia_bruta"] > 0:
        gastos_pct = actual["gastos"] / actual["ganancia_bruta"] * 100
        insights.append({
            "icon": "money_off",
            "tipo": "negative",
            "titulo": f"Gastos consumen el {gastos_pct:.0f}% de la ganancia bruta",
            "texto": f"Estás gastando S/ {actual['gastos']:,.2f} sobre S/ {actual['ganancia_bruta']:,.2f} de ganancia bruta. "
                     f"{'Revisa la nómina (S/ '+f'{actual['gastos_nomina']:,.2f}'+').' if actual['gastos_nomina']>actual['gastos_facturas'] else 'Revisa gastos en facturas.'}",
        })

    # 6) Top categoría de gasto
    if top_gastos and top_gastos[0]["monto"] > 0:
        tg = top_gastos[0]
        if actual["gastos"] > 0:
            pct_tg = tg["monto"] / actual["gastos"] * 100
            if pct_tg > 40:
                insights.append({
                    "icon": "receipt_long",
                    "tipo": "info",
                    "titulo": f"{tg['categoria']} concentra {pct_tg:.0f}% de los gastos",
                    "texto": f"S/ {tg['monto']:,.2f} en {tg['n']} movimiento(s). Negociar este proveedor / reducir esta categoría puede liberar "
                             "margen significativo.",
                })

    # 7) Aging CxC
    if aging["total"] > 0:
        b3 = aging["buckets"][2]  # 60+
        if b3["monto"] > 0:
            insights.append({
                "icon": "schedule",
                "tipo": "negative",
                "titulo": f"Cobranza en riesgo: S/ {b3['monto']:,.2f} con +60 días",
                "texto": f"Tienes {b3['n']} orden(es) con saldo pendiente hace más de 2 meses. "
                         "Activa cobranza inmediata o registra como pérdida para limpiar el aging.",
            })
        elif aging["total"] > actual["cobrado"] * 0.3 and actual["cobrado"] > 0:
            insights.append({
                "icon": "schedule",
                "tipo": "info",
                "titulo": f"Cuentas por cobrar: S/ {aging['total']:,.2f}",
                "texto": f"{aging['n_total']} orden(es) con saldo pendiente. Equivale al "
                         f"{aging['total']/actual['cobrado']*100:.0f}% del cobrado del período. "
                         "Considera política de adelantos del 50% al recepcionar.",
            })

    # 8) Proyección
    if proyeccion.get("ganancia_total_proyectada", 0) > 0:
        gtp = proyeccion["ganancia_total_proyectada"]
        if gtp > actual["ganancia_neta"] * 1.1:
            insights.append({
                "icon": "rocket_launch",
                "tipo": "positive",
                "titulo": f"Proyección 30d: S/ {gtp:,.2f} de ganancia",
                "texto": f"Si mantienes la tendencia de los últimos 14 días, generarás S/ {proyeccion['promedio_diario_estimado']:,.2f}/día. "
                         f"Total estimado próximos 30 días: S/ {gtp:,.2f}.",
            })
        elif gtp < actual["ganancia_neta"] * 0.7:
            insights.append({
                "icon": "trending_down",
                "tipo": "negative",
                "titulo": f"Proyección 30d en descenso: S/ {gtp:,.2f}",
                "texto": "La tendencia reciente es bajista. Refuerza captación de clientes "
                         "(promociones, recordatorios de mantenimiento) para revertir.",
            })

    # 9) Estado general (siempre uno)
    if not insights:
        insights.append({
            "icon": "info",
            "tipo": "info",
            "titulo": "Sin alertas en este período",
            "texto": "Los KPIs se mantienen estables. Sigue monitoreando el margen y la cobranza para decisiones tempranas.",
        })

    return insights[:8]


@router.get("/api/finanzas/dashboard")
async def get_finanzas_dashboard(request: Request, periodo: str = "mes"):
    """Dashboard ejecutivo consolidado del Centro Financiero."""
    tok = _auth(request)
    _require_admin(tok)
    taller_id = _tenant_id(tok)
    if periodo not in _PERIODO_RANGOS_SQL:
        periodo = "mes"
    rng = _PERIODO_RANGOS_SQL[periodo]
    db = _get_db()
    try:
        actual   = _kpis_rango(db, taller_id, rng["actual_inicio"],   rng["actual_fin"])
        anterior = _kpis_rango(db, taller_id, rng["anterior_inicio"], rng["anterior_fin"])

        deltas = {k: _delta(actual.get(k, 0), anterior.get(k, 0))
                  for k in ("cobrado", "ganancia_neta", "ganancia_bruta", "margen_pct",
                            "ticket_promedio", "gastos", "n_ordenes", "mdo", "rep_ganancia")}

        sparklines = _sparkline_diaria(db, taller_id, dias=7)
        historico  = _historico_diario(db, taller_id, dias=30)
        proyeccion = _proyeccion(historico, dias_futuro=30)
        top_gastos = _top_gastos(db, taller_id, rng["actual_inicio"], rng["actual_fin"])
        aging      = _aging_cxc(db, taller_id)
        desglose   = _desglose_items(db, taller_id, rng["actual_inicio"], rng["actual_fin"])

        # Métodos de pago del período actual
        met_rows = db.execute(text(f"""
            SELECT metodo, SUM(monto) FROM (
              SELECT COALESCE(NULLIF(TRIM(metodo_pago),''),'Efectivo') AS metodo,
                     COALESCE(monto_cobrado,0) AS monto
                FROM ordenes
               WHERE taller_id=:t AND COALESCE(monto_cobrado,0) > 0
                 AND fecha_dt::date >= ({rng["actual_inicio"]})
                 AND fecha_dt::date < ({rng["actual_fin"]})
              UNION ALL
              SELECT COALESCE(NULLIF(TRIM(metodo_pago),''),'Efectivo') AS metodo,
                     COALESCE(monto_pagado,0) AS monto
                FROM notas_venta
               WHERE taller_id=:t AND fecha::date >= ({rng["actual_inicio"]})
                 AND fecha::date < ({rng["actual_fin"]})
                 AND COALESCE(estado,'ACTIVA') NOT IN ('ANULADA','CANCELADA')
              UNION ALL
              SELECT COALESCE(NULLIF(TRIM(metodo_pago),''),'Efectivo') AS metodo,
                     COALESCE(monto,0) AS monto
                FROM abonos_credito
               WHERE taller_id=:t AND fecha_dt::date >= ({rng["actual_inicio"]})
                 AND fecha_dt::date < ({rng["actual_fin"]})
            ) u GROUP BY metodo ORDER BY 2 DESC
        """), {"t": taller_id}).fetchall()
        metodos_pago = [{"metodo": str(r[0]), "monto": round(float(r[1] or 0), 2)} for r in met_rows]

        insights = _generar_insights(
            actual, anterior, deltas, top_gastos, historico, aging,
            rng["label"], proyeccion,
        )

        return {
            "periodo": periodo,
            "label": rng["label"],
            "label_anterior": rng["label_anterior"],
            "actual": actual,
            "anterior": anterior,
            "deltas": deltas,
            "sparklines": sparklines,
            "historico": historico,
            "proyeccion": proyeccion,
            "top_gastos": top_gastos,
            "metodos_pago": metodos_pago,
            "aging": aging,
            # Mix de GANANCIA real (lo que efectivamente queda en el bolsillo)
            "mix": {
                "mano_obra":     actual["mdo"],           # MO total: ordenes + notas + creditos
                "rep_ganancia":  actual["rep_ganancia"],  # Margen rep: ordenes + notas + creditos
                "notas_venta":   actual["nv_emitido"],    # informativo: total emitido en notas
                "notas_pagado":  actual["cobrado_nv"],    # informativo: cobrado de notas
                "notas_credito": round(actual["nv_emitido"] - actual["cobrado_nv"], 2),
                "abonos":        actual["cobrado_abonos"],# informativo: cobrado de creditos
            },
            # Desglose por fuente: ayuda a entender de donde sale la ganancia
            "ganancia_por_fuente": {
                "ordenes":  {"mo": actual["mdo_ordenes"],  "rep_venta": actual["rep_venta_ordenes"],  "rep_costo": actual["rep_costo_ordenes"],  "rep_ganancia": round(actual["rep_venta_ordenes"]-actual["rep_costo_ordenes"],2)},
                "notas":    {"mo": actual["mdo_notas"],    "rep_venta": actual["rep_venta_notas"],    "rep_costo": actual["rep_costo_notas"],    "rep_ganancia": round(actual["rep_venta_notas"]-actual["rep_costo_notas"],2)},
                "creditos": {"mo": actual["mdo_creditos"], "rep_venta": actual["rep_venta_creditos"], "rep_costo": actual["rep_costo_creditos"], "rep_ganancia": round(actual["rep_venta_creditos"]-actual["rep_costo_creditos"],2)},
            },
            "desglose_ganancia": desglose,
            "insights": insights,
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
    except HTTPException:
        raise
    except Exception as e:
        import traceback; traceback.print_exc()
        raise HTTPException(500, f"Error en dashboard: {e}")
    finally:
        db.close()

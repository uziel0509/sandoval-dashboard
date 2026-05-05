"""
routers/dashboard_pro.py — Dashboard profesional multi-tenant.

Un endpoint consolidado /api/dashboard/pro que devuelve 12 bloques sincronizados
con el modelo contable de finanzas.py:
    ganancia_bruta = MO + (rep_venta − rep_costo) + NV
    ganancia_neta  = ganancia_bruta − gastos − nómina

Cada bloque lleva un `reporte` textual autoexplicativo para renderizar en UI.

Bloques:
  1. kpis         — Ganancia neta/bruta, margen%, ticket promedio, CxC · con Δ% vs mes anterior
  2. aging        — Aging cuentas por cobrar (0-30, 31-60, 61-90, 90+)
  3. cashflow     — Proyección flujo 30 días (cobros esperados vs gastos)
  4. ingresos_gastos_6m — 6 meses barras apiladas + línea ganancia neta
  5. top_clientes — Top 10 del mes con margen aportado
  6. rendimiento_tecnicos — Órdenes/ingresos por técnico
  7. top_repuestos — Rotación + margen de los más vendidos
  8. metodos_pago — Distribución donut del mes
  9. alertas      — Panel operativo accionable
 10. funnel_fases — Distribución de órdenes por fase actual
 11. tendencia_12m — Serie mensual 12m ganancia neta + proyección lineal
 12. margen_categorias — MO vs Repuestos vs NV con margen individual
"""
from routers._common import (
    router, _auth, _get_db, _require_admin, _tenant_id,
    datetime, timedelta, text,
    Request, HTTPException,
)
import json as _json
from datetime import date as _date


# ═══════════════════ Helpers contables compartidos ═══════════════════

_MO_CATS = {"servicio", "mano de obra", "mano_obra", "mano-obra", "manoobra", "servicios"}
_REP_CATS = {"repuesto", "repuestos", "general", "producto", "productos", ""}


def _cat_norm(c):
    return (c or "").strip().lower()


def _is_mo(c):
    return _cat_norm(c) in _MO_CATS


def _is_rep(c):
    return _cat_norm(c) in _REP_CATS


def _cost_lookup(db, taller_id, ref, precio):
    """Costo de un ítem: inventario.costo por código, sino 60% del precio."""
    if ref:
        r = db.execute(text(
            "SELECT costo FROM inventario WHERE codigo=:c AND taller_id=:t"
        ), {"c": ref, "t": taller_id}).fetchone()
        if r and r[0] is not None:
            try:
                return float(r[0])
            except Exception:
                pass
    try:
        return float(precio or 0) * 0.6
    except Exception:
        return 0.0


def _parse_items(raw):
    if not raw:
        return []
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        # Algunas órdenes guardan items_cotizacion como dict {items:[], total:...}
        if isinstance(raw.get("items"), list):
            return raw["items"]
        return []
    try:
        p = _json.loads(raw)
        if isinstance(p, list):
            return p
        if isinstance(p, dict) and isinstance(p.get("items"), list):
            return p["items"]
    except Exception:
        pass
    return []


def _pct_delta(cur, prev):
    if not prev or abs(prev) < 0.001:
        return None
    return round((cur - prev) / prev * 100, 1)


def _money(x):
    return round(float(x or 0), 2)


# ═══════════════════ 1. KPIs con Δ% ═══════════════════

def _ganancia_periodo(db, taller_id, ini, fin):
    """Calcula MO, rep_venta, rep_costo, NV, gastos, nómina en rango [ini, fin]."""
    mo = 0.0
    rep_venta = 0.0
    rep_costo = 0.0
    nv_total = 0.0

    # --- Órdenes con abonos en el rango (desglose por pagos JSON) ---
    rows = db.execute(text("""
        SELECT o.consecutivo, o.items_cotizacion::text, o.pagos::text,
               COALESCE(o.monto_cobrado, 0) AS cobrado
        FROM ordenes o
        WHERE o.taller_id = :t
          AND o.pagos IS NOT NULL AND o.pagos::text NOT IN ('null','[]','')
    """), {"t": taller_id}).fetchall()

    for r in rows:
        items = _parse_items(r[1])
        try:
            pagos = _json.loads(r[2]) if r[2] else []
        except Exception:
            pagos = []
        if not isinstance(pagos, list):
            pagos = []
        total_orden = sum(float(i.get("total") or 0) for i in items) or float(r[3] or 0)
        if total_orden <= 0:
            continue

        # suma pagado DENTRO del rango
        pagado_rango = 0.0
        for p in pagos:
            f = (p.get("fecha") or "")[:10]
            try:
                d = datetime.strptime(f, "%Y-%m-%d").date()
            except Exception:
                continue
            if ini <= d <= fin:
                try:
                    pagado_rango += float(p.get("monto") or 0)
                except Exception:
                    pass
        if pagado_rango <= 0:
            continue

        pct = min(pagado_rango / total_orden, 1.0)
        for it in items:
            cat = it.get("categoria") or it.get("category") or ""
            tot_it = float(it.get("total") or 0) * pct
            if _is_mo(cat):
                mo += tot_it
            elif _is_rep(cat):
                rep_venta += tot_it
                costo = _cost_lookup(db, taller_id, it.get("referencia"), it.get("precio_unitario") or it.get("precio"))
                rep_costo += costo * float(it.get("cantidad") or 1) * pct

    # --- Órdenes legacy sin pagos[] pero con monto_cobrado en rango ---
    rows_lg = db.execute(text("""
        SELECT o.items_cotizacion::text, COALESCE(o.monto_cobrado,0),
               COALESCE(NULLIF(SUBSTRING(o.fecha_cobro FROM 1 FOR 10),'')::date, o.fecha_dt::date)
        FROM ordenes o
        WHERE o.taller_id = :t AND o.estado='ARCHIVADO'
          AND COALESCE(o.monto_cobrado,0) > 0
          AND (o.pagos IS NULL OR o.pagos::text IN ('null','[]',''))
          AND COALESCE(NULLIF(SUBSTRING(o.fecha_cobro FROM 1 FOR 10),'')::date, o.fecha_dt::date)
              BETWEEN :ini AND :fin
    """), {"t": taller_id, "ini": ini, "fin": fin}).fetchall()
    for r in rows_lg:
        items = _parse_items(r[0])
        tot = sum(float(i.get("total") or 0) for i in items)
        cobrado = float(r[1] or 0)
        if tot <= 0:
            continue
        pct = min(cobrado / tot, 1.0)
        for it in items:
            cat = it.get("categoria") or ""
            tot_it = float(it.get("total") or 0) * pct
            if _is_mo(cat):
                mo += tot_it
            elif _is_rep(cat):
                rep_venta += tot_it
                costo = _cost_lookup(db, taller_id, it.get("referencia"), it.get("precio_unitario") or it.get("precio"))
                rep_costo += costo * float(it.get("cantidad") or 1) * pct

    # --- Notas de venta en rango (monto_pagado) ---
    nv = db.execute(text("""
        SELECT COALESCE(SUM(COALESCE(monto_pagado, total, 0)), 0)
        FROM notas_venta
        WHERE taller_id=:t AND fecha::date BETWEEN :ini AND :fin
    """), {"t": taller_id, "ini": ini, "fin": fin}).fetchone()
    nv_total = float(nv[0] or 0)

    # --- Abonos a créditos: parte MO/rep proporcional + NV no aplica ---
    ab = db.execute(text("""
        SELECT cr.items_json, SUM(COALESCE(ac.monto,0)) AS cobrado, MAX(cr.total) AS total_cr
        FROM abonos_credito ac
        JOIN creditos cr ON cr.id = ac.credito_id AND cr.taller_id = ac.taller_id
        WHERE ac.taller_id=:t AND ac.fecha_dt BETWEEN :ini AND :fin
        GROUP BY cr.id, cr.items_json
    """), {"t": taller_id, "ini": ini, "fin": fin}).fetchall()
    for r in ab:
        items = _parse_items(r[0])
        cobrado = float(r[1] or 0)
        total_cr = float(r[2] or 0)
        if cobrado <= 0 or total_cr <= 0:
            continue
        pct = min(cobrado / total_cr, 1.0)
        # creditos items_json no trae categoría → todo como repuesto
        for it in items:
            cat = it.get("categoria") or ""
            tot_it = float(it.get("precio") or 0) * float(it.get("cantidad") or 1) * pct
            if _is_mo(cat):
                mo += tot_it
            else:
                rep_venta += tot_it
                costo = _cost_lookup(db, taller_id, it.get("item_id") or it.get("codigo"), it.get("precio"))
                rep_costo += costo * float(it.get("cantidad") or 1) * pct

    # --- Gastos operacionales (excluye reposiciones que ya están en rep_costo) ---
    g = db.execute(text("""
        SELECT COALESCE(SUM(costo_total), 0)
        FROM gastos_operacionales
        WHERE taller_id=:t AND fecha BETWEEN :ini AND :fin
    """), {"t": taller_id, "ini": ini, "fin": fin}).fetchone()
    gastos = float(g[0] or 0)

    # --- Nómina (pagos_trabajadores) ---
    n = db.execute(text("""
        SELECT COALESCE(SUM(monto), 0)
        FROM pagos_trabajadores
        WHERE taller_id=:t AND fecha BETWEEN :ini AND :fin
    """), {"t": taller_id, "ini": ini, "fin": fin}).fetchone()
    nomina = float(n[0] or 0)

    bruta = mo + (rep_venta - rep_costo) + nv_total
    neta = bruta - gastos - nomina
    ingresos = mo + rep_venta + nv_total

    return {
        "mo": _money(mo),
        "rep_venta": _money(rep_venta),
        "rep_costo": _money(rep_costo),
        "rep_ganancia": _money(rep_venta - rep_costo),
        "nv": _money(nv_total),
        "gastos": _money(gastos),
        "nomina": _money(nomina),
        "ganancia_bruta": _money(bruta),
        "ganancia_neta": _money(neta),
        "ingresos": _money(ingresos),
        "margen_pct": round(neta / ingresos * 100, 1) if ingresos > 0 else 0.0,
    }


def _kpis_bloque(db, taller_id):
    hoy = _date.today()
    ini_mes = hoy.replace(day=1)
    # mes anterior
    if ini_mes.month == 1:
        ini_prev = ini_mes.replace(year=ini_mes.year - 1, month=12)
    else:
        ini_prev = ini_mes.replace(month=ini_mes.month - 1)
    fin_prev = ini_mes - timedelta(days=1)

    cur = _ganancia_periodo(db, taller_id, ini_mes, hoy)
    prev = _ganancia_periodo(db, taller_id, ini_prev, fin_prev)

    # Ticket promedio del mes
    tk = db.execute(text("""
        SELECT COUNT(*) FILTER (WHERE COALESCE(monto_cobrado,0) > 0),
               COALESCE(SUM(monto_cobrado), 0)
        FROM ordenes
        WHERE taller_id=:t AND fecha_dt::date BETWEEN :ini AND :fin
    """), {"t": taller_id, "ini": ini_mes, "fin": hoy}).fetchone()
    n_ord = int(tk[0] or 0)
    ticket = float(tk[1] or 0) / n_ord if n_ord > 0 else 0.0

    # Cuentas por cobrar (saldo pendiente total)
    cxc = db.execute(text("""
        SELECT COALESCE(SUM(pendiente), 0), COUNT(*) FILTER (WHERE pendiente > 0)
        FROM creditos WHERE taller_id=:t AND pendiente > 0
    """), {"t": taller_id}).fetchone()
    cxc_monto = float(cxc[0] or 0)
    cxc_n = int(cxc[1] or 0)

    # Reporte textual
    d_neta = _pct_delta(cur["ganancia_neta"], prev["ganancia_neta"])
    d_ing = _pct_delta(cur["ingresos"], prev["ingresos"])
    tend = ("mejor" if (d_neta or 0) > 0 else "peor") if d_neta is not None else "sin comparativa"
    reporte = (
        f"Del 1 al {hoy.day} de {hoy.strftime('%B')}: ingresos S/{cur['ingresos']:,.0f}, "
        f"ganancia neta S/{cur['ganancia_neta']:,.0f} ({cur['margen_pct']}% de margen). "
        f"Tendencia {tend} que el mes pasado"
        + (f" ({d_neta:+.1f}% neta, {d_ing:+.1f}% ingresos)." if d_neta is not None else ".")
        + f" Ticket promedio S/{ticket:,.0f} en {n_ord} órdenes cobradas. "
        f"Tienes S/{cxc_monto:,.0f} por cobrar en {cxc_n} créditos activos."
    )

    return {
        "actual": cur,
        "anterior": prev,
        "delta": {
            "ganancia_neta": _pct_delta(cur["ganancia_neta"], prev["ganancia_neta"]),
            "ganancia_bruta": _pct_delta(cur["ganancia_bruta"], prev["ganancia_bruta"]),
            "ingresos": _pct_delta(cur["ingresos"], prev["ingresos"]),
            "margen_pct": round(cur["margen_pct"] - prev["margen_pct"], 1),
            "gastos": _pct_delta(cur["gastos"], prev["gastos"]),
        },
        "ticket_promedio": _money(ticket),
        "ordenes_cobradas": n_ord,
        "cxc_total": _money(cxc_monto),
        "cxc_count": cxc_n,
        "reporte": reporte,
    }


# ═══════════════════ 2. Aging cuentas por cobrar ═══════════════════

def _aging_bloque(db, taller_id):
    rows = db.execute(text("""
        SELECT cliente_nombre, pendiente, fecha_venta_dt,
               (CURRENT_DATE - fecha_venta_dt) AS dias
        FROM creditos
        WHERE taller_id=:t AND pendiente > 0 AND fecha_venta_dt IS NOT NULL
        ORDER BY fecha_venta_dt ASC
    """), {"t": taller_id}).fetchall()

    buckets = {"0-30": 0.0, "31-60": 0.0, "61-90": 0.0, "90+": 0.0}
    counts = {"0-30": 0, "31-60": 0, "61-90": 0, "90+": 0}
    detalle = []
    for r in rows:
        pend = float(r[1] or 0)
        dias = int(r[3] or 0)
        if dias <= 30:
            k = "0-30"
        elif dias <= 60:
            k = "31-60"
        elif dias <= 90:
            k = "61-90"
        else:
            k = "90+"
        buckets[k] += pend
        counts[k] += 1
        detalle.append({
            "cliente": r[0],
            "saldo": _money(pend),
            "dias": dias,
            "bucket": k,
            "fecha": str(r[2]),
        })

    total = sum(buckets.values())
    mora = buckets["31-60"] + buckets["61-90"] + buckets["90+"]
    dias_prom = 0.0
    if detalle:
        dias_prom = sum(d["dias"] for d in detalle) / len(detalle)

    reporte = (
        f"Tienes S/{total:,.0f} por cobrar en {len(detalle)} créditos. "
        f"De ese monto, S/{mora:,.0f} ({(mora/total*100 if total else 0):.0f}%) tiene más de 30 días. "
        f"Los más críticos (+90 días): S/{buckets['90+']:,.0f} en {counts['90+']} casos — "
        f"contactar de inmediato. Días promedio de antigüedad: {dias_prom:.0f}."
    )

    return {
        "buckets": {k: _money(v) for k, v in buckets.items()},
        "counts": counts,
        "detalle": detalle[:50],
        "total": _money(total),
        "dias_promedio": round(dias_prom, 0),
        "reporte": reporte,
    }


# ═══════════════════ 3. Flujo de caja proyectado 30 días ═══════════════════

def _cashflow_bloque(db, taller_id):
    hoy = _date.today()
    futuro = hoy + timedelta(days=30)

    # CxC esperado: asumir cobro de 25% del pendiente en los próximos 30 días (histórico típico).
    cxc = db.execute(text("""
        SELECT COALESCE(SUM(pendiente), 0) FROM creditos WHERE taller_id=:t AND pendiente > 0
    """), {"t": taller_id}).scalar() or 0
    cobros_esperados = float(cxc) * 0.25  # heurística conservadora

    # Nómina proyectada: sueldos del mes de trabajadores activos (periodicidad mensual).
    nomina_q = db.execute(text("""
        SELECT COALESCE(SUM(salario), 0), COUNT(*)
        FROM trabajadores
        WHERE taller_id=:t AND activo = true
    """), {"t": taller_id}).fetchone()
    nomina_proyectada = float(nomina_q[0] or 0)
    n_trab = int(nomina_q[1] or 0)

    # Gastos recurrentes: promedio últimos 3 meses
    g3 = db.execute(text("""
        SELECT COALESCE(SUM(costo_total), 0)
        FROM gastos_operacionales
        WHERE taller_id=:t AND fecha >= :d
    """), {"t": taller_id, "d": hoy - timedelta(days=90)}).scalar() or 0
    gastos_proyectados = float(g3) / 3  # promedio mensual

    total_cobros = cobros_esperados
    total_gastos = nomina_proyectada + gastos_proyectados
    flujo_neto = total_cobros - total_gastos

    reporte = (
        f"Proyección conservadora para los próximos 30 días: cobros esperados "
        f"S/{total_cobros:,.0f} (25% de tu CxC de S/{float(cxc):,.0f}), "
        f"gastos proyectados S/{total_gastos:,.0f} "
        f"(nómina S/{nomina_proyectada:,.0f} para {n_trab} trabajadores + "
        f"gastos recurrentes S/{gastos_proyectados:,.0f}). "
        f"Flujo neto proyectado: S/{flujo_neto:,.0f}. "
        + ("⚠️ Alerta: flujo negativo, revisar cobranzas." if flujo_neto < 0 else "✔ Flujo positivo.")
    )

    return {
        "cobros_esperados": _money(total_cobros),
        "cxc_total": _money(cxc),
        "nomina_proyectada": _money(nomina_proyectada),
        "trabajadores_activos": n_trab,
        "gastos_proyectados": _money(gastos_proyectados),
        "total_gastos": _money(total_gastos),
        "flujo_neto": _money(flujo_neto),
        "hasta": str(futuro),
        "reporte": reporte,
    }


# ═══════════════════ 4. Ingresos vs Gastos últimos 6 meses ═══════════════════

def _ingresos_gastos_6m(db, taller_id):
    hoy = _date.today()
    meses = []
    for i in range(5, -1, -1):
        y = hoy.year
        m = hoy.month - i
        while m <= 0:
            m += 12
            y -= 1
        ini = _date(y, m, 1)
        if m == 12:
            fin = _date(y + 1, 1, 1) - timedelta(days=1)
        else:
            fin = _date(y, m + 1, 1) - timedelta(days=1)
        if fin > hoy:
            fin = hoy
        p = _ganancia_periodo(db, taller_id, ini, fin)
        meses.append({
            "mes": f"{y}-{m:02d}",
            "label": ini.strftime("%b %Y"),
            "mo": p["mo"],
            "repuestos": p["rep_venta"],
            "notas_venta": p["nv"],
            "ingresos": p["ingresos"],
            "gastos": p["gastos"] + p["nomina"],
            "ganancia_neta": p["ganancia_neta"],
        })

    if not meses:
        return {"meses": [], "reporte": "Sin datos para los últimos 6 meses."}

    mejor = max(meses, key=lambda m: m["ganancia_neta"])
    peor = min(meses, key=lambda m: m["ganancia_neta"])
    prom = sum(m["ganancia_neta"] for m in meses) / len(meses)

    reporte = (
        f"Últimos 6 meses: mejor mes {mejor['label']} con S/{mejor['ganancia_neta']:,.0f} de ganancia neta, "
        f"peor {peor['label']} con S/{peor['ganancia_neta']:,.0f}. "
        f"Promedio mensual: S/{prom:,.0f}. "
        f"Este mes ({meses[-1]['label']}) vas en S/{meses[-1]['ganancia_neta']:,.0f}."
    )
    return {"meses": meses, "promedio_neta": _money(prom), "reporte": reporte}


# ═══════════════════ 5. Top clientes del mes ═══════════════════

def _top_clientes(db, taller_id):
    hoy = _date.today()
    ini_mes = hoy.replace(day=1)

    rows = db.execute(text("""
        SELECT cli, SUM(monto) AS total, COUNT(*) AS n
        FROM (
            SELECT COALESCE(c.nombre || ' ' || COALESCE(c.apellidos,''), 'Sin cliente') AS cli,
                   COALESCE(o.monto_cobrado, 0) AS monto
            FROM ordenes o
            LEFT JOIN clientes c ON c.id::text = o.cliente_id AND c.taller_id = o.taller_id
            WHERE o.taller_id=:t AND o.fecha_dt::date BETWEEN :ini AND :fin
              AND COALESCE(o.monto_cobrado,0) > 0
            UNION ALL
            SELECT COALESCE(cliente_nombre, 'Cliente general'), COALESCE(monto_pagado, total, 0)
            FROM notas_venta WHERE taller_id=:t AND fecha::date BETWEEN :ini AND :fin
        ) s
        GROUP BY cli
        ORDER BY total DESC
        LIMIT 10
    """), {"t": taller_id, "ini": ini_mes, "fin": hoy}).fetchall()

    tops = [{"cliente": r[0].strip(), "total": _money(r[1]), "ordenes": int(r[2])} for r in rows]
    total = sum(t["total"] for t in tops)
    top3 = sum(t["total"] for t in tops[:3])

    if not tops:
        reporte = "Sin clientes registrados este mes."
    else:
        concentracion = (top3 / total * 100) if total > 0 else 0
        reporte = (
            f"Tu top 10 generó S/{total:,.0f} este mes. "
            f"El cliente #1 ({tops[0]['cliente'][:30]}) aporta S/{tops[0]['total']:,.0f}. "
            f"Los 3 primeros concentran el {concentracion:.0f}% del total — "
            + ("alto riesgo de dependencia." if concentracion > 50 else "cartera razonablemente diversificada.")
        )

    return {"clientes": tops, "total": _money(total), "reporte": reporte}


# ═══════════════════ 6. Rendimiento por técnico ═══════════════════

def _rendimiento_tecnicos(db, taller_id):
    hoy = _date.today()
    ini_mes = hoy.replace(day=1)

    rows = db.execute(text("""
        SELECT COALESCE(NULLIF(tecnico,''), '(sin asignar)') AS tec,
               COUNT(*) AS ordenes,
               COUNT(*) FILTER (WHERE estado='ARCHIVADO') AS completadas,
               COALESCE(SUM(monto_cobrado), 0) AS ingresos
        FROM ordenes
        WHERE taller_id=:t AND fecha_dt::date BETWEEN :ini AND :fin
        GROUP BY tec
        ORDER BY ingresos DESC
    """), {"t": taller_id, "ini": ini_mes, "fin": hoy}).fetchall()

    tecs = [{
        "tecnico": r[0],
        "ordenes": int(r[1]),
        "completadas": int(r[2]),
        "ingresos": _money(r[3]),
        "tasa_cierre": round(int(r[2]) / int(r[1]) * 100, 0) if r[1] else 0,
    } for r in rows]

    if not tecs:
        reporte = "Sin actividad de técnicos este mes."
    else:
        top = tecs[0]
        total_ord = sum(t["ordenes"] for t in tecs)
        reporte = (
            f"{len(tecs)} técnicos con actividad este mes ({total_ord} órdenes). "
            f"Top: {top['tecnico']} con {top['ordenes']} órdenes y S/{top['ingresos']:,.0f} en ingresos "
            f"({top['tasa_cierre']:.0f}% de cierre). "
            + ("Revisa asignaciones: un técnico concentra >50% de la carga."
               if top['ordenes'] / total_ord > 0.5 else "Carga distribuida razonablemente.")
        )

    return {"tecnicos": tecs, "reporte": reporte}


# ═══════════════════ 7. Top repuestos vendidos ═══════════════════

def _top_repuestos(db, taller_id):
    hoy = _date.today()
    ini_mes = hoy.replace(day=1)

    # Órdenes + notas de venta del mes (unificado como fuente de items vendidos)
    rows = db.execute(text("""
        SELECT items_cotizacion::text FROM ordenes
        WHERE taller_id=:t AND fecha_dt::date BETWEEN :ini AND :fin
          AND items_cotizacion IS NOT NULL
        UNION ALL
        SELECT items::text FROM notas_venta
        WHERE taller_id=:t AND fecha::date BETWEEN :ini AND :fin
          AND items IS NOT NULL
    """), {"t": taller_id, "ini": ini_mes, "fin": hoy}).fetchall()

    # Acumula por código/nombre de repuesto
    acc = {}
    for (raw,) in rows:
        items = _parse_items(raw)
        for it in items:
            cat = it.get("categoria") or ""
            if not _is_rep(cat):
                continue
            key = (it.get("referencia") or it.get("nombre") or "Sin nombre").strip() or "Sin nombre"
            cantidad = float(it.get("cantidad") or 0)
            tot = float(it.get("total") or 0)
            precio = float(it.get("precio_unitario") or it.get("precio") or 0)
            costo = _cost_lookup(db, taller_id, it.get("referencia"), precio)
            if key not in acc:
                acc[key] = {
                    "nombre": it.get("nombre") or key,
                    "codigo": it.get("referencia") or "",
                    "cantidad": 0.0,
                    "ingresos": 0.0,
                    "costo": 0.0,
                }
            acc[key]["cantidad"] += cantidad
            acc[key]["ingresos"] += tot
            acc[key]["costo"] += costo * cantidad

    items_list = []
    for v in acc.values():
        margen = v["ingresos"] - v["costo"]
        mg_pct = (margen / v["ingresos"] * 100) if v["ingresos"] > 0 else 0
        items_list.append({
            "nombre": v["nombre"][:40],
            "codigo": v["codigo"],
            "cantidad": round(v["cantidad"], 0),
            "ingresos": _money(v["ingresos"]),
            "margen": _money(margen),
            "margen_pct": round(mg_pct, 1),
        })
    items_list.sort(key=lambda x: x["ingresos"], reverse=True)
    top = items_list[:10]

    if not top:
        reporte = "Sin repuestos vendidos este mes."
    else:
        top_item = top[0]
        total_ing = sum(t["ingresos"] for t in top)
        reporte = (
            f"Top repuesto: {top_item['nombre']} — {int(top_item['cantidad'])} unidades, "
            f"S/{top_item['ingresos']:,.0f} ({top_item['margen_pct']:.0f}% de margen). "
            f"Los 10 primeros generaron S/{total_ing:,.0f} en ingresos. "
            "Prioriza stock de los primeros; revisa precios de los de bajo margen."
        )

    return {"repuestos": top, "reporte": reporte}


# ═══════════════════ 8. Distribución por método de pago ═══════════════════

def _metodos_pago(db, taller_id):
    hoy = _date.today()
    ini_mes = hoy.replace(day=1)

    rows = db.execute(text("""
        SELECT CASE WHEN metodo IN ('Yape','Plin') THEN 'Yape' ELSE metodo END AS metodo,
               SUM(monto) AS total
        FROM (
            SELECT COALESCE(NULLIF(TRIM(metodo_pago),''), 'Efectivo') AS metodo,
                   COALESCE(monto_cobrado,0) AS monto
            FROM ordenes WHERE taller_id=:t AND fecha_dt::date BETWEEN :ini AND :fin
            UNION ALL
            SELECT COALESCE(NULLIF(TRIM(metodo_pago),''), 'Efectivo'),
                   COALESCE(monto_pagado, 0)
            FROM notas_venta WHERE taller_id=:t AND fecha::date BETWEEN :ini AND :fin
            UNION ALL
            SELECT COALESCE(NULLIF(TRIM(metodo_pago),''), 'Efectivo'),
                   COALESCE(monto,0)
            FROM abonos_credito WHERE taller_id=:t AND fecha_dt BETWEEN :ini AND :fin
        ) s
        WHERE monto > 0
        GROUP BY 1
        ORDER BY total DESC
    """), {"t": taller_id, "ini": ini_mes, "fin": hoy}).fetchall()

    total = sum(float(r[1] or 0) for r in rows)
    dist = []
    for r in rows:
        m = float(r[1] or 0)
        dist.append({
            "metodo": r[0],
            "monto": _money(m),
            "pct": round(m / total * 100, 1) if total > 0 else 0,
        })

    if not dist:
        reporte = "Sin movimientos este mes."
    else:
        top = dist[0]
        efectivo = next((d["pct"] for d in dist if d["metodo"] == "Efectivo"), 0)
        reporte = (
            f"Este mes cobraste S/{total:,.0f} distribuido en {len(dist)} métodos. "
            f"Principal: {top['metodo']} con {top['pct']:.0f}%. "
            + (f"⚠ Alta concentración en Efectivo ({efectivo:.0f}%) — riesgo de robo/pérdida."
               if efectivo > 60 else "Mezcla saludable de medios de pago.")
        )

    return {"distribucion": dist, "total": _money(total), "reporte": reporte}


# ═══════════════════ 9. Panel de alertas operativas ═══════════════════

def _alertas_bloque(db, taller_id):
    alerts = []

    # Órdenes vencidas (>7 días sin archivar)
    venc = db.execute(text("""
        SELECT COUNT(*) FROM ordenes
        WHERE taller_id=:t AND estado NOT IN ('ARCHIVADO','ENTREGADO')
          AND fecha_dt < NOW() - INTERVAL '7 days'
    """), {"t": taller_id}).scalar() or 0
    if venc > 0:
        alerts.append({
            "tipo": "ordenes_vencidas",
            "severidad": "warn",
            "icon": "schedule",
            "mensaje": f"{int(venc)} órdenes con más de 7 días sin archivar",
            "count": int(venc),
        })

    # Créditos morosos +60 días
    mor = db.execute(text("""
        SELECT COUNT(*), COALESCE(SUM(pendiente),0)
        FROM creditos WHERE taller_id=:t AND pendiente > 0
          AND fecha_venta_dt < CURRENT_DATE - INTERVAL '60 days'
    """), {"t": taller_id}).fetchone()
    if int(mor[0] or 0) > 0:
        alerts.append({
            "tipo": "creditos_morosos",
            "severidad": "danger",
            "icon": "account_balance_wallet",
            "mensaje": f"{int(mor[0])} créditos +60 días · S/{float(mor[1]):,.0f} en riesgo",
            "count": int(mor[0]),
            "monto": _money(mor[1]),
        })

    # Stock bajo
    sb = db.execute(text("""
        SELECT COUNT(*) FROM inventario
        WHERE taller_id=:t AND COALESCE(stock,0) <= COALESCE(stock_minimo,0)
          AND COALESCE(stock_minimo,0) > 0
    """), {"t": taller_id}).scalar() or 0
    if sb > 0:
        alerts.append({
            "tipo": "stock_bajo",
            "severidad": "warn",
            "icon": "inventory_2",
            "mensaje": f"{int(sb)} productos bajo stock mínimo",
            "count": int(sb),
        })

    # Caja sin cerrar (días anteriores con ingresos pero sin cierre)
    cj = db.execute(text("""
        SELECT COUNT(*) FROM cierres_caja
        WHERE taller_id=:t AND estado='abierto' AND fecha::date < CURRENT_DATE
    """), {"t": taller_id}).scalar() or 0
    if cj > 0:
        alerts.append({
            "tipo": "caja_sin_cerrar",
            "severidad": "warn",
            "icon": "lock_open",
            "mensaje": f"{int(cj)} cajas de días anteriores sin cerrar",
            "count": int(cj),
        })

    # Nómina pendiente (trabajador sin pago en su periodo)
    nom = db.execute(text("""
        SELECT COUNT(*) FROM trabajadores t
        WHERE t.taller_id=:t AND t.activo = true
          AND NOT EXISTS (
              SELECT 1 FROM pagos_trabajadores p
              WHERE p.trabajador_id = t.id
                AND p.fecha >= CURRENT_DATE - INTERVAL '30 days'
          )
    """), {"t": taller_id}).scalar() or 0
    if nom > 0:
        alerts.append({
            "tipo": "nomina_pendiente",
            "severidad": "info",
            "icon": "groups",
            "mensaje": f"{int(nom)} trabajadores sin pago en los últimos 30 días",
            "count": int(nom),
        })

    reporte = (
        f"{len(alerts)} alertas activas." if alerts
        else "✔ Sin alertas operativas. Todo bajo control."
    )
    return {"alertas": alerts, "reporte": reporte}


# ═══════════════════ 10. Funnel de fases ═══════════════════

def _funnel_fases(db, taller_id):
    rows = db.execute(text("""
        SELECT UPPER(COALESCE(estado,'SIN ESTADO')) AS estado, COUNT(*) AS n
        FROM ordenes
        WHERE taller_id=:t AND fecha_dt > NOW() - INTERVAL '90 days'
        GROUP BY estado
    """), {"t": taller_id}).fetchall()

    # Orden canónico del funnel
    orden_fases = ["RECEPCIÓN", "RECEPCION", "DIAGNÓSTICO", "DIAGNOSTICO",
                   "REPARACIÓN", "REPARACION", "CALIDAD", "ENTREGA", "ARCHIVADO"]
    fases = {r[0]: int(r[1]) for r in rows}
    canon = []
    for f in orden_fases:
        if f in fases:
            canon.append({"fase": f, "count": fases[f]})
    # otros estados no canónicos
    for k, v in fases.items():
        if k not in orden_fases:
            canon.append({"fase": k, "count": v})

    total = sum(f["count"] for f in canon)
    for f in canon:
        f["pct"] = round(f["count"] / total * 100, 1) if total else 0

    activas = sum(f["count"] for f in canon if f["fase"] not in ("ARCHIVADO",))
    archivadas = sum(f["count"] for f in canon if f["fase"] == "ARCHIVADO")
    reporte = (
        f"{total} órdenes en últimos 90 días: {activas} activas en taller, "
        f"{archivadas} archivadas ({(archivadas/total*100 if total else 0):.0f}% de cierre). "
        + (f"Cuello de botella: {max(canon, key=lambda x: x['count'])['fase']}." if canon else "")
    )
    return {"fases": canon, "total": total, "reporte": reporte}


# ═══════════════════ 11. Tendencia 12 meses + proyección ═══════════════════

def _tendencia_12m(db, taller_id):
    hoy = _date.today()
    puntos = []
    for i in range(11, -1, -1):
        y = hoy.year
        m = hoy.month - i
        while m <= 0:
            m += 12
            y -= 1
        ini = _date(y, m, 1)
        if m == 12:
            fin = _date(y + 1, 1, 1) - timedelta(days=1)
        else:
            fin = _date(y, m + 1, 1) - timedelta(days=1)
        if fin > hoy:
            fin = hoy
        p = _ganancia_periodo(db, taller_id, ini, fin)
        puntos.append({
            "mes": f"{y}-{m:02d}",
            "label": ini.strftime("%b %y"),
            "ganancia_neta": p["ganancia_neta"],
            "ingresos": p["ingresos"],
        })

    # Regresión lineal simple sobre últimos 6 meses para proyectar 3 meses adelante
    vals = [p["ganancia_neta"] for p in puntos[-6:]]
    proyeccion = []
    if len(vals) >= 3:
        n = len(vals)
        xs = list(range(n))
        x_mean = sum(xs) / n
        y_mean = sum(vals) / n
        num = sum((xs[i] - x_mean) * (vals[i] - y_mean) for i in range(n))
        den = sum((xs[i] - x_mean) ** 2 for i in range(n))
        slope = num / den if den > 0 else 0
        intercept = y_mean - slope * x_mean
        for k in range(1, 4):
            proyeccion.append({
                "mes_offset": k,
                "proyectado": _money(intercept + slope * (n - 1 + k)),
            })
    # Calcular YoY
    yoy = None
    if len(puntos) >= 12:
        yoy = _pct_delta(puntos[-1]["ganancia_neta"], puntos[-12]["ganancia_neta"])

    reporte = (
        f"Últimos 12 meses: {sum(1 for p in puntos if p['ganancia_neta']>0)} con ganancia positiva. "
        + (f"Crecimiento YoY: {yoy:+.1f}% vs mismo mes año anterior. " if yoy is not None else "")
        + (f"Proyección próximos 3 meses: S/{proyeccion[0]['proyectado']:,.0f}, "
           f"S/{proyeccion[1]['proyectado']:,.0f}, S/{proyeccion[2]['proyectado']:,.0f} "
           "(regresión lineal sobre últimos 6 meses)." if proyeccion else "")
    )
    return {"puntos": puntos, "proyeccion": proyeccion, "yoy_pct": yoy, "reporte": reporte}


# ═══════════════════ 12. Margen por categoría ═══════════════════

def _margen_categorias(db, taller_id):
    hoy = _date.today()
    ini = hoy.replace(day=1)
    p = _ganancia_periodo(db, taller_id, ini, hoy)

    cats = [
        {
            "categoria": "Mano de obra",
            "ingresos": p["mo"],
            "costo": 0.0,
            "margen": p["mo"],
            "margen_pct": 100.0 if p["mo"] > 0 else 0,
        },
        {
            "categoria": "Repuestos",
            "ingresos": p["rep_venta"],
            "costo": p["rep_costo"],
            "margen": p["rep_ganancia"],
            "margen_pct": round(p["rep_ganancia"] / p["rep_venta"] * 100, 1) if p["rep_venta"] > 0 else 0,
        },
        {
            "categoria": "Notas de Venta",
            "ingresos": p["nv"],
            "costo": 0.0,
            "margen": p["nv"],
            "margen_pct": 100.0 if p["nv"] > 0 else 0,
        },
    ]
    total_ing = sum(c["ingresos"] for c in cats)
    for c in cats:
        c["share_pct"] = round(c["ingresos"] / total_ing * 100, 1) if total_ing else 0

    # La categoría con más margen absoluto
    cats_sorted = sorted(cats, key=lambda x: x["margen"], reverse=True)
    top = cats_sorted[0] if cats_sorted else None
    reporte = (
        f"Ingresos del mes S/{total_ing:,.0f}: "
        f"MO {cats[0]['share_pct']:.0f}%, Repuestos {cats[1]['share_pct']:.0f}%, NV {cats[2]['share_pct']:.0f}%. "
        + (f"Mayor margen absoluto: {top['categoria']} (S/{top['margen']:,.0f}). "
           f"Margen de repuestos: {cats[1]['margen_pct']:.0f}%." if top else "")
    )
    return {"categorias": cats, "total_ingresos": _money(total_ing), "reporte": reporte}


# ═══════════════════ Endpoint consolidado ═══════════════════

@router.get("/api/dashboard/pro")
async def dashboard_pro(request: Request):
    """Endpoint consolidado del dashboard profesional.

    Devuelve 12 bloques sincronizados con el modelo contable.
    Rol: admin (expone cifras sensibles de margen).
    """
    tok = _auth(request)
    _require_admin(tok)
    taller_id = _tenant_id(tok)
    db = _get_db()
    try:
        return {
            "kpis": _kpis_bloque(db, taller_id),
            "aging": _aging_bloque(db, taller_id),
            "cashflow": _cashflow_bloque(db, taller_id),
            "ingresos_gastos_6m": _ingresos_gastos_6m(db, taller_id),
            "top_clientes": _top_clientes(db, taller_id),
            "rendimiento_tecnicos": _rendimiento_tecnicos(db, taller_id),
            "top_repuestos": _top_repuestos(db, taller_id),
            "metodos_pago": _metodos_pago(db, taller_id),
            "alertas": _alertas_bloque(db, taller_id),
            "funnel_fases": _funnel_fases(db, taller_id),
            "tendencia_12m": _tendencia_12m(db, taller_id),
            "margen_categorias": _margen_categorias(db, taller_id),
            "generado_en": datetime.now().isoformat(),
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(500, f"Error dashboard pro: {e}")
    finally:
        db.close()

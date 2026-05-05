"""
routers/dashboard.py — Dashboard admin (multi-tenant).

Refactor 2026-04-21: taller_id del JWT via _tenant_id (antes TALLER_ID global).
FASES_ORDEN permanece en este módulo (lo importa ordenes.py).
"""
from fastapi import Query
from routers._common import (
    router, ADMIN_HTML,
    _auth, _get_db, _require_admin, _require_staff, _safe_date,
    _img_to_url, _parse_json_field, _make_token, _tenant_id,
    os, json, datetime, timedelta, Path,
    Request, HTTPException, UploadFile, File, List, HTMLResponse, text,
)

# ══════════════════════════════════════════════════════════════════════════════
# ÓRDENES DE SERVICIO — fases canónicas (importado por ordenes.py)
# ══════════════════════════════════════════════════════════════════════════════
FASES_ORDEN = ["RECEPCIÓN", "DIAGNÓSTICO", "REPUESTOS", "APROBACIÓN",
               "REPARACIÓN", "CONTROL CALIDAD", "LISTO PARA ENTREGA", "ARCHIVADO"]


@router.get("/api/dashboard")
async def admin_dashboard(request: Request):
    tok = _auth(request)
    _require_staff(tok)
    t = _tenant_id(tok)
    db = _get_db()
    try:
        # Órdenes por fase
        fases = db.execute(text(
            "SELECT estado, COUNT(*) FROM ordenes WHERE taller_id=:t GROUP BY estado"
        ), {"t": t}).fetchall()
        fases_map = {r[0]: r[1] for r in fases}
        total_activas = sum(v for k, v in fases_map.items() if k != "ARCHIVADO")

        # Ingresos del mes: monto cobrado en TODAS las órdenes del mes (archivadas o parciales)
        # + total de notas de venta del mes + abonos a créditos del mes.
        ingresos_ord = db.execute(text("""
            SELECT COALESCE(SUM(monto_cobrado), 0) FROM ordenes
            WHERE taller_id=:t
              AND fecha_dt::date >= date_trunc('month', NOW())::date
        """), {"t": t}).fetchone()[0] or 0
        ingresos_nv = db.execute(text("""
            SELECT COALESCE(SUM(total), 0) FROM notas_venta
            WHERE taller_id=:t
              AND fecha::date >= date_trunc('month', NOW())::date
        """), {"t": t}).fetchone()[0] or 0
        ingresos_ab = db.execute(text("""
            SELECT COALESCE(SUM(monto), 0) FROM abonos_credito
            WHERE taller_id=:t
              AND fecha_dt::date >= date_trunc('month', NOW())::date
        """), {"t": t}).fetchone()[0] or 0
        ingresos_mes = float(ingresos_ord) + float(ingresos_nv) + float(ingresos_ab)

        # Pendiente de cobro
        pendiente = db.execute(text("""
            SELECT COALESCE(SUM(orden_total(items_cotizacion)::float - monto_cobrado), 0)
            FROM ordenes WHERE taller_id=:t AND estado != 'ARCHIVADO'
            AND items_cotizacion IS NOT NULL AND items_cotizacion::text != 'null'
        """), {"t": t}).fetchone()[0] or 0

        # Citas de hoy
        from datetime import date
        hoy = date.today().strftime("%Y-%m-%d")
        citas_hoy = db.execute(text(
            "SELECT COUNT(*) FROM citas WHERE taller_id=:t AND fecha_cita=:h AND estado!='cancelada'"
        ), {"t": t, "h": hoy}).fetchone()[0] or 0

        # Stock bajo
        stock_bajo = db.execute(text(
            "SELECT COUNT(*) FROM inventario WHERE taller_id=:t AND stock <= stock_minimo AND stock_minimo > 0"
        ), {"t": t}).fetchone()[0] or 0

        # Órdenes recientes (últimas 8)
        recientes_rows = db.execute(text("""
            SELECT o.consecutivo, o.cliente_id, c.nombre, c.apellidos, o.vehiculo_placa,
                   o.estado, o.monto_cobrado, o.fecha, o.tecnico,
                   CASE WHEN o.items_cotizacion IS NOT NULL AND o.items_cotizacion::text != 'null'
                        THEN orden_total(o.items_cotizacion)::float ELSE 0 END as total
            FROM ordenes o
            LEFT JOIN clientes c ON c.id = o.cliente_id
            WHERE o.taller_id=:t
            ORDER BY o.consecutivo DESC LIMIT 8
        """), {"t": t}).fetchall()

        recientes = []
        for r in recientes_rows:
            total = r[9] or 0
            cobrado = r[6] or 0
            if cobrado >= total and total > 0: pago_estado = "PAGADO"
            elif cobrado > 0: pago_estado = "PARCIAL"
            else: pago_estado = "PENDIENTE"
            recientes.append({
                "consecutivo": r[0],
                "cliente": f"{r[2] or ''} {r[3] or ''}".strip()[:28],
                "placa": r[4],
                "estado": r[5],
                "pago_estado": pago_estado,
                "cobrado": cobrado,
                "total": total,
                "fecha": _safe_date(r[7]),
                "tecnico": r[8],
            })

        # Alertas
        alertas = []
        if stock_bajo > 0:
            items_bajo = db.execute(text(
                "SELECT nombre, stock, stock_minimo FROM inventario "
                "WHERE taller_id=:t AND stock <= stock_minimo AND stock_minimo > 0 LIMIT 5"
            ), {"t": t}).fetchall()
            for i in items_bajo:
                alertas.append({"tipo": "stock", "msg": f"Stock bajo: {i[0]} — quedan {i[1]} unidades", "sev": "warning"})

        aprobacion_pend = db.execute(text(
            "SELECT consecutivo FROM ordenes WHERE taller_id=:t AND estado='APROBACION' LIMIT 3"
        ), {"t": t}).fetchall()
        for a in aprobacion_pend:
            alertas.append({"tipo": "aprobacion", "msg": f"{a[0]} — esperando aprobación del cliente", "sev": "info"})

        # Ingresos últimos 7 días (por día)
        from datetime import timedelta
        semana_rows = db.execute(text("""
            SELECT
                fecha_dt::date AS dia,
                COALESCE(SUM(monto_cobrado), 0) AS total
            FROM ordenes
            WHERE taller_id=:t
            AND fecha_dt::date >= CURRENT_DATE - INTERVAL '6 days'
            GROUP BY dia ORDER BY dia
        """), {"t": t}).fetchall()

        # Construir array de 7 dias (rellenando 0 si no hay datos)
        dias_map = {str(r[0]): float(r[1]) for r in semana_rows}
        dias_semana = ['Lun','Mar','Mié','Jue','Vie','Sáb','Dom']
        ingresos_semana = []
        for i in range(7):
            d = date.today() - timedelta(days=6-i)
            ingresos_semana.append({
                "dia": dias_semana[d.weekday()],
                "fecha": str(d),
                "total": dias_map.get(str(d), 0.0)
            })

        # Caja hoy: cobrado en órdenes del día + notas de venta del día + abonos de créditos del día
        caja_ord = db.execute(text(
            "SELECT COALESCE(SUM(monto_cobrado), 0) FROM ordenes "
            "WHERE taller_id=:t AND fecha_dt::date = CURRENT_DATE"
        ), {"t": t}).fetchone()[0] or 0
        caja_nv = db.execute(text(
            "SELECT COALESCE(SUM(total), 0) FROM notas_venta "
            "WHERE taller_id=:t AND fecha::date = CURRENT_DATE"
        ), {"t": t}).fetchone()[0] or 0
        caja_ab = db.execute(text(
            "SELECT COALESCE(SUM(monto), 0) FROM abonos_credito "
            "WHERE taller_id=:t AND fecha_dt::date = CURRENT_DATE"
        ), {"t": t}).fetchone()[0] or 0
        caja_hoy = float(caja_ord) + float(caja_nv) + float(caja_ab)

        return {
            "fases": fases_map,
            "total_activas": total_activas,
            "ingresos_mes": round(float(ingresos_mes), 2),
            "ingresos_semana": ingresos_semana,
            "pendiente_cobro": round(float(max(pendiente, 0)), 2),
            "citas_hoy": int(citas_hoy),
            "caja_hoy": round(float(caja_hoy), 2),
            "stock_bajo": int(stock_bajo),
            "recientes": recientes,
            "alertas": alertas,
        }
    finally:
        db.close()


@router.get("/api/dashboard/stats")
async def dashboard_stats(request: Request):
    tok = _auth(request)
    _require_staff(tok)
    t = _tenant_id(tok)
    db = _get_db()
    try:
        dc = "fecha_dt::date"
        # Orders per fase (active)
        fases_r = db.execute(text(
            "SELECT estado, COUNT(*) FROM ordenes WHERE taller_id=:t AND estado!='ARCHIVADO' GROUP BY estado"
        ), {"t": t}).fetchall()
        fases = {r[0]: int(r[1]) for r in fases_r}
        # Revenue this month: órdenes (cualquier estado) + notas de venta + abonos de créditos
        rev_ord = db.execute(text(
            f"SELECT COALESCE(SUM(monto_cobrado),0) FROM ordenes WHERE taller_id=:t AND {dc} >= date_trunc('month',NOW())"
        ), {"t": t}).fetchone()[0] or 0
        rev_nv = db.execute(text(
            "SELECT COALESCE(SUM(total),0) FROM notas_venta WHERE taller_id=:t AND fecha::date >= date_trunc('month',NOW())::date"
        ), {"t": t}).fetchone()[0] or 0
        rev_ab = db.execute(text(
            "SELECT COALESCE(SUM(monto),0) FROM abonos_credito WHERE taller_id=:t AND fecha_dt::date >= date_trunc('month',NOW())::date"
        ), {"t": t}).fetchone()[0] or 0
        rev_mes = float(rev_ord) + float(rev_nv) + float(rev_ab)
        # Orders this month
        ord_mes = db.execute(text(
            f"SELECT COUNT(*) FROM ordenes WHERE taller_id=:t AND {dc} >= date_trunc('month',NOW())"
        ), {"t": t}).fetchone()[0]
        # Completed this month
        completadas = db.execute(text(
            f"SELECT COUNT(*) FROM ordenes WHERE taller_id=:t AND estado='ARCHIVADO' AND {dc} >= date_trunc('month',NOW())"
        ), {"t": t}).fetchone()[0]
        # Total clients
        total_cli = db.execute(text(
            "SELECT COUNT(*) FROM clientes WHERE taller_id=:t"
        ), {"t": t}).fetchone()[0]
        # Weekly revenue last 8 weeks — incluye ordenes ARCHIVADO + notas_venta, rellena semanas vacías con 0.
        weekly_r = db.execute(text(f"""
            WITH weeks AS (
                SELECT generate_series(
                    date_trunc('week', CURRENT_DATE - interval '7 weeks'),
                    date_trunc('week', CURRENT_DATE),
                    interval '1 week'
                )::date AS w
            ),
            ord_w AS (
                SELECT date_trunc('week', {dc})::date AS w, SUM(monto_cobrado) AS total
                FROM ordenes
                WHERE taller_id=:t AND estado='ARCHIVADO'
                  AND {dc} >= CURRENT_DATE - interval '8 weeks'
                GROUP BY 1
            ),
            nv_w AS (
                SELECT date_trunc('week', fecha::date)::date AS w, SUM(total) AS total
                FROM notas_venta
                WHERE taller_id=:t
                  AND fecha::date >= CURRENT_DATE - interval '8 weeks'
                GROUP BY 1
            )
            SELECT w.w, COALESCE(o.total,0) + COALESCE(n.total,0) AS total
            FROM weeks w
            LEFT JOIN ord_w o ON o.w = w.w
            LEFT JOIN nv_w  n ON n.w = w.w
            ORDER BY w.w
        """), {"t": t}).fetchall()
        weekly = [{"semana": str(r[0])[:10], "total": round(float(r[1] or 0), 2)} for r in weekly_r]
        # Recent orders
        recent_r = db.execute(text("""
            SELECT o.consecutivo, COALESCE(c.nombre||' '||COALESCE(c.apellidos,''),'Sin cliente') as cliente,
                   o.estado, o.monto_cobrado, COALESCE(v.marca||' '||v.modelo,'') as vehiculo, o.fecha,
                   o.vehiculo_placa
            FROM ordenes o
            LEFT JOIN clientes c ON c.id=o.cliente_id AND c.taller_id=o.taller_id
            LEFT JOIN vehiculos v ON v.placa=o.vehiculo_placa AND v.taller_id=o.taller_id
            WHERE o.taller_id=:t ORDER BY o.consecutivo DESC LIMIT 8
        """), {"t": t}).fetchall()
        recent = [{"consecutivo": r[0], "cliente": (r[1] or "").strip(), "estado": r[2],
                   "cobrado": float(r[3] or 0), "vehiculo": (r[4] or "").strip(),
                   "fecha": r[5], "placa": r[6]} for r in recent_r]
        # Revenue last 6 months — órdenes (todas) + notas_venta + abonos_credito
        monthly_r = db.execute(text(f"""
            WITH ord_m AS (
                SELECT date_trunc('month', {dc}) AS m, SUM(monto_cobrado) AS total
                FROM ordenes WHERE taller_id=:t AND {dc} >= NOW()-interval '6 months'
                GROUP BY 1
            ),
            nv_m AS (
                SELECT date_trunc('month', fecha::date) AS m, SUM(total) AS total
                FROM notas_venta WHERE taller_id=:t AND fecha::date >= (NOW()-interval '6 months')::date
                GROUP BY 1
            ),
            ab_m AS (
                SELECT date_trunc('month', fecha_dt::date) AS m, SUM(monto) AS total
                FROM abonos_credito WHERE taller_id=:t AND fecha_dt::date >= (NOW()-interval '6 months')::date
                GROUP BY 1
            )
            SELECT m, SUM(total) FROM (
                SELECT m, total FROM ord_m
                UNION ALL SELECT m, total FROM nv_m
                UNION ALL SELECT m, total FROM ab_m
            ) x GROUP BY m ORDER BY m
        """), {"t": t}).fetchall()
        monthly = [{"mes": str(r[0])[:7], "total": round(float(r[1] or 0), 2)} for r in monthly_r]
        # 2026-04-30 fix: cobros por fecha REAL del abono (pagos JSON), no fecha_dt de la orden
        # Si pagos JSON está vacío, fallback a fecha_dt para órdenes legacy con monto_cobrado>0.
        _CTE_PAGOS = """
        WITH pagos_jsonb AS (
          SELECT (p->>'fecha')::date AS dia, (p->>'monto')::numeric AS monto
          FROM ordenes o
          CROSS JOIN LATERAL json_array_elements(COALESCE(o.pagos, '[]'::json)) AS p
          WHERE o.taller_id = :t AND o.pagos IS NOT NULL
            AND COALESCE(json_array_length(o.pagos), 0) > 0
        ),
        pagos_legacy AS (
          SELECT o.fecha_dt::date AS dia, COALESCE(o.monto_cobrado, 0)::numeric AS monto
          FROM ordenes o
          WHERE o.taller_id = :t AND COALESCE(o.monto_cobrado, 0) > 0
            AND (o.pagos IS NULL OR COALESCE(json_array_length(o.pagos), 0) = 0)
        ),
        pagos_unif AS (SELECT * FROM pagos_jsonb UNION ALL SELECT * FROM pagos_legacy)
        """
        # Yesterday income (real cobros con fecha del abono)
        ayer_ord = db.execute(text(_CTE_PAGOS + " SELECT COALESCE(SUM(monto),0) FROM pagos_unif WHERE dia=CURRENT_DATE-1"), {"t": t}).fetchone()[0] or 0
        ayer_nv = db.execute(text(
            "SELECT COALESCE(SUM(total),0) FROM notas_venta WHERE taller_id=:t AND DATE(fecha)=CURRENT_DATE-1 AND COALESCE(estado,'ACTIVA') NOT IN ('ANULADA','CANCELADA')"
        ), {"t": t}).fetchone()[0] or 0
        ayer_ab = db.execute(text(
            "SELECT COALESCE(SUM(monto),0) FROM abonos_credito WHERE taller_id=:t AND fecha_dt::date=CURRENT_DATE-1"
        ), {"t": t}).fetchone()[0] or 0
        ayer_total = float(ayer_ord) + float(ayer_nv) + float(ayer_ab)
        # Órdenes "trabajadas ayer" = órdenes con cobro ayer (no creadas ayer)
        ayer_ord_n = db.execute(text(_CTE_PAGOS + " SELECT COUNT(DISTINCT 1) FROM pagos_unif WHERE dia=CURRENT_DATE-1 AND monto>0"), {"t": t}).fetchone()[0] or 0
        # Today income (mismo patrón)
        hoy_ord = db.execute(text(_CTE_PAGOS + " SELECT COALESCE(SUM(monto),0) FROM pagos_unif WHERE dia=CURRENT_DATE"), {"t": t}).fetchone()[0] or 0
        hoy_nv = db.execute(text(
            "SELECT COALESCE(SUM(total),0) FROM notas_venta WHERE taller_id=:t AND DATE(fecha)=CURRENT_DATE AND COALESCE(estado,'ACTIVA') NOT IN ('ANULADA','CANCELADA')"
        ), {"t": t}).fetchone()[0] or 0
        hoy_ab = db.execute(text(
            "SELECT COALESCE(SUM(monto),0) FROM abonos_credito WHERE taller_id=:t AND fecha_dt::date=CURRENT_DATE"
        ), {"t": t}).fetchone()[0] or 0
        hoy_total = float(hoy_ord) + float(hoy_nv) + float(hoy_ab)
        # Overdue orders (active > 7 days)
        vencidas = db.execute(text(
            f"SELECT COUNT(*) FROM ordenes WHERE taller_id=:t AND estado NOT IN ('ARCHIVADO','LISTO PARA ENTREGA') AND {dc} < CURRENT_DATE-7"
        ), {"t": t}).fetchone()[0]
        return {
            "ordenes_por_fase": fases,
            "ingresos_mes": round(float(rev_mes or 0), 2),
            "ordenes_mes": int(ord_mes or 0),
            "completadas_mes": int(completadas or 0),
            "total_clientes": int(total_cli or 0),
            "ingresos_semanales": weekly,
            "ingresos_mensuales": monthly,
            "ordenes_recientes": recent,
            "ayer_ingresos": ayer_total,
            "ayer_ordenes": int(ayer_ord_n),
            "hoy_ingresos": hoy_total,
            "ordenes_vencidas": int(vencidas),
        }
    except Exception as e:
        import traceback; traceback.print_exc()
        return {"error": str(e), "ordenes_por_fase": {}, "ingresos_mes": 0,
                "ordenes_mes": 0, "completadas_mes": 0, "total_clientes": 0,
                "ingresos_semanales": [], "ingresos_mensuales": [], "ordenes_recientes": []}
    finally:
        db.close()


@router.get("/api/historial")
async def historial_unificado(
    request: Request,
    dias: int = Query(30, ge=1, le=365),
    tipo: str = Query("todos", pattern="^(todos|venta|orden|abono|cierre)$"),
    limit: int = Query(500, ge=1, le=2000),
):
    """Historial unificado: notas de venta + órdenes archivadas + abonos de crédito + cierres de caja.
    Timeline ordenado por fecha desc. Cada evento lleva `tipo`, `fecha`, `descripcion`, `monto`, `referencia`, `cliente`.
    """
    tok = _auth(request)
    _require_staff(tok)
    t = _tenant_id(tok)
    db = _get_db()
    try:
        desde = (datetime.now() - timedelta(days=dias)).date()
        eventos = []

        if tipo in ("todos", "venta"):
            rows = db.execute(text("""
                SELECT nv.id, nv.numero, nv.fecha, nv.total, nv.metodo_pago,
                       COALESCE(c.nombre || ' ' || COALESCE(c.apellidos,''), nv.cliente_nombre, 'Cliente general') AS cli
                FROM notas_venta nv
                LEFT JOIN clientes c ON c.id::text = nv.cliente_id AND c.taller_id = nv.taller_id
                WHERE nv.taller_id=:t AND nv.fecha::date >= :d
                ORDER BY nv.fecha DESC, nv.id DESC
                LIMIT :lim
            """), {"t": t, "d": desde, "lim": limit}).fetchall()
            for r in rows:
                eventos.append({
                    "tipo": "venta",
                    "fecha": _safe_date(r[2]),
                    "descripcion": f"Nota de venta {r[1] or f'#{r[0]}'}",
                    "monto": float(r[3] or 0),
                    "referencia": str(r[1] or r[0]),
                    "cliente": (r[5] or "").strip() or "Cliente general",
                    "metodo_pago": r[4] or "-",
                    "id": r[0],
                })

        if tipo in ("todos", "orden"):
            # Desglose por abono individual (JSONB ordenes.pagos). Cada pago es un evento con su fecha real.
            rows = db.execute(text("""
                SELECT o.consecutivo, o.vehiculo_placa, o.estado,
                       COALESCE(c.nombre || ' ' || COALESCE(c.apellidos,''), 'Sin cliente') AS cli,
                       COALESCE(
                         NULLIF(SUBSTRING(p->>'fecha' FROM 1 FOR 10),'')::date,
                         NULLIF(SUBSTRING(o.fecha_cobro FROM 1 FOR 10),'')::date,
                         o.fecha_dt::date
                       ) AS f_pago,
                       COALESCE((p->>'monto')::float, 0) AS monto,
                       COALESCE(p->>'metodo', o.metodo_pago, 'Efectivo') AS metodo,
                       COALESCE(p->>'nota', '') AS nota,
                       idx
                FROM ordenes o
                LEFT JOIN clientes c ON c.id::text = o.cliente_id AND c.taller_id = o.taller_id
                LEFT JOIN LATERAL json_array_elements(COALESCE(o.pagos::jsonb, '[]'::jsonb)::json) WITH ORDINALITY AS t(p, idx) ON TRUE
                WHERE o.taller_id=:t
                  AND o.pagos IS NOT NULL
                  AND COALESCE((p->>'monto')::float, 0) > 0
                  AND COALESCE(
                        NULLIF(SUBSTRING(p->>'fecha' FROM 1 FOR 10),'')::date,
                        o.fecha_dt::date
                      ) >= :d
            """), {"t": t, "d": desde}).fetchall()
            for r in rows:
                nota_sfx = f" — {r[7]}" if r[7] else ""
                eventos.append({
                    "tipo": "orden",
                    "fecha": _safe_date(r[4]),
                    "descripcion": f"Abono Orden {r[0]} · {r[1] or 'sin placa'}{nota_sfx}",
                    "monto": float(r[5] or 0),
                    "referencia": r[0],
                    "cliente": (r[3] or "").strip() or "Sin cliente",
                    "estado": r[2],
                    "metodo_pago": r[6] or "-",
                    "id": f"{r[0]}#{r[8]}",
                })
            # Fallback: órdenes archivadas con monto_cobrado pero sin pagos[] (datos legacy).
            rows_legacy = db.execute(text("""
                SELECT o.consecutivo, o.vehiculo_placa, o.estado,
                       COALESCE(c.nombre || ' ' || COALESCE(c.apellidos,''), 'Sin cliente') AS cli,
                       COALESCE(
                         NULLIF(SUBSTRING(o.fecha_cobro FROM 1 FOR 10),'')::date,
                         o.fecha_dt::date
                       ) AS f_pago,
                       COALESCE(o.monto_cobrado, 0) AS monto,
                       COALESCE(o.metodo_pago, 'Efectivo') AS metodo
                FROM ordenes o
                LEFT JOIN clientes c ON c.id::text = o.cliente_id AND c.taller_id = o.taller_id
                WHERE o.taller_id=:t AND o.estado='ARCHIVADO'
                  AND o.fecha_dt::date >= :d
                  AND COALESCE(o.monto_cobrado, 0) > 0
                  AND (o.pagos IS NULL OR o.pagos::text IN ('null','[]','') OR json_array_length(o.pagos) = 0)
                ORDER BY o.fecha_dt DESC, o.consecutivo DESC
                LIMIT :lim
            """), {"t": t, "d": desde, "lim": limit}).fetchall()
            for r in rows_legacy:
                eventos.append({
                    "tipo": "orden",
                    "fecha": _safe_date(r[4]),
                    "descripcion": f"Orden {r[0]} · {r[1] or 'sin placa'}",
                    "monto": float(r[5] or 0),
                    "referencia": r[0],
                    "cliente": (r[3] or "").strip() or "Sin cliente",
                    "estado": r[2],
                    "metodo_pago": r[6] or "-",
                    "id": r[0],
                })

        if tipo in ("todos", "abono"):
            rows = db.execute(text("""
                SELECT ab.id, ab.credito_id, ab.fecha_dt, ab.monto, ab.nota, ab.metodo_pago,
                       COALESCE(cr.cliente_nombre, 'Cliente') AS cli
                FROM abonos_credito ab
                LEFT JOIN creditos cr ON cr.id = ab.credito_id AND cr.taller_id = ab.taller_id
                WHERE ab.taller_id=:t AND ab.fecha_dt::date >= :d
                ORDER BY ab.fecha_dt DESC, ab.id DESC
                LIMIT :lim
            """), {"t": t, "d": desde, "lim": limit}).fetchall()
            for r in rows:
                eventos.append({
                    "tipo": "abono",
                    "fecha": _safe_date(r[2]),
                    "descripcion": f"Abono a crédito #{r[1]}" + (f" — {r[4]}" if r[4] else ""),
                    "monto": float(r[3] or 0),
                    "referencia": r[1],
                    "cliente": (r[6] or "").strip() or "Cliente",
                    "metodo_pago": r[5] or "-",
                    "id": r[0],
                })

        if tipo in ("todos", "cierre"):
            rows = db.execute(text("""
                SELECT id, fecha, apertura_hora, cierre_hora,
                       total_efectivo, total_yape, total_transferencia, total_tarjeta,
                       total_notas, ganancia_neta,
                       saldo_apertura, usuario_cierre, notas_operador, estado
                FROM cierres_caja
                WHERE taller_id=:t AND fecha::date >= :d
                ORDER BY fecha DESC, id DESC
                LIMIT :lim
            """), {"t": t, "d": desde, "lim": limit}).fetchall()
            for r in rows:
                total_caja = float(r[4] or 0) + float(r[5] or 0) + float(r[6] or 0) + float(r[7] or 0) + float(r[8] or 0)
                eventos.append({
                    "tipo": "cierre",
                    "fecha": _safe_date(r[1]),
                    "descripcion": f"Cierre de caja · {r[11] or 'admin'}" + (f" — {r[12]}" if r[12] else ""),
                    "monto": total_caja,
                    "referencia": r[0],
                    "cliente": "—",
                    "saldo_apertura": float(r[10] or 0),
                    "ganancia_neta": float(r[9] or 0),
                    "estado": r[13],
                    "id": r[0],
                })

        eventos.sort(key=lambda e: (e["fecha"] or "", str(e["id"])), reverse=True)
        eventos = eventos[:limit]

        total_mov = sum(e["monto"] for e in eventos if e["tipo"] != "cierre")
        return {
            "eventos": eventos,
            "total": round(total_mov, 2),
            "count": len(eventos),
            "desde": str(desde),
            "hasta": str(datetime.now().date()),
        }
    except Exception as e:
        import traceback; traceback.print_exc()
        raise HTTPException(500, f"Error generando historial: {e}")
    finally:
        db.close()

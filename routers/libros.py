"""
routers/libros.py — Endpoints JWT para Libros Contables SANDOVAL PRO
=====================================================================
Todos los endpoints requieren JWT admin. Prefijo /admin/api/libros.

Endpoints:
  GET  /admin/api/libros/plan-cuentas
  GET  /admin/api/libros/diario?desde=&hasta=
  GET  /admin/api/libros/mayor?cuenta=&desde=&hasta=
  GET  /admin/api/libros/ventas?periodo=YYYYMM
  GET  /admin/api/libros/compras?periodo=YYYYMM
  GET  /admin/api/libros/caja-bancos?periodo=YYYYMM
  GET  /admin/api/libros/inventario?periodo=YYYYMM
  GET  /admin/api/libros/estado-resultados?periodo=YYYYMM
  GET  /admin/api/libros/balance?fecha=YYYY-MM-DD
  POST /admin/api/libros/asientos/manual
  POST /admin/api/libros/asientos/{id}/extornar
  GET  /admin/api/libros/{tipo}/pdf?...
  GET  /admin/api/libros/{tipo}/ple?...   (TXT PLE-SUNAT)
"""
from routers._common import (
    router, _auth, _get_db, _require_admin, _tenant_id,
    Request, HTTPException, text,
    os, json, datetime,
)
from fastapi import Query
from fastapi.responses import StreamingResponse, Response
import io
from datetime import date as _date


# ---------------------------------------------------------------------------
# Helpers locales
# ---------------------------------------------------------------------------

def _periodo_range(periodo: str):
    """'YYYYMM' → (date_desde, date_hasta)."""
    if not periodo or len(periodo) != 6:
        raise HTTPException(400, "periodo debe ser YYYYMM (ej: 202604)")
    try:
        year, month = int(periodo[:4]), int(periodo[4:])
        desde = _date(year, month, 1)
        # último día del mes
        if month == 12:
            hasta = _date(year + 1, 1, 1)
        else:
            hasta = _date(year, month + 1, 1)
        from datetime import timedelta
        hasta = hasta - timedelta(days=1)
        return desde, hasta
    except Exception:
        raise HTTPException(400, "periodo inválido")


def _setup_rls(db, taller_id: int):
    db.execute(text("SET app.taller_id = :t"), {"t": taller_id})


def _asiento_to_dict(row) -> dict:
    return {
        "id":        row[0],
        "numero":    row[1],
        "fecha":     str(row[2]),
        "glosa":     row[3],
        "tipo":      row[4],
        "origen":    row[5],
        "origen_id": row[6],
        "estado":    row[7],
        "usuario":   row[8],
        "debe":      float(row[9]  or 0),
        "haber":     float(row[10] or 0),
    }


# ---------------------------------------------------------------------------
# Plan de cuentas
# ---------------------------------------------------------------------------

@router.get("/api/libros/plan-cuentas")
async def get_plan_cuentas(request: Request):
    """Lista todas las cuentas del plan PCGE del taller."""
    tok = _auth(request)
    _require_admin(tok)
    taller_id = _tenant_id(tok)
    db = _get_db()
    try:
        _setup_rls(db, taller_id)
        rows = db.execute(text("""
            SELECT codigo, nombre, tipo, nivel, padre_codigo, activa, es_sistema
            FROM   plan_cuentas
            WHERE  taller_id=:t
            ORDER BY codigo
        """), {"t": taller_id}).fetchall()
        return [
            {
                "codigo":       r[0],
                "nombre":       r[1],
                "tipo":         r[2],
                "nivel":        r[3],
                "padre_codigo": r[4],
                "activa":       r[5],
                "es_sistema":   r[6],
            }
            for r in rows
        ]
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Libro Diario
# ---------------------------------------------------------------------------

@router.get("/api/libros/diario")
async def libro_diario(
    request: Request,
    desde: str = Query(None),
    hasta: str = Query(None),
):
    tok = _auth(request)
    _require_admin(tok)
    taller_id = _tenant_id(tok)

    today = _date.today()
    if not desde:
        desde = today.replace(day=1).isoformat()
    if not hasta:
        hasta = today.isoformat()

    db = _get_db()
    try:
        _setup_rls(db, taller_id)
        rows = db.execute(text("""
            SELECT a.id, a.numero, a.fecha, a.glosa, a.tipo, a.origen, a.origen_id,
                   a.estado, a.usuario,
                   SUM(l.debe)  AS total_debe,
                   SUM(l.haber) AS total_haber
            FROM   asientos_contables a
            JOIN   asiento_lineas l ON l.asiento_id = a.id
            WHERE  a.taller_id=:t
              AND  a.fecha BETWEEN :d AND :h
            GROUP BY a.id, a.numero, a.fecha, a.glosa, a.tipo, a.origen, a.origen_id,
                     a.estado, a.usuario
            ORDER BY a.fecha, a.numero
        """), {"t": taller_id, "d": desde, "h": hasta}).fetchall()

        asientos = []
        for row in rows:
            asiento = _asiento_to_dict(row)
            # obtener líneas
            lineas = db.execute(text("""
                SELECT cuenta_codigo, cuenta_nombre, debe, haber, glosa
                FROM   asiento_lineas
                WHERE  asiento_id=:aid ORDER BY orden
            """), {"aid": row[0]}).fetchall()
            asiento["lineas"] = [
                {
                    "cuenta_codigo": l[0], "cuenta_nombre": l[1],
                    "debe": float(l[2]), "haber": float(l[3]), "glosa": l[4],
                }
                for l in lineas
            ]
            asientos.append(asiento)

        return {"desde": desde, "hasta": hasta, "total": len(asientos), "asientos": asientos}
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Mayor de una cuenta
# ---------------------------------------------------------------------------

@router.get("/api/libros/mayor")
async def libro_mayor(
    request: Request,
    cuenta: str = Query(..., description="Código de cuenta PCGE"),
    desde: str  = Query(None),
    hasta: str  = Query(None),
):
    tok = _auth(request)
    _require_admin(tok)
    taller_id = _tenant_id(tok)

    today = _date.today()
    if not desde:
        desde = today.replace(day=1).isoformat()
    if not hasta:
        hasta = today.isoformat()

    db = _get_db()
    try:
        _setup_rls(db, taller_id)
        rows = db.execute(text("""
            SELECT a.fecha, a.numero, a.glosa,
                   l.debe, l.haber, l.glosa AS linea_glosa
            FROM   asiento_lineas l
            JOIN   asientos_contables a ON a.id = l.asiento_id
            WHERE  l.taller_id=:t
              AND  l.cuenta_codigo=:cta
              AND  a.fecha BETWEEN :d AND :h
              AND  a.estado='ACTIVO'
            ORDER BY a.fecha, a.numero
        """), {"t": taller_id, "cta": cuenta, "d": desde, "h": hasta}).fetchall()

        saldo = 0.0
        movimientos = []
        for r in rows:
            debe  = float(r[3] or 0)
            haber = float(r[4] or 0)
            saldo += debe - haber
            movimientos.append({
                "fecha":  str(r[0]),
                "numero": r[1],
                "glosa":  r[2],
                "debe":   debe,
                "haber":  haber,
                "saldo":  round(saldo, 2),
                "detalle": r[5],
            })

        total_debe  = sum(m["debe"]  for m in movimientos)
        total_haber = sum(m["haber"] for m in movimientos)
        return {
            "cuenta": cuenta,
            "desde": desde, "hasta": hasta,
            "total_debe":  round(total_debe, 2),
            "total_haber": round(total_haber, 2),
            "saldo_final": round(saldo, 2),
            "movimientos": movimientos,
        }
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Libro de Ventas (notas_venta + órdenes cobradas)
# ---------------------------------------------------------------------------

@router.get("/api/libros/ventas")
async def libro_ventas(
    request: Request,
    periodo: str = Query(..., description="YYYYMM"),
):
    tok = _auth(request)
    _require_admin(tok)
    taller_id = _tenant_id(tok)
    desde, hasta = _periodo_range(periodo)

    db = _get_db()
    try:
        _setup_rls(db, taller_id)

        # Notas de venta del período
        nv_rows = db.execute(text("""
            SELECT numero, CAST(fecha AS date), cliente_nombre,
                   COALESCE(subtotal,0), COALESCE(igv,0), COALESCE(total,0),
                   metodo_pago, estado
            FROM   notas_venta
            WHERE  taller_id=:t AND CAST(fecha AS date) BETWEEN :d AND :h
              AND  estado != 'ANULADA'
            ORDER BY fecha
        """), {"t": taller_id, "d": desde, "h": hasta}).fetchall()

        ventas = []
        for r in nv_rows:
            subtotal = float(r[3] or 0)
            igv = round(subtotal * 0.18, 2)
            total = round(subtotal + igv, 2)
            ventas.append({
                "tipo": "nota_venta",
                "numero":    r[0],
                "fecha":     str(r[1]),
                "cliente":   r[2],
                "subtotal":  subtotal,
                "igv":       igv,
                "total":     total,
                "metodo":    r[6],
                "estado":    r[7],
            })

        # Órdenes cobradas del período
        ord_rows = db.execute(text("""
            SELECT consecutivo,
                   COALESCE(fecha_dt::date, CURRENT_DATE) AS f_cobro,
                   cliente_id,
                   COALESCE(orden_total(items_cotizacion), 0) AS total_ord,
                   metodo_pago
            FROM   ordenes
            WHERE  taller_id=:t
              AND  COALESCE(fecha_dt::date, CURRENT_DATE) BETWEEN :d AND :h
              AND  COALESCE(monto_cobrado, 0) > 0
            ORDER BY fecha_dt
        """), {"t": taller_id, "d": desde, "h": hasta}).fetchall()

        for r in ord_rows:
            total = float(r[3] or 0)
            if total <= 0:
                continue
            subtotal = round(total / 1.18, 2)
            igv = round(subtotal * 0.18, 2)
            total = round(subtotal + igv, 2)
            ventas.append({
                "tipo":     "orden",
                "numero":   r[0],
                "fecha":    str(r[1]),
                "cliente":  r[2] or "",
                "subtotal": subtotal,
                "igv":      igv,
                "total":    total,
                "metodo":   r[4] or "Efectivo",
                "estado":   "COBRADA",
            })

        ventas.sort(key=lambda x: x["fecha"])
        total_subtotal = round(sum(v["subtotal"] for v in ventas), 2)
        total_igv      = round(sum(v["igv"]      for v in ventas), 2)
        total_total    = round(sum(v["total"]     for v in ventas), 2)

        return {
            "periodo": periodo,
            "desde": str(desde), "hasta": str(hasta),
            "total_subtotal": total_subtotal,
            "total_igv":      total_igv,
            "total_total":    total_total,
            "registros":      len(ventas),
            "ventas":         ventas,
        }
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Libro de Compras (facturas tipo mercaderia/gasto)
# ---------------------------------------------------------------------------

@router.get("/api/libros/compras")
async def libro_compras(
    request: Request,
    periodo: str = Query(..., description="YYYYMM"),
):
    tok = _auth(request)
    _require_admin(tok)
    taller_id = _tenant_id(tok)
    desde, hasta = _periodo_range(periodo)

    db = _get_db()
    try:
        _setup_rls(db, taller_id)
        # 2026-05-04 B2 fix: usar parse_fecha_text() para cubrir DD/MM/YYYY (peruano) e ISO.
        # Antes el regex ~ '^[0-9]{4}-...' solo cubria 16/281 facturas (las ISO).
        rows = db.execute(text("""
            SELECT numero_factura, parse_fecha_text(fecha), proveedor,
                   ruc_proveedor, tipo,
                   COALESCE(subtotal,0), COALESCE(igv,0), COALESCE(total,0),
                   estado
            FROM   facturas
            WHERE  taller_id=:t
              AND  parse_fecha_text(fecha) BETWEEN :d AND :h
              AND  estado NOT IN ('ANULADA')
            ORDER BY parse_fecha_text(fecha), id
        """), {"t": taller_id, "d": desde, "h": hasta}).fetchall()

        compras = []
        for r in rows:
            subtotal = float(r[5] or 0)
            igv = round(subtotal * 0.18, 2)
            total = round(subtotal + igv, 2)
            compras.append({
                "numero_factura": r[0],
                "fecha":          str(r[1]),
                "proveedor":      r[2],
                "ruc_proveedor":  r[3],
                "tipo":           r[4],
                "subtotal":       subtotal,
                "igv":            igv,
                "total":          total,
                "estado":         r[8],
            })

        return {
            "periodo": periodo,
            "desde": str(desde), "hasta": str(hasta),
            "total_subtotal": round(sum(c["subtotal"] for c in compras), 2),
            "total_igv":      round(sum(c["igv"]      for c in compras), 2),
            "total_total":    round(sum(c["total"]     for c in compras), 2),
            "registros":      len(compras),
            "compras":        compras,
        }
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Caja y Bancos
# ---------------------------------------------------------------------------

@router.get("/api/libros/caja-bancos")
async def libro_caja_bancos(
    request: Request,
    periodo: str = Query(..., description="YYYYMM"),
):
    tok = _auth(request)
    _require_admin(tok)
    taller_id = _tenant_id(tok)
    desde, hasta = _periodo_range(periodo)

    db = _get_db()
    try:
        _setup_rls(db, taller_id)
        rows = db.execute(text("""
            SELECT a.fecha, a.numero, a.glosa,
                   l.debe, l.haber
            FROM   asiento_lineas l
            JOIN   asientos_contables a ON a.id = l.asiento_id
            WHERE  l.taller_id=:t
              AND  l.cuenta_codigo IN ('101','1041')
              AND  a.fecha BETWEEN :d AND :h
              AND  a.estado='ACTIVO'
            ORDER BY a.fecha, a.numero
        """), {"t": taller_id, "d": desde, "h": hasta}).fetchall()

        saldo = 0.0
        movimientos = []
        for r in rows:
            debe  = float(r[3] or 0)
            haber = float(r[4] or 0)
            saldo += debe - haber
            movimientos.append({
                "fecha":   str(r[0]),
                "numero":  r[1],
                "concepto": r[2],
                "entrada":  debe,
                "salida":   haber,
                "saldo":    round(saldo, 2),
            })

        return {
            "periodo": periodo,
            "desde": str(desde), "hasta": str(hasta),
            "total_entradas": round(sum(m["entrada"] for m in movimientos), 2),
            "total_salidas":  round(sum(m["salida"]  for m in movimientos), 2),
            "saldo_final":    round(saldo, 2),
            "movimientos":    movimientos,
        }
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Inventario contable
# ---------------------------------------------------------------------------

@router.get("/api/libros/inventario")
async def libro_inventario(
    request: Request,
    periodo: str = Query(..., description="YYYYMM"),
):
    tok = _auth(request)
    _require_admin(tok)
    taller_id = _tenant_id(tok)
    desde, hasta = _periodo_range(periodo)

    db = _get_db()
    try:
        _setup_rls(db, taller_id)
        rows = db.execute(text("""
            SELECT codigo, nombre, stock, costo AS precio_costo, precio AS precio_venta,
                   COALESCE(stock * costo, 0) AS valor_inventario
            FROM   inventario
            WHERE  taller_id=:t
            ORDER BY codigo
        """), {"t": taller_id}).fetchall()

        items = [
            {
                "codigo":           r[0],
                "nombre":           r[1],
                "stock":            float(r[2] or 0),
                "precio_costo":     float(r[3] or 0),
                "precio_venta":     float(r[4] or 0),
                "valor_inventario": float(r[5] or 0),
                "unidad":           "und",
            }
            for r in rows
        ]

        return {
            "periodo": periodo,
            "total_valor": round(sum(i["valor_inventario"] for i in items), 2),
            "total_items": len(items),
            "items": items,
        }
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Estado de Resultados
# ---------------------------------------------------------------------------

@router.get("/api/libros/estado-resultados")
async def estado_resultados(
    request: Request,
    periodo: str = Query(..., description="YYYYMM"),
):
    tok = _auth(request)
    _require_admin(tok)
    taller_id = _tenant_id(tok)
    desde, hasta = _periodo_range(periodo)

    db = _get_db()
    try:
        _setup_rls(db, taller_id)

        # Ingresos (cuentas 70x): suma de haber
        ingresos = db.execute(text("""
            SELECT COALESCE(SUM(l.haber), 0)
            FROM   asiento_lineas l
            JOIN   asientos_contables a ON a.id = l.asiento_id
            WHERE  l.taller_id=:t
              AND  l.cuenta_codigo LIKE '7%'
              AND  a.fecha BETWEEN :d AND :h
              AND  a.estado='ACTIVO'
        """), {"t": taller_id, "d": desde, "h": hasta}).scalar() or 0

        # Costos (60x SOLO compras de mercaderia/materia prima — fix 2026-04-30 era LIKE '6%' que duplicaba gastos)
        # Clase 60: 601 mercaderias, 602 materias primas, 603 suministros, 604 envases.
        costos = db.execute(text("""
            SELECT COALESCE(SUM(l.debe), 0)
            FROM   asiento_lineas l
            JOIN   asientos_contables a ON a.id = l.asiento_id
            WHERE  l.taller_id=:t
              AND  l.cuenta_codigo LIKE '60%'
              AND  a.fecha BETWEEN :d AND :h
              AND  a.estado='ACTIVO'
        """), {"t": taller_id, "d": desde, "h": hasta}).scalar() or 0

        # Gastos (63x, 64x, 65x): suma de debe
        gastos = db.execute(text("""
            SELECT COALESCE(SUM(l.debe), 0)
            FROM   asiento_lineas l
            JOIN   asientos_contables a ON a.id = l.asiento_id
            WHERE  l.taller_id=:t
              AND  (l.cuenta_codigo LIKE '63%' OR l.cuenta_codigo LIKE '64%'
                    OR l.cuenta_codigo LIKE '65%')
              AND  a.fecha BETWEEN :d AND :h
              AND  a.estado='ACTIVO'
        """), {"t": taller_id, "d": desde, "h": hasta}).scalar() or 0

        ingresos_f = round(float(ingresos), 2)
        costos_f   = round(float(costos), 2)
        gastos_f   = round(float(gastos), 2)
        utilidad   = round(ingresos_f - costos_f - gastos_f, 2)

        return {
            "periodo": periodo,
            "desde": str(desde), "hasta": str(hasta),
            "ingresos":   ingresos_f,
            "costos":     costos_f,
            "gastos":     gastos_f,
            "utilidad_bruta":  round(ingresos_f - costos_f, 2),
            "utilidad_neta":   utilidad,
        }
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Balance General (simplificado)
# ---------------------------------------------------------------------------

@router.get("/api/libros/balance")
async def balance_general(
    request: Request,
    fecha: str = Query(None, description="YYYY-MM-DD"),
):
    tok = _auth(request)
    _require_admin(tok)
    taller_id = _tenant_id(tok)

    if not fecha:
        fecha = _date.today().isoformat()

    db = _get_db()
    try:
        _setup_rls(db, taller_id)

        def _saldo_cuenta(patron: str, columna: str) -> float:
            """Saldo neto de cuentas que empiezan con patron hasta fecha."""
            col_debe  = "SUM(l.debe)"
            col_haber = "SUM(l.haber)"
            val = db.execute(text(f"""
                SELECT COALESCE({col_debe},0) - COALESCE({col_haber},0)
                FROM   asiento_lineas l
                JOIN   asientos_contables a ON a.id = l.asiento_id
                WHERE  l.taller_id=:t
                  AND  l.cuenta_codigo LIKE :pat
                  AND  a.fecha <= :f
                  AND  a.estado='ACTIVO'
            """), {"t": taller_id, "pat": patron + "%", "f": fecha}).scalar() or 0
            return round(float(val), 2)

        activo_caja      = _saldo_cuenta("10", "activo")
        activo_cobrar    = _saldo_cuenta("12", "activo")
        activo_inventario = _saldo_cuenta("20", "activo")
        pasivo_pagar     = abs(_saldo_cuenta("42", "pasivo"))
        pasivo_igv       = abs(_saldo_cuenta("401", "pasivo"))

        total_activo  = round(activo_caja + activo_cobrar + activo_inventario, 2)
        total_pasivo  = round(pasivo_pagar + pasivo_igv, 2)
        patrimonio    = round(total_activo - total_pasivo, 2)

        return {
            "fecha": fecha,
            "activo": {
                "caja_bancos":         activo_caja,
                "cuentas_por_cobrar":  activo_cobrar,
                "inventario":          activo_inventario,
                "total":               total_activo,
            },
            "pasivo": {
                "cuentas_por_pagar":   pasivo_pagar,
                "igv_por_pagar":       pasivo_igv,
                "total":               total_pasivo,
            },
            "patrimonio": patrimonio,
        }
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Asiento manual
# ---------------------------------------------------------------------------

@router.post("/api/libros/asientos/manual")
async def crear_asiento_manual(request: Request):
    tok = _auth(request)
    _require_admin(tok)
    taller_id = _tenant_id(tok)
    body = await request.json()

    fecha  = body.get("fecha") or _date.today().isoformat()
    glosa  = (body.get("glosa") or "").strip()
    lineas = body.get("lineas") or []

    if not glosa:
        raise HTTPException(400, "glosa requerida")
    if len(lineas) < 2:
        raise HTTPException(400, "Se requieren al menos 2 líneas")

    lineas_norm = []
    for l in lineas:
        lineas_norm.append({
            "cuenta": str(l.get("cuenta_codigo") or l.get("cuenta", "")),
            "debe":   float(l.get("debe", 0)),
            "haber":  float(l.get("haber", 0)),
            "glosa":  str(l.get("glosa", "")),
        })

    db = _get_db()
    try:
        db.execute(text("SET app.taller_id = :t"), {"t": taller_id})

        from utils.contabilidad_engine import _insertar_asiento, _sembrar_cuentas
        _sembrar_cuentas(db, taller_id)
        usuario = tok.get("nombre", "admin")

        asiento_id = _insertar_asiento(
            db, taller_id, fecha, glosa, lineas_norm,
            tipo="manual", origen="manual", origen_id=None,
            usuario=usuario,
        )
        db.commit()
        return {"ok": True, "asiento_id": asiento_id}
    except ValueError as e:
        raise HTTPException(400, str(e))
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Extornar asiento
# ---------------------------------------------------------------------------

@router.post("/api/libros/asientos/{asiento_id}/extornar")
async def extornar_asiento_endpoint(
    asiento_id: int,
    request: Request,
):
    tok = _auth(request)
    _require_admin(tok)
    taller_id = _tenant_id(tok)
    body = await request.json()
    motivo = (body.get("motivo") or "Sin motivo").strip()

    db = _get_db()
    try:
        db.execute(text("SET app.taller_id = :t"), {"t": taller_id})
        from utils.contabilidad_engine import extornar_asiento
        ext_id = extornar_asiento(
            db, taller_id, asiento_id, motivo, tok.get("nombre", "admin")
        )
        return {"ok": True, "asiento_extorno_id": ext_id}
    except ValueError as e:
        raise HTTPException(400, str(e))
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Exportación PDF
# ---------------------------------------------------------------------------

@router.get("/api/libros/{tipo}/pdf")
async def exportar_pdf(
    tipo: str,
    request: Request,
    periodo: str  = Query(None),
    desde: str    = Query(None),
    hasta: str    = Query(None),
    cuenta: str   = Query(None),
    fecha: str    = Query(None),
):
    tok = _auth(request)
    _require_admin(tok)
    taller_id = _tenant_id(tok)

    _TIPOS_VALIDOS = {
        "diario", "mayor", "ventas", "compras",
        "caja-bancos", "inventario", "estado-resultados", "balance",
    }
    if tipo not in _TIPOS_VALIDOS:
        raise HTTPException(400, f"tipo inválido: {tipo}")

    try:
        from utils.pdf_libros import generar_pdf_libro
        pdf_bytes = generar_pdf_libro(
            tipo=tipo,
            taller_id=taller_id,
            periodo=periodo,
            desde=desde,
            hasta=hasta,
            cuenta=cuenta,
            fecha=fecha,
        )
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="libro_{tipo}_{periodo or fecha or "general"}.pdf"'},
        )
    except Exception as e:
        raise HTTPException(500, f"Error generando PDF: {e}")


# ---------------------------------------------------------------------------
# Exportación PLE (TXT SUNAT)
# ---------------------------------------------------------------------------

@router.get("/api/libros/{tipo}/ple")
async def exportar_ple(
    tipo: str,
    request: Request,
    periodo: str = Query(..., description="YYYYMM"),
    cuenta: str  = Query(None),
):
    tok = _auth(request)
    _require_admin(tok)
    taller_id = _tenant_id(tok)

    _TIPOS_PLE = {"ventas", "compras", "diario", "mayor", "caja-bancos"}
    if tipo not in _TIPOS_PLE:
        raise HTTPException(400, f"PLE no disponible para: {tipo}")

    try:
        from utils.pdf_libros import generar_ple
        txt_bytes = generar_ple(
            tipo=tipo,
            taller_id=taller_id,
            periodo=periodo,
            cuenta=cuenta,
        )
        filename = f"LE{periodo}_{tipo.replace('-','_')}.txt"
        return Response(
            content=txt_bytes,
            media_type="text/plain; charset=iso-8859-1",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as e:
        raise HTTPException(500, f"Error generando PLE: {e}")

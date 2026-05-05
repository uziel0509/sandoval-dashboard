"""
utils/contabilidad_engine.py — Motor de asientos contables SANDOVAL PRO
========================================================================
Genera asientos de doble partida en PCGE 2019 desde eventos del sistema.

IMPORTANTE: Todas las funciones son fail-safe. El caller las envuelve en
try/except para no bloquear el flujo de negocio ante errores contables.

Numeración correlativa por taller+mes: A-AAAAMM-NNNNN
Idempotencia garantizada por UNIQUE (taller_id, origen, origen_id).
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Dict, Any

from sqlalchemy import text

log = logging.getLogger("sandoval.contabilidad")

# ---------------------------------------------------------------------------
# Constantes PCGE mínimas
# ---------------------------------------------------------------------------
C_CAJA           = "101"
C_CUENTAS_COBRAR = "1212"
C_IGV_VENTA      = "4011"    # IGV cuenta propia (débito fiscal de ventas)
C_IGV_COMPRA     = "40111"   # IGV crédito fiscal (de compras)
C_POR_PAGAR      = "421"
C_VENTAS_MERCH   = "7011"
C_VENTAS_SERV    = "7012"
C_COMPRAS        = "601"
C_GASTOS         = "639"     # Cuenta genérica para gastos sin clasificar

# ---------------------------------------------------------------------------
# Helpers privados
# ---------------------------------------------------------------------------

def _d2(v) -> Decimal:
    """Convierte a Decimal con 2 decimales (ROUND_HALF_UP)."""
    return Decimal(str(v or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _validar_balanceo(lineas: list[dict]) -> None:
    """Lanza ValueError si Σdebe ≠ Σhaber."""
    total_debe  = sum(_d2(l.get("debe",  0)) for l in lineas)
    total_haber = sum(_d2(l.get("haber", 0)) for l in lineas)
    if total_debe != total_haber:
        raise ValueError(
            f"Asiento desbalanceado: debe={total_debe} haber={total_haber}"
        )


def _nombre_cuenta(db, taller_id: int, codigo: str) -> str:
    """Obtiene el nombre de la cuenta del plan_cuentas del taller."""
    row = db.execute(
        text("SELECT nombre FROM plan_cuentas WHERE taller_id=:t AND codigo=:c"),
        {"t": taller_id, "c": codigo}
    ).fetchone()
    return row[0] if row else codigo


def _setup_ctx(db, taller_id: int) -> None:
    """Setea el GUC para RLS."""
    db.execute(text("SET app.taller_id = :t"), {"t": taller_id})


def siguiente_numero(db, taller_id: int, fecha) -> str:
    """
    Genera el siguiente número correlativo mensual: A-AAAAMM-NNNNN.
    Busca el max existente en el mes y añade 1.
    Thread-safe por secuencia en DB via MAX+1 (aceptable para volumen taller).
    """
    if isinstance(fecha, str):
        try:
            fecha = datetime.strptime(fecha[:10], "%Y-%m-%d").date()
        except Exception:
            fecha = date.today()
    prefix = f"A-{fecha.strftime('%Y%m')}-"
    row = db.execute(
        text("""
            SELECT MAX(CAST(SPLIT_PART(numero, '-', 3) AS INTEGER))
            FROM   asientos_contables
            WHERE  taller_id=:t AND numero LIKE :pfx
        """),
        {"t": taller_id, "pfx": prefix + "%"}
    ).fetchone()
    seq = (row[0] or 0) + 1
    return f"{prefix}{seq:05d}"


def _insertar_asiento(
    db,
    taller_id: int,
    fecha,
    glosa: str,
    lineas: list[dict],
    tipo: str = "diario",
    origen: str | None = None,
    origen_id: str | None = None,
    usuario: str = "sistema",
) -> int:
    """
    Inserta cabecera + líneas en una transacción.
    Retorna asiento_id. La sesión DB ya debe tener SET app.taller_id.
    El trigger trg_doble_partida (DEFERRABLE) valida el balanceo al commit.
    """
    _validar_balanceo(lineas)

    if isinstance(fecha, str):
        try:
            fecha = datetime.strptime(fecha[:10], "%Y-%m-%d").date()
        except Exception:
            fecha = date.today()

    numero = siguiente_numero(db, taller_id, fecha)

    asiento_id = db.execute(
        text("""
            INSERT INTO asientos_contables
                (taller_id, numero, fecha, glosa, tipo, origen, origen_id, usuario)
            VALUES (:t, :n, :f, :g, :tipo, :orig, :orig_id, :usr)
            RETURNING id
        """),
        {
            "t": taller_id, "n": numero, "f": fecha,
            "g": glosa[:500], "tipo": tipo,
            "orig": origen, "orig_id": str(origen_id) if origen_id else None,
            "usr": usuario,
        }
    ).scalar()

    for idx, linea in enumerate(lineas):
        cuenta = linea["cuenta"]
        nombre = linea.get("nombre") or _nombre_cuenta(db, taller_id, cuenta)
        db.execute(
            text("""
                INSERT INTO asiento_lineas
                    (asiento_id, taller_id, cuenta_codigo, cuenta_nombre,
                     debe, haber, glosa, orden)
                VALUES (:aid, :t, :cta, :nom, :debe, :haber, :gl, :ord)
            """),
            {
                "aid": asiento_id, "t": taller_id,
                "cta": cuenta, "nom": nombre[:200],
                "debe":  float(_d2(linea.get("debe",  0))),
                "haber": float(_d2(linea.get("haber", 0))),
                "gl":  linea.get("glosa", "")[:300],
                "ord": idx,
            }
        )

    return asiento_id


def _ya_existe(db, taller_id: int, origen: str, origen_id) -> bool:
    """Comprueba idempotencia: ¿ya existe asiento para (origen, origen_id)?"""
    row = db.execute(
        text("""
            SELECT 1 FROM asientos_contables
            WHERE taller_id=:t AND origen=:orig AND origen_id=:oid
              AND estado='ACTIVO'
        """),
        {"t": taller_id, "orig": origen, "oid": str(origen_id)}
    ).fetchone()
    return row is not None


def _sembrar_cuentas(db, taller_id: int) -> None:
    """
    Siembra las cuentas PCGE mínimas para un taller nuevo (copia desde taller=1).
    Solo inserta las que no existan.
    """
    db.execute(text("""
        INSERT INTO plan_cuentas
            (taller_id, codigo, nombre, tipo, nivel, padre_codigo, es_sistema)
        SELECT :t, codigo, nombre, tipo, nivel, padre_codigo, TRUE
        FROM   plan_cuentas
        WHERE  taller_id=1 AND es_sistema=TRUE
        ON CONFLICT (taller_id, codigo) DO NOTHING
    """), {"t": taller_id})


# ---------------------------------------------------------------------------
# Asiento: Venta contado (orden cobrada o nota_venta efectivo)
# ---------------------------------------------------------------------------

def generar_asiento_orden_cobro(db, taller_id: int, orden_id: str) -> int | None:
    """
    Genera asiento por cobro de orden de servicio.
    Si la orden ya tiene asiento activo, retorna None (idempotente).
    Detecta pago contado vs crédito según monto_cobrado vs total.
    """
    _setup_ctx(db, taller_id)
    _sembrar_cuentas(db, taller_id)

    if _ya_existe(db, taller_id, "orden", orden_id):
        return None

    fila = db.execute(
        text("""
            SELECT COALESCE(orden_total(items_cotizacion), 0) AS total_orden,
                   COALESCE(monto_cobrado, 0)                AS cobrado,
                   metodo_pago,
                   COALESCE(fecha_cobro, fecha)              AS fecha_cobro,
                   consecutivo
            FROM   ordenes
            WHERE  consecutivo=:id AND taller_id=:t
        """),
        {"id": orden_id, "t": taller_id}
    ).fetchone()

    if not fila:
        raise ValueError(f"Orden {orden_id} no encontrada para taller {taller_id}")

    total   = _d2(fila[0])
    cobrado = _d2(fila[1])
    if total <= 0:
        return None  # Sin monto, no genera asiento

    subtotal = _d2(total / Decimal("1.18"))
    igv      = total - subtotal
    # Recalcular IGV exacto: igv = round(subtotal * 0.18, 2)
    igv      = _d2(subtotal * Decimal("0.18"))
    total    = subtotal + igv

    fecha_cobro = fila[3] or date.today().isoformat()
    glosa = f"Cobro orden {orden_id}"

    # Venta contado si cobrado == total, crédito si es parcial
    es_contado = (cobrado >= total)
    cuenta_activo = C_CAJA if es_contado else C_CUENTAS_COBRAR

    lineas = [
        {"cuenta": cuenta_activo, "debe": float(total),    "haber": 0,             "glosa": glosa},
        {"cuenta": C_VENTAS_SERV, "debe": 0,               "haber": float(subtotal),"glosa": glosa},
        {"cuenta": C_IGV_VENTA,   "debe": 0,               "haber": float(igv),    "glosa": glosa},
    ]

    aid = _insertar_asiento(
        db, taller_id, fecha_cobro, glosa, lineas,
        tipo="diario", origen="orden", origen_id=orden_id,
        usuario="sistema"
    )
    db.commit()
    log.info("Asiento orden %s → id=%d", orden_id, aid)
    return aid


# ---------------------------------------------------------------------------
# Asiento: Nota de venta
# ---------------------------------------------------------------------------

def generar_asiento_nota_venta(db, taller_id: int, nv_id: int) -> int | None:
    """
    Genera asiento por nota de venta (venta directa de repuestos/servicios).
    """
    _setup_ctx(db, taller_id)
    _sembrar_cuentas(db, taller_id)

    if _ya_existe(db, taller_id, "nota_venta", nv_id):
        return None

    fila = db.execute(
        text("""
            SELECT COALESCE(total, 0), COALESCE(subtotal, 0), COALESCE(igv, 0),
                   COALESCE(metodo_pago, 'Efectivo'), numero,
                   COALESCE(fecha, NOW())::date
            FROM   notas_venta
            WHERE  id=:id AND taller_id=:t
        """),
        {"id": nv_id, "t": taller_id}
    ).fetchone()

    if not fila:
        raise ValueError(f"Nota venta {nv_id} no encontrada")

    total    = _d2(fila[0])
    subtotal_db = _d2(fila[1])
    igv_db   = _d2(fila[2])
    metodo   = fila[3] or "Efectivo"
    numero   = fila[4]
    fecha    = fila[5]

    if total <= 0:
        return None

    # 2026-04-29 fix: respetar desglose IGV de DB si cuadra; si no, asumir total bruto.
    DOSCE = Decimal("0.01")
    if subtotal_db > 0 and igv_db > 0 and abs(subtotal_db + igv_db - total) <= DOSCE:
        igv = igv_db
        # Ajuste de centavo para balancear exactamente con total
        subtotal = total - igv
    else:
        # subtotal==total o sin desglose: total YA incluye IGV (caso típico boletas pequeñas)
        # IGV = total * 18 / 118 (redondeo 2 decimales)
        igv = _d2((total * Decimal("18")) / Decimal("118"))
        subtotal = total - igv

    glosa = f"Nota de venta {numero}"
    es_contado = metodo.lower() not in ("crédito", "credito", "crédito")
    cuenta_activo = C_CAJA if es_contado else C_CUENTAS_COBRAR

    lineas = [
        {"cuenta": cuenta_activo, "debe": float(total),    "haber": 0,              "glosa": glosa},
        {"cuenta": C_VENTAS_MERCH,"debe": 0,               "haber": float(subtotal),"glosa": glosa},
        {"cuenta": C_IGV_VENTA,   "debe": 0,               "haber": float(igv),     "glosa": glosa},
    ]

    aid = _insertar_asiento(
        db, taller_id, fecha, glosa, lineas,
        tipo="diario", origen="nota_venta", origen_id=str(nv_id),
        usuario="sistema"
    )
    db.commit()
    log.info("Asiento nota_venta %d → id=%d", nv_id, aid)
    return aid


# ---------------------------------------------------------------------------
# Asiento: Factura de compra (mercadería o gasto)
# ---------------------------------------------------------------------------

def generar_asiento_factura_compra(db, taller_id: int, fact_id: int) -> int | None:
    """
    Genera asiento por factura de compra registrada.
    Debe 601/63x + Debe 40111 (IGV crédito) / Haber 421
    """
    _setup_ctx(db, taller_id)
    _sembrar_cuentas(db, taller_id)

    if _ya_existe(db, taller_id, "factura", fact_id):
        return None

    fila = db.execute(
        text("""
            SELECT COALESCE(total, 0), COALESCE(subtotal, 0), COALESCE(igv, 0),
                   tipo, numero_factura, proveedor,
                   COALESCE(fecha, TO_CHAR(NOW(), 'YYYY-MM-DD'))
            FROM   facturas
            WHERE  id=:id AND taller_id=:t
        """),
        {"id": fact_id, "t": taller_id}
    ).fetchone()

    if not fila:
        raise ValueError(f"Factura {fact_id} no encontrada")

    total    = _d2(fila[0])
    subtotal_db = _d2(fila[1])
    igv_db   = _d2(fila[2])
    tipo     = fila[3] or "gasto"
    num_fac  = fila[4] or str(fact_id)
    prov     = fila[5] or "Proveedor"
    fecha    = fila[6]

    if total <= 0:
        return None

    # 2026-04-30 fix: respetar desglose si cuadra; si no, asumir total bruto.
    DOSCE = Decimal("0.01")
    if subtotal_db > 0 and igv_db > 0 and abs(subtotal_db + igv_db - total) <= DOSCE:
        igv = igv_db
        subtotal = total - igv
    else:
        igv = _d2((total * Decimal("18")) / Decimal("118"))
        subtotal = total - igv

    # Cuenta de costo/gasto según tipo
    if tipo == "mercaderia":
        cta_gasto = C_COMPRAS   # 601
    else:
        cta_gasto = C_GASTOS    # 639

    glosa = f"Factura compra {num_fac} - {prov}"
    lineas = [
        {"cuenta": cta_gasto,    "debe": float(subtotal), "haber": 0,            "glosa": glosa},
        {"cuenta": C_IGV_COMPRA, "debe": float(igv),      "haber": 0,            "glosa": glosa},
        {"cuenta": C_POR_PAGAR,  "debe": 0,               "haber": float(total), "glosa": glosa},
    ]

    aid = _insertar_asiento(
        db, taller_id, fecha[:10], glosa, lineas,
        tipo="diario", origen="factura", origen_id=str(fact_id),
        usuario="sistema"
    )
    db.commit()
    log.info("Asiento factura %d → id=%d", fact_id, aid)
    return aid


# ---------------------------------------------------------------------------
# Asiento: Gasto operacional
# ---------------------------------------------------------------------------

def generar_asiento_gasto(db, taller_id: int, gasto_id: int) -> int | None:
    """
    Genera asiento por gasto operacional.
    Debe 639 / Haber 101 (salida de caja)
    """
    _setup_ctx(db, taller_id)
    _sembrar_cuentas(db, taller_id)

    if _ya_existe(db, taller_id, "gasto", gasto_id):
        return None

    fila = db.execute(
        text("""
            SELECT COALESCE(costo_total, 0), descripcion,
                   COALESCE(fecha, CURRENT_DATE)
            FROM   gastos_operacionales
            WHERE  id=:id AND taller_id=:t
        """),
        {"id": gasto_id, "t": taller_id}
    ).fetchone()

    if not fila:
        raise ValueError(f"Gasto {gasto_id} no encontrado")

    total = _d2(fila[0])
    desc  = fila[1] or "Gasto operacional"
    fecha = fila[2]

    if total <= 0:
        return None

    glosa = f"Gasto: {desc[:60]}"
    lineas = [
        {"cuenta": C_GASTOS, "debe": float(total), "haber": 0,            "glosa": glosa},
        {"cuenta": C_CAJA,   "debe": 0,            "haber": float(total), "glosa": glosa},
    ]

    aid = _insertar_asiento(
        db, taller_id, fecha, glosa, lineas,
        tipo="diario", origen="gasto", origen_id=str(gasto_id),
        usuario="sistema"
    )
    db.commit()
    log.info("Asiento gasto %d → id=%d", gasto_id, aid)
    return aid


# ---------------------------------------------------------------------------
# Asiento: Abono a crédito (recibe pago de orden/deuda crediticia)
# ---------------------------------------------------------------------------

def generar_asiento_abono_credito(db, taller_id: int, abono_id: int) -> int | None:
    """
    Genera asiento por abono a crédito de una orden.
    Debe 101 Caja / Haber 1212 Cuentas por cobrar
    """
    _setup_ctx(db, taller_id)
    _sembrar_cuentas(db, taller_id)

    if _ya_existe(db, taller_id, "abono", abono_id):
        return None

    fila = db.execute(
        text("""
            SELECT COALESCE(monto, 0), referencia_id, metodo_pago,
                   COALESCE(fecha, NOW())::date
            FROM   abonos_credito
            WHERE  id=:id AND taller_id=:t
        """),
        {"id": abono_id, "t": taller_id}
    ).fetchone()

    if not fila:
        raise ValueError(f"Abono {abono_id} no encontrado")

    monto  = _d2(fila[0])
    ref    = fila[1] or str(abono_id)
    fecha  = fila[3]

    if monto <= 0:
        return None

    glosa = f"Abono crédito ref {ref}"
    lineas = [
        {"cuenta": C_CAJA,           "debe": float(monto), "haber": 0,            "glosa": glosa},
        {"cuenta": C_CUENTAS_COBRAR, "debe": 0,            "haber": float(monto), "glosa": glosa},
    ]

    aid = _insertar_asiento(
        db, taller_id, fecha, glosa, lineas,
        tipo="diario", origen="abono", origen_id=str(abono_id),
        usuario="sistema"
    )
    db.commit()
    log.info("Asiento abono %d → id=%d", abono_id, aid)
    return aid


# ---------------------------------------------------------------------------
# Extorno de asiento
# ---------------------------------------------------------------------------

def extornar_asiento(
    db,
    taller_id: int,
    asiento_id: int,
    motivo: str,
    usuario: str,
) -> int:
    """
    Extorna un asiento: crea asiento espejo (debe↔haber invertidos)
    y marca el original como ANULADO.
    Nunca borra el asiento original.
    """
    _setup_ctx(db, taller_id)

    cab = db.execute(
        text("""
            SELECT id, numero, fecha, glosa, tipo, origen, origen_id, estado
            FROM   asientos_contables
            WHERE  id=:id AND taller_id=:t
        """),
        {"id": asiento_id, "t": taller_id}
    ).fetchone()

    if not cab:
        raise ValueError(f"Asiento {asiento_id} no encontrado")
    if cab[7] == "ANULADO":
        raise ValueError(f"Asiento {asiento_id} ya está anulado")

    lineas_orig = db.execute(
        text("""
            SELECT cuenta_codigo, cuenta_nombre, debe, haber, glosa
            FROM   asiento_lineas
            WHERE  asiento_id=:aid
            ORDER BY orden
        """),
        {"aid": asiento_id}
    ).fetchall()

    if not lineas_orig:
        raise ValueError(f"Asiento {asiento_id} sin líneas")

    # Líneas espejo: debe y haber invertidos
    lineas_ext = [
        {
            "cuenta": r[0],
            "nombre": r[1],
            "debe":   float(_d2(r[3])),   # haber original → debe extorno
            "haber":  float(_d2(r[2])),   # debe original  → haber extorno
            "glosa":  f"EXTORNO: {r[4]}",
        }
        for r in lineas_orig
    ]

    glosa_ext = f"EXTORNO de {cab[1]}: {motivo}"
    ext_id = _insertar_asiento(
        db, taller_id, date.today(), glosa_ext, lineas_ext,
        tipo="extorno",
        origen=f"extorno_{cab[5]}" if cab[5] else "extorno",
        origen_id=str(cab[6]) if cab[6] else None,
        usuario=usuario,
    )

    # Marcar original como ANULADO
    db.execute(
        text("""
            UPDATE asientos_contables
            SET estado='ANULADO', anulado_por=:ext, anulado_en=NOW()
            WHERE id=:id AND taller_id=:t
        """),
        {"ext": ext_id, "id": asiento_id, "t": taller_id}
    )
    db.commit()
    log.info("Extorno %d → nuevo asiento %d", asiento_id, ext_id)
    return ext_id

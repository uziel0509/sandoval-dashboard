"""
routers/equipo.py — Gestión de trabajadores del taller y sus pagos (multi-tenant).

Permite registrar al equipo (técnicos, recepcionistas), su salario y periodicidad,
y llevar control de pagos parciales. Los pagos se integran como gasto operativo
al calcular ganancia neta en finanzas.
"""
from routers._common import (
    router,
    _auth, _get_db, _require_admin, _require_staff, _safe_date, _tenant_id,
    datetime, timedelta, Request, HTTPException, text,
)


# ── Trabajadores ──────────────────────────────────────────────────────────────

_ROLES = {"tecnico", "recepcionista", "administrativo", "mecanico", "ayudante", "otro"}
_PERIODS = {"diario", "semanal", "quincenal", "mensual"}


def _saldo_pendiente(db, trabajador_id: int, taller_id: int, salario: float,
                     periodicidad: str) -> dict:
    """Devuelve info del período vigente: pagado, pendiente, etiqueta."""
    now = datetime.now()
    if periodicidad == "diario":
        desde = now.strftime("%Y-%m-%d")
        hasta = desde
        etiqueta = desde
    elif periodicidad == "semanal":
        lunes = (now - timedelta(days=now.weekday())).strftime("%Y-%m-%d")
        domingo = (now - timedelta(days=now.weekday()) + timedelta(days=6)).strftime("%Y-%m-%d")
        desde, hasta = lunes, domingo
        etiqueta = f"Sem {now.isocalendar()[1]}"
    elif periodicidad == "quincenal":
        if now.day <= 15:
            desde = now.strftime("%Y-%m-01")
            hasta = now.strftime("%Y-%m-15")
            etiqueta = f"{now.strftime('%Y-%m')} Q1"
        else:
            desde = now.strftime("%Y-%m-16")
            # Último día del mes: primer día del mes siguiente - 1 día
            if now.month == 12:
                next_month = datetime(now.year + 1, 1, 1)
            else:
                next_month = datetime(now.year, now.month + 1, 1)
            hasta = (next_month - timedelta(days=1)).strftime("%Y-%m-%d")
            etiqueta = f"{now.strftime('%Y-%m')} Q2"
    else:  # mensual
        desde = now.strftime("%Y-%m-01")
        if now.month == 12:
            next_month = datetime(now.year + 1, 1, 1)
        else:
            next_month = datetime(now.year, now.month + 1, 1)
        hasta = (next_month - timedelta(days=1)).strftime("%Y-%m-%d")
        etiqueta = now.strftime("%Y-%m")

    row = db.execute(text(
        "SELECT COALESCE(SUM(monto), 0) FROM pagos_trabajadores "
        "WHERE taller_id=:t AND trabajador_id=:tr "
        "  AND fecha >= :d AND fecha <= :h"
    ), {"t": taller_id, "tr": trabajador_id, "d": desde, "h": hasta}).fetchone()
    pagado = float(row[0] or 0)
    pendiente = round(max(float(salario) - pagado, 0.0), 2)
    return {
        "periodo": etiqueta,
        "pagado_periodo": round(pagado, 2),
        "pendiente_periodo": pendiente,
    }


@router.get("/api/equipo")
async def list_trabajadores(request: Request):
    tok = _auth(request)
    _require_staff(tok)
    taller_id = _tenant_id(tok)
    db = _get_db()
    try:
        rows = db.execute(text(
            "SELECT id, nombre, dni, rol, salario, periodicidad, telefono, "
            "       fecha_ingreso, activo, notas "
            "FROM trabajadores WHERE taller_id=:t "
            "ORDER BY activo DESC, nombre"
        ), {"t": taller_id}).fetchall()

        out = []
        for r in rows:
            saldo = _saldo_pendiente(db, r[0], taller_id, float(r[4] or 0), r[5] or "mensual")
            out.append({
                "id": r[0],
                "nombre": r[1],
                "dni": r[2] or "",
                "rol": r[3] or "tecnico",
                "salario": float(r[4] or 0),
                "periodicidad": r[5] or "mensual",
                "telefono": r[6] or "",
                "fecha_ingreso": r[7].isoformat() if r[7] else None,
                "activo": bool(r[8]),
                "notas": r[9] or "",
                **saldo,
            })
        return out
    finally:
        db.close()


@router.post("/api/equipo")
async def create_trabajador(request: Request):
    tok = _auth(request)
    _require_admin(tok)
    taller_id = _tenant_id(tok)
    body = await request.json()
    nombre = (body.get("nombre") or "").strip()
    if not nombre:
        raise HTTPException(400, "Nombre requerido")
    rol = (body.get("rol") or "tecnico").lower().strip()
    if rol not in _ROLES:
        rol = "otro"
    periodicidad = (body.get("periodicidad") or "mensual").lower().strip()
    if periodicidad not in _PERIODS:
        periodicidad = "mensual"
    try:
        salario = float(body.get("salario") or 0)
    except (TypeError, ValueError):
        raise HTTPException(400, "Salario inválido")
    if salario < 0:
        raise HTTPException(400, "Salario negativo")

    db = _get_db()
    try:
        res = db.execute(text("""
            INSERT INTO trabajadores
              (taller_id, nombre, dni, rol, salario, periodicidad, telefono, fecha_ingreso, activo, notas)
            VALUES (:t, :n, :dni, :rol, :sal, :per, :tel, :fi, :act, :notas)
            RETURNING id
        """), {
            "t": taller_id, "n": nombre,
            "dni": (body.get("dni") or "").strip() or None,
            "rol": rol, "sal": salario, "per": periodicidad,
            "tel": (body.get("telefono") or "").strip() or None,
            "fi": _safe_date(body.get("fecha_ingreso")) or datetime.now().date(),
            "act": bool(body.get("activo", True)),
            "notas": (body.get("notas") or "").strip() or None,
        })
        new_id = res.fetchone()[0]
        db.commit()
        return {"ok": True, "id": new_id}
    finally:
        db.close()


@router.put("/api/equipo/{tid}")
async def update_trabajador(tid: int, request: Request):
    tok = _auth(request)
    _require_admin(tok)
    taller_id = _tenant_id(tok)
    body = await request.json()

    rol = (body.get("rol") or "tecnico").lower().strip()
    if rol not in _ROLES:
        rol = "otro"
    periodicidad = (body.get("periodicidad") or "mensual").lower().strip()
    if periodicidad not in _PERIODS:
        periodicidad = "mensual"
    try:
        salario = float(body.get("salario") or 0)
    except (TypeError, ValueError):
        raise HTTPException(400, "Salario inválido")

    db = _get_db()
    try:
        res = db.execute(text("""
            UPDATE trabajadores SET
              nombre=:n, dni=:dni, rol=:rol, salario=:sal, periodicidad=:per,
              telefono=:tel, fecha_ingreso=:fi, activo=:act, notas=:notas
            WHERE id=:id AND taller_id=:t
        """), {
            "id": tid, "t": taller_id,
            "n": (body.get("nombre") or "").strip(),
            "dni": (body.get("dni") or "").strip() or None,
            "rol": rol, "sal": salario, "per": periodicidad,
            "tel": (body.get("telefono") or "").strip() or None,
            "fi": _safe_date(body.get("fecha_ingreso")),
            "act": bool(body.get("activo", True)),
            "notas": (body.get("notas") or "").strip() or None,
        })
        if res.rowcount == 0:
            raise HTTPException(404, "Trabajador no encontrado")
        db.commit()
        return {"ok": True}
    finally:
        db.close()


@router.delete("/api/equipo/{tid}")
async def delete_trabajador(tid: int, request: Request):
    tok = _auth(request)
    _require_admin(tok)
    taller_id = _tenant_id(tok)
    db = _get_db()
    try:
        res = db.execute(text(
            "DELETE FROM trabajadores WHERE id=:id AND taller_id=:t"
        ), {"id": tid, "t": taller_id})
        if res.rowcount == 0:
            raise HTTPException(404, "Trabajador no encontrado")
        db.commit()
        return {"ok": True}
    finally:
        db.close()


# ── Pagos a trabajadores ──────────────────────────────────────────────────────

_TIPOS_PAGO = {"sueldo", "adelanto", "bono", "comision"}


@router.get("/api/equipo/{tid}/pagos")
async def list_pagos_trabajador(tid: int, request: Request):
    tok = _auth(request)
    _require_staff(tok)
    taller_id = _tenant_id(tok)
    db = _get_db()
    try:
        rows = db.execute(text(
            "SELECT id, monto, fecha, metodo_pago, tipo, periodo_cubierto, "
            "       observacion, registrado_por, creado_en "
            "FROM pagos_trabajadores "
            "WHERE trabajador_id=:tr AND taller_id=:t "
            "ORDER BY fecha DESC, id DESC"
        ), {"tr": tid, "t": taller_id}).fetchall()
        return [{
            "id": r[0], "monto": float(r[1] or 0),
            "fecha": r[2].isoformat() if r[2] else None,
            "metodo_pago": r[3] or "Efectivo",
            "tipo": r[4] or "sueldo",
            "periodo_cubierto": r[5] or "",
            "observacion": r[6] or "",
            "registrado_por": r[7] or "",
            "creado_en": r[8].isoformat() if r[8] else None,
        } for r in rows]
    finally:
        db.close()


@router.post("/api/equipo/{tid}/pagos")
async def create_pago_trabajador(tid: int, request: Request):
    tok = _auth(request)
    _require_admin(tok)
    taller_id = _tenant_id(tok)
    body = await request.json()

    try:
        monto = float(body.get("monto") or 0)
    except (TypeError, ValueError):
        raise HTTPException(400, "Monto inválido")
    if monto <= 0:
        raise HTTPException(400, "Monto debe ser > 0")

    tipo = (body.get("tipo") or "sueldo").lower().strip()
    if tipo not in _TIPOS_PAGO:
        tipo = "sueldo"

    db = _get_db()
    try:
        # Verificar trabajador
        exists = db.execute(text(
            "SELECT 1 FROM trabajadores WHERE id=:id AND taller_id=:t"
        ), {"id": tid, "t": taller_id}).fetchone()
        if not exists:
            raise HTTPException(404, "Trabajador no encontrado")

        res = db.execute(text("""
            INSERT INTO pagos_trabajadores
              (taller_id, trabajador_id, monto, fecha, metodo_pago, tipo,
               periodo_cubierto, observacion, registrado_por)
            VALUES (:t, :tr, :m, :f, :mp, :tipo, :per, :obs, :who)
            RETURNING id
        """), {
            "t": taller_id, "tr": tid, "m": monto,
            "f": _safe_date(body.get("fecha")) or datetime.now().date(),
            "mp": (body.get("metodo_pago") or "Efectivo").strip(),
            "tipo": tipo,
            "per": (body.get("periodo_cubierto") or "").strip() or None,
            "obs": (body.get("observacion") or "").strip() or None,
            "who": tok.get("nombre") or tok.get("sub") or "admin",
        })
        new_id = res.fetchone()[0]
        db.commit()
        return {"ok": True, "id": new_id}
    finally:
        db.close()


@router.delete("/api/equipo/pagos/{pago_id}")
async def delete_pago_trabajador(pago_id: int, request: Request):
    tok = _auth(request)
    _require_admin(tok)
    taller_id = _tenant_id(tok)
    db = _get_db()
    try:
        res = db.execute(text(
            "DELETE FROM pagos_trabajadores WHERE id=:id AND taller_id=:t"
        ), {"id": pago_id, "t": taller_id})
        if res.rowcount == 0:
            raise HTTPException(404, "Pago no encontrado")
        db.commit()
        return {"ok": True}
    finally:
        db.close()


# ── Resumen para dashboard / finanzas ─────────────────────────────────────────

@router.get("/api/equipo/resumen")
async def resumen_equipo(request: Request):
    """Totales del mes actual: nómina pagada, pendiente, cantidad de trabajadores."""
    tok = _auth(request)
    _require_staff(tok)
    taller_id = _tenant_id(tok)
    db = _get_db()
    try:
        pagado_mes = db.execute(text(
            "SELECT COALESCE(SUM(monto), 0) FROM pagos_trabajadores "
            "WHERE taller_id=:t AND fecha >= date_trunc('month', NOW())::date"
        ), {"t": taller_id}).fetchone()[0] or 0

        activos = db.execute(text(
            "SELECT COUNT(*), COALESCE(SUM(salario), 0) FROM trabajadores "
            "WHERE taller_id=:t AND activo=TRUE"
        ), {"t": taller_id}).fetchone()

        # Saldo pendiente total del mes (solo mensuales — aproximación conservadora)
        pendiente_mes = db.execute(text("""
            SELECT COALESCE(SUM(
              GREATEST(tr.salario - COALESCE((
                SELECT SUM(pp.monto) FROM pagos_trabajadores pp
                WHERE pp.trabajador_id = tr.id AND pp.taller_id = tr.taller_id
                  AND pp.fecha >= date_trunc('month', NOW())::date
                  AND pp.tipo IN ('sueldo','adelanto')
              ), 0), 0)
            ), 0)
            FROM trabajadores tr
            WHERE tr.taller_id=:t AND tr.activo=TRUE AND tr.periodicidad='mensual'
        """), {"t": taller_id}).fetchone()[0] or 0

        return {
            "trabajadores_activos": int(activos[0] or 0),
            "nomina_mensual_comprometida": round(float(activos[1] or 0), 2),
            "pagado_mes": round(float(pagado_mes), 2),
            "pendiente_mes_mensuales": round(float(pendiente_mes), 2),
        }
    finally:
        db.close()

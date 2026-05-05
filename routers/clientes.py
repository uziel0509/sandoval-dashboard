"""
routers/clientes.py — Clientes + vehículos del taller (multi-tenant).

Refactor 2026-04-21b:
  * Nueva columna `documento` (DNI / RUC) separada de la PK interna `id`.
  * POST/PUT/GET ahora leen y devuelven `documento`.
  * Búsqueda por `documento` habilitada.
"""
from routers._common import (
    router, ADMIN_HTML,
    _auth, _get_db, _require_admin, _require_staff, _safe_date,
    _img_to_url, _parse_json_field, _make_token, _tenant_id,
    os, json, datetime, timedelta, Path,
    Request, HTTPException, UploadFile, File, List, HTMLResponse, text,
)
from fastapi import Query


@router.get("/api/clientes/{cid}", name="get_cliente")
async def get_cliente(cid: str, request: Request):
    tok = _auth(request)
    _require_staff(tok)
    taller_id = _tenant_id(tok)
    db = _get_db()
    try:
        row = db.execute(text(
            "SELECT id, nombre, apellidos, telefono, email, direccion, ciudad, "
            "tipo, observaciones, COALESCE(documento, ''), "
            "COALESCE(tipo_cliente, 'individual') "
            "FROM clientes WHERE id=:id AND taller_id=:t"
        ), {"id": cid, "t": taller_id}).fetchone()
        if not row:
            raise HTTPException(404, "Cliente no encontrado")
        return {
            "id": row[0],
            "nombre": row[1],
            "apellidos": row[2],
            "telefono": row[3],
            "email": row[4],
            "direccion": row[5],
            "ciudad": row[6],
            "tipo": row[7],
            "observaciones": row[8],
            "documento": row[9],
            "tipo_cliente": row[10],
        }
    finally:
        db.close()


@router.get("/api/clientes")
async def list_clientes(
    request: Request,
    q: str | None = None,
    limit: int = Query(200, ge=1, le=500),
):
    tok = _auth(request)
    _require_staff(tok)
    taller_id = _tenant_id(tok)
    db = _get_db()
    try:
        sql = """SELECT id, nombre, apellidos, telefono, email, direccion, tipo,
                        fecha_registro, ciudad, COALESCE(documento, ''),
                        COALESCE(tipo_cliente, 'individual')
                 FROM clientes WHERE taller_id=:t"""
        params = {"t": taller_id}
        if q:
            sql += (" AND (nombre ILIKE :q OR apellidos ILIKE :q "
                    "OR telefono ILIKE :q OR documento ILIKE :q OR id ILIKE :q)")
            params["q"] = f"%{q}%"
        sql += " ORDER BY nombre LIMIT :lim"
        params["lim"] = limit
        rows = db.execute(text(sql), params).fetchall()
        return [{
            "id": r[0],
            "nombre": f"{r[1] or ''} {r[2] or ''}".strip(),
            "nombre_raw": r[1],
            "apellidos": r[2],
            "telefono": r[3],
            "email": r[4],
            "direccion": r[5],
            "tipo": r[6],
            "fecha_registro": _safe_date(r[7]),
            "ciudad": r[8],
            "documento": r[9],
            "tipo_cliente": r[10],
        } for r in rows]
    finally:
        db.close()


def _pick_documento(body: dict) -> str:
    """Acepta alias: documento, dni, ruc. Rechaza ids auto-generados CLI-*."""
    for k in ("documento", "dni", "ruc"):
        v = body.get(k)
        if v is None:
            continue
        v = str(v).strip()
        if v and not v.upper().startswith("CLI-"):
            return v
    return ""


@router.post("/api/clientes")
async def create_cliente(request: Request):
    tok = _auth(request)
    _require_staff(tok)
    taller_id = _tenant_id(tok)
    body = await request.json()
    if not body.get("nombre"):
        raise HTTPException(400, "Nombre requerido")
    documento = _pick_documento(body)
    if not documento:
        raise HTTPException(400, "DNI / RUC requerido")

    db = _get_db()
    try:
        dup = db.execute(text(
            "SELECT id FROM clientes WHERE taller_id=:t AND documento=:d LIMIT 1"
        ), {"t": taller_id, "d": documento}).fetchone()
        if dup:
            raise HTTPException(
                409,
                f"Ya existe un cliente con este documento ({documento}).",
            )

        # `id` se autogenera como llave interna para preservar FKs existentes
        # (órdenes, citas, cotizaciones, notas, vehículos).
        prefix = datetime.now().strftime("CLI-%Y%m%d-")
        count = db.execute(text(
            "SELECT COUNT(*) FROM clientes WHERE id LIKE :p AND taller_id=:t"
        ), {"p": f"{prefix}%", "t": taller_id}).fetchone()[0]
        cid = f"{prefix}{str(count + 1).zfill(3)}"

        db.execute(text("""
            INSERT INTO clientes (id, taller_id, nombre, apellidos, telefono, email,
                direccion, ciudad, tipo, observaciones, documento, fecha_registro)
            VALUES (:id, :t, :n, :ap, :tel, :em, :dir, :ciu, :tipo, :obs, :doc, NOW())
        """), {
            "id": cid, "t": taller_id,
            "n": body.get("nombre", ""),
            "ap": body.get("apellidos", ""),
            "tel": body.get("telefono", ""),
            "em": body.get("email", ""),
            "dir": body.get("direccion", ""),
            "ciu": body.get("ciudad", ""),
            "tipo": body.get("tipo", "persona"),
            "obs": body.get("observaciones", ""),
            "doc": documento[:20],
        })
        db.commit()
        return {"id": cid, "documento": documento}
    finally:
        db.close()


@router.put("/api/clientes/{cid}")
async def update_cliente(cid: str, request: Request):
    tok = _auth(request)
    _require_staff(tok)
    taller_id = _tenant_id(tok)
    body = await request.json()
    db = _get_db()
    try:
        fields = [
            "nombre", "apellidos", "telefono", "email",
            "direccion", "ciudad", "tipo", "observaciones",
        ]
        sets, params = [], {"id": cid, "t": taller_id}
        for f in fields:
            if f in body:
                sets.append(f"{f}=:{f}")
                params[f] = body[f]
        # tipo_cliente: 'individual' | 'empresa' (validado)
        if "tipo_cliente" in body:
            tc = str(body.get("tipo_cliente") or "").lower().strip()
            if tc in ("individual", "empresa"):
                sets.append("tipo_cliente=:tipo_cliente")
                params["tipo_cliente"] = tc

        if any(k in body for k in ("documento", "dni", "ruc")):
            new_doc = _pick_documento(body)[:20]
            if new_doc:
                dup = db.execute(text(
                    "SELECT id FROM clientes "
                    "WHERE taller_id=:t AND documento=:d AND id<>:id LIMIT 1"
                ), {"t": taller_id, "d": new_doc, "id": cid}).fetchone()
                if dup:
                    raise HTTPException(
                        409,
                        f"Ya existe otro cliente con este documento ({new_doc}).",
                    )
            sets.append("documento=:documento")
            params["documento"] = new_doc or None

        if sets:
            db.execute(text(
                f"UPDATE clientes SET {', '.join(sets)} "
                "WHERE id=:id AND taller_id=:t"
            ), params)
            db.commit()
        return {"ok": True}
    finally:
        db.close()


@router.get("/api/clientes/{cid}/vehiculos")
async def get_cliente_vehiculos(cid: str, request: Request):
    tok = _auth(request)
    _require_staff(tok)
    taller_id = _tenant_id(tok)
    db = _get_db()
    try:
        rows = db.execute(text(
            "SELECT placa, marca, modelo, año, color, tipo "
            "FROM vehiculos WHERE cliente_id=:c AND taller_id=:t"
        ), {"c": cid, "t": taller_id}).fetchall()
        return [{
            "placa": r[0], "marca": r[1], "modelo": r[2],
            "año": r[3], "color": r[4], "tipo": r[5],
        } for r in rows]
    finally:
        db.close()


@router.get("/api/clientes/{cid}/flota")
async def get_cliente_flota(cid: str, request: Request):
    """Vehículos del cliente con datos de conductor para módulo Gestión de Flotas.
    Devuelve {flota: [...]} con placa, vehículo, conductor, DNI, teléfono, estado."""
    tok = _auth(request)
    _require_staff(tok)
    taller_id = _tenant_id(tok)
    db = _get_db()
    try:
        # 2026-05-04 BUGFIX flota: has_conductor era solo (pin_hash IS NOT NULL).
        # Pero los conductores SIN PIN custom siguen siendo conductores asignados —
        # entran con la placa + RUC del cliente como PIN inicial (ver utils/flota.py
        # detect_login_role). Antes la UI mostraba "Sin asignar" aunque el nombre
        # estuviera lleno. Ahora has_conductor = TRUE si hay nombre, DNI, telefono o PIN.
        rows = db.execute(text(
            "SELECT placa, marca, modelo, \"año\" AS anio, color, tipo, "
            "       conductor_nombre, conductor_dni, conductor_telefono, "
            "       conductor_email, conductor_activo, conductor_pin_must_change, "
            "       (conductor_pin_hash IS NOT NULL) AS pin_set, "
            "       (COALESCE(NULLIF(TRIM(conductor_nombre), ''), "
            "                 NULLIF(TRIM(conductor_dni), ''), "
            "                 NULLIF(TRIM(conductor_telefono), '')) IS NOT NULL "
            "        OR conductor_pin_hash IS NOT NULL) AS has_conductor, "
            "       conductor_assigned_at "
            "FROM vehiculos WHERE cliente_id=:c AND taller_id=:t "
            "ORDER BY (COALESCE(NULLIF(TRIM(conductor_nombre), ''), "
            "                   NULLIF(TRIM(conductor_dni), ''), "
            "                   NULLIF(TRIM(conductor_telefono), '')) IS NOT NULL "
            "          OR conductor_pin_hash IS NOT NULL) DESC, "
            "         conductor_activo DESC NULLS LAST, placa"
        ), {"c": cid, "t": taller_id}).fetchall()
        flota = [{
            "placa": r[0], "marca": r[1], "modelo": r[2], "año": r[3],
            "color": r[4], "tipo": r[5],
            "conductor_nombre": r[6] or "",
            "conductor_dni": r[7] or "",
            "conductor_telefono": r[8] or "",
            "conductor_email": r[9] or "",
            # Si conductor_activo es NULL pero hay datos, asumir TRUE (default)
            "conductor_activo": (bool(r[10]) if r[10] is not None else bool(r[13])),
            "pin_must_change": bool(r[11]) if r[11] is not None else False,
            "pin_set": bool(r[12]),
            "has_conductor": bool(r[13]),
            "assigned_at": r[14].isoformat() if r[14] else None,
        } for r in rows]
        return {"flota": flota, "total": len(flota)}
    finally:
        db.close()

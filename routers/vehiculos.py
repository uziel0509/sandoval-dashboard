"""
routers/vehiculos.py — Vehículos asociados a clientes (multi-tenant).

Refactor 2026-04-21: taller_id del JWT via _tenant_id.
"""
from routers._common import (
    router, ADMIN_HTML,
    _auth, _get_db, _require_admin, _require_staff, _safe_date,
    _img_to_url, _parse_json_field, _make_token, _tenant_id,
    os, json, datetime, timedelta, Path,
    Request, HTTPException, UploadFile, File, List, HTMLResponse, text,
)
from fastapi import Query

@router.get("/api/vehiculos")
async def list_vehiculos(
    request: Request,
    q: str | None = None,
    limit: int = Query(300, ge=1, le=500),
):
    tok = _auth(request)
    _require_staff(tok)
    taller_id = _tenant_id(tok)
    db = _get_db()
    try:
        sql = """SELECT v.placa, v.marca, v.modelo, v.año, v.color, v.tipo, v.cliente_id,
                        c.nombre, c.apellidos
                 FROM vehiculos v LEFT JOIN clientes c ON c.id=v.cliente_id
                 WHERE v.taller_id=:t"""
        params = {"t": taller_id}
        if q:
            sql += " AND (v.placa ILIKE :q OR v.marca ILIKE :q OR c.nombre ILIKE :q)"
            params["q"] = f"%{q}%"
        sql += " ORDER BY v.placa LIMIT :lim"
        params["lim"] = limit
        rows = db.execute(text(sql), params).fetchall()
        return [{"placa": r[0], "marca": r[1], "modelo": r[2], "año": r[3], "color": r[4],
                 "tipo": r[5], "cliente_id": r[6],
                 "cliente": f"{r[7] or ''} {r[8] or ''}".strip()} for r in rows]
    finally:
        db.close()

@router.get("/api/vehiculos/{placa}")
async def get_vehiculo(placa: str, request: Request):
    tok = _auth(request)
    _require_staff(tok)
    taller_id = _tenant_id(tok)
    db = _get_db()
    try:
        row = db.execute(text(
            "SELECT placa, marca, modelo, año, color, tipo, cliente_id, vin, "
            "responsable, tel_responsable, observaciones "
            "FROM vehiculos WHERE placa=:p AND taller_id=:t"
        ), {"p": placa.upper(), "t": taller_id}).fetchone()
        if not row: raise HTTPException(404, "Vehículo no encontrado")
        return {"placa": row[0], "marca": row[1], "modelo": row[2], "anio": row[3],
                "color": row[4], "tipo": row[5], "cliente_id": row[6],
                "vin": row[7], "responsable": row[8], "tel_responsable": row[9],
                "observaciones": row[10]}
    finally:
        db.close()

@router.put("/api/vehiculos/{placa}")
async def update_vehiculo(placa: str, request: Request):
    tok = _auth(request)
    _require_staff(tok)
    taller_id = _tenant_id(tok)
    body = await request.json()
    db = _get_db()
    try:
        fields = ["marca", "modelo", "año", "color", "tipo", "cliente_id", "vin",
                  "responsable", "tel_responsable", "observaciones"]
        sets, params = [], {"p": placa.upper(), "t": taller_id}
        for f in fields:
            fk = "anio" if f == "año" else f
            if fk in body or f in body:
                sets.append(f"{f}=:{fk}"); params[fk] = body.get(fk, body.get(f))
        if sets:
            db.execute(text(f"UPDATE vehiculos SET {', '.join(sets)} WHERE placa=:p AND taller_id=:t"), params)
            db.commit()
        return {"ok": True}
    finally:
        db.close()

@router.post("/api/vehiculos")
async def create_vehiculo(request: Request):
    tok = _auth(request)
    _require_staff(tok)
    taller_id = _tenant_id(tok)
    body = await request.json()
    placa = (body.get("placa") or "").upper().strip()
    if not placa or not body.get("cliente_id"):
        raise HTTPException(400, "Placa y cliente requeridos")
    db = _get_db()
    try:
        # Valida que el cliente pertenezca al mismo taller antes de vincular
        cli_ok = db.execute(text(
            "SELECT 1 FROM clientes WHERE id=:c AND taller_id=:t"
        ), {"c": body["cliente_id"], "t": taller_id}).fetchone()
        if not cli_ok:
            raise HTTPException(400, "Cliente no válido para este taller")
        exists = db.execute(text(
            "SELECT 1 FROM vehiculos WHERE placa=:p AND taller_id=:t"
        ), {"p": placa, "t": taller_id}).fetchone()
        if exists:
            raise HTTPException(409, f"Ya existe un vehículo con placa {placa}")
        db.execute(text("""
            INSERT INTO vehiculos (taller_id, placa, cliente_id, marca, modelo, año, color, tipo)
            VALUES (:t, :p, :c, :mk, :mo, :y, :col, :tipo)
        """), {
            "t": taller_id, "p": placa, "c": body.get("cliente_id"),
            "mk": body.get("marca", ""), "mo": body.get("modelo", ""),
            "y": body.get("año"), "col": body.get("color", ""), "tipo": body.get("tipo", "auto"),
        })
        db.commit()
        return {"placa": placa}
    finally:
        db.close()

# ══════════════════════════════════════════════════════════════════════════════
# INVENTARIO
# ══════════════════════════════════════════════════════════════════════════════

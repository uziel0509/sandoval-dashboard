"""
routers/citas.py — Citas del taller (multi-tenant).

Refactor 2026-04-21: taller_id del JWT via _tenant_id (antes TALLER_ID global).
Limite parametrizado con Query bounds.
"""
from fastapi import Query
from routers._common import (
    router, ADMIN_HTML,
    _auth, _get_db, _require_admin, _require_staff, _safe_date,
    _img_to_url, _parse_json_field, _make_token, _tenant_id,
    os, json, datetime, timedelta, Path,
    Request, HTTPException, UploadFile, File, List, HTMLResponse, text,
)


@router.get("/api/citas")
async def list_citas(
    request: Request,
    estado: str = None,
    limit: int = Query(200, ge=1, le=500),
):
    tok = _auth(request)
    _require_staff(tok)
    taller_id = _tenant_id(tok)
    db = _get_db()
    try:
        # Si cita no tiene cliente_id, fallback a JOIN por placa con vehiculos
        sql = """SELECT ci.id, ci.cliente_id,
                        COALESCE(c.nombre, vc.nombre) AS nombre,
                        COALESCE(c.apellidos, vc.apellidos) AS apellidos,
                        COALESCE(c.telefono, vc.telefono) AS telefono,
                        ci.vehiculo_placa,
                        ci.fecha_cita, ci.hora, ci.motivo, ci.estado, ci.notas
                 FROM citas ci
                 LEFT JOIN clientes c ON c.id=ci.cliente_id AND c.taller_id=ci.taller_id
                 LEFT JOIN vehiculos v ON v.placa=ci.vehiculo_placa AND v.taller_id=ci.taller_id
                 LEFT JOIN clientes vc ON vc.id=v.cliente_id AND vc.taller_id=ci.taller_id
                 WHERE ci.taller_id=:t"""
        params = {"t": taller_id}
        if estado:
            sql += " AND ci.estado=:e"; params["e"] = estado
        sql += " ORDER BY ci.fecha_cita DESC, ci.hora LIMIT :lim"
        params["lim"] = limit
        rows = db.execute(text(sql), params).fetchall()
        return [{"id": r[0], "cliente_id": r[1],
                 "cliente": f"{r[2] or ''} {r[3] or ''}".strip(),
                 "telefono": r[4] or '',
                 "placa": r[5], "fecha": r[6], "hora": r[7],
                 "motivo": r[8], "estado": r[9], "notas": r[10]} for r in rows]
    finally:
        db.close()


@router.post("/api/citas")
async def create_cita(request: Request):
    tok = _auth(request)
    _require_staff(tok)
    taller_id = _tenant_id(tok)
    body = await request.json()
    db = _get_db()
    try:
        db.execute(text("""
            INSERT INTO citas (taller_id, cliente_id, vehiculo_placa, fecha_cita, hora,
                motivo, estado, notas, vista_admin)
            VALUES (:t, :c, :p, :f, :h, :m, 'programada', :n, 0)
        """), {
            "t": taller_id, "c": body.get("cliente_id"), "p": body.get("placa", ""),
            "f": body.get("fecha_cita") or body.get("fecha"),
            "h": body.get("hora_cita") or body.get("hora", ""),
            "m": body.get("motivo", ""), "n": body.get("notas", ""),
        })
        db.commit()
        return {"ok": True}
    finally:
        db.close()


@router.get("/api/citas/{cid}")
async def get_cita(cid: int, request: Request):
    tok = _auth(request)
    _require_staff(tok)
    taller_id = _tenant_id(tok)
    db = _get_db()
    try:
        row = db.execute(text(
            "SELECT id, cliente_id, vehiculo_placa, fecha_cita, hora, motivo, estado, notas "
            "FROM citas WHERE id=:id AND taller_id=:t"
        ), {"id": cid, "t": taller_id}).fetchone()
        if not row: raise HTTPException(404, "Cita no encontrada")
        return {"id": row[0], "cliente_id": row[1], "vehiculo_placa": row[2],
                "fecha_cita": row[3], "hora": row[4], "motivo": row[5],
                "estado": row[6], "notas": row[7]}
    finally:
        db.close()


@router.put("/api/citas/{cid}")
async def update_cita(cid: int, request: Request):
    tok = _auth(request)
    _require_staff(tok)
    taller_id = _tenant_id(tok)
    body = await request.json()
    db = _get_db()
    try:
        fields = ["estado", "hora", "fecha_cita", "motivo", "notas"]
        sets, params = [], {"id": cid, "t": taller_id}
        for f in fields:
            if f in body:
                sets.append(f"{f}=:{f}"); params[f] = body[f]
        if sets:
            db.execute(text(
                f"UPDATE citas SET {', '.join(sets)} WHERE id=:id AND taller_id=:t"
            ), params)
            db.commit()
        return {"ok": True}
    finally:
        db.close()

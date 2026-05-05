"""
routers/cotizaciones.py — Cotizaciones y sus items (multi-tenant).

Refactor 2026-04-21:
  * taller_id del JWT via _tenant_id (antes TALLER_ID global).
  * Fix cross-tenant: verificación explícita de pertenencia antes de DELETE de items
    en update_cotizacion (el DELETE previo no scopeaba por taller y podía borrar
    items de otro taller si el id colisionaba con una cotización ajena).
  * list_cotizaciones acepta limit y filtro q.
"""
from routers._common import (
    router, ADMIN_HTML,
    _auth, _get_db, _require_admin, _require_staff, _safe_date,
    _img_to_url, _parse_json_field, _make_token, _tenant_id,
    os, json, datetime, timedelta, Path,
    Request, HTTPException, UploadFile, File, List, HTMLResponse, text,
)
from fastapi import Query


def _norm_fecha(raw):
    if not raw:
        return None
    s = str(raw).strip()[:19]
    try:
        if len(s) == 10:
            datetime.strptime(s, "%Y-%m-%d"); return s + " 12:00:00"
        datetime.strptime(s.replace("T", " "), "%Y-%m-%d %H:%M:%S"); return s.replace("T", " ")
    except Exception:
        try:
            datetime.strptime(s[:16].replace("T", " "), "%Y-%m-%d %H:%M")
            return s.replace("T", " ") + ":00"
        except Exception:
            return None


@router.get("/api/cotizaciones")
async def list_cotizaciones(
    request: Request,
    q: str | None = None,
    estado: str | None = None,
    limit: int = Query(200, ge=1, le=500),
):
    tok = _auth(request); _require_staff(tok)
    taller_id = _tenant_id(tok)
    db = _get_db()
    try:
        sql = """SELECT c.id, c.numero, c.fecha_creacion as fecha, c.cliente_id,
                        c.nombre_cliente, c.estado, c.total,
                        cl.nombre, cl.apellidos
                 FROM cotizaciones c LEFT JOIN clientes cl ON cl.id=c.cliente_id
                 WHERE c.taller_id=:t"""
        params = {"t": taller_id}
        if estado:
            sql += " AND c.estado=:est"; params["est"] = estado
        if q:
            sql += " AND (c.numero ILIKE :q OR c.nombre_cliente ILIKE :q OR cl.nombre ILIKE :q)"
            params["q"] = f"%{q}%"
        sql += " ORDER BY c.id DESC LIMIT :lim"
        params["lim"] = limit
        rows = db.execute(text(sql), params).fetchall()
        return [{"id": r[0], "numero": r[1], "fecha": _safe_date(r[2]),
                 "cliente_id": r[3],
                 "nombre_cliente": r[4] or f"{r[7] or ''} {r[8] or ''}".strip(),
                 "estado": r[5], "total": r[6]} for r in rows]
    finally:
        db.close()


@router.get("/api/cotizaciones/{cid}")
async def get_cotizacion(cid: int, request: Request):
    tok = _auth(request); _require_staff(tok)
    taller_id = _tenant_id(tok)
    db = _get_db()
    try:
        row = db.execute(text(
            "SELECT id, numero, fecha_creacion, cliente_id, nombre_cliente, estado, total, nota "
            "FROM cotizaciones WHERE id=:id AND taller_id=:t"
        ), {"id": cid, "t": taller_id}).fetchone()
        if not row:
            raise HTTPException(404, "Cotización no encontrada")
        items = db.execute(text(
            "SELECT descripcion, tipo, cantidad, precio_unitario, subtotal "
            "FROM cotizacion_items WHERE cotizacion_id=:id ORDER BY id"
        ), {"id": cid}).fetchall()
        return {"id": row[0], "numero": row[1], "fecha": _safe_date(row[2]),
                "cliente_id": row[3], "nombre_cliente": row[4], "estado": row[5],
                "total": row[6], "nota": row[7],
                "items": [{"descripcion": i[0], "tipo": i[1], "cantidad": i[2],
                           "precio_unitario": i[3], "subtotal": i[4]} for i in items]}
    finally:
        db.close()


@router.post("/api/cotizaciones")
async def create_cotizacion(request: Request):
    tok = _auth(request); _require_staff(tok)
    taller_id = _tenant_id(tok)
    body = await request.json()
    db = _get_db()
    try:
        fecha_custom = _norm_fecha(body.get("fecha"))
        fecha_dia = (fecha_custom[:10] if fecha_custom else datetime.now().strftime("%Y-%m-%d"))
        count = db.execute(text(
            "SELECT COUNT(*) FROM cotizaciones WHERE taller_id=:t AND CAST(fecha_creacion AS date)=CAST(:d AS date)"
        ), {"t": taller_id, "d": fecha_dia}).fetchone()[0]
        numero = f"COT-{fecha_dia.replace('-','')}-{str(count+1).zfill(3)}"
        items = body.get("items", [])
        total = sum(float(i.get("subtotal", 0)) for i in items)
        base_params = {
            "t": taller_id, "n": numero,
            "c": body.get("cliente_id"),
            "cn": body.get("nombre_cliente", ""),
            "tot": total, "nota": body.get("nota", ""),
            "cp": tok.get("nombre", ""),
        }
        if fecha_custom:
            base_params["fc"] = fecha_custom
            cot_id = db.execute(text("""
                INSERT INTO cotizaciones (taller_id, numero, cliente_id, nombre_cliente,
                    estado, total, nota, creado_por, fecha_creacion)
                VALUES (:t, :n, :c, :cn, 'PENDIENTE', :tot, :nota, :cp, CAST(:fc AS timestamp))
                RETURNING id
            """), base_params).fetchone()[0]
        else:
            cot_id = db.execute(text("""
                INSERT INTO cotizaciones (taller_id, numero, cliente_id, nombre_cliente,
                    estado, total, nota, creado_por, fecha_creacion)
                VALUES (:t, :n, :c, :cn, 'PENDIENTE', :tot, :nota, :cp, NOW())
                RETURNING id
            """), base_params).fetchone()[0]
        for item in items:
            db.execute(text("""
                INSERT INTO cotizacion_items (cotizacion_id, descripcion, tipo, cantidad, precio_unitario, subtotal)
                VALUES (:id, :desc, :tipo, :cant, :pu, :sub)
            """), {
                "id": cot_id, "desc": item.get("nombre") or item.get("descripcion", ""),
                "tipo": item.get("tipo", "servicio"),
                "cant": item.get("cantidad", 1), "pu": item.get("precio_unitario", 0),
                "sub": item.get("subtotal", 0),
            })
        db.commit()
        return {"id": cot_id, "numero": numero}
    finally:
        db.close()


@router.put("/api/cotizaciones/{cid}")
async def update_cotizacion(cid: int, request: Request):
    tok = _auth(request); _require_staff(tok)
    taller_id = _tenant_id(tok)
    body = await request.json()
    db = _get_db()
    try:
        # Verificación de pertenencia antes de cualquier escritura.
        # Sin esto, el DELETE de items podría borrar datos de otro taller.
        owner = db.execute(text(
            "SELECT 1 FROM cotizaciones WHERE id=:id AND taller_id=:t"
        ), {"id": cid, "t": taller_id}).fetchone()
        if not owner:
            raise HTTPException(404, "Cotización no encontrada")

        items = body.get("items", [])
        total = round(sum(float(i.get("subtotal", 0)) for i in items), 2)
        fecha_custom = _norm_fecha(body.get("fecha"))
        update_params = {
            "cn": body.get("nombre_cliente", ""),
            "est": body.get("estado", "PENDIENTE"),
            "tot": total, "nota": body.get("nota", ""),
            "id": cid, "t": taller_id,
        }
        if fecha_custom:
            update_params["fc"] = fecha_custom
            db.execute(text("""
                UPDATE cotizaciones SET nombre_cliente=:cn, estado=:est, total=:tot, nota=:nota,
                    fecha_creacion=CAST(:fc AS timestamp), fecha=CAST(:fc AS timestamp)
                WHERE id=:id AND taller_id=:t
            """), update_params)
        else:
            db.execute(text("""
                UPDATE cotizaciones SET nombre_cliente=:cn, estado=:est, total=:tot, nota=:nota
                WHERE id=:id AND taller_id=:t
            """), update_params)
        db.execute(text("DELETE FROM cotizacion_items WHERE cotizacion_id=:id"), {"id": cid})
        for item in items:
            db.execute(text("""
                INSERT INTO cotizacion_items
                    (cotizacion_id, descripcion, tipo, cantidad, precio_unitario, subtotal)
                VALUES (:cid, :desc, :tipo, :cant, :pu, :sub)
            """), {
                "cid": cid,
                "desc": item.get("descripcion") or item.get("nombre", ""),
                "tipo": item.get("tipo", "servicio"),
                "cant": float(item.get("cantidad", 1)),
                "pu": float(item.get("precio_unitario", 0)),
                "sub": float(item.get("subtotal", 0)),
            })
        db.commit()
        return {"ok": True, "total": total}
    finally:
        db.close()

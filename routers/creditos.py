"""
routers/creditos.py — Créditos y abonos (multi-tenant).

Refactor 2026-04-21:
  * taller_id del JWT via _tenant_id (antes usaba fallback a TALLER_ID global si
    el JWT no traía taller_id — peligroso: un token sin claim caía a taller 1).
  * abono_credito: SELECT ... FOR UPDATE para evitar sobrepago por concurrencia.
  * list_creditos con limit validado.
"""
from routers._common import (
    router, ADMIN_HTML,
    _auth, _get_db, _require_admin, _require_staff, _safe_date,
    _img_to_url, _parse_json_field, _make_token, _tenant_id,
    os, json, datetime, timedelta, Path,
    Request, HTTPException, UploadFile, File, List, HTMLResponse, text,
)
from fastapi import Query


def _norm_dia(raw):
    """Convierte YYYY-MM-DD a date str. Retorna None si inválido."""
    if not raw:
        return None
    s = str(raw).strip()[:10]
    try:
        datetime.strptime(s, "%Y-%m-%d"); return s
    except Exception:
        return None


@router.get("/api/creditos")
async def list_creditos(
    request: Request,
    limit: int = Query(200, ge=1, le=500),
):
    tok = _auth(request); _require_staff(tok)
    taller_id = _tenant_id(tok)
    db = _get_db()
    try:
        rows = db.execute(text("""
            SELECT id, cliente_nombre, telefono, descripcion, total, pendiente, estado,
                   nota, fecha_venta, fecha_amortizacion, items_json
            FROM creditos WHERE taller_id=:tid
            ORDER BY id DESC LIMIT :lim
        """), {"tid": taller_id, "lim": limit}).fetchall()
        return [{"id": r[0], "cliente": r[1], "telefono": r[2], "descripcion": r[3],
                 "total": r[4], "pendiente": r[5], "estado": r[6], "nota": r[7],
                 "fecha_venta": r[8], "fecha_amortizacion": r[9],
                 "items": _parse_json_field(r[10])} for r in rows]
    finally:
        db.close()


@router.post("/api/creditos")
async def create_credito(request: Request):
    tok = _auth(request); _require_staff(tok)
    taller_id = _tenant_id(tok)
    body = await request.json()
    if not body.get("cliente_nombre") or not body.get("total"):
        raise HTTPException(400, "Cliente y total requeridos")
    fecha = _norm_dia(body.get("fecha")) or datetime.now().strftime("%Y-%m-%d")
    items = body.get("items", []) or []
    db = _get_db()
    try:
        res = db.execute(text("""
            INSERT INTO creditos (taller_id, cliente_nombre, telefono, descripcion, items_json,
                total, pendiente, estado, nota, fecha_venta, fecha_venta_dt, creado_por)
            VALUES (:tid, :cn, :tel, :desc, :items, :tot, :tot, 'PENDIENTE', :nota, :fv, CAST(:fv AS date), :cp)
            RETURNING id
        """), {
            "tid": taller_id, "cn": body.get("cliente_nombre"),
            "tel": body.get("telefono", ""),
            "desc": body.get("descripcion", ""),
            "items": json.dumps(items),
            "tot": float(body["total"]), "nota": body.get("nota", ""),
            "fv": fecha, "cp": tok.get("nombre", "admin"),
        })
        credito_id = res.scalar()
        # Descontar stock para cada repuesto con codigo del inventario.
        # GREATEST(stock-q, 0) evita negativos si UI desincronizada; taller_id aisla tenant.
        for it in items:
            if not isinstance(it, dict):
                continue
            categoria = (it.get("categoria") or "").strip().lower()
            codigo = (it.get("codigo") or "").strip() if it.get("codigo") else ""
            if categoria != "repuesto" or not codigo:
                continue
            try:
                cantidad = float(it.get("cantidad") or 0)
            except (TypeError, ValueError):
                cantidad = 0
            if cantidad <= 0:
                continue
            db.execute(text(
                "UPDATE inventario SET stock = GREATEST(stock - :q, 0) "
                "WHERE codigo=:c AND taller_id=:t"
            ), {"q": cantidad, "c": codigo, "t": taller_id})
        db.commit()
        return {"ok": True, "id": credito_id, "fecha_venta": fecha}
    finally:
        db.close()


@router.post("/api/creditos/{cid}/abono")
async def abono_credito(cid: int, request: Request):
    tok = _auth(request); _require_staff(tok)
    taller_id = _tenant_id(tok)
    body = await request.json()
    monto = float(body.get("monto", 0))
    if monto <= 0:
        raise HTTPException(400, "Monto inválido")
    fecha = _norm_dia(body.get("fecha")) or datetime.now().strftime("%Y-%m-%d")
    db = _get_db()
    try:
        # Lock de fila para cálculo consistente del saldo frente a abonos concurrentes.
        credito = db.execute(text(
            "SELECT pendiente FROM creditos WHERE id=:id AND taller_id=:tid FOR UPDATE"
        ), {"id": cid, "tid": taller_id}).fetchone()
        if not credito:
            raise HTTPException(404, "Crédito no encontrado")
        nuevo_pend = max(0, (credito[0] or 0) - monto)
        nuevo_estado = "PAGADO" if nuevo_pend == 0 else "PARCIAL"
        db.execute(text(
            "UPDATE creditos SET pendiente=:p, estado=:e WHERE id=:id AND taller_id=:tid"
        ), {"p": nuevo_pend, "e": nuevo_estado, "id": cid, "tid": taller_id})
        db.execute(text("""
            INSERT INTO abonos_credito (taller_id, credito_id, monto, nota, metodo_pago, fecha, fecha_dt)
            VALUES (:tid, :c, :m, :n, :mp, :f, CAST(:f AS date))
        """), {
            "tid": taller_id, "c": cid, "m": monto, "n": body.get("nota", ""),
            "mp": body.get("metodo_pago", "Efectivo"), "f": fecha,
        })
        db.commit()
        return {"ok": True, "pendiente": nuevo_pend, "estado": nuevo_estado, "fecha": fecha}
    finally:
        db.close()


@router.put('/api/creditos/{cid}')
async def update_credito(cid: int, request: Request):
    tok = _auth(request); _require_staff(tok)
    taller_id = _tenant_id(tok)
    body = await request.json()
    fecha = _norm_dia(body.get("fecha"))
    db = _get_db()
    try:
        if fecha:
            db.execute(text('''
                UPDATE creditos SET cliente_nombre=:cn, telefono=:tel, descripcion=:desc,
                nota=:nota, fecha_venta=:fv, fecha_venta_dt=:fvd
                WHERE id=:id AND taller_id=:tid
            '''), {
                "cn": body.get("cliente_nombre", ""), "tel": body.get("telefono", ""),
                "desc": body.get("descripcion", ""), "nota": body.get("nota", ""),
                "fv": fecha, "fvd": fecha, "id": cid, "tid": taller_id
            })
        else:
            db.execute(text('''
                UPDATE creditos SET cliente_nombre=:cn, telefono=:tel, descripcion=:desc, nota=:nota
                WHERE id=:id AND taller_id=:tid
            '''), {
                "cn": body.get("cliente_nombre", ""), "tel": body.get("telefono", ""),
                "desc": body.get("descripcion", ""), "nota": body.get("nota", ""),
                "id": cid, "tid": taller_id
            })
        if "total" in body:
            db.execute(text(
                "UPDATE creditos SET total=:tot, pendiente=:tot, items_json=:items "
                "WHERE id=:id AND taller_id=:tid"
            ), {"tot": float(body["total"]),
                "items": json.dumps(body.get("items", [])),
                "id": cid, "tid": taller_id})
        db.commit()
        return {"ok": True}
    finally:
        db.close()

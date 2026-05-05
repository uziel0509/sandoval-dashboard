"""
routers/cuentas_bancarias.py — CRUD de cuentas bancarias del taller.
Multi-tenant: filtra por taller_id del JWT.
"""
from routers._common import (
    router, _auth, _get_db, _require_admin, _require_staff,
    _tenant_id, Request, HTTPException, text,
)


@router.get("/api/cuentas-bancarias")
async def list_cuentas_bancarias(request: Request):
    tok = _auth(request)
    _require_staff(tok)
    taller_id = _tenant_id(tok)
    db = _get_db()
    try:
        rows = db.execute(text(
            "SELECT id, banco, titular, numero_cuenta, cci, tipo, moneda, activa, orden, "
            "COALESCE(telefono, '') "
            "FROM cuentas_bancarias WHERE taller_id=:t "
            "ORDER BY orden ASC, id ASC"
        ), {"t": taller_id}).fetchall()
        return [{
            "id": r[0], "banco": r[1], "titular": r[2],
            "numero_cuenta": r[3], "cci": r[4], "tipo": r[5],
            "moneda": r[6], "activa": bool(r[7]), "orden": r[8],
            "telefono": r[9],
        } for r in rows]
    finally:
        db.close()


@router.post("/api/cuentas-bancarias")
async def create_cuenta_bancaria(request: Request):
    tok = _auth(request)
    _require_admin(tok)
    taller_id = _tenant_id(tok)
    body = await request.json()
    banco = (body.get("banco") or "").strip()
    if not banco:
        raise HTTPException(400, "El banco es obligatorio")
    db = _get_db()
    try:
        r = db.execute(text(
            "INSERT INTO cuentas_bancarias "
            "(taller_id, banco, titular, numero_cuenta, cci, tipo, moneda, activa, orden, telefono) "
            "VALUES (:t, :b, :tit, :nc, :cci, :tp, :m, :a, :o, :tel) RETURNING id"
        ), {
            "t": taller_id,
            "b": banco[:60],
            "tit": (body.get("titular") or "").strip()[:120],
            "nc": (body.get("numero_cuenta") or "").strip()[:40],
            "cci": (body.get("cci") or "").strip()[:40],
            "tp": (body.get("tipo") or "Ahorros").strip()[:30],
            "m": (body.get("moneda") or "PEN").strip()[:10],
            "a": bool(body.get("activa", True)),
            "o": int(body.get("orden") or 0),
            "tel": (body.get("telefono") or "").strip()[:30],
        }).fetchone()
        db.commit()
        return {"ok": True, "id": r[0]}
    finally:
        db.close()


@router.put("/api/cuentas-bancarias/{cuenta_id}")
async def update_cuenta_bancaria(cuenta_id: int, request: Request):
    tok = _auth(request)
    _require_admin(tok)
    taller_id = _tenant_id(tok)
    body = await request.json()
    allowed = {
        "banco": 60, "titular": 120, "numero_cuenta": 40, "cci": 40,
        "tipo": 30, "moneda": 10, "telefono": 30,
    }
    sets, params = [], {"id": cuenta_id, "t": taller_id}
    for k, maxlen in allowed.items():
        if k in body:
            v = (body.get(k) or "").strip()[:maxlen]
            sets.append(f"{k}=:{k}"); params[k] = v
    if "activa" in body:
        sets.append("activa=:activa"); params["activa"] = bool(body["activa"])
    if "orden" in body:
        sets.append("orden=:orden"); params["orden"] = int(body["orden"] or 0)
    if not sets:
        raise HTTPException(400, "Nada que actualizar")
    db = _get_db()
    try:
        db.execute(text(
            f"UPDATE cuentas_bancarias SET {', '.join(sets)} "
            "WHERE id=:id AND taller_id=:t"
        ), params)
        db.commit()
        return {"ok": True}
    finally:
        db.close()


@router.delete("/api/cuentas-bancarias/{cuenta_id}")
async def delete_cuenta_bancaria(cuenta_id: int, request: Request):
    tok = _auth(request)
    _require_admin(tok)
    taller_id = _tenant_id(tok)
    db = _get_db()
    try:
        db.execute(text(
            "DELETE FROM cuentas_bancarias WHERE id=:id AND taller_id=:t"
        ), {"id": cuenta_id, "t": taller_id})
        db.commit()
        return {"ok": True}
    finally:
        db.close()


# ─────────── Short link generator para aprobación ────────────
@router.post("/api/ordenes/{consecutivo}/share-link")
async def share_link_orden(consecutivo: str, request: Request):
    """Devuelve (o crea) un código corto base62 de 6 caracteres que redirige
    al token completo de aprobación. Así WhatsApp no rompe el URL.
    """
    import secrets, string
    tok = _auth(request)
    _require_staff(tok)
    taller_id = _tenant_id(tok)
    db = _get_db()
    try:
        row = db.execute(text(
            "SELECT approval_token FROM ordenes WHERE consecutivo=:c AND taller_id=:t"
        ), {"c": consecutivo, "t": taller_id}).fetchone()
        if not row:
            raise HTTPException(404, "Orden no encontrada")
        token = row[0]
        if not token or str(token).startswith("USED_"):
            import uuid
            token = uuid.uuid4().hex
            db.execute(text(
                "UPDATE ordenes SET approval_token=:tok WHERE consecutivo=:c AND taller_id=:t"
            ), {"tok": token, "c": consecutivo, "t": taller_id})
            db.commit()

        # Reutilizar si ya existe un short-link vigente para este token
        existing = db.execute(text(
            "SELECT code FROM short_links WHERE token=:tok AND taller_id=:t "
            "ORDER BY created_at DESC LIMIT 1"
        ), {"tok": token, "t": taller_id}).fetchone()
        if existing:
            return {"ok": True, "code": existing[0], "token": token}

        alphabet = string.ascii_letters + string.digits
        for _ in range(10):
            code = ''.join(secrets.choice(alphabet) for _ in range(6))
            dup = db.execute(text(
                "SELECT 1 FROM short_links WHERE code=:c"
            ), {"c": code}).fetchone()
            if not dup:
                break
        else:
            raise HTTPException(500, "No se pudo generar código corto")

        db.execute(text(
            "INSERT INTO short_links (code, token, taller_id, kind) "
            "VALUES (:c, :tok, :t, 'aprobacion')"
        ), {"c": code, "tok": token, "t": taller_id})
        db.commit()
        return {"ok": True, "code": code, "token": token}
    finally:
        db.close()

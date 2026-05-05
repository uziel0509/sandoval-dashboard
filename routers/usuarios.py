"""
routers/usuarios.py — Gestión de usuarios del taller (multi-tenant).

Refactor 2026-04-21:
  * taller_id del JWT via _tenant_id (antes TALLER_ID global).
  * Fix latente: bcrypt ahora se importa desde _common explícitamente
    (antes se usaba sin importarlo — NameError si otros módulos no lo cargaban).
  * update_usuario valida que al menos un campo venga en el body.
"""
from utils.password_policy import validate_password_strength
from routers._common import (
    router, ADMIN_HTML,
    _auth, _get_db, _require_admin, _safe_date,
    _img_to_url, _parse_json_field, _make_token, _tenant_id,
    os, json, datetime, timedelta, Path,
    Request, HTTPException, UploadFile, File, List, HTMLResponse, text,
    bcrypt,
)


@router.get("/api/usuarios")
async def list_usuarios(request: Request):
    tok = _auth(request)
    _require_admin(tok)
    taller_id = _tenant_id(tok)
    db = _get_db()
    try:
        rows = db.execute(text(
            "SELECT id, username, nombre, rol, email, activo, ultimo_login, fecha_creacion "
            "FROM usuarios WHERE taller_id=:t ORDER BY nombre"
        ), {"t": taller_id}).fetchall()
        return [{"id": r[0], "username": r[1], "nombre": r[2], "rol": r[3],
                 "email": r[4], "activo": r[5], "ultimo_login": _safe_date(r[6]),
                 "fecha_creacion": _safe_date(r[7])} for r in rows]
    finally:
        db.close()


@router.post("/api/usuarios")
async def create_usuario(request: Request):
    tok = _auth(request)
    _require_admin(tok)
    taller_id = _tenant_id(tok)
    body = await request.json()
    if not body.get("username") or not body.get("password"):
        raise HTTPException(400, "Usuario y contraseña requeridos")
    _ok, _why = validate_password_strength(body["password"], role=body.get("rol", "tecnico"))
    if not _ok:
        raise HTTPException(400, f"Contraseña debil: {_why}")
    db = _get_db()
    try:
        exists = db.execute(text(
            "SELECT 1 FROM usuarios WHERE username=:u AND taller_id=:t"
        ), {"u": body["username"], "t": taller_id}).fetchone()
        if exists:
            raise HTTPException(409, "Usuario ya existe")
        ph = bcrypt.hashpw(body["password"].encode(), bcrypt.gensalt()).decode()
        db.execute(text("""
            INSERT INTO usuarios (taller_id, username, password_hash, nombre, rol, email, activo, fecha_creacion)
            VALUES (:t, :u, :ph, :n, :rol, :e, TRUE, NOW())
        """), {
            "t": taller_id, "u": body["username"], "ph": ph,
            "n": body.get("nombre", body["username"]),
            "rol": body.get("rol", "tecnico"), "e": body.get("email", ""),
        })
        db.commit()
        return {"ok": True}
    finally:
        db.close()


@router.put("/api/usuarios/{uid}")
async def update_usuario(uid: int, request: Request):
    tok = _auth(request)
    _require_admin(tok)
    taller_id = _tenant_id(tok)
    body = await request.json()
    db = _get_db()
    try:
        sets, params = [], {"id": uid, "t": taller_id}
        for f in ["nombre", "rol", "email", "activo"]:
            if f in body:
                sets.append(f"{f}=:{f}"); params[f] = body[f]
        if "password" in body and body["password"]:
            _ok, _why = validate_password_strength(body["password"], role=body.get("rol", "tecnico"))
            if not _ok:
                raise HTTPException(400, f"Contraseña debil: {_why}")
            ph = bcrypt.hashpw(body["password"].encode(), bcrypt.gensalt()).decode()
            sets.append("password_hash=:ph"); params["ph"] = ph
        if sets:
            db.execute(text(
                f"UPDATE usuarios SET {', '.join(sets)} WHERE id=:id AND taller_id=:t"
            ), params)
            db.commit()
        return {"ok": True}
    finally:
        db.close()

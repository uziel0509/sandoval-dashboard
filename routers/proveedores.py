"""
routers/proveedores.py — Proveedores del taller (multi-tenant).

Refactor 2026-04-21 (Fase B.1):
  - Upsert por (taller_id, ruc): si el RUC ya existe, agrega el nombre al array
    `alias` y conserva como nombre canónico el más largo.
  - GET/POST/PUT devuelven ruc + alias[].
  - PUT maneja cambio de RUC con control de colisión contra el índice único.
  - Elimina el bug "Lubrillantas vs Lubrillantas Jesús de Nazaret".

Contrato preservado:
  - Endpoints y verbos HTTP idénticos → el portal PC sigue funcionando sin
    cambios (usa POST raramente).
  - El body sigue aceptando `nombre`, `email`, `telefono`, `direccion`,
    `ciudad`, `tipo`, `productos`. Ahora además acepta `ruc` y `alias`.
"""
import re

from routers._common import (
    router, ADMIN_HTML,
    _auth, _get_db, _require_admin, _require_staff, _safe_date,
    _img_to_url, _parse_json_field, _make_token, _tenant_id,
    os, json, datetime, timedelta, Path,
    Request, HTTPException, UploadFile, File, List, HTMLResponse, text,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
_RUC_VALID_RE = re.compile(r"^[A-Z0-9\-]{3,20}$")


def _pick_ruc(body: dict) -> str:
    """Normaliza y valida el RUC/DNI/CI recibido en el body.

    Reglas:
      - Trim, mayúsculas, colapsa espacios internos.
      - Rechaza placeholders OCR ('CLI-*', 'N/A', '---').
      - Máx. 20 chars, set [A-Z0-9-].
      - Retorna '' si no hay RUC válido → proveedor sin RUC (permitido por
        el índice único filtrado WHERE ruc <> '').
    """
    raw = (body.get("ruc") or "").strip().upper()
    if not raw:
        return ""
    raw = re.sub(r"\s+", "", raw)
    if raw.startswith("CLI-") or raw in ("N/A", "NA", "---", "SIN RUC", "SINRUC"):
        return ""
    if not _RUC_VALID_RE.match(raw):
        return ""
    return raw[:20]


def _canonical_nombre(existing: str, incoming: str) -> str:
    """Elige como nombre canónico el más largo (asume que es el más completo).

    Empate → conserva el existente para no generar ruido en el historial.
    """
    e = (existing or "").strip()
    i = (incoming or "").strip()
    if not e:
        return i
    if not i:
        return e
    return i if len(i) > len(e) else e


def _merge_alias(current: list, *candidates: str) -> list:
    """Fusiona aliases sin duplicados (case-insensitive), máx. 10 elementos."""
    seen = set()
    out = []
    for v in list(current or []) + list(candidates):
        v = (v or "").strip()
        if not v:
            continue
        k = v.lower()
        if k in seen:
            continue
        seen.add(k)
        out.append(v)
        if len(out) >= 10:
            break
    return out


def _row_to_dict(r) -> dict:
    """Serializa una fila de proveedores al shape que consume el frontend."""
    return {
        "id":        r[0],
        "nombre":    r[1],
        "email":     r[2],
        "telefono":  r[3],
        "direccion": r[4],
        "ciudad":    r[5],
        "tipo":      r[6],
        "ruc":       r[7] or "",
        "alias":     list(r[8] or []),
    }


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/proveedores
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/api/proveedores")
async def list_proveedores(request: Request):
    tok = _auth(request)
    _require_staff(tok)
    taller_id = _tenant_id(tok)
    db = _get_db()
    try:
        rows = db.execute(text(
            "SELECT id, nombre, email, telefono, direccion, ciudad, tipo, ruc, alias "
            "FROM proveedores WHERE taller_id=:t ORDER BY nombre"
        ), {"t": taller_id}).fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        db.close()


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/proveedores  — upsert por (taller_id, ruc)
# ─────────────────────────────────────────────────────────────────────────────
@router.post("/api/proveedores")
async def create_proveedor(request: Request):
    """Crea o fusiona un proveedor.

    Flujo:
      1. Si llega RUC válido y ya existe (taller_id, ruc) → MERGE:
         actualiza nombre al canónico (más largo), agrega alias, refresca
         campos opcionales si vienen no vacíos. Responde 200 con merged=True.
      2. Si no existe match por RUC → INSERT nuevo con ruc + alias iniciales.
      3. Si no hay RUC y existe un proveedor homónimo (LOWER(nombre)) → MERGE
         blando: agrega alias, no toca ruc. Esto absorbe el caso en que el
         usuario tipea el mismo nombre dos veces sin RUC.
    """
    tok = _auth(request)
    _require_admin(tok)
    taller_id = _tenant_id(tok)
    body = await request.json()

    nombre_in = (body.get("nombre") or "").strip()
    if not nombre_in:
        raise HTTPException(400, "Nombre requerido")

    ruc = _pick_ruc(body)
    extra_alias = body.get("alias") or []
    if isinstance(extra_alias, str):
        extra_alias = [extra_alias]

    db = _get_db()
    try:
        existing = None
        if ruc:
            existing = db.execute(text(
                "SELECT id, nombre, email, telefono, direccion, ciudad, tipo, ruc, alias "
                "FROM proveedores WHERE taller_id=:t AND ruc=:ruc"
            ), {"t": taller_id, "ruc": ruc}).fetchone()

        if existing is None:
            existing = db.execute(text(
                "SELECT id, nombre, email, telefono, direccion, ciudad, tipo, ruc, alias "
                "FROM proveedores WHERE taller_id=:t AND LOWER(TRIM(nombre))=LOWER(TRIM(:n)) "
                "LIMIT 1"
            ), {"t": taller_id, "n": nombre_in}).fetchone()

        if existing is not None:
            pid         = existing[0]
            cur_nombre  = existing[1]
            cur_ruc     = existing[7] or ""
            cur_alias   = list(existing[8] or [])

            new_nombre = _canonical_nombre(cur_nombre, nombre_in)
            new_alias  = _merge_alias(cur_alias, cur_nombre, nombre_in, *extra_alias)
            new_ruc    = ruc or cur_ruc

            sets = ["nombre=:n", "alias=:al", "ruc=:ruc"]
            params = {
                "id": pid, "t": taller_id,
                "n": new_nombre, "al": new_alias, "ruc": new_ruc,
            }
            for key, col in (("email", "email"), ("telefono", "telefono"),
                             ("direccion", "direccion"), ("ciudad", "ciudad"),
                             ("tipo", "tipo"), ("productos", "productos")):
                v = body.get(key)
                if v:
                    sets.append(f"{col}=:{key}")
                    params[key] = v

            db.execute(text(
                f"UPDATE proveedores SET {', '.join(sets)} "
                f"WHERE id=:id AND taller_id=:t"
            ), params)
            db.commit()
            return {"ok": True, "merged": True, "id": pid,
                    "nombre": new_nombre, "ruc": new_ruc, "alias": new_alias}

        initial_alias = _merge_alias([], *extra_alias)
        # `proveedores.id` es VARCHAR(20) NOT NULL sin default — usamos el RUC
        # como id natural si lo hay (criterio de negocio: 1 RUC = 1 proveedor),
        # o generamos uno con prefijo PROV- si el caller no envió RUC.
        import hashlib as _hashlib
        if ruc and len(ruc) >= 8:
            new_id = ruc[:20]
        elif body.get("id"):
            new_id = str(body["id"])[:20]
        else:
            new_id = ("PROV-" + _hashlib.md5(nombre_in.encode()).hexdigest()[:6].upper())[:20]

        row = db.execute(text("""
            INSERT INTO proveedores (id, taller_id, nombre, email, telefono, direccion,
                                     ciudad, tipo, productos, ruc, alias)
            VALUES (:id, :t, :n, :e, :tel, :dir, :ciu, :tipo, :prod, :ruc, :al)
            RETURNING id
        """), {
            "id": new_id,
            "t": taller_id, "n": nombre_in,
            "e": body.get("email", ""), "tel": body.get("telefono", ""),
            "dir": body.get("direccion", ""), "ciu": body.get("ciudad", ""),
            "tipo": body.get("tipo", ""), "prod": body.get("productos", ""),
            "ruc": ruc, "al": initial_alias,
        }).fetchone()
        db.commit()
        return {"ok": True, "merged": False, "id": row[0],
                "nombre": nombre_in, "ruc": ruc, "alias": initial_alias}
    finally:
        db.close()


# ─────────────────────────────────────────────────────────────────────────────
# PUT /api/proveedores/{pid}
# ─────────────────────────────────────────────────────────────────────────────
@router.put("/api/proveedores/{pid}")
async def update_proveedor(pid: int, request: Request):
    tok = _auth(request)
    _require_admin(tok)
    taller_id = _tenant_id(tok)
    body = await request.json()
    db = _get_db()
    try:
        sets, params = [], {"id": pid, "t": taller_id}
        for f in ("nombre", "email", "telefono", "direccion", "ciudad", "tipo", "productos"):
            if f in body:
                sets.append(f"{f}=:{f}")
                params[f] = body[f]

        if "ruc" in body:
            new_ruc = _pick_ruc(body)
            if new_ruc:
                clash = db.execute(text(
                    "SELECT id FROM proveedores "
                    "WHERE taller_id=:t AND ruc=:ruc AND id<>:id LIMIT 1"
                ), {"t": taller_id, "ruc": new_ruc, "id": pid}).fetchone()
                if clash:
                    raise HTTPException(
                        409,
                        f"RUC {new_ruc} ya pertenece al proveedor id={clash[0]}. "
                        f"Fusionar manualmente o usar POST (upsert)."
                    )
            sets.append("ruc=:ruc"); params["ruc"] = new_ruc

        if "alias" in body:
            al = body.get("alias") or []
            if isinstance(al, str):
                al = [al]
            sets.append("alias=:al"); params["al"] = _merge_alias([], *al)

        if sets:
            db.execute(text(
                f"UPDATE proveedores SET {', '.join(sets)} WHERE id=:id AND taller_id=:t"
            ), params)
            db.commit()
        return {"ok": True}
    finally:
        db.close()


# ─────────────────────────────────────────────────────────────────────────────
# DELETE /api/proveedores/{pid}
# ─────────────────────────────────────────────────────────────────────────────
@router.delete("/api/proveedores/{pid}")
async def delete_proveedor(pid: int, request: Request):
    tok = _auth(request)
    _require_admin(tok)
    taller_id = _tenant_id(tok)
    db = _get_db()
    try:
        db.execute(text(
            "DELETE FROM proveedores WHERE id=:id AND taller_id=:t"
        ), {"id": pid, "t": taller_id})
        db.commit()
        return {"ok": True}
    finally:
        db.close()


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/proveedores/{pid}/merge/{other_id}  — fusión manual
# ─────────────────────────────────────────────────────────────────────────────
@router.post("/api/proveedores/{pid}/merge/{other_id}")
async def merge_proveedores(pid: int, other_id: int, request: Request):
    """Fusiona `other_id` dentro de `pid` (ambos del mismo taller).

    Acción:
      - Combina alias (incluye el nombre del eliminado).
      - Conserva como canónico el nombre más largo.
      - Conserva el RUC del destino; si el destino no tiene RUC pero el
        origen sí, lo adopta (con check de colisión).
      - Borra el proveedor `other_id`.
      - NO reasigna FKs en inventario/facturas: los repuestos ya viven por
        (taller_id, nombre_norm) y la relación con proveedor es textual.

    Solo admin.
    """
    tok = _auth(request)
    _require_admin(tok)
    taller_id = _tenant_id(tok)
    if pid == other_id:
        raise HTTPException(400, "No se puede fusionar un proveedor consigo mismo")
    db = _get_db()
    try:
        dst = db.execute(text(
            "SELECT id, nombre, ruc, alias FROM proveedores "
            "WHERE id=:id AND taller_id=:t"
        ), {"id": pid, "t": taller_id}).fetchone()
        src = db.execute(text(
            "SELECT id, nombre, ruc, alias FROM proveedores "
            "WHERE id=:id AND taller_id=:t"
        ), {"id": other_id, "t": taller_id}).fetchone()
        if not dst or not src:
            raise HTTPException(404, "Proveedor no encontrado en este taller")

        new_nombre = _canonical_nombre(dst[1], src[1])
        new_alias  = _merge_alias(list(dst[3] or []), dst[1], src[1], *list(src[3] or []))
        new_ruc    = dst[2] or ""
        if not new_ruc and src[2]:
            clash = db.execute(text(
                "SELECT id FROM proveedores "
                "WHERE taller_id=:t AND ruc=:ruc AND id NOT IN (:a, :b) LIMIT 1"
            ), {"t": taller_id, "ruc": src[2], "a": pid, "b": other_id}).fetchone()
            if not clash:
                new_ruc = src[2]

        db.execute(text(
            "UPDATE proveedores SET nombre=:n, alias=:al, ruc=:ruc "
            "WHERE id=:id AND taller_id=:t"
        ), {"n": new_nombre, "al": new_alias, "ruc": new_ruc,
            "id": pid, "t": taller_id})
        db.execute(text(
            "DELETE FROM proveedores WHERE id=:id AND taller_id=:t"
        ), {"id": other_id, "t": taller_id})
        db.commit()
        return {"ok": True, "id": pid, "nombre": new_nombre,
                "ruc": new_ruc, "alias": new_alias, "absorbed": other_id}
    finally:
        db.close()

"""
routers/config_router.py — Config del taller (multi-tenant).

Refactor 2026-04-21: taller_id del JWT via _tenant_id (antes TALLER_ID global).
"""
import json as _json
from utils.upload_validator import validate_upload_bytes, safe_extension
from routers._common import (
    router, ADMIN_HTML,
    _auth, _get_db, _require_admin, _require_staff, _safe_date,
    _img_to_url, _parse_json_field, _make_token, _tenant_id,
    os, json, datetime, timedelta, Path,
    Request, HTTPException, UploadFile, File, List, HTMLResponse, text,
)


DEFAULT_TERMINOS = [
    'La aprobación de este presupuesto autoriza al taller a iniciar los trabajos detallados.',
    'Los precios incluyen IGV. La mano de obra y repuestos tienen garantía por escrito tras la entrega.',
    'Para asegurar el stock de repuestos, se solicita coordinar el adelanto con administración.',
    'Cualquier trabajo adicional no contemplado será comunicado antes de su ejecución.',
    'El plazo de entrega se confirmará una vez aprobado el presupuesto y asegurado el stock.',
    'Este presupuesto tiene una vigencia de 2 días calendario desde su emisión. Pasado ese plazo, los precios y la disponibilidad de repuestos pueden variar sin previo aviso.',
]


def _load_terminos(db, taller_id):
    row = db.execute(text(
        "SELECT valor FROM config_sistema WHERE taller_id=:t AND clave='terminos_aprobacion'"
    ), {"t": taller_id}).fetchone()
    if not row or not row[0]:
        return list(DEFAULT_TERMINOS)
    try:
        data = _json.loads(row[0])
        if isinstance(data, list) and data:
            return [str(x).strip() for x in data if str(x).strip()]
    except Exception:
        pass
    return list(DEFAULT_TERMINOS)


@router.get("/api/config")
async def get_config(request: Request):
    tok = _auth(request)
    _require_staff(tok)
    taller_id = _tenant_id(tok)
    db = _get_db()
    try:
        row = db.execute(text(
            "SELECT nombre, empresa_nombre, empresa_ruc, empresa_direccion, empresa_telefono, "
            "empresa_email, igv_porcentaje, moneda FROM talleres WHERE id=:t"
        ), {"t": taller_id}).fetchone()
        if not row:
            raise HTTPException(404, "Taller no encontrado")
        terminos = _load_terminos(db, taller_id)
        nombre_taller = row[1] or row[0] or ''
        return {
            "nombre": row[0],
            "empresa_nombre": nombre_taller,
            "nombre_taller": nombre_taller,
            "ruc": row[2] or '',
            "direccion": row[3] or '',
            "telefono": row[4] or '',
            "email": row[5] or '',
            "igv": row[6] or 18,
            "moneda": row[7] or "S/",
            "terminos": terminos,
        }
    finally:
        db.close()


@router.put("/api/config")
async def update_config(request: Request):
    tok = _auth(request)
    _require_admin(tok)
    taller_id = _tenant_id(tok)
    body = await request.json()
    db = _get_db()
    try:
        name_val = body.get("empresa_nombre")
        if name_val is None:
            name_val = body.get("nombre_taller")
        if name_val is None:
            name_val = body.get("nombre")

        mapping = {
            "ruc": "empresa_ruc",
            "direccion": "empresa_direccion",
            "telefono": "empresa_telefono",
            "email": "empresa_email",
            "igv": "igv_porcentaje",
            "moneda": "moneda",
        }
        sets, params = [], {"t": taller_id}
        if name_val is not None:
            sets.append("empresa_nombre=:empresa_nombre")
            params["empresa_nombre"] = name_val
            sets.append("nombre=:nombre")
            params["nombre"] = name_val
        for k, col in mapping.items():
            if k in body:
                sets.append(f"{col}=:{col}"); params[col] = body[k]
        if sets:
            db.execute(text(
                f"UPDATE talleres SET {', '.join(sets)} WHERE id=:t"
            ), params)

        if "terminos" in body:
            terms = body.get("terminos") or []
            if isinstance(terms, str):
                terms = [ln.strip() for ln in terms.splitlines() if ln.strip()]
            if not isinstance(terms, list):
                terms = []
            terms = [str(t).strip() for t in terms if str(t).strip()]
            val = _json.dumps(terms, ensure_ascii=False)
            existing = db.execute(text(
                "SELECT 1 FROM config_sistema WHERE taller_id=:t AND clave='terminos_aprobacion'"
            ), {"t": taller_id}).fetchone()
            if existing:
                db.execute(text(
                    "UPDATE config_sistema SET valor=:v "
                    "WHERE taller_id=:t AND clave='terminos_aprobacion'"
                ), {"t": taller_id, "v": val})
            else:
                db.execute(text(
                    "INSERT INTO config_sistema (taller_id, clave, valor) "
                    "VALUES (:t, 'terminos_aprobacion', :v)"
                ), {"t": taller_id, "v": val})

        db.commit()
        return {"ok": True}
    finally:
        db.close()


# ── FIRMA Y SELLO DEL TALLER ────────────────────────────────────────────
_FIRMA_DIR = "/var/www/sandoval/assets/firma"

@router.get("/api/config/firma")
async def get_firma_config(request: Request):
    """Retorna info de la firma del taller (existe? URL?)."""
    tok = _auth(request)
    _require_staff(tok)
    taller_id = _tenant_id(tok)
    fpath = os.path.join(_FIRMA_DIR, f"taller_{taller_id}.png")
    if os.path.isfile(fpath):
        import time
        v = int(os.path.getmtime(fpath))
        return {"exists": True, "url": f"/assets/firma/taller_{taller_id}.png?v={v}"}
    return {"exists": False, "url": None}


@router.post("/api/config/firma")
async def upload_firma(request: Request, file: UploadFile = File(...)):
    """Sube imagen de firma+sello del titular del taller. Solo admin."""
    tok = _auth(request)
    _require_admin(tok)
    taller_id = _tenant_id(tok)
    os.makedirs(_FIRMA_DIR, exist_ok=True)
    # Validar tipo
    ct = (file.content_type or "").lower()
    if ct not in ("image/png", "image/jpeg", "image/jpg", "image/webp"):
        raise HTTPException(400, f"Formato inválido: {ct}. Usa PNG/JPG/WEBP")
    # Guardar SIEMPRE como PNG (convertir si es necesario)
    raw = await file.read()
    if len(raw) > 5 * 1024 * 1024:
        raise HTTPException(400, "Imagen muy grande (máx 5MB)")
    _ext = safe_extension(file.filename or '', '.png')
    if _ext not in {'.png','.jpg','.jpeg','.webp'}:
        raise HTTPException(400, 'Extension no permitida para firma')
    _ok, _kind = validate_upload_bytes(raw, _ext)
    if not _ok:
        raise HTTPException(400, 'Contenido no coincide con extension de firma')
    out_path = os.path.join(_FIRMA_DIR, f"taller_{taller_id}.png")
    try:
        from PIL import Image
        from io import BytesIO
        img = Image.open(BytesIO(raw))
        if img.mode not in ('RGB', 'RGBA'):
            img = img.convert('RGBA')
        # Solo resize si supera 1200px (sin procesar fondo)
        if img.width > 1200:
            ratio = 1200 / img.width
            img = img.resize((1200, int(img.height * ratio)), Image.LANCZOS)
        img.save(out_path, 'PNG', optimize=True)
        try:
            import os as _os
            _os.chmod(out_path, 0o644)
        except Exception:
            pass
    except ImportError:
        with open(out_path, "wb") as fout:
            fout.write(raw)
    return {"ok": True, "url": f"/assets/firma/taller_{taller_id}.png"}


@router.delete("/api/config/firma")
async def delete_firma(request: Request):
    tok = _auth(request)
    _require_admin(tok)
    taller_id = _tenant_id(tok)
    fpath = os.path.join(_FIRMA_DIR, f"taller_{taller_id}.png")
    if os.path.isfile(fpath):
        os.remove(fpath)
    return {"ok": True}


"""
routers/inventario.py — Inventario del taller (multi-tenant).

Refactor 2026-04-21:
  - taller_id del JWT via _tenant_id (antes TALLER_ID global).
  - Fase B.2: endpoints de códigos de barras (lookup + asignación).
  - Fase B.4: `_norm_nombre_inv` reforzado para dedupe de inventario tolerante
    a variaciones OCR (guiones, espacios en unidades, viscosidad 10W-40 vs
    10W40, unidades de empaque sueltas UN/PZA/UND).
"""
import re
import unicodedata as _u_inv

from routers._common import (
    router, ADMIN_HTML,
    _auth, _get_db, _require_admin, _require_staff, _safe_date,
    _img_to_url, _parse_json_field, _make_token, _tenant_id,
    os, json, datetime, timedelta, Path,
    Request, HTTPException, UploadFile, File, List, HTMLResponse, text,
)
from fastapi import Query


# ─── Normalización de nombre de inventario (dedupe tolerante a OCR) ─────────
_RE_NORM_HYPHEN_WORD = re.compile(r'(\w)-(\w)')           # W-712     → W712
_RE_NORM_VISCOSITY   = re.compile(r'(\d+)w\s*-?\s*(\d+)', re.I)  # 10W-40 → 10w40
_RE_NORM_UNIT_NUM    = re.compile(                         # 4 L → 4l, 500 ML → 500ml
    r'(\d+(?:\.\d+)?)\s*(l|ml|gl|gal|oz|cc|kg|g|lb)\b', re.I)
_RE_NORM_PKG         = re.compile(                         # "1 UND", "X PZA" → quitar
    r'\b(u|un|und|unid|unidad|pz|pza|pzs|pcs)\b', re.I)
_RE_NORM_SPACES      = re.compile(r'\s+')


def _norm_nombre_inv(s):
    """Normaliza un nombre para dedupe (case/accent/ortografía tolerante).

    Estrategia conservadora:
      - Quita acentos (NFKD + ASCII).
      - Une tokens separados por guión entre alfanuméricos (W-712 → W712).
      - Normaliza viscosidad 10W-40 / 10 W 40 → 10w40.
      - Pega cantidad+unidad: "4 L" → "4l".
      - Elimina unidades de empaque sueltas (UN, UND, PZA, PCS).
      - Mantiene tamaño de envase (4L, 1L) y viscosidad como tokens
        diferenciadores — son productos distintos.

    Retorna máximo 150 chars.
    """
    if not s:
        return ""
    s = _u_inv.normalize("NFKD", s).encode("ASCII", "ignore").decode().lower()
    s = _RE_NORM_HYPHEN_WORD.sub(r'\1\2', s)
    s = _RE_NORM_VISCOSITY.sub(r'\1w\2', s)
    s = _RE_NORM_UNIT_NUM.sub(r'\1\2', s)
    s = _RE_NORM_PKG.sub(' ', s)
    s = ''.join(c if (c.isalnum() or c == ' ') else ' ' for c in s)
    s = _RE_NORM_SPACES.sub(' ', s).strip()
    return s[:150]


def _norm_barcode(code: str) -> str:
    """Normaliza un código de barras (trim, alphanumeric only, uppercase, máx 64)."""
    if not code:
        return ""
    c = re.sub(r'[^A-Za-z0-9]', '', code).upper()
    return c[:64]


@router.get("/api/inventario")
async def list_inventario(
    request: Request,
    q: str | None = None,
    categoria: str | None = None,
    tipo: str | None = None,
    stock_bajo: bool = False,
    limit: int = Query(500, ge=1, le=1000),
):
    tok = _auth(request)
    _require_staff(tok)
    taller_id = _tenant_id(tok)
    db = _get_db()
    try:
        sql = ("SELECT codigo, nombre, categoria, tipo, precio, costo, stock, stock_minimo, "
               "descripcion, codigo_barras "
               "FROM inventario WHERE taller_id=:t")
        params = {"t": taller_id}
        if q:
            sql += (" AND (nombre ILIKE :q OR codigo ILIKE :q OR categoria ILIKE :q "
                    "OR codigo_barras = :qraw)")
            params["q"] = f"%{q}%"
            params["qraw"] = _norm_barcode(q)
        if categoria:
            sql += " AND categoria=:cat"; params["cat"] = categoria
        if tipo:
            sql += " AND tipo=:tipo"; params["tipo"] = tipo
        if stock_bajo:
            sql += " AND stock <= stock_minimo AND stock_minimo > 0"
        sql += " ORDER BY nombre LIMIT :lim"
        params["lim"] = limit
        rows = db.execute(text(sql), params).fetchall()
        result = []
        for r in rows:
            precio = r[4] or 0; costo = r[5] or 0
            margen = round((precio - costo) / precio * 100, 1) if precio > 0 else 0
            stock = r[6] or 0; smin = r[7] or 0
            estado = "AGOTADO" if stock == 0 else ("BAJO" if stock <= smin and smin > 0 else "OK")
            result.append({
                "codigo": r[0], "nombre": r[1], "categoria": r[2], "tipo": r[3],
                "precio": precio, "costo": costo, "margen": margen,
                "stock": stock, "stock_minimo": smin, "estado_stock": estado,
                "descripcion": r[8], "codigo_barras": r[9] or "",
            })
        return result
    finally:
        db.close()


@router.get("/api/inventario/categorias")
async def get_categorias(request: Request):
    tok = _auth(request)
    _require_staff(tok)
    taller_id = _tenant_id(tok)
    db = _get_db()
    try:
        rows = db.execute(text(
            "SELECT DISTINCT categoria FROM inventario WHERE taller_id=:t AND categoria IS NOT NULL ORDER BY categoria"
        ), {"t": taller_id}).fetchall()
        return [r[0] for r in rows]
    finally:
        db.close()


# Nota: /api/inventario/abc DEBE ir antes de /api/inventario/{codigo}
# para que FastAPI no lo capture como un codigo="abc".
@router.get("/api/inventario/abc")
async def inventario_abc(request: Request):
    """
    Clasifica repuestos por rotación (Pareto 80/15/5):
      A = 80% del volumen  -> alta rotación
      B = 15%              -> rotación media
      C = 5%               -> baja rotación / stock muerto
    """
    tok = _auth(request)
    _require_staff(tok)
    taller_id = _tenant_id(tok)
    db = _get_db()
    try:
        usage_rows = db.execute(text("""
            SELECT
                item->>'referencia'              AS codigo,
                SUM((item->>'cantidad')::float)  AS total_usado
            FROM ordenes o
            CROSS JOIN jsonb_array_elements(
                COALESCE(o.items_cotizacion::jsonb, '[]'::jsonb)
            ) item
            WHERE o.taller_id   = :t
              AND o.estado       = 'ARCHIVADO'
              AND item->>'referencia' IS NOT NULL
              AND item->>'categoria' IN ('Repuesto','Repuesto Historico','Repuestos')
            GROUP BY 1
            ORDER BY 2 DESC
        """), {'t': taller_id}).fetchall()

        if not usage_rows:
            return {"items": [], "clase_a": 0, "clase_b": 0, "clase_c": 0,
                    "mensaje": "Sin datos de órdenes completadas aún."}

        total_vol = sum(float(r[1]) for r in usage_rows)
        items_abc = []
        cumulative = 0.0
        for r in usage_rows:
            vol = float(r[1])
            pct = vol / total_vol * 100
            cumulative += pct
            clase = 'A' if (cumulative - pct) < 80 else ('B' if (cumulative - pct) < 95 else 'C')
            items_abc.append({
                "codigo": r[0], "total_usado": round(vol, 1),
                "pct_uso": round(pct, 2), "clase": clase,
            })

        if items_abc:
            codigos = [i["codigo"] for i in items_abc]
            inv_rows = db.execute(text(
                "SELECT codigo, nombre, stock, precio, costo "
                "FROM inventario WHERE taller_id=:t AND codigo = ANY(:c)"
            ), {"t": taller_id, "c": codigos}).fetchall()
            inv_map = {r[0]: {"nombre": r[1], "stock": r[2],
                              "precio": float(r[3] or 0), "costo": float(r[4] or 0)}
                       for r in inv_rows}
            for item in items_abc:
                info = inv_map.get(item["codigo"], {})
                item["nombre"] = info.get("nombre", item["codigo"])
                item["stock"]  = info.get("stock",  0)
                item["precio"] = info.get("precio", 0)

        return {
            "items":   items_abc,
            "clase_a": sum(1 for i in items_abc if i["clase"] == 'A'),
            "clase_b": sum(1 for i in items_abc if i["clase"] == 'B'),
            "clase_c": sum(1 for i in items_abc if i["clase"] == 'C'),
        }
    finally:
        db.close()


# Nota: /api/inventario/barcode/{code} DEBE ir antes de /api/inventario/{codigo}
# (mismo razonamiento que /abc) para no ser capturado por la ruta dinámica.
@router.get("/api/inventario/barcode/{code}")
async def lookup_inventario_barcode(code: str, request: Request):
    """Busca un ítem por código de barras (EAN/UPC/Code128).

    Ruta pensada para el scanner móvil. Devuelve 404 si no existe — el frontend
    debe ofrecer "asignar a un ítem existente" usando PUT .../{codigo}/barcode.
    """
    tok = _auth(request)
    _require_staff(tok)
    taller_id = _tenant_id(tok)
    bc = _norm_barcode(code)
    if not bc:
        raise HTTPException(400, "Código de barras inválido")
    db = _get_db()
    try:
        row = db.execute(text(
            "SELECT codigo, nombre, categoria, tipo, precio, costo, stock, stock_minimo, "
            "descripcion, codigo_barras "
            "FROM inventario WHERE taller_id=:t AND codigo_barras=:bc LIMIT 1"
        ), {"t": taller_id, "bc": bc}).fetchone()
        if not row:
            raise HTTPException(404, f"Sin coincidencia para código {bc}")
        return {
            "codigo": row[0], "nombre": row[1], "categoria": row[2], "tipo": row[3],
            "precio": row[4], "costo": row[5], "stock": row[6],
            "stock_minimo": row[7], "descripcion": row[8],
            "codigo_barras": row[9] or "",
        }
    finally:
        db.close()


@router.post("/api/inventario")
async def create_inventario(request: Request):
    tok = _auth(request)
    _require_admin(tok)
    taller_id = _tenant_id(tok)
    body = await request.json()
    if not body.get("nombre"):
        raise HTTPException(400, "Nombre requerido")
    db = _get_db()
    try:
        codigo = body.get("codigo") or f"IT-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        exists = db.execute(text("SELECT 1 FROM inventario WHERE codigo=:c AND taller_id=:t"),
                            {"c": codigo, "t": taller_id}).fetchone()
        if exists:
            codigo = codigo + "-2"
        nombre = body.get("nombre") or ""
        cb = _norm_barcode(body.get("codigo_barras") or "")
        if cb:
            clash = db.execute(text(
                "SELECT codigo FROM inventario WHERE taller_id=:t AND codigo_barras=:bc LIMIT 1"
            ), {"t": taller_id, "bc": cb}).fetchone()
            if clash:
                raise HTTPException(
                    409,
                    f"Código de barras {cb} ya asignado al ítem {clash[0]}"
                )
        db.execute(text("""
            INSERT INTO inventario (codigo, taller_id, nombre, categoria, tipo, descripcion,
                precio, costo, stock, stock_minimo, nombre_norm, codigo_barras)
            VALUES (:c, :t, :n, :cat, :tipo, :desc, :p, :co, :s, :sm, :nn, :cb)
        """), {
            "c": codigo, "t": taller_id, "n": nombre,
            "cat": body.get("categoria", "General"), "tipo": body.get("tipo", "repuesto"),
            "desc": body.get("descripcion", ""), "p": body.get("precio", 0),
            "co": body.get("costo", 0), "s": body.get("stock", 0),
            "sm": body.get("stock_minimo", 0),
            "nn": _norm_nombre_inv(nombre), "cb": cb,
        })
        db.commit()
        return {"codigo": codigo, "codigo_barras": cb}
    finally:
        db.close()


@router.get("/api/inventario/{codigo}")
async def get_inventario_item(codigo: str, request: Request):
    tok = _auth(request)
    _require_staff(tok)
    taller_id = _tenant_id(tok)
    db = _get_db()
    try:
        row = db.execute(text(
            "SELECT codigo, nombre, categoria, tipo, precio, costo, stock, stock_minimo, "
            "descripcion, codigo_barras "
            "FROM inventario WHERE codigo=:c AND taller_id=:t"
        ), {"c": codigo, "t": taller_id}).fetchone()
        if not row: raise HTTPException(404, "Item no encontrado")
        return {"codigo": row[0], "nombre": row[1], "categoria": row[2], "tipo": row[3],
                "precio": row[4], "costo": row[5], "stock": row[6],
                "stock_minimo": row[7], "descripcion": row[8],
                "codigo_barras": row[9] or ""}
    finally:
        db.close()


@router.put("/api/inventario/{codigo}")
async def update_inventario(codigo: str, request: Request):
    tok = _auth(request)
    _require_admin(tok)
    taller_id = _tenant_id(tok)
    body = await request.json()
    db = _get_db()
    try:
        fields = ["nombre", "categoria", "tipo", "descripcion", "precio", "costo", "stock", "stock_minimo"]
        sets, params = [], {"c": codigo, "t": taller_id}
        for f in fields:
            if f in body:
                sets.append(f"{f}=:{f}"); params[f] = body[f]
        if "nombre" in body:
            sets.append("nombre_norm=:nn"); params["nn"] = _norm_nombre_inv(body.get("nombre") or "")
        if "codigo_barras" in body:
            cb = _norm_barcode(body.get("codigo_barras") or "")
            if cb:
                clash = db.execute(text(
                    "SELECT codigo FROM inventario "
                    "WHERE taller_id=:t AND codigo_barras=:bc AND codigo<>:c LIMIT 1"
                ), {"t": taller_id, "bc": cb, "c": codigo}).fetchone()
                if clash:
                    raise HTTPException(
                        409,
                        f"Código de barras {cb} ya asignado al ítem {clash[0]}"
                    )
            sets.append("codigo_barras=:cb"); params["cb"] = cb
        if sets:
            db.execute(text(f"UPDATE inventario SET {', '.join(sets)} WHERE codigo=:c AND taller_id=:t"), params)
            db.commit()
        return {"ok": True}
    finally:
        db.close()


@router.delete("/api/inventario/{codigo}")
async def delete_inventario(codigo: str, request: Request):
    tok = _auth(request)
    _require_admin(tok)
    taller_id = _tenant_id(tok)
    db = _get_db()
    try:
        db.execute(text("DELETE FROM inventario WHERE codigo=:c AND taller_id=:t"),
                   {"c": codigo, "t": taller_id})
        db.commit()
        return {"ok": True}
    finally:
        db.close()


@router.put("/api/inventario/{codigo}/barcode")
async def set_inventario_barcode(codigo: str, request: Request):
    """Asigna/actualiza el código de barras de un ítem existente.

    Pensado para el flujo móvil: escanear → "asignar a este repuesto".
    Responde 409 si el código pertenece a otro ítem del mismo taller.
    Body: {"codigo_barras": "7501234567890"} — o "" para limpiar.
    """
    tok = _auth(request)
    _require_staff(tok)
    taller_id = _tenant_id(tok)
    body = await request.json()
    cb = _norm_barcode(body.get("codigo_barras") or "")
    db = _get_db()
    try:
        if cb:
            clash = db.execute(text(
                "SELECT codigo FROM inventario "
                "WHERE taller_id=:t AND codigo_barras=:bc AND codigo<>:c LIMIT 1"
            ), {"t": taller_id, "bc": cb, "c": codigo}).fetchone()
            if clash:
                raise HTTPException(
                    409,
                    f"Código de barras {cb} ya asignado al ítem {clash[0]}"
                )
        res = db.execute(text(
            "UPDATE inventario SET codigo_barras=:bc "
            "WHERE codigo=:c AND taller_id=:t"
        ), {"bc": cb, "c": codigo, "t": taller_id})
        db.commit()
        if getattr(res, "rowcount", 0) == 0:
            raise HTTPException(404, "Ítem no encontrado")
        return {"ok": True, "codigo": codigo, "codigo_barras": cb}
    finally:
        db.close()


@router.post("/api/inventario/{codigo}/usar")
async def usar_stock_inventario(codigo: str, request: Request):
    """Decrementa stock de un ítem. La resta es atómica (UPDATE ... GREATEST(...,0))."""
    tok = _auth(request)
    _require_staff(tok)
    taller_id = _tenant_id(tok)
    body = await request.json()
    cantidad = float(body.get("cantidad", 1))
    db = _get_db()
    try:
        db.execute(text(
            "UPDATE inventario SET stock = GREATEST(stock - :q, 0) WHERE codigo=:c AND taller_id=:t"
        ), {"q": cantidad, "c": codigo, "t": taller_id})
        db.commit()
        row = db.execute(text(
            "SELECT stock FROM inventario WHERE codigo=:c AND taller_id=:t"
        ), {"c": codigo, "t": taller_id}).fetchone()
        return {"ok": True, "stock_actual": row[0] if row else 0}
    finally:
        db.close()

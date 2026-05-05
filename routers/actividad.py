"""
routers/actividad.py — Log de actividades (multi-tenant).

Refactor 2026-04-21: taller_id del JWT via _tenant_id (antes TALLER_ID global).
Limit parametrizado con Query bounds.
"""
from fastapi import Query
from routers._common import (
    router, ADMIN_HTML,
    _auth, _get_db, _require_admin, _safe_date,
    _img_to_url, _parse_json_field, _make_token, _tenant_id,
    os, json, datetime, timedelta, Path,
    Request, HTTPException, UploadFile, File, List, HTMLResponse, text,
)


@router.get("/api/actividad")
async def get_actividad(
    request: Request,
    limit: int = Query(50, ge=1, le=500),
):
    tok = _auth(request)
    _require_admin(tok)
    taller_id = _tenant_id(tok)
    db = _get_db()
    try:
        rows = db.execute(text("""
            SELECT a.id, a.modulo, a.accion, a.detalle, u.nombre, a.fecha
            FROM actividades a LEFT JOIN usuarios u ON u.id::text = a.usuario_id::text
            WHERE a.taller_id=:t ORDER BY a.id DESC LIMIT :lim
        """), {"t": taller_id, "lim": limit}).fetchall()
        return [{"id": r[0], "modulo": r[1], "accion": r[2], "referencia": r[3],
                 "usuario": r[4], "fecha": _safe_date(r[5])} for r in rows]
    except Exception:
        return []
    finally:
        db.close()

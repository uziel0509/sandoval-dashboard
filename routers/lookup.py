"""
routers/lookup.py — Consulta RUC (SUNAT) / DNI (RENIEC) via CODART API.

Uso:
  GET /api/lookup/ruc/{ruc}  → {ok, nombre, direccion, estado, condicion, distrito, provincia, departamento}
  GET /api/lookup/dni/{dni}  → {ok, nombres, apellido_paterno, apellido_materno, nombre_completo}

Cache in-memory con TTL 24h para conservar cuota del API externo.
Token leído desde env var CODART_TOKEN (.env).
"""
import os
import time
import requests

from routers._common import router, _auth, _require_staff, Request, HTTPException

_API_BASE = "https://api-codart.cgrt.org/api/v1/consultas"
_TTL_SECONDS = 24 * 3600
_cache: dict[str, tuple[float, dict]] = {}


def _token() -> str:
    t = os.environ.get("CODART_TOKEN", "").strip()
    if not t:
        raise HTTPException(500, "CODART_TOKEN no configurado en .env")
    return t


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {_token()}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _cache_get(key: str) -> dict | None:
    row = _cache.get(key)
    if not row:
        return None
    ts, payload = row
    if time.time() - ts > _TTL_SECONDS:
        _cache.pop(key, None)
        return None
    return payload


def _cache_put(key: str, payload: dict) -> None:
    _cache[key] = (time.time(), payload)


@router.get("/api/lookup/ruc/{ruc}")
async def lookup_ruc(ruc: str, request: Request):
    tok = _auth(request); _require_staff(tok)
    ruc = (ruc or "").strip()
    if not ruc.isdigit() or len(ruc) != 11:
        raise HTTPException(400, "RUC debe tener 11 dígitos")
    cached = _cache_get(f"ruc:{ruc}")
    if cached:
        return cached
    try:
        r = requests.get(f"{_API_BASE}/sunat/ruc/{ruc}", headers=_headers(), timeout=8)
    except requests.RequestException as e:
        raise HTTPException(502, f"Error consultando SUNAT: {e}")
    if r.status_code != 200:
        raise HTTPException(502, f"SUNAT respondió {r.status_code}")
    try:
        data = r.json()
    except ValueError:
        raise HTTPException(502, "Respuesta SUNAT inválida")
    if not data.get("success") or not data.get("result"):
        return {"ok": False, "error": data.get("message") or "No encontrado"}
    res = data["result"]
    payload = {
        "ok": True,
        "ruc": res.get("numero_documento") or ruc,
        "nombre": (res.get("razon_social") or "").strip(),
        "direccion": (res.get("direccion") or "").strip(),
        "estado": res.get("estado") or "",
        "condicion": res.get("condicion") or "",
        "distrito": res.get("distrito") or "",
        "provincia": res.get("provincia") or "",
        "departamento": res.get("departamento") or "",
        "tipo": res.get("tipo") or "",
        "actividad": res.get("actividad_economica") or "",
    }
    _cache_put(f"ruc:{ruc}", payload)
    return payload


@router.get("/api/lookup/dni/{dni}")
async def lookup_dni(dni: str, request: Request):
    tok = _auth(request); _require_staff(tok)
    dni = (dni or "").strip()
    if not dni.isdigit() or len(dni) != 8:
        raise HTTPException(400, "DNI debe tener 8 dígitos")
    cached = _cache_get(f"dni:{dni}")
    if cached:
        return cached
    try:
        r = requests.get(f"{_API_BASE}/reniec/dni/{dni}", headers=_headers(), timeout=8)
    except requests.RequestException as e:
        raise HTTPException(502, f"Error consultando RENIEC: {e}")
    if r.status_code != 200:
        raise HTTPException(502, f"RENIEC respondió {r.status_code}")
    try:
        data = r.json()
    except ValueError:
        raise HTTPException(502, "Respuesta RENIEC inválida")
    if not data.get("success") or not data.get("result"):
        return {"ok": False, "error": data.get("message") or "No encontrado"}
    res = data["result"]
    nombres = (res.get("first_name") or "").strip()
    ap_pat = (res.get("first_last_name") or "").strip()
    ap_mat = (res.get("second_last_name") or "").strip()
    nombre_completo = " ".join(p for p in [nombres, ap_pat, ap_mat] if p)
    payload = {
        "ok": True,
        "dni": res.get("document_number") or dni,
        "nombres": nombres,
        "apellido_paterno": ap_pat,
        "apellido_materno": ap_mat,
        "nombre_completo": nombre_completo,
    }
    _cache_put(f"dni:{dni}", payload)
    return payload

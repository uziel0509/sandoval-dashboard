"""utils.api.lookup — endpoints CODART (RUC/DNI).

Fix 2026-05-01: las variables _os_codart, _time_codart, _codart_cache, _req_codart
estaban referenciadas pero NUNCA definidas — rompía /api/lookup/ruc/* con NameError
en cada llamada. Ahora se definen al inicio del módulo.
"""
from __future__ import annotations
import os as _os_codart
import json as _json
import time as _time_codart
from typing import Optional
from starlette.requests import Request
from starlette.responses import JSONResponse
from utils.api.common import _require_auth, json_ok, json_err, _get_sessions_db

try:
    import requests as _req_codart
except Exception:
    _req_codart = None

# URL CORRECTA: incluye /api/v1/consultas/ (la base sin ese path da 404 "route not found")
_CODART_BASE = "https://api-codart.cgrt.org/api/v1/consultas"
_CODART_TTL = 60 * 60 * 24  # 24h cache
_CODART_CACHE_MAX = 5000  # cap memoria (postgres-pro recomendación)
_codart_cache: dict = {}
# FIX security-reviewer #3 + postgres-pro: lock para race condition
import threading as _threading_codart
_codart_cache_lock = _threading_codart.Lock()


# === IMPORTS_LEGACY ===
import secrets
import hashlib
import hmac
import os
import json
import sqlite3
import threading as _threading
from collections import defaultdict as _defaultdict
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from starlette.requests import Request
from starlette.responses import JSONResponse, FileResponse, RedirectResponse
from sqlalchemy import text, text as _sa_text
from utils.models import (
    get_db, Usuario, Cliente, Vehiculo, ItemInventario,
    Orden, Cita, NotaVenta, Proveedor, log_actividad,
    verify_password, hash_password,
)
from utils.security_events import track_login_failure as _track_login_fail
from utils.auth_cookies import (
    get_token_from_request, set_token_cookie, clear_token_cookie,
    COOKIE_CLIENT_NAME, COOKIE_ADMIN_NAME,
)
from utils.upload_validator import validate_upload_bytes, safe_extension
# === FIN IMPORTS_LEGACY ===

def _codart_headers():
    tok = (_os_codart.environ.get("CODART_TOKEN") or "").strip()
    if not tok:
        return None
    return {
        "Authorization": f"Bearer {tok}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _codart_cache_get(key):
    with _codart_cache_lock:
        row = _codart_cache.get(key)
        if not row: return None
        ts, payload = row
        if _time_codart.time() - ts > _CODART_TTL:
            _codart_cache.pop(key, None); return None
        return payload


def _codart_cache_put(key, payload):
    with _codart_cache_lock:
        # postgres-pro: cap memoria — si supera _CODART_CACHE_MAX, limpiar mitad mas vieja
        if len(_codart_cache) >= _CODART_CACHE_MAX:
            sorted_keys = sorted(_codart_cache.items(), key=lambda kv: kv[1][0])
            for old_k, _ in sorted_keys[:_CODART_CACHE_MAX // 2]:
                _codart_cache.pop(old_k, None)
        _codart_cache[key] = (_time_codart.time(), payload)


async def api_lookup_ruc(request: Request) -> JSONResponse:
    user = _require_auth(request)
    if isinstance(user, JSONResponse): return user
    # 2026-05-04 FASE2.3: rate limit 30/min por IP (CODART/SUNAT proxy)
    try:
        from utils.api.ratelimit import enforce_endpoint_rate_limit as _rl
        _rl(request, "lookup_ruc", max_per_min=30)
    except Exception as _e:
        if 'too many' in str(_e).lower() or '429' in str(_e):
            return json_err("Demasiadas consultas. Espera un minuto.", 429)
    ruc = (request.path_params.get("ruc") or "").strip()
    if not ruc.isdigit() or len(ruc) != 11:
        return json_err("RUC debe tener 11 dígitos", 400)
    cached = _codart_cache_get(f"ruc:{ruc}")
    if cached: return json_ok(cached)
    headers = _codart_headers()
    if headers is None:
        return json_err("CODART_TOKEN no configurado", 500)
    if _req_codart is None:
        return json_err("requests no disponible", 500)
    try:
        r = _req_codart.get(f"{_CODART_BASE}/sunat/ruc/{ruc}", headers=headers, timeout=8)
    except Exception as e:
        return json_err(f"Error SUNAT: {e}", 502)
    if r.status_code != 200:
        return json_err(f"SUNAT respondió {r.status_code}", 502)
    try:
        data = r.json()
    except Exception:
        return json_err("Respuesta SUNAT inválida", 502)
    if not data.get("success") or not data.get("result"):
        return json_ok({"ok": False, "error": data.get("message") or "No encontrado"})
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
    _codart_cache_put(f"ruc:{ruc}", payload)
    return json_ok(payload)


async def api_lookup_dni(request: Request) -> JSONResponse:
    user = _require_auth(request)
    if isinstance(user, JSONResponse): return user
    # 2026-05-04 FASE2.3: rate limit 30/min por IP (CODART/RENIEC proxy)
    try:
        from utils.api.ratelimit import enforce_endpoint_rate_limit as _rl
        _rl(request, "lookup_dni", max_per_min=30)
    except Exception as _e:
        if 'too many' in str(_e).lower() or '429' in str(_e):
            return json_err("Demasiadas consultas. Espera un minuto.", 429)
    dni = (request.path_params.get("dni") or "").strip()
    if not dni.isdigit() or len(dni) != 8:
        return json_err("DNI debe tener 8 dígitos", 400)
    cached = _codart_cache_get(f"dni:{dni}")
    if cached: return json_ok(cached)
    headers = _codart_headers()
    if headers is None:
        return json_err("CODART_TOKEN no configurado", 500)
    if _req_codart is None:
        return json_err("requests no disponible", 500)
    try:
        r = _req_codart.get(f"{_CODART_BASE}/reniec/dni/{dni}", headers=headers, timeout=8)
    except Exception as e:
        return json_err(f"Error RENIEC: {e}", 502)
    if r.status_code != 200:
        return json_err(f"RENIEC respondió {r.status_code}", 502)
    try:
        data = r.json()
    except Exception:
        return json_err("Respuesta RENIEC inválida", 502)
    if not data.get("success") or not data.get("result"):
        return json_ok({"ok": False, "error": data.get("message") or "No encontrado"})
    res = data["result"]
    nombres = (res.get("first_name") or "").strip()
    ap_pat = (res.get("first_last_name") or "").strip()
    ap_mat = (res.get("second_last_name") or "").strip()
    payload = {
        "ok": True,
        "dni": res.get("document_number") or dni,
        "nombres": nombres,
        "apellido_paterno": ap_pat,
        "apellido_materno": ap_mat,
        "nombre_completo": " ".join(p for p in [nombres, ap_pat, ap_mat] if p),
    }
    _codart_cache_put(f"dni:{dni}", payload)
    return json_ok(payload)


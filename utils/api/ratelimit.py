"""utils.api.ratelimit — state in-memory rate-limit login."""
from __future__ import annotations
import threading as _threading
from collections import defaultdict as _defaultdict
from datetime import datetime, timedelta

_login_attempts = _defaultdict(list)
_rl_lock = _threading.Lock()


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

def _check_rate_limit(ip: str) -> bool:
    """Retorna True si la IP está bloqueada (demasiados intentos)"""
    from datetime import datetime, timedelta
    now = datetime.now()
    window = timedelta(minutes=15)
    with _rl_lock:
        attempts = [t for t in _login_attempts[ip] if now - t < window]
        _login_attempts[ip] = attempts
        return len(attempts) >= 5


def _record_failed_attempt(ip: str):
    from datetime import datetime
    with _rl_lock:
        _login_attempts[ip].append(datetime.now())


def _clear_attempts(ip: str):
    with _rl_lock:
        _login_attempts[ip] = []


# 2026-05-04 FASE2.3: rate limit generico por endpoint (PDF/OCR/CODART)
# Estructura: { (endpoint, ip): [datetime, ...] }
_endpoint_hits: dict = _defaultdict(list)


def check_endpoint_rate_limit(endpoint: str, ip: str, max_per_min: int = 30) -> bool:
    """
    Retorna True si el endpoint+IP excede max_per_min hits en la ultima ventana
    de 60 segundos. Falso = OK, puede seguir.
    """
    now = datetime.now()
    window = timedelta(seconds=60)
    key = (endpoint, ip)
    with _rl_lock:
        hits = [t for t in _endpoint_hits[key] if now - t < window]
        if len(hits) >= max_per_min:
            _endpoint_hits[key] = hits  # mantener evidencia para proximos
            return True
        hits.append(now)
        _endpoint_hits[key] = hits
        return False


def enforce_endpoint_rate_limit(request, endpoint_label: str, max_per_min: int = 30):
    """
    Helper one-liner para usar dentro de un endpoint. Si excede el limite,
    lanza HTTPException 429.
    """
    from fastapi import HTTPException
    ip = (request.client.host if request and request.client else "?")[:64]
    if check_endpoint_rate_limit(endpoint_label, ip, max_per_min):
        raise HTTPException(429, f"Demasiadas solicitudes a {endpoint_label}. Espera 1 minuto.")


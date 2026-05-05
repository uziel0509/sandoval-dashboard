"""
utils/csrf.py — CSRF protection capa app (P2-B1, 2026-05-04).

Estrategia "Double Submit Cookie":
  1. Backend genera cookie `csrf_token` (NO HttpOnly, accesible JS).
  2. Frontend lee la cookie y la envía en cada POST/PUT/PATCH/DELETE
     como header `X-CSRF-Token`.
  3. Middleware compara cookie vs header (timing-safe). Si difieren → 403.
  4. SameSite=Lax + Origin/Referer check protegen contra CSRF clásico.

Por qué Double Submit (no synchronizer pattern con state server):
  - Stateless (cero queries DB por request).
  - Compatible con multi-portal sin sticky sessions.
  - Funciona junto con Cookies HttpOnly de auth.

Endpoints exentos (no requieren CSRF):
  - GET / HEAD / OPTIONS (RFC 7231: idempotentes).
  - /api/login, /api/logout, /api/login/2fa, /healthz (auth/lifecycle).
  - /api/lookup/* (proxy SUNAT/RENIEC, no muta estado).
  - /aprobacion/{token}, /reporte/{token}, /encuesta/{token} (públicos
    con token unforgeable propio).
  - Webhooks de Telegram (validados por su propio token).
"""
from __future__ import annotations

import hmac
import secrets
from typing import Iterable

from starlette.responses import Response
from starlette.types import ASGIApp, Receive, Scope, Send


CSRF_COOKIE_NAME = "csrf_token"
CSRF_HEADER_NAME = "x-csrf-token"      # ASGI normaliza headers a lowercase
CSRF_TOKEN_BYTES = 32                  # 256 bits


def generate_csrf_token() -> str:
    """Token unforgeable (256 bits)."""
    return secrets.token_urlsafe(CSRF_TOKEN_BYTES)


def set_csrf_cookie(response: Response, token: str = None) -> str:
    """Setea/refresca la cookie csrf_token en la respuesta. Devuelve el token."""
    if not token:
        token = generate_csrf_token()
    # NO HttpOnly: el frontend NECESITA leerla con document.cookie
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=token,
        max_age=36000,             # 10h, mismo TTL que JWT admin
        httponly=False,
        secure=True,
        samesite="lax",
        path="/",
    )
    return token


# ── Whitelist de paths exentos ───────────────────────────────────────────────
_EXEMPT_PREFIXES = (
    # Endpoints de auth/lifecycle (login emite la cookie csrf, logout no necesita)
    "/admin/api/login",
    "/admin/api/logout",
    "/admin/api/login/2fa",
    "/api/login",
    "/api/logout",
    "/api/login/2fa",
    "/superadmin/api/login",
    "/superadmin/api/logout",
    "/healthz",
    # Lookup proxies (no mutan estado, solo leen)
    "/api/lookup/",
    "/admin/api/lookup/",
    # Endpoints públicos con token unforgeable propio
    "/aprobacion/",
    "/reporte/",
    "/encuesta/",
    "/a/",
    # Cron (usa X-Cron-Token propio)
    "/admin/api/practicantes/_cron/",
    # Webhooks (validados por su propio token)
    "/api/telegram_webhook",
    # Estáticos (los GETs ya pasan por _SAFE_METHODS, esto es para POSTs raros)
    # NOTA: NO poner "/admin/" aquí porque matchea "/admin/api/*"!
)

_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def is_exempt(path: str, method: str) -> bool:
    """True si el request NO requiere CSRF check."""
    if method.upper() in _SAFE_METHODS:
        return True
    for p in _EXEMPT_PREFIXES:
        if path.startswith(p):
            return True
    return False


# ── Middleware ASGI ──────────────────────────────────────────────────────────
class CSRFMiddleware:
    """Valida X-CSRF-Token contra cookie csrf_token en mutaciones.

    Aplica solo a métodos POST/PUT/PATCH/DELETE en paths NO exentos.
    Si la cookie no existe (primer request del navegador), se setea en la
    respuesta del primer GET — el frontend la lee y la usa en mutaciones.
    """

    def __init__(self, app: ASGIApp, exempt_prefixes: Iterable[str] = ()):
        self.app = app
        self._extra_exempt = tuple(exempt_prefixes)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        method = scope.get("method", "GET").upper()
        path = scope.get("path", "") or scope.get("raw_path", b"").decode("latin-1", "ignore")

        # Exento → pasa directo (pero seteamos cookie en GETs si falta)
        if is_exempt(path, method) or any(path.startswith(p) for p in self._extra_exempt):
            await self._maybe_set_cookie_on_response(scope, receive, send)
            return

        # Mutación → validar cookie vs header
        cookie_jar = self._parse_cookies(scope)

        # 2026-05-05 P1-2/P1-1 EXPANSIÓN COMPLETA: tras migración HttpOnly
        # ULTRA-MASIVA todos los portales tienen CSRF helpers:
        #   - sandoval_token         (admin SPA — desde 2026-05-04)
        #   - sandoval_client_token  (portal cliente PC + móvil — desde 2026-05-05)
        #   - sandoval_sa_token      (super_admin — desde 2026-05-05)
        # PWA staff sigue exenta vía sandoval_api_token (no migrada — riesgo SPA
        # 922KB), PERO sus mutaciones desde la PWA pasan por cookie sandoval_token
        # post-login admin → ya cubiertas por CSRF estándar (ver _swCsrfHeaders).
        AUTH_COOKIE_NAMES = ("sandoval_token", "sandoval_client_token", "sandoval_sa_token")
        has_auth_cookie = any(cookie_jar.get(n) for n in AUTH_COOKIE_NAMES)
        if not has_auth_cookie:
            await self.app(scope, receive, send)
            return

        cookie_token = cookie_jar.get(CSRF_COOKIE_NAME)
        header_token = self._get_header(scope, CSRF_HEADER_NAME)

        if not cookie_token or not header_token:
            await self._reject(send, "CSRF token missing")
            return
        if not hmac.compare_digest(cookie_token, header_token):
            await self._reject(send, "CSRF token mismatch")
            return

        # OK → continuar
        await self.app(scope, receive, send)

    @staticmethod
    def _parse_cookies(scope: Scope) -> dict:
        jar = {}
        for k, v in scope.get("headers", []):
            if k != b"cookie":
                continue
            for c in v.decode("latin-1", "ignore").split(";"):
                name, _, val = c.partition("=")
                jar[name.strip()] = val.strip()
        return jar

    @staticmethod
    def _get_header(scope: Scope, name: str) -> str | None:
        target = name.lower().encode("latin-1")
        for k, v in scope.get("headers", []):
            if k.lower() == target:
                return v.decode("latin-1", "ignore").strip()
        return None

    @staticmethod
    async def _reject(send: Send, msg: str):
        await send({
            "type": "http.response.start",
            "status": 403,
            "headers": [(b"content-type", b"application/json")],
        })
        await send({
            "type": "http.response.body",
            "body": ('{"error":"CSRF: ' + msg + '"}').encode("utf-8"),
        })

    async def _maybe_set_cookie_on_response(self, scope, receive, send):
        """Si el request es GET y NO tiene cookie csrf_token, la inyectamos."""
        cookie_jar = self._parse_cookies(scope)
        if cookie_jar.get(CSRF_COOKIE_NAME):
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "GET").upper()
        if method != "GET":
            await self.app(scope, receive, send)
            return

        new_token = generate_csrf_token()
        # Wrap send para inyectar Set-Cookie en la primera respuesta start
        cookie_value = (
            f"{CSRF_COOKIE_NAME}={new_token}; Max-Age=36000; "
            f"Path=/; Secure; SameSite=Lax"
        ).encode("latin-1")

        async def _send_wrapper(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((b"set-cookie", cookie_value))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, _send_wrapper)

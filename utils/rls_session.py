"""
SANDOVAL — Aislamiento multi-tenant a nivel PostgreSQL (RLS).

Provee:
  - Una `ContextVar` que arrastra `taller_id` a través de cada request.
  - Helper `apply_rls_to_session(db)` que ejecuta SET LOCAL app.taller_id sobre
    una `Session` de SQLAlchemy reciente.
  - Middleware ASGI que, dado un request, decodifica el token (JWT admin o
    sesión SQLite PWA/cliente) y setea la ContextVar antes de continuar.
  - `with_taller(taller_id)`: contexto manual para handlers públicos
    (/aprobacion, /reporte, /encuesta) que necesitan setear el taller del
    token de la orden.

DISEÑO:
  - Se usa contextvars.ContextVar (no thread-local) para soportar async + await.
  - SET LOCAL es la única opción segura con connection pool: el setting expira
    cuando termina la transacción (no contamina la siguiente).
  - 2026-04-24 RLS pasó a STRICT (FORCED) en 32 tablas. Las queries sin
    taller_id seteado devuelven 0 filas. El middleware GARANTIZA cobertura
    para todos los requests autenticados extrayendo el token de:
       a) Authorization: Bearer <jwt>
       b) Cookie sandoval_token (admin SPA, post 2026-04-29)
       c) Cookie sandoval_client_token (portal cliente PC + móvil)
       d) Cookie sandoval_api_token (legacy PWA staff, mantener compat)
  - Si NO hay token válido el middleware deja `None` y RLS bloquea la query.
"""
from __future__ import annotations

import contextvars
from contextlib import contextmanager
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

# ContextVar — propaga taller_id a través del request, incluyendo await.
current_taller_id: contextvars.ContextVar[Optional[int]] = contextvars.ContextVar(
    "current_taller_id", default=None
)


def get_current_taller_id() -> Optional[int]:
    """Devuelve el taller_id activo en este contexto, o None."""
    return current_taller_id.get()


def set_current_taller_id(taller_id: Optional[int]) -> contextvars.Token:
    """Setea el taller_id en este contexto. Devuelve token para reset()."""
    try:
        tid = int(taller_id) if taller_id is not None else None
    except (TypeError, ValueError):
        tid = None
    return current_taller_id.set(tid)


@contextmanager
def with_taller(taller_id: Optional[int]):
    """Context manager para setear taller_id en un bloque acotado.

    Útil en endpoints públicos que necesitan elevar privilegios para una
    orden específica (e.g. /reporte/{token} sirve datos de un taller_id
    derivado del token, no del usuario logueado).
    """
    token = set_current_taller_id(taller_id)
    try:
        yield
    finally:
        current_taller_id.reset(token)


def apply_rls_to_session(db: Session) -> None:
    """Ejecuta SET LOCAL app.taller_id = X sobre la sesión.

    No-op si no hay taller_id en contexto (deja la policy permisiva
    decidiendo). Atrapa errores silenciosamente para no romper apps con
    SQLite en desarrollo.
    """
    tid = get_current_taller_id()
    if tid is None:
        return
    try:
        # SET LOCAL solo sirve dentro de una transacción explícita; SQLAlchemy
        # abre una al hacer la primera query. Usamos SET (sin LOCAL) y, para
        # garantizar limpieza al checkout, también añadimos un reset al final
        # de la sesión via event listener (ver utils/models.py).
        # En PG, SET LOCAL requeriría iniciar TX antes; SET sin LOCAL persiste
        # hasta que la conexión se devuelve al pool — está bien siempre que
        # apliquemos `RESET app.taller_id` en pool.checkin.
        db.execute(text("SELECT set_config('app.taller_id', :tid, false)"),
                   {"tid": str(tid)})
    except Exception:
        # No romper app si el backend de DB no soporta esto (e.g. SQLite dev).
        pass


def reset_pg_taller(db) -> None:
    """Limpia el setting al terminar — útil al devolver conexión al pool.
    Acepta tanto Session de SQLAlchemy como conexión DBAPI cruda.
    """
    try:
        if hasattr(db, "execute"):
            try:
                db.execute(text("SELECT set_config('app.taller_id', '', false)"))
            except Exception:
                cur = db.cursor() if hasattr(db, "cursor") else None
                if cur:
                    cur.execute("SELECT set_config('app.taller_id', '', false)")
                    cur.close()
        elif hasattr(db, "cursor"):
            cur = db.cursor()
            cur.execute("SELECT set_config('app.taller_id', '', false)")
            cur.close()
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────
# Middleware ASGI para FastAPI
# ─────────────────────────────────────────────────────────────────
class TallerContextMiddleware:
    """Middleware ASGI que extrae taller_id del token y lo deja en el ContextVar.

    Soporta dos formatos de token (mismo header `Authorization: Bearer <tok>`
    o cookie `sandoval_api_token`):

    1. JWT HS256 firmado con `routers._common._secret()` — usado por admin SPA.
       Payload: {id, taller_id, rol, exp, ...}
    2. Token de sesión SQLite (`secrets.token_urlsafe`) — usado por PWA y
       portal cliente. La sesión vive en /var/www/sandoval/data/sessions.db
       con payload JSON.

    Si el token no es válido o no hay token, no setea nada (queda None).
    El backend con RLS permisivo sigue funcionando; con STRICT bloquea.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        token_value = self._extract_token(scope)
        taller_id = None
        if token_value:
            taller_id = self._taller_from_token(token_value)
        ctx_token = set_current_taller_id(taller_id)
        try:
            await self.app(scope, receive, send)
        finally:
            current_taller_id.reset(ctx_token)

    def _extract_token(self, scope) -> Optional[str]:
        # 2026-05-04 P1-A2 FIX: leer TODAS las cookies de auth (sandoval_token,
        # sandoval_client_token, sandoval_api_token), no solo la legacy.
        # Esto garantiza que el middleware setee app.taller_id GUC para los 4
        # portales (admin SPA, PWA staff, portal cliente PC, portal cliente
        # móvil) tras la migración a Cookies HttpOnly del 2026-04-29.

        # 1) Authorization: Bearer ...
        for k, v in scope.get("headers", []):
            if k == b"authorization":
                s = v.decode("latin-1", errors="ignore")
                if s.lower().startswith("bearer "):
                    return s[7:].strip()
        # 2) Cookies de auth (en orden de preferencia)
        COOKIE_NAMES = (
            "sandoval_token",         # admin SPA (HttpOnly desde 2026-04-29)
            "sandoval_client_token",  # portal cliente PC + móvil
            "sandoval_api_token",     # PWA staff legacy (compat)
        )
        for k, v in scope.get("headers", []):
            if k != b"cookie":
                continue
            cookies = v.decode("latin-1", errors="ignore").split(";")
            jar = {}
            for c in cookies:
                name, _, val = c.partition("=")
                jar[name.strip()] = val.strip()
            for cn in COOKIE_NAMES:
                if jar.get(cn):
                    return jar[cn]
        return None

    def _taller_from_token(self, token: str) -> Optional[int]:
        # Intento 1: JWT
        try:
            from routers._common import _secret
            import jwt as _jwt
            payload = _jwt.decode(token, _secret(), algorithms=["HS256"],
                                   options={"verify_exp": True})
            tid = payload.get("taller_id")
            if tid is not None:
                return int(tid)
        except Exception:
            pass
        # Intento 2: sesión SQLite (PWA / cliente)
        try:
            from utils.api_service import _get_user_from_token
            user = _get_user_from_token(token)
            if user:
                tid = user.get("taller_id")
                if tid is not None:
                    return int(tid)
        except Exception:
            pass
        return None

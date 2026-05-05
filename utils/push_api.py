"""
utils/push_api.py — Endpoints REST para Web Push (PWA móvil).

Registra en FastAPI:
  GET    /api/push/vapid-public-key   — pública (para applicationServerKey)
  POST   /api/push/subscribe          — auth, guarda subscription
  DELETE /api/push/unsubscribe        — auth, desactiva subscription
  POST   /api/push/test               — auth, envía push de prueba

Usa el mismo auth que el resto de la PWA (token en SQLite sessions via
`utils.api_service._require_auth`), de modo que el portal móvil puede
llamar estos endpoints con su Bearer token sin cambios.

Uso desde main.py:
    from utils.push_api import register_push_routes
    register_push_routes(app)
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from starlette.requests import Request
from starlette.responses import JSONResponse
from sqlalchemy import text

logger = logging.getLogger("sandoval.push_api")


def register_push_routes(app):
    """Registra las rutas push en la app FastAPI."""
    from utils.api_service import _require_auth
    from utils.models import get_db
    from utils.push_dispatcher import send_push

    @app.get("/api/push/vapid-public-key")
    async def vapid_public_key():
        key = os.environ.get("VAPID_PUBLIC_KEY", "")
        if not key:
            return JSONResponse({"error": "VAPID_PUBLIC_KEY no configurada"}, status_code=500)
        return {"publicKey": key}

    @app.post("/api/push/subscribe")
    async def subscribe_push(request: Request):
        user = _require_auth(request)
        if isinstance(user, JSONResponse):
            return user
        taller_id = user.get("taller_id")
        usuario_id = user.get("id")
        if not taller_id:
            return JSONResponse({"error": "sesión sin taller_id"}, status_code=400)

        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "body JSON inválido"}, status_code=400)

        endpoint = (body.get("endpoint") or "").strip()
        keys = body.get("keys") or {}
        p256dh = (keys.get("p256dh") or "").strip()
        auth_k = (keys.get("auth") or "").strip()
        if not (endpoint and p256dh and auth_k):
            return JSONResponse({"error": "endpoint/p256dh/auth requeridos"},
                                status_code=400)

        user_agent = (request.headers.get("user-agent") or "")[:500]
        db = get_db()
        try:
            db.execute(text("""
                INSERT INTO push_subscriptions
                    (taller_id, usuario_id, endpoint, p256dh, auth, user_agent, enabled)
                VALUES (:t, :u, :ep, :p, :a, :ua, TRUE)
                ON CONFLICT (endpoint) DO UPDATE SET
                    taller_id  = EXCLUDED.taller_id,
                    usuario_id = EXCLUDED.usuario_id,
                    p256dh     = EXCLUDED.p256dh,
                    auth       = EXCLUDED.auth,
                    user_agent = EXCLUDED.user_agent,
                    enabled    = TRUE,
                    last_used  = NOW()
            """), {
                "t": taller_id, "u": usuario_id, "ep": endpoint,
                "p": p256dh, "a": auth_k, "ua": user_agent,
            })
            db.commit()
        finally:
            db.close()
        return {"ok": True}

    @app.delete("/api/push/unsubscribe")
    async def unsubscribe_push(request: Request):
        user = _require_auth(request)
        if isinstance(user, JSONResponse):
            return user
        taller_id = user.get("taller_id")

        try:
            body = await request.json()
        except Exception:
            body = {}
        endpoint = (body.get("endpoint") or "").strip()
        if not endpoint:
            return JSONResponse({"error": "endpoint requerido"}, status_code=400)

        db = get_db()
        try:
            db.execute(text(
                "UPDATE push_subscriptions SET enabled=FALSE "
                "WHERE endpoint=:ep AND taller_id=:t"
            ), {"ep": endpoint, "t": taller_id})
            db.commit()
        finally:
            db.close()
        return {"ok": True}

    @app.post("/api/push/test")
    async def push_test(request: Request):
        user = _require_auth(request)
        if isinstance(user, JSONResponse):
            return user
        taller_id = user.get("taller_id")
        usuario_id = user.get("id")
        if not taller_id:
            return JSONResponse({"error": "sesión sin taller_id"}, status_code=400)

        result = send_push(
            taller_id=taller_id,
            usuario_id=usuario_id,
            title="SANDOVAL PRO",
            body="Notificación de prueba ✓",
            url="/app/",
            tag="test",
        )
        return {"ok": True, **result}

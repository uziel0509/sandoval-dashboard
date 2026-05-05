"""
utils/push_dispatcher.py — Envío de Web Push (VAPID) multi-tenant.

Uso desde código backend:

    from utils.push_dispatcher import send_push
    send_push(
        taller_id=tok["taller_id"],
        title="Presupuesto aprobado",
        body="El cliente aprobó O-0451",
        url="/app/#ordenes/0451",
    )

Propiedades:
  - No bloquea el request si falla el envío (log + seguir).
  - Auto-limpia subscriptions expiradas: 404/410 → enabled=FALSE.
  - Filtra por taller_id: nunca manda push a otro taller.
  - Opcionalmente filtra por usuario_id (notificar solo a un usuario).

Variables de entorno requeridas (en /var/www/sandoval/.env):
  VAPID_PUBLIC_KEY   — base64url raw public key (87 chars)
  VAPID_PRIVATE_KEY  — base64url raw private key (43 chars)
  VAPID_SUBJECT      — 'mailto:admin@...' o URL
"""
from __future__ import annotations

import base64
import json
import logging
import os
import threading
from typing import Optional, Iterable

from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend
from pywebpush import webpush, WebPushException
from sqlalchemy import text

logger = logging.getLogger("sandoval.push")


# ─── VAPID private key en formato PEM (pywebpush lo requiere así) ───────────
_VAPID_PRIV_PEM_CACHE: Optional[str] = None


def _vapid_priv_pem() -> str:
    """Convierte VAPID_PRIVATE_KEY (base64url raw, 32 bytes) → PEM PKCS8.

    Lo cacheamos porque la conversión es costosa y la clave no rota en runtime.
    """
    global _VAPID_PRIV_PEM_CACHE
    if _VAPID_PRIV_PEM_CACHE is not None:
        return _VAPID_PRIV_PEM_CACHE

    raw = os.environ.get("VAPID_PRIVATE_KEY", "")
    if not raw:
        raise RuntimeError("VAPID_PRIVATE_KEY no configurado en .env")

    # urlsafe base64 decode con padding
    padding = 4 - (len(raw) % 4)
    if padding != 4:
        raw = raw + ("=" * padding)
    raw_bytes = base64.urlsafe_b64decode(raw)
    if len(raw_bytes) != 32:
        raise RuntimeError(
            f"VAPID_PRIVATE_KEY longitud inválida: {len(raw_bytes)} bytes (se esperan 32)"
        )

    priv_num = int.from_bytes(raw_bytes, "big")
    priv_key = ec.derive_private_key(priv_num, ec.SECP256R1(), default_backend())
    pem = priv_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()

    _VAPID_PRIV_PEM_CACHE = pem
    return pem


def _vapid_claims() -> dict:
    return {"sub": os.environ.get("VAPID_SUBJECT", "mailto:admin@sandoval.local")}


# ─── Envío ───────────────────────────────────────────────────────────────────
def _send_one(sub: dict, payload: dict) -> tuple[bool, int]:
    """Envía un push a una sola subscription. Retorna (ok, status_code)."""
    subscription_info = {
        "endpoint": sub["endpoint"],
        "keys": {"p256dh": sub["p256dh"], "auth": sub["auth"]},
    }
    try:
        resp = webpush(
            subscription_info=subscription_info,
            data=json.dumps(payload, ensure_ascii=False),
            vapid_private_key=_vapid_priv_pem(),
            vapid_claims=_vapid_claims(),
            ttl=86400,  # 24h — si el dispositivo está off, el push aún llega al reencender
        )
        return True, getattr(resp, "status_code", 200)
    except WebPushException as e:
        status = getattr(getattr(e, "response", None), "status_code", 0)
        return False, status
    except Exception as e:
        logger.exception("Push send error to %s: %s", sub.get("endpoint", "")[:60], e)
        return False, 0


def _deactivate_subscription(db, sub_id: int):
    try:
        db.execute(text("UPDATE push_subscriptions SET enabled=FALSE WHERE id=:id"),
                   {"id": sub_id})
        db.commit()
    except Exception:
        logger.exception("No se pudo desactivar subscription id=%s", sub_id)


def send_push(
    taller_id: int,
    title: str,
    body: str,
    url: Optional[str] = None,
    usuario_id: Optional[int] = None,
    icon: Optional[str] = None,
    tag: Optional[str] = None,
) -> dict:
    """Envía Web Push a todas las subscriptions activas del taller.

    Args:
        taller_id: Scope multi-tenant obligatorio.
        title, body: Mostrados en la notificación.
        url: Click → navega a esta URL (relativa al origen del PWA).
        usuario_id: Si se pasa, filtra solo ese usuario (ej. notificar sólo al admin).
        icon: Path del icono (default: /icon-192.png).
        tag: Agrupa notificaciones — una nueva con el mismo tag reemplaza la anterior.

    Retorna {'sent': N, 'failed': M, 'deactivated': K}.
    """
    if not taller_id or not title:
        logger.warning("send_push: llamada sin taller_id o title — no-op")
        return {"sent": 0, "failed": 0, "deactivated": 0}

    try:
        from utils.models import get_db
    except Exception:
        logger.exception("send_push: no se pudo importar get_db")
        return {"sent": 0, "failed": 0, "deactivated": 0, "error": "db_import"}

    db = get_db()
    sent = failed = deactivated = 0
    try:
        sql = ("SELECT id, endpoint, p256dh, auth FROM push_subscriptions "
               "WHERE taller_id=:t AND enabled=TRUE")
        params = {"t": taller_id}
        if usuario_id:
            sql += " AND usuario_id=:u"
            params["u"] = usuario_id
        rows = db.execute(text(sql), params).fetchall()

        payload = {
            "title": title,
            "body": body,
            "url": url or "/app/",
            "icon": icon or "/app/icon-192.png",
            "badge": "/app/icon-192.png",
            "tag": tag or "sandoval",
        }

        for row in rows:
            ok, status = _send_one(
                {"endpoint": row[1], "p256dh": row[2], "auth": row[3]},
                payload,
            )
            if ok:
                sent += 1
                db.execute(text(
                    "UPDATE push_subscriptions SET last_used=NOW() WHERE id=:id"
                ), {"id": row[0]})
            else:
                failed += 1
                if status in (404, 410):
                    _deactivate_subscription(db, row[0])
                    deactivated += 1
        db.commit()
    finally:
        db.close()

    logger.info("push taller=%s sent=%d failed=%d deactivated=%d",
                taller_id, sent, failed, deactivated)
    return {"sent": sent, "failed": failed, "deactivated": deactivated}


def send_push_async(*args, **kwargs):
    """Dispara send_push en pool acotado — no bloquea al caller, loguea excepciones.
    2026-05-04 FASE1.4: reemplazo de Thread(daemon=True) por fire_and_forget."""
    from utils._async_helpers import fire_and_forget as _faf
    _faf(send_push, *args, **kwargs)

"""security_events.py - Helper para registrar eventos de seguridad y disparar alertas.
Reusa la tabla eventos_seguridad existente (RLS forzado).
Severidades: INFO < WARN < CRIT
Eventos CRIT envian push Telegram al admin.
"""
from __future__ import annotations
import logging
import os
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

# In-memory counter para detectar brute-force (15 min sliding window)
_recent_failures: dict = {}  # {ip: [timestamps]}
_FAIL_WINDOW = timedelta(minutes=15)
_FAIL_THRESHOLD = 5  # 5 fallos en 15 min -> CRIT


def _get_db():
    from utils.models import get_db
    return get_db()


def log_event(
    *,
    tipo: str,
    descripcion: str,
    severidad: str = 'INFO',
    taller_id: Optional[int] = None,
    user_id: Optional[str] = None,
    ip: Optional[str] = None,
    endpoint: Optional[str] = None,
    payload_sanitizado: Optional[str] = None,
    bloqueado: bool = False,
    push_telegram: Optional[bool] = None,
) -> None:
    """Registra evento en eventos_seguridad. Si push_telegram=None, decide automaticamente
    segun severidad (CRIT siempre, WARN solo si tipo es brute_force/idor/upload_malicious).
    """
    if severidad not in ('INFO', 'WARN', 'CRIT'):
        severidad = 'INFO'

    try:
        from sqlalchemy import text as _t
        db = _get_db()
        try:
            # 2026-04-30 fix: setear app.taller_id SIEMPRE (RLS bloquea si NULL)
            tid = int(taller_id or 0)
            try:
                db.execute(_t("SET LOCAL app.taller_id = :t"), {"t": str(tid)})
            except Exception:
                pass
            db.execute(_t(
                "INSERT INTO eventos_seguridad "
                "(taller_id, tipo, severidad, ip, user_id, endpoint, descripcion, "
                "payload_sanitizado, bloqueado) VALUES "
                "(:t, :tipo, :sev, :ip, :u, :ep, :desc, :pl, :blk)"
            ), {
                "t": tid, "tipo": tipo[:50], "sev": severidad,
                "ip": ip, "u": user_id, "ep": endpoint,
                "desc": descripcion[:500], "pl": payload_sanitizado,
                "blk": bloqueado,
            })
            db.commit()
        finally:
            db.close()
    except Exception as e:
        logger.warning("[sec_event] No se pudo grabar evento %s: %s", tipo, e)

    # Decidir push Telegram
    if push_telegram is None:
        push_telegram = (severidad == 'CRIT' or
                         tipo in ('brute_force', 'idor_attempt', 'upload_malicious',
                                  'token_revocado_uso', 'login_admin_critico'))
    if push_telegram:
        _push_telegram_alert(tipo, descripcion, severidad, ip=ip, user_id=user_id,
                             endpoint=endpoint)


def _push_telegram_alert(tipo: str, descripcion: str, severidad: str,
                         ip: Optional[str] = None, user_id: Optional[str] = None,
                         endpoint: Optional[str] = None) -> None:
    """Envia alerta a admin via Telegram bot."""
    try:
        token = os.environ.get('TELEGRAM_BOT_TOKEN', '').strip()
        chat_id = os.environ.get('TELEGRAM_ADMIN_CHAT_ID', '').strip()
        if not token or not chat_id:
            return
        emoji = {'CRIT': '🚨', 'WARN': '⚠️', 'INFO': 'ℹ️'}.get(severidad, '🔔')
        msg = (
            f"{emoji} *SEGURIDAD {severidad}*\n"
            f"*Tipo*: `{tipo}`\n"
            f"*Detalle*: {descripcion}\n"
        )
        if ip:
            msg += f"*IP*: `{ip}`\n"
        if user_id:
            msg += f"*Usuario*: `{user_id}`\n"
        if endpoint:
            msg += f"*Endpoint*: `{endpoint}`\n"
        msg += f"*Fecha*: {datetime.utcnow().isoformat()}Z"

        import urllib.request, urllib.parse, json as _json
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = urllib.parse.urlencode({
            'chat_id': chat_id, 'text': msg, 'parse_mode': 'Markdown',
        }).encode()
        req = urllib.request.Request(url, data=data, method='POST')
        urllib.request.urlopen(req, timeout=5).read()
    except Exception as e:
        logger.warning("[sec_event] Telegram push fallo: %s", e)


def track_login_failure(ip: str, username: str = '') -> bool:
    """Registra fallo de login y retorna True si supera threshold (brute force).
    Auto-genera evento CRIT si activa la alarma.
    """
    if not ip:
        return False
    now = datetime.utcnow()
    cutoff = now - _FAIL_WINDOW
    arr = _recent_failures.setdefault(ip, [])
    arr[:] = [t for t in arr if t > cutoff]
    arr.append(now)
    if len(arr) >= _FAIL_THRESHOLD:
        log_event(
            tipo='brute_force',
            descripcion=f'{len(arr)} logins fallidos en 15min desde {ip} (user={username})',
            severidad='CRIT', ip=ip, user_id=username,
        )
        return True
    return False


def track_idor_attempt(ip: str, user_id: str, endpoint: str, target_id: str) -> None:
    """Registra intento IDOR cuando una query rechaza por taller_id mismatch."""
    log_event(
        tipo='idor_attempt',
        descripcion=f'Acceso rechazado por mismatch tenant a {target_id}',
        severidad='WARN', ip=ip, user_id=user_id, endpoint=endpoint,
    )


def track_upload_rejected(ip: str, user_id: str, filename: str, reason: str) -> None:
    """Registra rechazo de upload por magic-bytes o tipo invalido."""
    log_event(
        tipo='upload_malicious',
        descripcion=f'Upload rechazado: {filename} - razon: {reason}',
        severidad='WARN', ip=ip, user_id=user_id,
    )


def track_revoked_token_use(jti: str, ip: str) -> None:
    """Registra uso de token previamente revocado."""
    log_event(
        tipo='token_revocado_uso',
        descripcion=f'Intento de uso de JWT revocado jti={jti[:16]}...',
        severidad='CRIT', ip=ip,
    )


def cleanup_old_events(days: int = 90) -> int:
    """Limpia eventos > N dias. Retorna count eliminados."""
    try:
        from sqlalchemy import text as _t
        db = _get_db()
        try:
            r = db.execute(_t(
                "DELETE FROM eventos_seguridad WHERE fecha < NOW() - (:d || ' days')::interval"
            ), {"d": str(days)})
            db.commit()
            return r.rowcount or 0
        finally:
            db.close()
    except Exception as e:
        logger.warning("[sec_event] cleanup fallo: %s", e)
        return 0

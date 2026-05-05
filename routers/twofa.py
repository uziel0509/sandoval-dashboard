"""
routers/2fa.py — 2FA TOTP (RFC 6238) para admins SANDOVAL PRO.

Endpoints:
  POST /admin/api/2fa/enroll   → genera secret + QR (no activa aun)
  POST /admin/api/2fa/verify   → valida code y ACTIVA 2FA + genera 10 backup codes
  POST /admin/api/2fa/disable  → desactiva 2FA (requiere code valido)
  POST /admin/api/login/2fa    → segundo paso login: temp_token + code → JWT final
"""
import secrets
import hashlib
import hmac
import json
from io import BytesIO
import base64

from routers._common import (
    router, _auth, _get_db, _require_admin, _make_token, _tenant_id, TALLER_ID,
    Request, HTTPException, text, datetime, timedelta,
)
import pyotp, qrcode
import jwt as pyjwt
import os

# 2026-05-05 SEC-REVIEWER #2 FIX: imports al top-level (antes estaban dentro
# del bloque exitoso de login_2fa, lo que causaba que un ImportError parcial
# devolviera HTTP 500 en runtime en lugar de detectarse al boot).
from starlette.responses import JSONResponse as _JR
from utils.auth_cookies import set_token_cookie, COOKIE_ADMIN_NAME


def _temp_secret():
    """Secret separado del JWT principal para tokens temporales (5 min TTL).
    Permite distinguir un temp_token (paso 1 login) de un JWT real (post 2FA)."""
    key = os.environ.get("SECRET_KEY")
    if not key or len(key) < 32:
        raise HTTPException(500, "SECRET_KEY no configurado")
    return key + "_2fa_temp_v1"


def _gen_backup_codes(n=10):
    """Genera N codigos de 8 chars (formato XXXX-XXXX). Retorna (codes_plain, codes_hashed)."""
    codes_plain = []
    codes_hashed = []
    for _ in range(n):
        c = secrets.token_hex(4).upper()  # 8 chars hex
        codes_plain.append(f"{c[:4]}-{c[4:]}")
        codes_hashed.append(hashlib.sha256(c.encode()).hexdigest())
    return codes_plain, codes_hashed


def _qr_data_url(secret: str, username: str) -> str:
    """Genera QR como data: URL base64 para mostrar en frontend."""
    uri = pyotp.totp.TOTP(secret).provisioning_uri(
        name=username, issuer_name="SANDOVAL PRO"
    )
    img = qrcode.make(uri)
    buf = BytesIO()
    img.save(buf, format='PNG')
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


@router.post("/api/2fa/enroll")
async def enroll_2fa(request: Request):
    """Paso 1: usuario admin pide generar QR. Aun no activa 2FA."""
    tok = _auth(request)
    _require_admin(tok)
    user_id = tok.get("sub")
    db = _get_db()
    try:
        row = db.execute(text(
            "SELECT username, totp_enabled FROM usuarios WHERE id=:id AND taller_id=:t"
        ), {"id": user_id, "t": _tenant_id(tok)}).fetchone()
        if not row:
            raise HTTPException(404, "Usuario no encontrado")
        if row[1]:
            raise HTTPException(400, "2FA ya está activado para este usuario")
        secret = pyotp.random_base32()  # 32 chars base32
        # Guardar secret PROVISIONAL (totp_enabled=FALSE hasta que verify exitoso)
        db.execute(text(
            "UPDATE usuarios SET totp_secret=:s WHERE id=:id AND taller_id=:t"
        ), {"s": secret, "id": user_id, "t": _tenant_id(tok)})
        db.commit()
        qr_data_url = _qr_data_url(secret, row[0])
        return {
            "secret": secret,             # mostrar al usuario por si quiere ingresar manual
            "qr_data_url": qr_data_url,   # img.src = qr_data_url
            "issuer": "SANDOVAL PRO",
            "instructions": "Escanea con Google Authenticator/Authy y luego envía el código de 6 dígitos para activar."
        }
    finally:
        db.close()


@router.post("/api/2fa/verify")
async def verify_2fa(request: Request):
    """Paso 2: usuario envia code 6 digitos. Si valido, activa 2FA + emite backup codes."""
    tok = _auth(request)
    _require_admin(tok)
    user_id = tok.get("sub")
    body = await request.json()
    code = (body.get("code") or "").strip()
    if not code or len(code) != 6 or not code.isdigit():
        raise HTTPException(400, "Código inválido (debe ser 6 dígitos)")
    db = _get_db()
    try:
        row = db.execute(text(
            "SELECT totp_secret, totp_enabled FROM usuarios WHERE id=:id AND taller_id=:t"
        ), {"id": user_id, "t": _tenant_id(tok)}).fetchone()
        if not row or not row[0]:
            raise HTTPException(400, "No hay enroll pendiente — llama primero a /enroll")
        if row[1]:
            raise HTTPException(400, "2FA ya activo")
        if not pyotp.TOTP(row[0]).verify(code, valid_window=1):
            raise HTTPException(400, "Código incorrecto. Verifica la hora del dispositivo.")
        # Generar 10 backup codes
        plain, hashed = _gen_backup_codes(10)
        db.execute(text("""
            UPDATE usuarios
               SET totp_enabled=TRUE,
                   totp_backup_codes=:codes,
                   totp_enrolled_at=NOW()
             WHERE id=:id AND taller_id=:t
        """), {"codes": json.dumps(hashed), "id": user_id, "t": _tenant_id(tok)})
        db.commit()
        return {
            "ok": True,
            "message": "2FA activado correctamente",
            "backup_codes": plain,   # SOLO se muestran 1 vez
            "warning": "Guarda estos códigos en lugar seguro. Cada uno funciona UNA VEZ si pierdes el dispositivo."
        }
    finally:
        db.close()


@router.post("/api/2fa/disable")
async def disable_2fa(request: Request):
    """Desactiva 2FA. Requiere code TOTP o backup code valido."""
    tok = _auth(request)
    _require_admin(tok)
    user_id = tok.get("sub")
    body = await request.json()
    code = (body.get("code") or "").strip()
    if not code:
        raise HTTPException(400, "Código requerido para desactivar 2FA")
    db = _get_db()
    try:
        row = db.execute(text(
            "SELECT totp_secret, totp_backup_codes, totp_enabled FROM usuarios "
            "WHERE id=:id AND taller_id=:t"
        ), {"id": user_id, "t": _tenant_id(tok)}).fetchone()
        if not row or not row[2]:
            raise HTTPException(400, "2FA no está activo")
        ok = False
        if len(code) == 6 and code.isdigit():
            ok = pyotp.TOTP(row[0]).verify(code, valid_window=1)
        else:
            # Backup code formato XXXX-XXXX
            normalized = code.replace("-", "").upper()
            if len(normalized) == 8:
                code_hash = hashlib.sha256(normalized.encode()).hexdigest()
                import json
                hashed_list = json.loads(row[1] or "[]")
                # 2026-04-30 sec-audit: usar hmac.compare_digest (anti timing attack)
                ok = any(hmac.compare_digest(code_hash, h) for h in hashed_list)
        if not ok:
            raise HTTPException(400, "Código incorrecto")
        db.execute(text("""
            UPDATE usuarios SET totp_enabled=FALSE, totp_secret=NULL,
                                totp_backup_codes=NULL, totp_enrolled_at=NULL
             WHERE id=:id AND taller_id=:t
        """), {"id": user_id, "t": _tenant_id(tok)})
        db.commit()
        return {"ok": True, "message": "2FA desactivado"}
    finally:
        db.close()


@router.post("/api/login/2fa")
async def login_2fa(request: Request):
    """Paso 2 del login cuando user tiene 2FA activo.

    Body: {"temp_token": "...", "code": "123456" or "XXXX-XXXX"}
    Returns: JWT final + user info (mismo formato que /api/login normal).
    """
    # 2026-04-30 sec-audit: rate limit anti brute force del codigo 6 digitos
    from routers._common import _client_ip, _check_login_rate_limit, _log_login_attempt
    ip = _client_ip(request)
    db_rl = _get_db()
    try:
        _check_login_rate_limit(db_rl, ip, max_fails=5, window_minutes=15)
    finally:
        db_rl.close()
    body = await request.json()
    temp = body.get("temp_token") or ""
    code = (body.get("code") or "").strip()
    if not temp or not code:
        raise HTTPException(400, "temp_token y code requeridos")
    try:
        payload = pyjwt.decode(temp, _temp_secret(), algorithms=["HS256"])
    except pyjwt.ExpiredSignatureError:
        raise HTTPException(401, "Sesión temporal expirada — vuelve a iniciar login")
    except Exception:
        raise HTTPException(401, "temp_token inválido")
    if payload.get("typ") != "2fa_pending":
        raise HTTPException(401, "Token no es de tipo 2FA pending")
    user_id = payload.get("sub")
    taller_id = payload.get("taller_id")
    # 2026-05-04 P2-B5 FIX: helper local que registra intento fallido ANTES de raise.
    # Antes el rate_limit solo contaba fails de /api/login, no de /api/login/2fa,
    # permitiendo al atacante con temp_token válido probar códigos sin límite real.
    def _fail_2fa(reason: str, status: int = 401):
        try:
            db_fail = _get_db()
            try:
                _log_login_attempt(db_fail, ip, f"2fa:{user_id}", False)
            finally:
                db_fail.close()
        except Exception:
            pass
        raise HTTPException(status, reason)
    db = _get_db()
    try:
        row = db.execute(text("""
            SELECT id, nombre, rol, email, totp_secret, totp_backup_codes
              FROM usuarios WHERE id=:id AND taller_id=:t AND totp_enabled=TRUE
        """), {"id": user_id, "t": taller_id}).fetchone()
        if not row:
            _fail_2fa("Usuario sin 2FA activo o no existe", 401)
        ok = False
        used_backup_index = -1
        hashed_list = json.loads(row[5] or "[]")
        if len(code) == 6 and code.isdigit():
            ok = pyotp.TOTP(row[4]).verify(code, valid_window=1)
        else:
            normalized = code.replace("-", "").upper()
            if len(normalized) == 8:
                code_hash = hashlib.sha256(normalized.encode()).hexdigest()
                # 2026-04-30 sec-audit: usar hmac.compare_digest (anti timing attack)
                for _idx, _h in enumerate(hashed_list):
                    if hmac.compare_digest(code_hash, _h):
                        ok = True
                        used_backup_index = _idx
                        break
        if not ok:
            _fail_2fa("Código 2FA incorrecto", 401)
        # Si fue backup code, removerlo (single-use)
        if used_backup_index >= 0:
            hashed_list.pop(used_backup_index)
            db.execute(text(
                "UPDATE usuarios SET totp_backup_codes=:c WHERE id=:id AND taller_id=:t"
            ), {"c": json.dumps(hashed_list), "id": user_id, "t": taller_id})
            db.commit()
        # Emitir JWT final
        token = _make_token({
            "id": row[0], "nombre": row[1], "rol": row[2],
            "taller_id": taller_id,
        })
        # 2026-05-05 P0-F4 FIX: setear cookie HttpOnly también en login 2FA
        # (antes solo el login normal /api/login la seteaba — inconsistencia).
        # Mantener `token` en el body por compat con frontend admin SPA que aún
        # usa localStorage (Issue #3 roadmap eliminar localStorage 100%).
        # Imports movidos al top del módulo (sec-reviewer #2).
        _resp = _JR({
            "token": token,
            "user": {"id": row[0], "nombre": row[1], "rol": row[2], "email": row[3]},
            "backup_codes_remaining": len(hashed_list),
        })
        set_token_cookie(_resp, token, cookie_name=COOKIE_ADMIN_NAME)
        return _resp
    finally:
        db.close()

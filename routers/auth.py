from routers._common import (
    router, TALLER_ID, ADMIN_HTML,
    _auth, _get_db, _require_admin, _safe_date,
    _img_to_url, _parse_json_field, _make_token,
    _client_ip, _check_login_rate_limit, _log_login_attempt,
    os, json, datetime, timedelta, Path,
    Request, HTTPException, UploadFile, File, List, HTMLResponse, text,
    bcrypt,
)

# ══════════════════════════════════════════════════════════════════════════════
# AUTH
# ══════════════════════════════════════════════════════════════════════════════
@router.post("/api/login")
async def admin_login(request: Request):
    # 2026-05-04 FASE1.2: validacion Pydantic V2 con LoginPayload
    # (regla: trim username, longitud, caracteres permitidos).
    body = await request.json()
    try:
        from utils.schemas import LoginPayload
        _p = LoginPayload.model_validate(body or {})
        username = _p.username.strip()
        password = _p.password
    except Exception as _ve:
        raise HTTPException(422, f"Datos invalidos: {str(_ve)[:200]}")
    if not username or not password:
        raise HTTPException(400, "Usuario y contraseña requeridos")
    ip = _client_ip(request)
    db = _get_db()
    try:
        _check_login_rate_limit(db, ip)
        # Nota multi-tenant: username es único por (taller_id, username). Mientras solo
        # exista taller 1 en producción la query sigue filtrando por TALLER_ID para
        # evitar colisiones cuando se onboardeen talleres adicionales. El refactor a
        # login con taller_code/subdomain vive en el roadmap (ver BRD §5 Fase 2).
        # IMPORTANTE: con RLS STRICT activo, una query directa sobre `usuarios`
        # SIN `app.taller_id` seteado devuelve 0 filas (porque el usuario aún
        # no está autenticado y no hay contexto). Usamos la función SECURITY
        # DEFINER `lookup_usuario_by_username` que bypasea RLS para este lookup.
        row = db.execute(text("""
            SELECT id, nombre, rol, email, activo, password_hash, taller_id
              FROM lookup_usuario_by_username(:u)
             WHERE taller_id = :t
        """), {"u": username, "t": TALLER_ID}).fetchone()
        # Fallback por si la función no existe (BD pre-RLS o restaurada)
        if row is None:
            try:
                row = db.execute(text(
                    "SELECT id, nombre, rol, email, activo, password_hash, taller_id FROM usuarios "
                    "WHERE (username=:u OR email=:u) AND taller_id=:t"
                ), {"u": username, "t": TALLER_ID}).fetchone()
            except Exception:
                row = None
        if not row or not row[4]:
            _log_login_attempt(db, ip, username, False)
            try: _track_login_fail(ip, username)
            except Exception: pass
            raise HTTPException(401, "Usuario o contraseña incorrectos")
        ph = row[5] or ""
        # 2026-04-29 audit fix V3: unificar a verify_password (compat Argon2/bcrypt/PBKDF2-100k)
        # Eliminado branch duplicado PBKDF2-260k que generaba mismatch silencioso con hash_password
        try:
            from utils.models import verify_password as _vp
            ok = _vp(password, ph)
        except Exception:
            ok = False
        if not ok:
            _log_login_attempt(db, ip, username, False)
            try: _track_login_fail(ip, username)
            except Exception: pass
            raise HTTPException(401, "Usuario o contraseña incorrectos")
        user = {
            "id": row[0],
            "nombre": row[1],
            "rol": row[2],
            "email": row[3],
            "taller_id": row[6],
        }
        db.execute(
            text("UPDATE usuarios SET ultimo_login=NOW() WHERE id=:id AND taller_id=:t"),
            {"id": row[0], "t": user["taller_id"]},
        )
        # Rehash a Argon2id si el hash actual es legacy (bcrypt/PBKDF2)
        try:
            if _new_needs_rehash(ph):
                _newh = _new_hash_pwd(password)
                db.execute(text("UPDATE usuarios SET password_hash=:h WHERE id=:id AND taller_id=:t"),
                           {"h": _newh, "id": row[0], "t": user["taller_id"]})
        except Exception:
            pass
        db.commit()
        _log_login_attempt(db, ip, username, True)
        # 2026-04-30 2FA TOTP: si user tiene totp_enabled, devolver temp_token (paso 1)
        # 2026-05-04 B1 fix: FAIL-CLOSE. Antes un except Exception: pass silenciaba errores
        # y emitia el token completo (bypass total de 2FA).
        try:
            t2fa = db.execute(text(
                "SELECT totp_enabled FROM usuarios WHERE id=:id AND taller_id=:t"
            ), {"id": row[0], "t": user["taller_id"]}).fetchone()
        except Exception as _e:
            import logging as _lg
            _lg.getLogger("sandoval.auth").error("2FA check DB failure: %s", _e)
            raise HTTPException(500, "Error verificando 2FA. Intenta nuevamente.") from _e
        if t2fa and t2fa[0]:
            try:
                from routers.twofa import _temp_secret as _ts
                import jwt as _pyjwt
                from datetime import datetime as _dt, timedelta as _td
                temp_token = _pyjwt.encode({
                    "sub": str(row[0]),
                    "taller_id": user["taller_id"],
                    "typ": "2fa_pending",
                    "exp": _dt.utcnow() + _td(minutes=5),
                }, _ts(), algorithm="HS256")
                from starlette.responses import JSONResponse as _JR2
                return _JR2({"requires_2fa": True, "temp_token": temp_token, "username": username})
            except Exception as _e:
                import logging as _lg
                _lg.getLogger("sandoval.auth").error("2FA temp_token issue failure: %s", _e)
                raise HTTPException(500, "Error generando token 2FA. Intenta nuevamente.") from _e
        # 2026-04-29 P1-EtA: setear cookie HttpOnly + body con token (dual-auth para compat)
        _tok = _make_token(user)
        from starlette.responses import JSONResponse as _JR
        _resp = _JR({"token": _tok, "user": user})
        set_token_cookie(_resp, _tok, cookie_name=COOKIE_ADMIN_NAME)
        return _resp
    finally:
        db.close()

@router.get("/api/me")
async def admin_me(request: Request):
    tok = _auth(request)
    # 2026-04-30 incluir totp_enabled para UI Configuracion 2FA
    totp_enabled = False
    try:
        db = _get_db()
        try:
            row = db.execute(text(
                "SELECT COALESCE(totp_enabled, FALSE) FROM usuarios WHERE id=:id AND taller_id=:t"
            ), {"id": tok["sub"], "t": tok.get("taller_id")}).fetchone()
            totp_enabled = bool(row[0]) if row else False
        finally:
            db.close()
    except Exception:
        pass
    return {
        "id": tok["sub"],
        "nombre": tok["nombre"],
        "rol": tok["rol"],
        "taller_id": tok.get("taller_id"),
        "totp_enabled": totp_enabled,
    }

# ══════════════════════════════════════════════════════════════════════════════
# DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════
from utils.security_events import track_login_failure as _track_login_fail
from utils.auth_cookies import set_token_cookie, clear_token_cookie, COOKIE_ADMIN_NAME, COOKIE_CLIENT_NAME
from utils.models import hash_password as _new_hash_pwd, needs_rehash as _new_needs_rehash


@router.post("/api/logout")
async def admin_logout(request: Request):
    """Logout admin: anade jti del token actual a jwt_revoked hasta su exp.

    2026-05-05 P0-F6 FIX (v2 — docstring corregido por security-reviewer):
    Lee el token en cascada para revocar el jti correctamente en BOTH casos:
      1. Authorization: Bearer <jwt>      (clientes legacy con localStorage)
      2. Cookie sandoval_token (HttpOnly)  (admin SPA post migración)
    Si el cliente solo envía cookie (futuro post-eliminación de localStorage),
    el jti SE revoca en backend. Antes era ignorado y el token quedaba válido
    hasta su exp natural (10h).

    NOTA: este endpoint es para ADMIN. La cookie `sandoval_client_token` (portal
    cliente) tiene su propio endpoint de logout en `routers/clientes.py` /
    `utils/api/auth.py`. Por eso aquí get_token_from_request() usa el cookie name
    explícito COOKIE_ADMIN_NAME.
    """
    # Intento 1: Authorization: Bearer ...
    token = None
    auth_h = request.headers.get("Authorization", "")
    if auth_h.startswith("Bearer "):
        token = auth_h[7:].strip()
    # Intento 2: cookie HttpOnly del ADMIN (sandoval_token)
    # 2026-05-05 P0-FIX (backend-engineer audit): NO re-importar COOKIE_ADMIN_NAME
    # aquí. Python lo detecta como asignación local y dispara UnboundLocalError
    # en la línea 223 (clear_token_cookie) cuando se entra por la rama Bearer.
    # Ya está importado a nivel módulo en línea 158.
    if not token:
        try:
            from utils.auth_cookies import get_token_from_request
            token = get_token_from_request(request, cookie_name=COOKIE_ADMIN_NAME)
        except Exception:
            token = None
    if not token:
        return {"ok": True}  # idempotente: si no hay token, ya esta deslogueado
    try:
        # Decodificar SIN validar exp para extraer jti aun de tokens recien expirados
        import jwt as _pyjwt
        from datetime import datetime as _dt
        data = _pyjwt.decode(token, _secret(), algorithms=["HS256"], options={"verify_exp": False})
        jti = data.get("jti")
        exp_ts = data.get("exp")
        if jti and exp_ts:
            db = _get_db()
            try:
                from datetime import datetime as _dt2
                exp_dt = _dt2.utcfromtimestamp(int(exp_ts))
                # No revocar si ya expiro (no aporta defensa)
                if exp_dt > _dt2.utcnow():
                    db.execute(text(
                        "INSERT INTO jwt_revoked (jti, exp, user_id, reason) "
                        "VALUES (:j, :e, :u, 'logout') "
                        "ON CONFLICT (jti) DO NOTHING"
                    ), {"j": jti, "e": exp_dt, "u": int(data.get("sub")) if data.get("sub") else None})
                    db.commit()
            finally:
                db.close()
    except Exception:
        pass
    # 2026-04-29 P1-EtA: borrar cookie HttpOnly al hacer logout
    from starlette.responses import JSONResponse as _JR
    _resp = _JR({"ok": True, "message": "Sesion cerrada"})
    # 2026-05-05 SYNC-GUARDIAN FIX: limpiar AMBAS cookies (admin + cliente).
    # Antes solo se borraba sandoval_token. Si un usuario alternaba admin/cliente
    # en la misma sesión navegador, sandoval_client_token quedaba viva tras logout.
    clear_token_cookie(_resp, cookie_name=COOKIE_ADMIN_NAME)
    clear_token_cookie(_resp, cookie_name=COOKIE_CLIENT_NAME)
    return _resp

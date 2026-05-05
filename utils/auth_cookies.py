"""auth_cookies.py - Helpers para cookies HttpOnly de autenticacion.

Implementa dual-auth: el backend acepta tokens via:
1. Cookie HttpOnly (preferido, anti-XSS)
2. Header Authorization: Bearer (legacy localStorage, sigue funcionando)

Esto permite migrar los 4 portales de forma gradual sin romper sesiones existentes.

Beneficios:
- Cookie HttpOnly: JS no puede leerla -> robo de token via XSS imposible
- Cookie Secure: solo viaja sobre HTTPS
- Cookie SameSite=Lax: bloquea CSRF de orígenes externos
- Cookie Max-Age 36000s (10h): igual que JWT exp
- Path /: cubre todo el dominio
- Compat con Authorization header: rollback parcial sin downtime
"""
from __future__ import annotations
from typing import Optional
from fastapi import Request, Response
from starlette.responses import JSONResponse


# Nombres de cookie por tipo de portal (mismo nombre que localStorage para compat de migracion)
COOKIE_ADMIN_NAME = "sandoval_token"
COOKIE_CLIENT_NAME = "sandoval_client_token"

# Configuracion comun
COOKIE_MAX_AGE = 10 * 60 * 60  # 10 horas (== JWT exp admin)
COOKIE_PATH = "/"
COOKIE_SAMESITE = "lax"  # Lax permite navegacion normal, bloquea CSRF cross-site POST


def get_token_from_request(request: Request, cookie_name: str = COOKIE_ADMIN_NAME) -> Optional[str]:
    """Lee el token JWT/sesion priorizando:
    1. Cookie HttpOnly (preferido, post-migracion)
    2. Header Authorization: Bearer ... (compat legacy localStorage)

    Devuelve None si no hay token en ninguna fuente.
    """
    # 1) Cookie HttpOnly (preferido)
    cookie_val = request.cookies.get(cookie_name)
    if cookie_val:
        return cookie_val

    # 2) Authorization header (compat legacy)
    auth_header = request.headers.get("Authorization", "") or request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:]

    return None


def set_token_cookie(response, token: str, *, cookie_name: str = COOKIE_ADMIN_NAME,
                     max_age: int = COOKIE_MAX_AGE) -> None:
    """Setea cookie HttpOnly + Secure + SameSite=Lax con el token.

    Tambien permite que el frontend antiguo siga leyendo el token del JSON
    body (compat durante migracion gradual).
    """
    response.set_cookie(
        key=cookie_name,
        value=token,
        max_age=max_age,
        path=COOKIE_PATH,
        httponly=True,    # JS no puede leerla (anti-XSS)
        secure=True,      # solo HTTPS (anti-MITM)
        samesite=COOKIE_SAMESITE,  # Lax: permite navegacion, bloquea CSRF
    )


def clear_token_cookie(response, *, cookie_name: str = COOKIE_ADMIN_NAME) -> None:
    """Borra la cookie en logout (Max-Age=0 + valor vacio)."""
    response.delete_cookie(
        key=cookie_name,
        path=COOKIE_PATH,
        httponly=True,
        secure=True,
        samesite=COOKIE_SAMESITE,
    )


def make_login_response(token: str, user_data: dict, *,
                        cookie_name: str = COOKIE_ADMIN_NAME,
                        status_code: int = 200) -> JSONResponse:
    """Crea JSONResponse con token en cookie HttpOnly Y en JSON body (compat).

    Asi:
    - Frontend nuevo: usa cookie automatica con `credentials: 'include'`
    - Frontend antiguo: sigue leyendo `body.token` y haciendo localStorage.setItem
    Despues de la migracion completa, se puede dejar de devolver `token` en el body.
    """
    body = {"token": token, "user": user_data} if isinstance(user_data, dict) else {"token": token}
    response = JSONResponse(body, status_code=status_code)
    set_token_cookie(response, token, cookie_name=cookie_name)
    return response


def make_logout_response(*, cookie_name: str = COOKIE_ADMIN_NAME,
                         status_code: int = 200) -> JSONResponse:
    """Crea JSONResponse limpiando la cookie. Usado en logout."""
    response = JSONResponse({"ok": True, "message": "Sesión cerrada"}, status_code=status_code)
    clear_token_cookie(response, cookie_name=cookie_name)
    return response

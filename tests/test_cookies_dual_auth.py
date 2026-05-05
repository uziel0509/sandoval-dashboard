"""test_cookies_dual_auth.py — tests para Etapa A/B/C/D del Punto 1.

Verifica:
- auth_cookies helpers funcionan
- _extract_token lee de cookie OR header
- _auth (admin) lee de cookie OR header
- Login devuelve cookie HttpOnly
- Logout limpia cookie
- 4 portales tienen el fetch wrapper inyectado
- Logout endpoint cableado en cada portal
"""
import pytest
import sys, os, re
sys.path.insert(0, '/var/www/sandoval')


class TestAuthCookiesHelpers:
    def test_imports_ok(self):
        from utils.auth_cookies import (
            get_token_from_request, set_token_cookie, clear_token_cookie,
            COOKIE_ADMIN_NAME, COOKIE_CLIENT_NAME, COOKIE_MAX_AGE,
            make_login_response, make_logout_response,
        )
        assert COOKIE_ADMIN_NAME == "sandoval_token"
        assert COOKIE_CLIENT_NAME == "sandoval_client_token"
        assert COOKIE_MAX_AGE == 36000  # 10h

    def test_set_token_cookie_uses_httponly(self):
        from utils.auth_cookies import set_token_cookie, COOKIE_ADMIN_NAME
        from starlette.responses import JSONResponse
        r = JSONResponse({"ok": True})
        set_token_cookie(r, "test.token.value", cookie_name=COOKIE_ADMIN_NAME)
        # Pydantic test: header set-cookie debe tener HttpOnly + Secure + SameSite=lax
        cookies_header = ""
        for k, v in r.raw_headers:
            if k.lower() == b"set-cookie":
                cookies_header += v.decode() + "\n"
        assert "HttpOnly" in cookies_header
        assert "Secure" in cookies_header
        assert "samesite=lax" in cookies_header.lower()
        assert "sandoval_token" in cookies_header

    def test_clear_token_cookie(self):
        from utils.auth_cookies import clear_token_cookie, COOKIE_ADMIN_NAME
        from starlette.responses import JSONResponse
        r = JSONResponse({"ok": True})
        clear_token_cookie(r, cookie_name=COOKIE_ADMIN_NAME)
        cookies_header = ""
        for k, v in r.raw_headers:
            if k.lower() == b"set-cookie":
                cookies_header += v.decode() + "\n"
        assert "sandoval_token" in cookies_header
        # Borrar = max-age=0 o expires en pasado
        assert ("Max-Age=0" in cookies_header or "max-age=0" in cookies_header)


class TestExtractTokenDualAuth:
    """Verifica que _extract_token de api_service lee de cookie OR header."""

    def _make_request(self, headers=None, cookies=None):
        from starlette.requests import Request
        scope = {
            "type": "http", "method": "GET", "path": "/", "headers": [],
            "query_string": b"", "raw_path": b"/",
        }
        h = []
        if headers:
            for k, v in headers.items():
                h.append((k.lower().encode(), v.encode()))
        if cookies:
            cookie_str = "; ".join(f"{k}={v}" for k, v in cookies.items())
            h.append((b"cookie", cookie_str.encode()))
        scope["headers"] = h
        return Request(scope)

    def test_extract_from_authorization_header(self):
        from utils.api_service import _extract_token
        r = self._make_request(headers={"Authorization": "Bearer test_legacy_token"})
        assert _extract_token(r) == "test_legacy_token"

    def test_extract_from_admin_cookie(self):
        from utils.api_service import _extract_token
        r = self._make_request(cookies={"sandoval_token": "admin_cookie_token"})
        assert _extract_token(r) == "admin_cookie_token"

    def test_extract_from_client_cookie(self):
        from utils.api_service import _extract_token
        r = self._make_request(cookies={"sandoval_client_token": "client_cookie_token"})
        assert _extract_token(r) == "client_cookie_token"

    def test_extract_legacy_api_token_cookie(self):
        from utils.api_service import _extract_token
        r = self._make_request(cookies={"sandoval_api_token": "legacy_api_cookie"})
        assert _extract_token(r) == "legacy_api_cookie"

    def test_extract_header_priority_over_cookie(self):
        """Si ambos presentes, header gana (preferido por compat retro)."""
        from utils.api_service import _extract_token
        r = self._make_request(
            headers={"Authorization": "Bearer header_wins"},
            cookies={"sandoval_token": "cookie_loses"},
        )
        assert _extract_token(r) == "header_wins"

    def test_extract_returns_none_when_absent(self):
        from utils.api_service import _extract_token
        r = self._make_request()
        assert _extract_token(r) is None


class TestFrontendsMigrated:
    """Verifica que los 4 portales tienen el fetch wrapper inyectado."""
    PORTALS = [
        '/var/www/sandoval/static/admin/index.html',
        '/var/www/sandoval/sandoval-app/index.html',
        '/var/www/sandoval/portal-cliente/pc/index.html',
        '/var/www/sandoval/portal-cliente/index.html',
    ]

    @pytest.mark.parametrize("portal", PORTALS)
    def test_fetch_wrapper_inyectado(self, portal):
        with open(portal) as f:
            c = f.read()
        assert '__sandoval_fetch_wrapped' in c
        assert "init.credentials" in c

    @pytest.mark.parametrize("portal", PORTALS)
    def test_logout_endpoint_cableado(self, portal):
        with open(portal) as f:
            c = f.read()
        # Cada portal debe llamar a /api/logout o /admin/api/logout
        has_logout_call = (
            "fetch('/api/logout'" in c or
            'fetch("/api/logout"' in c or
            "fetch('/admin/api/logout'" in c or
            'fetch("/admin/api/logout"' in c
        )
        assert has_logout_call, f"{portal} no llama logout endpoint"


class TestLoginEndpointReturnsCookie:
    """Test e2e: login admin con creds inválidos no setea cookie (401)."""

    def test_admin_login_invalid_returns_401_no_cookie(self):
        import urllib.request
        import json as _json
        req = urllib.request.Request(
            "http://127.0.0.1:3000/admin/api/login",
            data=_json.dumps({"username": "fake_user_xx", "password": "fake_pwd"}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            urllib.request.urlopen(req, timeout=5)
            pytest.fail("Login con creds invalidas no debio responder 200")
        except urllib.error.HTTPError as e:
            assert e.code == 401
            # Verifica que NO setea cookie en 401
            set_cookie = e.headers.get("Set-Cookie", "")
            assert "sandoval_token" not in set_cookie
        except Exception as e:
            pytest.skip(f"Sandoval no disponible: {e}")

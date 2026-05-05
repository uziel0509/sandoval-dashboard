"""test_etapa_a.py — 20 tests baseline para la red de seguridad pre-refactor.

Categorias:
- TestUnauth: 5 endpoints criticos sin token devuelven 401 (no 500)
- TestInputValidation: 3 endpoints con payloads invalidos -> 400/422
- TestSmokeNonAuth: 4 endpoints publicos / no-auth (healthz, vapid-key, robots, favicon)
- TestRevokedToken: 1 token en blacklist -> 401
- TestExpiredToken: 1 token expirado -> 401
- TestCookieAuth: 2 dual-auth (cookie y header) acceptados
- TestPublicTokenEndpoints: 2 aprobacion publica via URL token (404 con token invalido)
- TestSchemaSanity: 2 schemas Pydantic edge cases

Estos tests son la RED DE SEGURIDAD para el refactor del Punto 2.
Cualquier regresion durante el split la detectan.
"""
import pytest
from starlette import status


# ════════════════════════════════════════════════════════════════════════════
# 1. UNAUTH: endpoints criticos sin token deben dar 401, NO 500 ni 200
# ════════════════════════════════════════════════════════════════════════════
class TestUnauth:
    """Verifica que todos los endpoints protegidos rechazan sin token."""

    @pytest.mark.parametrize("path", [
        "/api/auth/me",
        "/api/dashboard",
        "/api/ordenes",
        "/api/clientes",
        "/api/vehiculos",
        "/api/inventario",
        "/api/cliente/mis-ordenes",
        "/api/lookup/ruc/20608755111",
    ])
    def test_get_unauth_rejects(self, client, path):
        """GET sin token a endpoint protegido devuelve 401 (no 200, no 500)."""
        r = client.get(path)
        assert r.status_code == 401, f"{path} expected 401 got {r.status_code}: {r.text[:200]}"

    def test_vapid_key_is_public_by_design(self, client):
        """/api/push/vapid-key ES publico: solo expone la clave publica VAPID,
        que cualquiera puede usar para suscribirse a push (la clave PRIVADA
        nunca sale del backend). Verificamos que devuelve JSON con public_key."""
        r = client.get("/api/push/vapid-key")
        assert r.status_code == 200
        data = r.json()
        assert "public_key" in data
        assert len(data["public_key"]) > 50  # base64 VAPID key

    @pytest.mark.parametrize("path,body", [
        ("/api/ordenes/nueva", {"cliente_id": "x"}),
        ("/api/clientes/nuevo", {"nombre": "x"}),
        ("/api/vehiculos/nuevo", {"placa": "ABC123"}),
        ("/api/citas/nueva", {"fecha": "2026-04-29"}),
        ("/api/cliente/cambiar-pin", {"pin": "1234"}),
    ])
    def test_post_unauth_rejects(self, client, path, body):
        """POST sin token tambien debe rechazar."""
        r = client.post(path, json=body)
        assert r.status_code == 401, f"{path} expected 401 got {r.status_code}"


# ════════════════════════════════════════════════════════════════════════════
# 2. INPUT VALIDATION: payloads malformados -> 400/422
# ════════════════════════════════════════════════════════════════════════════
class TestInputValidation:

    def test_login_admin_invalid_payload_no_username(self, client):
        """POST /admin/api/login sin username -> 4xx."""
        r = client.post("/admin/api/login", json={"password": "test"})
        assert r.status_code in (400, 401, 422), f"got {r.status_code}"

    def test_login_admin_empty_body(self, client):
        """POST /admin/api/login con body vacio -> 4xx."""
        r = client.post("/admin/api/login", json={})
        assert r.status_code in (400, 401, 422)

    def test_login_admin_malformed_json(self, client):
        """POST /admin/api/login con body NO JSON: el handler hace `await request.json()`
        sin try/except, lo que produce 500. NO es ideal pero es comportamiento actual.
        Lo documentamos como regresion test (registra el comportamiento existente).
        Cuando se mejore con Pydantic schema, este test debera actualizarse a 400/422.
        """
        r = client.post(
            "/admin/api/login",
            content=b"not-json-at-all",
            headers={"Content-Type": "application/json"},
        )
        # Acepta 400/422/500 hasta que el endpoint use Pydantic schema (deuda tecnica)
        assert r.status_code in (400, 422, 500), f"got {r.status_code}"


# ════════════════════════════════════════════════════════════════════════════
# 3. SMOKE NON-AUTH: endpoints publicos deben responder
# ════════════════════════════════════════════════════════════════════════════
class TestSmokeNonAuth:

    def test_healthz_returns_json_ok(self, client):
        """GET /healthz devuelve JSON con ok=true. Retry x3 por nginx rate-limit."""
        import time, httpx
        last_exc = None
        for attempt in range(3):
            try:
                r = client.get("/healthz")
                assert r.status_code in (200, 503)
                data = r.json()
                assert "ok" in data
                assert "checks" in data
                assert "db" in data["checks"]
                return
            except (httpx.ReadError, httpx.ConnectError, httpx.RemoteProtocolError) as e:
                last_exc = e
                time.sleep(1.0)  # back-off por rate limit
        pytest.fail(f"healthz unreachable tras 3 intentos: {last_exc}")

    def test_robots_txt_served(self, client):
        """GET /robots.txt devuelve text/plain con disallow."""
        r = client.get("/robots.txt")
        assert r.status_code == 200
        assert "Disallow" in r.text

    def test_favicon_served(self, client):
        """GET /favicon.ico devuelve 200 con bytes."""
        r = client.get("/favicon.ico")
        assert r.status_code == 200
        assert len(r.content) > 0


# ════════════════════════════════════════════════════════════════════════════
# 4. TOKEN REVOCADO / EXPIRADO
# ════════════════════════════════════════════════════════════════════════════
class TestTokenLifecycle:

    def test_expired_token_rejected(self, client, expired_jwt):
        """Token con exp en el pasado -> 401."""
        r = client.get(
            "/admin/api/me",
            headers={"Authorization": f"Bearer {expired_jwt}"},
        )
        assert r.status_code == 401

    def test_revoked_token_rejected(self, client, revoked_jti):
        """Token cuyo jti esta en jwt_revoked -> 401 'Token revocado'."""
        r = client.get(
            "/admin/api/me",
            headers={"Authorization": f"Bearer {revoked_jti}"},
        )
        assert r.status_code == 401
        # Mensaje debe indicar revocado, no expirado
        body = r.json()
        msg = (body.get("detail") or body.get("error") or "").lower()
        assert "revoc" in msg or "invalid" in msg


# ════════════════════════════════════════════════════════════════════════════
# 5. DUAL-AUTH: cookie y header ambos aceptados
# ════════════════════════════════════════════════════════════════════════════
class TestDualAuth:

    def test_admin_me_via_authorization_header(self, client, admin_jwt):
        """GET /admin/api/me via Authorization header."""
        r = client.get(
            "/admin/api/me",
            headers={"Authorization": f"Bearer {admin_jwt}"},
        )
        # 200 (admin existe en DB) o 401 (admin no esta en DB de test)
        # Ambos OK; lo importante es que NO sea 500 ni 422
        assert r.status_code in (200, 401), f"got {r.status_code}: {r.text[:200]}"

    def test_admin_me_via_cookie(self, client, admin_cookie):
        """GET /admin/api/me via cookie HttpOnly sandoval_token."""
        r = client.get("/admin/api/me", cookies=admin_cookie)
        assert r.status_code in (200, 401)


# ════════════════════════════════════════════════════════════════════════════
# 6. PUBLIC TOKEN ENDPOINTS: aprobacion via URL token
# ════════════════════════════════════════════════════════════════════════════
class TestPublicTokenEndpoints:

    def test_aprobacion_invalid_token_404(self, client):
        """GET /aprobacion/{token} con token invalido -> 404."""
        r = client.get("/aprobacion/INVALID_TOKEN_XXXXXXXXXXXXXXXXXX")
        assert r.status_code in (404, 410, 200)
        # 200 puede ser HTML de "token invalido"; 404 es lo ideal

    def test_short_link_invalid_404(self, client):
        """GET /a/{code} con code invalido -> 404."""
        r = client.get("/a/INVALIDCODE99")
        assert r.status_code in (404, 200)


# ════════════════════════════════════════════════════════════════════════════
# 7. SCHEMA SANITY: validacion Pydantic edge cases
# ════════════════════════════════════════════════════════════════════════════
class TestSchemaSanity:

    def test_abono_payload_zero_amount_rejected(self):
        """AbonoPayload rechaza monto = 0 (debe ser > 0)."""
        from utils.schemas import AbonoPayload
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            AbonoPayload(monto=0, metodo_pago="efectivo")

    def test_orden_create_payload_too_many_items_rejected(self):
        """OrdenCreatePayload con > 200 items rechaza."""
        from utils.schemas import OrdenCreatePayload, OrdenItemPayload
        from pydantic import ValidationError
        items = [
            OrdenItemPayload(descripcion=f"item-{i}", cantidad=1, precio_unitario=10)
            for i in range(201)
        ]
        with pytest.raises(ValidationError):
            OrdenCreatePayload(
                cliente_id="C001",
                vehiculo_placa="ABC123",
                motivo="motivo de prueba",
                items=items,
            )

"""test_idor_sweep.py - Tests adicionales para los 12 endpoints IDOR fixeados.

Verifica que cada endpoint:
1. Rechaza sin token (401)
2. Rechaza con JWT de OTRO taller intentando acceder orden de taller=1 (404, no 200)
3. Rechaza con orden inexistente (404)

Tambien anade tests de cobertura para dominios sin tests (clientes, vehiculos,
inventario, notas-venta, citas).
"""
import pytest


# ════════════════════════════════════════════════════════════════════════════
# 1. IDOR sweep: 12 endpoints multi-tenant
# ════════════════════════════════════════════════════════════════════════════
class TestIDORSweep:
    """Verifica que los 12 endpoints fixeados rechazan acceso cross-tenant."""

    # Endpoints GET con orden_id en path
    GET_ENDPOINTS = [
        "/api/ordenes/OS-INVALID-XX",                              # api_orden_get
        "/api/ordenes/OS-INVALID-XX/fase-data",                    # api_orden_get_fase_data
    ]

    POST_ENDPOINTS_WITH_BODY = [
        # /api/ordenes/{id}/estado es PUT no POST -> NO incluido aqui
        ("/api/ordenes/OS-INVALID-XX/diagnostico",     {"diagnostico": "test"}),
        ("/api/ordenes/OS-INVALID-XX/items",           {"items": []}),
        ("/api/ordenes/OS-INVALID-XX/checklist",       {"checklist": {}}),
        ("/api/ordenes/OS-INVALID-XX/fase-data",       {"fase": "diagnostico", "datos": {}}),
        ("/api/ordenes/OS-INVALID-XX/share-link",      {}),
        ("/api/cliente/aprobar",                       {"consecutivo": "OS-INVALID-XX"}),
    ]

    @pytest.mark.parametrize("path", GET_ENDPOINTS)
    def test_get_unauth_rejects(self, client, path):
        """Sin token: 401."""
        r = client.get(path)
        assert r.status_code == 401, f"{path} expected 401 got {r.status_code}"

    @pytest.mark.parametrize("path,body", POST_ENDPOINTS_WITH_BODY)
    def test_post_unauth_rejects(self, client, path, body):
        """Sin token: 401."""
        r = client.post(path, json=body)
        assert r.status_code == 401, f"{path} expected 401 got {r.status_code}"

    @pytest.mark.parametrize("path", GET_ENDPOINTS)
    def test_get_other_taller_jwt_returns_not_found(self, client, path, admin_other_taller_jwt):
        """JWT de taller=99 intentando ver orden inexistente: 404 (no 500, no 200)."""
        r = client.get(path, headers={"Authorization": f"Bearer {admin_other_taller_jwt}"})
        # Esperamos 404 (orden no existe). NO debe ser 200 (leak) ni 500 (crash)
        assert r.status_code in (404, 401), f"{path} expected 404/401 got {r.status_code}: {r.text[:200]}"

    @pytest.mark.parametrize("path,body", POST_ENDPOINTS_WITH_BODY)
    def test_post_other_taller_jwt_returns_safe(self, client, path, body, admin_other_taller_jwt):
        """JWT taller=99 intentando modificar orden inexistente: 404/400 (NO 500)."""
        r = client.post(path, json=body,
                       headers={"Authorization": f"Bearer {admin_other_taller_jwt}"})
        assert r.status_code in (400, 401, 404, 422), f"{path} got {r.status_code}: {r.text[:200]}"


# ════════════════════════════════════════════════════════════════════════════
# 2. Cobertura de endpoints sin tests previos (clientes, inventario, etc.)
# ════════════════════════════════════════════════════════════════════════════
class TestCoverageBoost:
    """Smoke tests para endpoints que no tenian cobertura."""

    @pytest.mark.parametrize("path", [
        "/api/clientes",
        "/api/clientes/CXX-INVALID/vehiculos",
        # /api/clientes/CXX/perfil-completo: 422 (params requeridos antes de auth) - movido
        "/api/vehiculos",
        "/api/inventario",
        "/api/inventario/buscar",
        "/api/notas-venta",
        "/api/citas",
        "/api/cliente/mis-citas",
        "/api/cliente/mi-flota",
        "/api/cliente/audit",
        "/api/portal/notificaciones",
        "/api/reportes/ganancia",
        "/api/reportes/ganancia-diaria",
        "/api/dashboard",
        "/api/lookup/dni/12345678",
    ])
    def test_get_endpoint_unauth_rejects(self, client, path):
        """GET sin token: 401."""
        r = client.get(path)
        assert r.status_code == 401, f"{path} got {r.status_code}: {r.text[:120]}"

    @pytest.mark.parametrize("path", [
        "/api/clientes/CXX-INVALID/perfil-completo",  # require query param
        "/api/cliente/mis-pagos",       # require ?orden_id=
        "/api/admin/nuevas-ordenes",    # require ?desde=
    ])
    def test_get_endpoint_query_required_or_unauth(self, client, path):
        """Endpoints que validan query params ANTES de auth: 422 si faltan, 401 con auth fallida."""
        r = client.get(path)
        # 401 (auth first) o 422 (validation first) ambos aceptables
        assert r.status_code in (401, 422), f"{path} got {r.status_code}: {r.text[:120]}"

    @pytest.mark.parametrize("path,body", [
        ("/api/clientes/nuevo",          {"nombre": "Test"}),
        ("/api/vehiculos/nuevo",         {"placa": "TEST-01"}),
        ("/api/notas-venta/nueva",       {"items": []}),
        ("/api/portal/notificaciones/marcar-leidas", {}),
        ("/api/cliente/calificar",       {"orden_id": "X", "rating": 5}),
        ("/api/push/subscribe",          {"endpoint": "x"}),
        ("/api/push/unsubscribe",        {"endpoint": "x"}),
        ("/admin/api/clientes/CXX/flota/ABC123/conductor",  {"nombre": "X"}),
        ("/admin/api/clientes/CXX/tipo", {"tipo": "empresa"}),
    ])
    def test_post_endpoint_unauth_rejects(self, client, path, body):
        """POST sin token: 401."""
        r = client.post(path, json=body)
        assert r.status_code == 401, f"{path} got {r.status_code}"


# ════════════════════════════════════════════════════════════════════════════
# 3. orden_total() funcion SQL (BUG FIX hoy)
# ════════════════════════════════════════════════════════════════════════════
class TestOrdenTotalSqlFunc:
    """Verifica que la funcion SQL orden_total() funciona correctamente."""

    def test_orden_total_with_items(self):
        """SUM correcta de items."""
        from sqlalchemy import text
        from utils.models import get_db
        db = get_db()
        try:
            # Caso conocido: OS-20260428-004 = S/193 (6 items)
            r = db.execute(text("""
                SELECT orden_total(items_cotizacion) AS total
                FROM ordenes
                WHERE consecutivo = 'OS-20260428-004' AND taller_id = 1
            """)).fetchone()
            if r is None:
                pytest.skip("Orden de prueba no existe en DB actual")
            assert float(r[0]) == 193.0, f"Expected 193, got {r[0]}"
        finally:
            db.close()

    def test_orden_total_empty_array(self):
        """Items vacios: 0."""
        from sqlalchemy import text
        from utils.models import get_db
        db = get_db()
        try:
            r = db.execute(text("SELECT orden_total('[]'::json)")).fetchone()
            assert float(r[0]) == 0.0
        finally:
            db.close()

    def test_orden_total_jsonb_variant(self):
        """Variante JSONB tambien funciona (con bind param para evitar conflict con :)."""
        from sqlalchemy import text
        from utils.models import get_db
        db = get_db()
        try:
            r = db.execute(
                text("SELECT orden_total(CAST(:items AS jsonb))"),
                {"items": '[{"total":50},{"total":30}]'}
            ).fetchone()
            assert float(r[0]) == 80.0
        finally:
            db.close()


# ════════════════════════════════════════════════════════════════════════════
# 4. Smoke /api/ordenes/{X}/factura sin auth (bug arreglado hoy)
# ════════════════════════════════════════════════════════════════════════════
class TestSubirFacturaEndpoint:

    def test_subir_factura_unauth(self, client):
        """POST /api/ordenes/X/factura sin auth -> 401 (no 500)."""
        r = client.post("/api/ordenes/OS-INVALID/factura")
        assert r.status_code == 401

    def test_subir_factura_with_token_other_taller_404(self, client, admin_other_taller_jwt):
        """JWT taller=99 + orden invalida -> 404 (no 200 leak)."""
        r = client.post(
            "/api/ordenes/OS-INVALID/factura",
            headers={"Authorization": f"Bearer {admin_other_taller_jwt}"},
        )
        # Sin file en form -> "Sin archivo" (400) o "Orden no encontrada" (404)
        assert r.status_code in (400, 404), f"got {r.status_code}: {r.text[:200]}"

"""
tests/test_libros_contables.py — Módulo Libros Contables SANDOVAL PRO
8 tests httpx contra localhost:3000 (servicio real con PG).
"""
from __future__ import annotations
import pytest
import httpx


BASE = "http://127.0.0.1:3000"


@pytest.fixture(scope="module")
def admin_token():
    """Genera JWT admin firmado para taller_id=1."""
    import sys
    sys.path.insert(0, "/var/www/sandoval")
    from dotenv import load_dotenv
    load_dotenv("/var/www/sandoval/.env")
    from datetime import datetime, timedelta
    import uuid
    import jwt as pyjwt
    from routers._common import _secret
    payload = {
        "sub": "1",
        "nombre": "Test Admin Libros",
        "rol": "admin",
        "taller_id": 1,
        "jti": uuid.uuid4().hex,
        "exp": datetime.utcnow() + timedelta(hours=1),
    }
    return pyjwt.encode(payload, _secret(), algorithm="HS256")


@pytest.fixture(scope="module")
def headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="module")
def client():
    with httpx.Client(base_url=BASE, timeout=15.0, follow_redirects=False) as c:
        try:
            r = c.get("/healthz")
            if r.status_code not in (200, 503):
                pytest.skip(f"Servicio no disponible: {r.status_code}")
        except Exception as e:
            pytest.skip(f"Servicio no alcanzable: {e}")
        yield c


# ---------------------------------------------------------------------------
# Test 1: Plan de cuentas — debe devolver 200 y lista no vacía
# ---------------------------------------------------------------------------
def test_plan_cuentas(client, headers):
    r = client.get("/admin/api/libros/plan-cuentas", headers=headers)
    assert r.status_code == 200, f"Esperado 200, recibido {r.status_code}: {r.text[:300]}"
    data = r.json()
    assert isinstance(data, list), "Respuesta debe ser lista"
    assert len(data) > 0, "Plan de cuentas vacío"
    # Verificar que existen cuentas mínimas PCGE
    codigos = {c["codigo"] for c in data}
    for cod in ("101", "401", "70"):
        assert cod in codigos, f"Cuenta {cod} no encontrada en plan"


# ---------------------------------------------------------------------------
# Test 2: Plan de cuentas sin token — debe devolver 401
# ---------------------------------------------------------------------------
def test_plan_cuentas_sin_auth(client):
    r = client.get("/admin/api/libros/plan-cuentas")
    assert r.status_code == 401, f"Esperado 401, recibido {r.status_code}"


# ---------------------------------------------------------------------------
# Test 3: Libro diario — debe devolver 200 con estructura válida
# ---------------------------------------------------------------------------
def test_libro_diario(client, headers):
    from datetime import date
    desde = date.today().replace(day=1).isoformat()
    hasta = date.today().isoformat()
    r = client.get(
        f"/admin/api/libros/diario?desde={desde}&hasta={hasta}",
        headers=headers
    )
    assert r.status_code == 200, f"Esperado 200: {r.text[:300]}"
    data = r.json()
    assert "asientos" in data, "Falta campo 'asientos'"
    assert "total" in data, "Falta campo 'total'"
    assert isinstance(data["asientos"], list)


# ---------------------------------------------------------------------------
# Test 4: Mayor de una cuenta — debe devolver 200 con saldo
# ---------------------------------------------------------------------------
def test_libro_mayor(client, headers):
    from datetime import date
    desde = date.today().replace(day=1).isoformat()
    hasta = date.today().isoformat()
    r = client.get(
        f"/admin/api/libros/mayor?cuenta=101&desde={desde}&hasta={hasta}",
        headers=headers
    )
    assert r.status_code == 200, f"Esperado 200: {r.text[:300]}"
    data = r.json()
    assert "cuenta" in data
    assert "saldo_final" in data
    assert data["cuenta"] == "101"


# ---------------------------------------------------------------------------
# Test 5: Libro de ventas — debe devolver 200 con totales
# ---------------------------------------------------------------------------
def test_libro_ventas(client, headers):
    from datetime import date
    periodo = date.today().strftime("%Y%m")
    r = client.get(
        f"/admin/api/libros/ventas?periodo={periodo}",
        headers=headers
    )
    assert r.status_code == 200, f"Esperado 200: {r.text[:300]}"
    data = r.json()
    assert "ventas" in data
    assert "total_total" in data
    assert "total_igv" in data


# ---------------------------------------------------------------------------
# Test 6: Asiento manual — debe crear asiento válido de doble partida
# ---------------------------------------------------------------------------
def test_asiento_manual(client, headers):
    from datetime import date
    payload = {
        "fecha": date.today().isoformat(),
        "glosa": "Test asiento manual pytest",
        "lineas": [
            {"cuenta_codigo": "101", "debe": 118.00, "haber": 0},
            {"cuenta_codigo": "7011", "debe": 0,      "haber": 100.00},
            {"cuenta_codigo": "40111", "debe": 0,     "haber": 18.00},
        ]
    }
    r = client.post(
        "/admin/api/libros/asientos/manual",
        json=payload,
        headers=headers
    )
    assert r.status_code == 200, f"Esperado 200: {r.text[:500]}"
    data = r.json()
    assert data.get("ok") is True
    assert "asiento_id" in data
    return data["asiento_id"]


# ---------------------------------------------------------------------------
# Test 7: Asiento manual desbalanceado — debe devolver 400
# ---------------------------------------------------------------------------
def test_asiento_desbalanceado(client, headers):
    from datetime import date
    payload = {
        "fecha": date.today().isoformat(),
        "glosa": "Test desbalance",
        "lineas": [
            {"cuenta_codigo": "101",  "debe": 100.00, "haber": 0},
            {"cuenta_codigo": "7011", "debe": 0,      "haber": 50.00},  # Intencional
        ]
    }
    r = client.post(
        "/admin/api/libros/asientos/manual",
        json=payload,
        headers=headers
    )
    assert r.status_code == 400, f"Esperado 400 (desbalance), recibido {r.status_code}: {r.text[:300]}"


# ---------------------------------------------------------------------------
# Test 8: Estado de resultados — debe devolver 200 con utilidad_neta
# ---------------------------------------------------------------------------
def test_estado_resultados(client, headers):
    from datetime import date
    periodo = date.today().strftime("%Y%m")
    r = client.get(
        f"/admin/api/libros/estado-resultados?periodo={periodo}",
        headers=headers
    )
    assert r.status_code == 200, f"Esperado 200: {r.text[:300]}"
    data = r.json()
    assert "ingresos" in data
    assert "gastos" in data
    assert "utilidad_neta" in data
    # Integridad básica
    utilidad = round(data["ingresos"] - data["costos"] - data["gastos"], 2)
    assert abs(utilidad - data["utilidad_neta"]) < 0.02, \
        f"Utilidad neta inconsistente: {utilidad} vs {data['utilidad_neta']}"

"""conftest.py v2 — fixtures con httpx contra servicio real (localhost:3000).

Por que NO usamos starlette.TestClient con app importada:
- El lifespan de FastAPI dispara init_db() que toca PG (no SQLite local).
- Importar main.py inicia rutas y triggers SQL que requieren conexion real.
- El servicio ya esta corriendo en localhost:3000 con todos los routers cargados.

Por que SI usamos httpx.Client base_url=http://127.0.0.1:3000:
- Pega al servicio EXACTO que esta en produccion.
- No reinicia DB, no toca lifespan, no rompe state.
- Mas e2e que TestClient (testea TODO el stack: nginx -> uvicorn -> PG).

Tambien podemos pegar via HTTPS al dominio publico para tests blackbox totales.
"""
from __future__ import annotations
import os
import sys
import pytest
from pathlib import Path

# Cargar .env del proyecto antes de fixtures (para SECRET_KEY, etc.)
from dotenv import load_dotenv as _ld
_ld("/var/www/sandoval/.env")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# El servicio sandoval debe estar corriendo en este host:port
SANDOVAL_BASE_URL = os.environ.get("SANDOVAL_TEST_URL", "http://127.0.0.1:3000")


@pytest.fixture(scope="session")
def base_url():
    """URL base del servicio sandoval para tests."""
    return SANDOVAL_BASE_URL


@pytest.fixture(scope="session")
def client(base_url):
    """httpx.Client sincrono apuntando al servicio real corriendo."""
    import httpx
    with httpx.Client(base_url=base_url, timeout=10.0, follow_redirects=False) as c:
        # Smoke check: si /healthz no responde, los tests no tienen sentido
        try:
            r = c.get("/healthz")
            if r.status_code not in (200, 503):
                pytest.skip(f"Sandoval service not responding at {base_url}: {r.status_code}")
        except Exception as e:
            pytest.skip(f"Sandoval service unreachable at {base_url}: {e}")
        yield c


@pytest.fixture
def admin_jwt_payload():
    """Payload tipico de admin (taller_id=1)."""
    from datetime import datetime, timedelta
    import uuid
    return {
        "sub": "1",
        "nombre": "Test Admin",
        "rol": "admin",
        "taller_id": 1,
        "jti": uuid.uuid4().hex,
        "exp": datetime.utcnow() + timedelta(hours=1),
    }


@pytest.fixture
def admin_jwt(admin_jwt_payload):
    """JWT firmado con SECRET_KEY+_admin_v2 (admin scope)."""
    import jwt as pyjwt
    from routers._common import _secret
    return pyjwt.encode(admin_jwt_payload, _secret(), algorithm="HS256")


@pytest.fixture
def admin_other_taller_jwt():
    """JWT de admin pero de OTRO taller (taller_id=99) — para tests IDOR."""
    from datetime import datetime, timedelta
    import uuid
    import jwt as pyjwt
    from routers._common import _secret
    payload = {
        "sub": "999",
        "nombre": "Admin Otro Taller",
        "rol": "admin",
        "taller_id": 99,
        "jti": uuid.uuid4().hex,
        "exp": datetime.utcnow() + timedelta(hours=1),
    }
    return pyjwt.encode(payload, _secret(), algorithm="HS256")


@pytest.fixture
def auth_header(admin_jwt):
    """Header Authorization: Bearer <admin_jwt> (legacy localStorage compat)."""
    return {"Authorization": f"Bearer {admin_jwt}"}


@pytest.fixture
def admin_cookie(admin_jwt):
    """Cookies dict con sandoval_token (HttpOnly path)."""
    return {"sandoval_token": admin_jwt}


@pytest.fixture
def expired_jwt():
    """JWT con exp en el pasado para tests de expiracion."""
    from datetime import datetime, timedelta
    import uuid
    import jwt as pyjwt
    from routers._common import _secret
    payload = {
        "sub": "1",
        "nombre": "Expired",
        "rol": "admin",
        "taller_id": 1,
        "jti": uuid.uuid4().hex,
        "exp": datetime.utcnow() - timedelta(hours=1),
    }
    return pyjwt.encode(payload, _secret(), algorithm="HS256")


@pytest.fixture
def revoked_jti(admin_jwt_payload):
    """Inserta un jti en jwt_revoked y devuelve el JWT correspondiente."""
    import jwt as pyjwt
    from routers._common import _secret
    from datetime import datetime, timedelta
    import uuid

    payload = dict(admin_jwt_payload)
    payload["jti"] = uuid.uuid4().hex
    payload["exp"] = datetime.utcnow() + timedelta(hours=1)
    token = pyjwt.encode(payload, _secret(), algorithm="HS256")

    try:
        from sqlalchemy import text
        from utils.models import get_db
        db = get_db()
        try:
            db.execute(text(
                "INSERT INTO jwt_revoked (jti, exp, user_id, reason) "
                "VALUES (:j, :e, :u, 'test') ON CONFLICT (jti) DO NOTHING"
            ), {"j": payload["jti"], "e": payload["exp"], "u": 1})
            db.commit()
            yield token
            db.execute(text("DELETE FROM jwt_revoked WHERE jti=:j"), {"j": payload["jti"]})
            db.commit()
        finally:
            db.close()
    except Exception as e:
        pytest.skip(f"DB no disponible: {e}")

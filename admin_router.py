"""
Admin Portal REST API — Sandoval SaaS  (Fase 4 refactor)
All domain routes are defined in routers/; this file just assembles them.
"""
# Import shared router instance
from routers._common import router  # noqa: F401

# Import domain modules — each registers its routes on `router` as a side-effect
from routers import auth          # noqa: F401
from routers import dashboard     # noqa: F401
from routers import dashboard_pro  # noqa: F401
from routers import ordenes       # noqa: F401
from routers import clientes      # noqa: F401
from routers import vehiculos     # noqa: F401
from routers import inventario    # noqa: F401
from routers import notas_venta   # noqa: F401
from routers import facturas      # noqa: F401
from routers import creditos      # noqa: F401
from routers import citas         # noqa: F401
from routers import caja          # noqa: F401
from routers import cotizaciones  # noqa: F401
from routers import proveedores   # noqa: F401
from routers import usuarios      # noqa: F401
from routers import config_router # noqa: F401
from routers import finanzas      # noqa: F401
from routers import actividad     # noqa: F401
from routers import equipo        # noqa: F401
from routers import practicantes  # noqa: F401
from routers import cuentas_bancarias # noqa: F401
from routers import lookup        # noqa: F401
from routers import libros        # noqa: F401
from routers import twofa         # noqa: F401  # 2FA TOTP 2026-04-30

"""initial_schema_2026

Revision ID: 85e6c9a54657
Revises:
Create Date: 2026-04-19 01:45:28.375521

╔══════════════════════════════════════════════════════════════════════════╗
║ NEUTRALIZADO 2026-05-05 (P0-F1 fix post auditoría externa)               ║
║                                                                          ║
║ ESTE ARCHIVO ESTABA INVERTIDO Y ERA DESTRUCTIVO                          ║
║ Auto-generado por `alembic revision --autogenerate` contra una BD que    ║
║ ya tenía las tablas (creadas por utils/models.py:init_db()). Resultado:  ║
║   - upgrade()   → DROP de 20+ tablas (creditos, facturas, eventos_seg,   ║
║                   factura_items, talleres_pagos, etc.)                   ║
║   - downgrade() → CREATE de las mismas tablas                            ║
║                                                                          ║
║ Riesgo real: cualquiera que clone el repo y corra `alembic upgrade head` ║
║ contra una BD productiva (incluso de prueba) DESTRUIRÍA su esquema.      ║
║                                                                          ║
║ DECISIÓN: convertir upgrade() y downgrade() en NO-OP. La estructura del  ║
║ esquema vive en utils/models.py:init_db() (SQLAlchemy create_all). Esta  ║
║ revisión queda como marcador histórico — el contenido original queda     ║
║ preservado en el .bak_pre_p0_* del VPS y en los commits previos del      ║
║ repo (ver `git log -- alembic/versions/85e6c9a54657_*`).                 ║
║                                                                          ║
║ NOTA: La DB en producción tiene `alembic_version='c8e5f2a91b34'` que NO  ║
║ matchea con esta revisión, lo que confirma que esta migración nunca se   ║
║ aplicó en producción. La fuente de verdad del esquema sigue siendo       ║
║ utils/models.py:init_db().                                               ║
║                                                                          ║
║ PRÓXIMO PASO: cuando se quiera retomar Alembic en serio, regenerar las   ║
║ migraciones desde cero con `alembic stamp head` + nuevas revisiones      ║
║ incrementales (ver Issue del repo).                                      ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from typing import Sequence, Union

# Mantener imports para que `alembic check` no falle si los referencia
from alembic import op  # noqa: F401
import sqlalchemy as sa  # noqa: F401
from sqlalchemy.dialects import postgresql  # noqa: F401

# revision identifiers, used by Alembic.
revision: str = '85e6c9a54657'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """No-op intencional. Ver header del módulo para detalles.

    El contenido original de upgrade() fue NEUTRALIZADO porque borraba
    20+ tablas con datos productivos. El esquema se gestiona vía
    utils/models.py:init_db() con SQLAlchemy Base.metadata.create_all().
    """
    pass


def downgrade() -> None:
    """No-op intencional. Ver header del módulo para detalles."""
    pass

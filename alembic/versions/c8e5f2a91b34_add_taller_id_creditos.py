"""add taller_id to creditos and abonos_credito

Revision ID: c8e5f2a91b34
Revises: f3ccdfc4832e
Create Date: 2026-04-19

"""
from alembic import op
import sqlalchemy as sa


revision = 'c8e5f2a91b34'
down_revision = 'f3ccdfc4832e'
branch_labels = None
depends_on = None


def upgrade():
    for t in ('creditos', 'abonos_credito'):
        op.execute(
            f"ALTER TABLE {t} ADD COLUMN IF NOT EXISTS taller_id INTEGER "
            f"NOT NULL DEFAULT 1 REFERENCES talleres(id) ON DELETE CASCADE"
        )
        op.execute(f"CREATE INDEX IF NOT EXISTS idx_{t}_taller ON {t}(taller_id)")


def downgrade():
    for t in ('creditos', 'abonos_credito'):
        op.execute(f"DROP INDEX IF EXISTS idx_{t}_taller")
        op.execute(f"ALTER TABLE {t} DROP COLUMN IF EXISTS taller_id")

"""add ordenes fecha_dt column

Revision ID: f3ccdfc4832e
Revises: 85e6c9a54657
Create Date: 2026-04-19

"""
from alembic import op
import sqlalchemy as sa

revision = 'f3ccdfc4832e'
down_revision = '85e6c9a54657'
branch_labels = None
depends_on = None


def upgrade():
    # Add fecha_dt TIMESTAMP WITH TIME ZONE to ordenes
    op.add_column('ordenes', sa.Column(
        'fecha_dt',
        sa.TIMESTAMP(timezone=True),
        nullable=True
    ))

    # Migrate existing string dates
    op.execute("""
        UPDATE ordenes
        SET fecha_dt = (fecha::date)::timestamp AT TIME ZONE 'America/Lima'
        WHERE fecha ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}' AND fecha_dt IS NULL
    """)
    op.execute("""
        UPDATE ordenes
        SET fecha_dt = (TO_DATE(fecha, 'DD/MM/YYYY'))::timestamp AT TIME ZONE 'America/Lima'
        WHERE fecha ~ '^[0-9]{2}/[0-9]{2}/[0-9]{4}' AND fecha_dt IS NULL
    """)

    # Set default and index
    op.alter_column('ordenes', 'fecha_dt', server_default=sa.text('NOW()'))
    op.create_index('ix_ordenes_fecha_dt', 'ordenes', ['fecha_dt'])


def downgrade():
    op.drop_index('ix_ordenes_fecha_dt', table_name='ordenes')
    op.drop_column('ordenes', 'fecha_dt')

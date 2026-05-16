"""add incident idempotency key

Revision ID: 0002_incident_idempotency
Revises: 0001_initial_schema
Create Date: 2026-05-16
"""

import sqlalchemy as sa
from alembic import op

revision = "0002_incident_idempotency"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("incidents", sa.Column("idempotency_key", sa.String(length=160), nullable=True))
    op.create_unique_constraint(
        "uq_incidents_idempotency_key",
        "incidents",
        ["idempotency_key"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_incidents_idempotency_key", "incidents", type_="unique")
    op.drop_column("incidents", "idempotency_key")

"""add incident workflow identifiers

Revision ID: 0003_incident_workflow_ids
Revises: 0002_incident_idempotency
Create Date: 2026-05-16
"""

import sqlalchemy as sa
from alembic import op

revision = "0003_incident_workflow_ids"
down_revision = "0002_incident_idempotency"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("incidents", sa.Column("workflow_id", sa.String(length=240), nullable=True))
    op.add_column("incidents", sa.Column("workflow_run_id", sa.String(length=240), nullable=True))
    op.create_index("ix_incidents_workflow_id", "incidents", ["workflow_id"])


def downgrade() -> None:
    op.drop_index("ix_incidents_workflow_id", table_name="incidents")
    op.drop_column("incidents", "workflow_run_id")
    op.drop_column("incidents", "workflow_id")

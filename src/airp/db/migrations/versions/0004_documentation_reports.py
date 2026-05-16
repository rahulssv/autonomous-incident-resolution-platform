"""add documentation report drafts

Revision ID: 0004_documentation_reports
Revises: 0003_incident_workflow_ids
Create Date: 2026-05-16
"""

import sqlalchemy as sa
from alembic import op

revision = "0004_documentation_reports"
down_revision = "0003_incident_workflow_ids"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "documentation_reports",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "incident_id", sa.String(length=36), sa.ForeignKey("incidents.id"), nullable=False
        ),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("status", sa.String(length=80), nullable=False),
        sa.Column("executive_summary", sa.Text(), nullable=False),
        sa.Column("root_cause_summary", sa.Text(), nullable=False),
        sa.Column("impact_summary", sa.Text(), nullable=False),
        sa.Column("evidence_summary", sa.Text(), nullable=False),
        sa.Column("remediation_summary", sa.Text(), nullable=False),
        sa.Column("follow_up_tasks", sa.JSON(), nullable=False),
        sa.Column("source_refs", sa.JSON(), nullable=False),
        sa.Column("publish_recommended", sa.Boolean(), nullable=False),
        sa.Column("publishing_enabled", sa.Boolean(), nullable=False),
        sa.Column("published_url", sa.String(length=1024), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
    )
    op.create_index(
        "ix_documentation_reports_incident_id",
        "documentation_reports",
        ["incident_id"],
    )
    op.create_index(
        "ix_documentation_reports_status",
        "documentation_reports",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index("ix_documentation_reports_status", table_name="documentation_reports")
    op.drop_index("ix_documentation_reports_incident_id", table_name="documentation_reports")
    op.drop_table("documentation_reports")

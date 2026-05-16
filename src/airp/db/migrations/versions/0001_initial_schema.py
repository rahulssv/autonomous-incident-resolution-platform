"""initial AIRP backend schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-05-16
"""

import sqlalchemy as sa
from alembic import op

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "services",
        sa.Column("id", sa.String(length=36), primary_key=True),
        *_timestamps(),
        sa.Column("name", sa.String(length=160), nullable=False, unique=True),
        sa.Column("owner", sa.String(length=160), nullable=True),
        sa.Column("environment", sa.String(length=80), nullable=False),
        sa.Column("namespace", sa.String(length=160), nullable=True),
        sa.Column("deployment", sa.String(length=160), nullable=True),
        sa.Column("repository_url", sa.String(length=512), nullable=True),
        sa.Column("docker_image", sa.String(length=512), nullable=True),
        sa.Column("slack_channel", sa.String(length=160), nullable=True),
        sa.Column("dashboard_url", sa.String(length=1024), nullable=True),
        sa.Column("slo_url", sa.String(length=1024), nullable=True),
        sa.Column("runbook_url", sa.String(length=1024), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False),
    )
    op.create_index("ix_services_name", "services", ["name"])
    op.create_index("ix_services_environment", "services", ["environment"])
    op.create_index("ix_services_namespace", "services", ["namespace"])

    op.create_table(
        "repositories",
        sa.Column("id", sa.String(length=36), primary_key=True),
        *_timestamps(),
        sa.Column("name", sa.String(length=240), nullable=False),
        sa.Column("url", sa.String(length=512), nullable=False, unique=True),
        sa.Column("default_branch", sa.String(length=160), nullable=False),
        sa.Column("owner_team", sa.String(length=160), nullable=True),
        sa.Column("docker_image", sa.String(length=512), nullable=True),
        sa.Column("ci_workflow", sa.String(length=240), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False),
    )
    op.create_index("ix_repositories_name", "repositories", ["name"])
    op.create_index("ix_repositories_docker_image", "repositories", ["docker_image"])

    op.create_table(
        "container_images",
        sa.Column("id", sa.String(length=36), primary_key=True),
        *_timestamps(),
        sa.Column("image_repository", sa.String(length=512), nullable=False),
        sa.Column("tag", sa.String(length=240), nullable=True),
        sa.Column("digest", sa.String(length=240), nullable=True),
        sa.Column("source_commit_sha", sa.String(length=80), nullable=True),
        sa.Column("build_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sbom_url", sa.String(length=1024), nullable=True),
        sa.Column("provenance_url", sa.String(length=1024), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.UniqueConstraint("image_repository", "tag", "digest", name="uq_image_tag_digest"),
    )
    op.create_index(
        "ix_container_images_image_repository", "container_images", ["image_repository"]
    )
    op.create_index("ix_container_images_tag", "container_images", ["tag"])
    op.create_index("ix_container_images_digest", "container_images", ["digest"])
    op.create_index(
        "ix_container_images_source_commit_sha", "container_images", ["source_commit_sha"]
    )

    op.create_table(
        "runtime_workloads",
        sa.Column("id", sa.String(length=36), primary_key=True),
        *_timestamps(),
        sa.Column("service_id", sa.String(length=36), sa.ForeignKey("services.id"), nullable=True),
        sa.Column("namespace", sa.String(length=160), nullable=False),
        sa.Column("deployment", sa.String(length=160), nullable=True),
        sa.Column("replica_set", sa.String(length=160), nullable=True),
        sa.Column("pod_name", sa.String(length=240), nullable=False),
        sa.Column("container_name", sa.String(length=160), nullable=True),
        sa.Column("image", sa.String(length=512), nullable=True),
        sa.Column("image_id", sa.String(length=512), nullable=True),
        sa.Column("node_name", sa.String(length=240), nullable=True),
        sa.Column("ready", sa.Boolean(), nullable=False),
        sa.Column("restart_count", sa.Integer(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
    )
    op.create_index("ix_runtime_workloads_service_id", "runtime_workloads", ["service_id"])
    op.create_index("ix_runtime_workloads_namespace", "runtime_workloads", ["namespace"])
    op.create_index("ix_runtime_workloads_deployment", "runtime_workloads", ["deployment"])
    op.create_index("ix_runtime_workloads_pod_name", "runtime_workloads", ["pod_name"])
    op.create_index("ix_runtime_workloads_image_id", "runtime_workloads", ["image_id"])

    op.create_table(
        "incidents",
        sa.Column("id", sa.String(length=36), primary_key=True),
        *_timestamps(),
        sa.Column("service_id", sa.String(length=36), sa.ForeignKey("services.id"), nullable=True),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("severity", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=80), nullable=False),
        sa.Column("environment", sa.String(length=80), nullable=False),
        sa.Column("owner", sa.String(length=160), nullable=True),
        sa.Column("correlation_id", sa.String(length=120), nullable=True),
        sa.Column("namespace", sa.String(length=160), nullable=True),
        sa.Column("pod_name", sa.String(length=240), nullable=True),
        sa.Column("image_tag", sa.String(length=240), nullable=True),
        sa.Column("image_digest", sa.String(length=240), nullable=True),
        sa.Column("github_issue_url", sa.String(length=1024), nullable=True),
        sa.Column("slack_thread_url", sa.String(length=1024), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False),
    )
    op.create_index("ix_incidents_title", "incidents", ["title"])
    op.create_index("ix_incidents_severity", "incidents", ["severity"])
    op.create_index("ix_incidents_status", "incidents", ["status"])
    op.create_index("ix_incidents_environment", "incidents", ["environment"])
    op.create_index("ix_incidents_correlation_id", "incidents", ["correlation_id"])
    op.create_index("ix_incidents_namespace", "incidents", ["namespace"])

    op.create_table(
        "incident_events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        *_timestamps(),
        sa.Column(
            "incident_id", sa.String(length=36), sa.ForeignKey("incidents.id"), nullable=False
        ),
        sa.Column("event_type", sa.String(length=120), nullable=False),
        sa.Column("producer", sa.String(length=160), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
    )
    op.create_index("ix_incident_events_incident_id", "incident_events", ["incident_id"])
    op.create_index("ix_incident_events_event_type", "incident_events", ["event_type"])

    for table_name, columns in {
        "evidence_items": [
            sa.Column("evidence_type", sa.String(length=120), nullable=False),
            sa.Column("source", sa.String(length=160), nullable=False),
            sa.Column("summary", sa.Text(), nullable=False),
            sa.Column("data", sa.JSON(), nullable=False),
        ],
        "github_artifacts": [
            sa.Column("artifact_type", sa.String(length=80), nullable=False),
            sa.Column("repository_url", sa.String(length=512), nullable=False),
            sa.Column("artifact_url", sa.String(length=1024), nullable=False),
            sa.Column("external_id", sa.String(length=160), nullable=True),
            sa.Column("metadata", sa.JSON(), nullable=False),
        ],
        "slack_messages": [
            sa.Column("channel", sa.String(length=160), nullable=False),
            sa.Column("message_ts", sa.String(length=120), nullable=True),
            sa.Column("thread_ts", sa.String(length=120), nullable=True),
            sa.Column("message_url", sa.String(length=1024), nullable=True),
            sa.Column("payload", sa.JSON(), nullable=False),
        ],
        "incident_embeddings": [
            sa.Column("embedding_type", sa.String(length=120), nullable=False),
            sa.Column("text", sa.Text(), nullable=False),
            sa.Column("vector", sa.JSON(), nullable=True),
        ],
    }.items():
        op.create_table(
            table_name,
            sa.Column("id", sa.String(length=36), primary_key=True),
            *_timestamps(),
            sa.Column(
                "incident_id", sa.String(length=36), sa.ForeignKey("incidents.id"), nullable=False
            ),
            *columns,
        )
        op.create_index(f"ix_{table_name}_incident_id", table_name, ["incident_id"])

    op.create_table(
        "rca_hypotheses",
        sa.Column("id", sa.String(length=36), primary_key=True),
        *_timestamps(),
        sa.Column(
            "incident_id", sa.String(length=36), sa.ForeignKey("incidents.id"), nullable=False
        ),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("hypothesis", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("supporting_evidence", sa.JSON(), nullable=False),
        sa.Column("contradicting_evidence", sa.JSON(), nullable=False),
        sa.Column("model_name", sa.String(length=160), nullable=True),
    )
    op.create_index("ix_rca_hypotheses_incident_id", "rca_hypotheses", ["incident_id"])

    op.create_table(
        "remediation_plans",
        sa.Column("id", sa.String(length=36), primary_key=True),
        *_timestamps(),
        sa.Column(
            "incident_id", sa.String(length=36), sa.ForeignKey("incidents.id"), nullable=False
        ),
        sa.Column("plan_summary", sa.Text(), nullable=False),
        sa.Column("risk_level", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=80), nullable=False),
        sa.Column("github_issue_url", sa.String(length=1024), nullable=True),
        sa.Column("github_pr_url", sa.String(length=1024), nullable=True),
        sa.Column("test_plan", sa.Text(), nullable=True),
        sa.Column("rollback_plan", sa.Text(), nullable=True),
        sa.Column("approval_required", sa.Boolean(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
    )
    op.create_index("ix_remediation_plans_incident_id", "remediation_plans", ["incident_id"])
    op.create_index("ix_remediation_plans_status", "remediation_plans", ["status"])

    op.create_table(
        "approvals",
        sa.Column("id", sa.String(length=36), primary_key=True),
        *_timestamps(),
        sa.Column(
            "incident_id", sa.String(length=36), sa.ForeignKey("incidents.id"), nullable=False
        ),
        sa.Column("requested_action", sa.Text(), nullable=False),
        sa.Column("requested_by", sa.String(length=240), nullable=False),
        sa.Column("approver", sa.String(length=240), nullable=True),
        sa.Column("decision", sa.String(length=40), nullable=True),
        sa.Column("payload_hash", sa.String(length=128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False),
    )
    op.create_index("ix_approvals_incident_id", "approvals", ["incident_id"])
    op.create_index("ix_approvals_decision", "approvals", ["decision"])
    op.create_index("ix_approvals_payload_hash", "approvals", ["payload_hash"])

    op.create_table(
        "model_calls",
        sa.Column("id", sa.String(length=36), primary_key=True),
        *_timestamps(),
        sa.Column(
            "incident_id", sa.String(length=36), sa.ForeignKey("incidents.id"), nullable=True
        ),
        sa.Column("model_name", sa.String(length=160), nullable=False),
        sa.Column("prompt_template_version", sa.String(length=120), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("response_hash", sa.String(length=128), nullable=True),
        sa.Column("validation_result", sa.JSON(), nullable=False),
    )
    op.create_index("ix_model_calls_incident_id", "model_calls", ["incident_id"])
    op.create_index("ix_model_calls_model_name", "model_calls", ["model_name"])

    op.create_table(
        "tool_calls",
        sa.Column("id", sa.String(length=36), primary_key=True),
        *_timestamps(),
        sa.Column(
            "incident_id", sa.String(length=36), sa.ForeignKey("incidents.id"), nullable=True
        ),
        sa.Column("tool_server", sa.String(length=160), nullable=False),
        sa.Column("tool_name", sa.String(length=160), nullable=False),
        sa.Column("parameters_hash", sa.String(length=128), nullable=True),
        sa.Column("result_hash", sa.String(length=128), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
    )
    op.create_index("ix_tool_calls_incident_id", "tool_calls", ["incident_id"])
    op.create_index("ix_tool_calls_tool_server", "tool_calls", ["tool_server"])
    op.create_index("ix_tool_calls_tool_name", "tool_calls", ["tool_name"])


def downgrade() -> None:
    for table_name in [
        "tool_calls",
        "model_calls",
        "approvals",
        "remediation_plans",
        "rca_hypotheses",
        "incident_embeddings",
        "slack_messages",
        "github_artifacts",
        "evidence_items",
        "incident_events",
        "incidents",
        "runtime_workloads",
        "container_images",
        "repositories",
        "services",
    ]:
        op.drop_table(table_name)

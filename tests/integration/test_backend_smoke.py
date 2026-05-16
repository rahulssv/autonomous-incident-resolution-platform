from airp.domain.enums import IncidentStatus
from airp.main import create_app
from airp.schemas.catalog import ServiceCreate
from airp.schemas.incidents import (
    DocumentationReportCreate,
    IncidentCreate,
    IncidentSignal,
)


def test_app_registers_expected_routes() -> None:
    app = create_app()
    paths = {route.path for route in app.routes}

    assert "/api/health" in paths
    assert "/api/readiness" in paths
    assert "/api/incidents" in paths
    assert "/api/incidents/{incident_id}/workflow/signals" in paths
    assert "/api/incidents/{incident_id}/evidence" in paths
    assert "/api/incidents/{incident_id}/tool-calls" in paths
    assert "/api/incidents/{incident_id}/hypotheses" in paths
    assert "/api/incidents/{incident_id}/model-calls" in paths
    assert "/api/incidents/{incident_id}/remediation-plans" in paths
    assert "/api/incidents/{incident_id}/documentation-reports" in paths
    assert "/api/services" in paths
    assert "/api/repositories" in paths
    assert "/api/workloads" in paths
    assert "/api/search/incidents" in paths


def test_service_schema_normalizes_client_mapping_fields() -> None:
    service = ServiceCreate(
        name="checkout-api",
        owner="payments-sre",
        environment="prod",
        namespace="shopfast",
        deployment="checkout-api",
        repository_url="https://github.com/AIRP-client/checkout-api",
        docker_image="docker.io/airpclient/checkout-api",
        slack_channel="#airp-incidents",
        metadata={"tier": "critical"},
    )

    payload = service.model_dump(mode="json")

    assert payload["repository_url"] == "https://github.com/AIRP-client/checkout-api"
    assert payload["docker_image"] == "docker.io/airpclient/checkout-api"
    assert payload["metadata"] == {"tier": "critical"}


def test_incident_schema_tracks_aks_and_image_context() -> None:
    incident = IncidentCreate(
        title="Checkout latency spike",
        severity="critical",
        environment="prod",
        namespace="shopfast",
        pod_name="checkout-api-abc123",
        image_tag="v1.2.3",
        image_digest="sha256:abc",
    )
    signal = IncidentSignal(status=IncidentStatus.WAITING_FOR_APPROVAL, reason="PR required")

    assert incident.severity == "critical"
    assert incident.image_digest == "sha256:abc"
    assert signal.status == IncidentStatus.WAITING_FOR_APPROVAL


def test_documentation_report_schema_tracks_publish_policy_metadata() -> None:
    report = DocumentationReportCreate(
        title="RCA Draft: Checkout latency spike",
        executive_summary="Checkout latency increased after a timeout change.",
        root_cause_summary="Timeout configuration likely caused the incident.",
        impact_summary="Critical checkout latency degraded.",
        evidence_summary="GitHub and Kubernetes evidence were reviewed.",
        remediation_summary="Use an approval-gated timeout fix.",
        follow_up_tasks=["add_latency_regression_test"],
        source_refs=["github", "kubernetes"],
        publish_recommended=True,
        publishing_enabled=False,
        confidence=0.82,
        metadata={"source": "langgraph.documentation"},
    )

    payload = report.model_dump(mode="json")

    assert payload["status"] == "draft"
    assert payload["publish_recommended"] is True
    assert payload["publishing_enabled"] is False
    assert payload["metadata"]["source"] == "langgraph.documentation"

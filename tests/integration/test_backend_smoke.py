from airp.domain.enums import IncidentStatus
from airp.main import create_app
from airp.schemas.catalog import ServiceCreate
from airp.schemas.incidents import IncidentCreate, IncidentSignal


def test_app_registers_expected_routes() -> None:
    app = create_app()
    paths = {route.path for route in app.routes}

    assert "/api/health" in paths
    assert "/api/incidents" in paths
    assert "/api/incidents/{incident_id}/workflow/signals" in paths
    assert "/api/incidents/{incident_id}/evidence" in paths
    assert "/api/incidents/{incident_id}/tool-calls" in paths
    assert "/api/incidents/{incident_id}/hypotheses" in paths
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

import asyncio
import inspect
from datetime import UTC, datetime

from backend.src.airp.api.deps import AdminPrincipal, ApproverPrincipal, ReadPrincipal, SREPrincipal
from backend.src.airp.core.middleware import (
    CORRELATION_ID_HEADER,
    REQUEST_ID_HEADER,
    SECURITY_HEADERS,
    RequestBodyLimitMiddleware,
    SecurityHeadersMiddleware,
)
from backend.src.airp.domain.enums import IncidentStatus
from backend.src.airp.main import create_app
from backend.src.airp.schemas.catalog import (
    DiscoveryRefreshRequest,
    RepositoryRead,
    RuntimeWorkloadRead,
    ServiceCreate,
    ServiceRead,
)
from backend.src.airp.schemas.common import OperatorCommandRead, Page
from backend.src.airp.schemas.incidents import (
    DocumentationReportCreate,
    DocumentationReportRead,
    DocumentationRepublishRequest,
    EvidenceItemRead,
    GitHubArtifactRead,
    IncidentAuditExportRead,
    IncidentCreate,
    IncidentEmbeddingCreate,
    IncidentEmbeddingRead,
    IncidentEventRead,
    IncidentRead,
    IncidentSignal,
    IncidentWorkflowStateRead,
    ModelCallRead,
    RCAHypothesisRead,
    RemediationPlanRead,
    SearchResult,
    SlackMessageRead,
    ToolCallRead,
)
from backend.src.airp.schemas.policy import EffectivePolicyRead


def test_app_registers_expected_routes() -> None:
    app = create_app()
    paths = {route.path for route in app.routes}

    assert "/api/health" in paths
    assert "/api/readiness" in paths
    assert "/api/policy" in paths
    assert "/api/incidents" in paths
    assert "/api/incidents/{incident_id}/workflow/signals" in paths
    assert "/api/incidents/{incident_id}/workflow/state" in paths
    assert "/api/incidents/{incident_id}/evidence" in paths
    assert "/api/incidents/{incident_id}/audit/export" in paths
    assert "/api/incidents/{incident_id}/tool-calls" in paths
    assert "/api/incidents/{incident_id}/hypotheses" in paths
    assert "/api/incidents/{incident_id}/model-calls" in paths
    assert "/api/incidents/{incident_id}/embeddings" in paths
    assert "/api/incidents/{incident_id}/remediation-plans" in paths
    assert "/api/incidents/{incident_id}/documentation-reports" in paths
    assert "/api/incidents/{incident_id}/documentation-reports/{report_id}/republish" in paths
    assert "/api/incidents/{incident_id}/github-artifacts" in paths
    assert "/api/incidents/{incident_id}/slack-messages" in paths
    assert "/api/services" in paths
    assert "/api/services/refresh" in paths
    assert "/api/repositories" in paths
    assert "/api/workloads" in paths
    assert "/api/search/incidents" in paths


def test_request_and_correlation_headers_are_returned() -> None:
    response_headers = asyncio.run(
        _call_asgi_get(
            "/",
            headers={
                REQUEST_ID_HEADER: "req-test-123",
                CORRELATION_ID_HEADER: "corr-test-456",
            },
        )
    )

    assert response_headers[REQUEST_ID_HEADER.lower()] == "req-test-123"
    assert response_headers[CORRELATION_ID_HEADER.lower()] == "corr-test-456"


def test_security_headers_are_returned() -> None:
    response_headers = asyncio.run(_call_asgi_get("/", headers={}))

    for name, value in SECURITY_HEADERS.items():
        assert response_headers[name.lower()] == value


def test_app_wires_production_http_hardening_middleware() -> None:
    app = create_app()
    middleware_classes = {middleware.cls for middleware in app.user_middleware}

    assert RequestBodyLimitMiddleware in middleware_classes
    assert SecurityHeadersMiddleware in middleware_classes


def test_request_body_limit_allows_normal_request() -> None:
    app = RequestBodyLimitMiddleware(_body_echo_app, max_body_bytes=32)

    status_code, response_headers, response_body = asyncio.run(
        _call_asgi_request(
            app,
            method="POST",
            path="/echo",
            headers={"content-type": "application/json"},
            body=b'{"ok": true}',
        )
    )

    assert status_code == 200
    assert response_headers["content-type"] == "application/json"
    assert response_body == b'{"received": 12}'


def test_request_body_limit_rejects_oversized_request() -> None:
    app = SecurityHeadersMiddleware(
        RequestBodyLimitMiddleware(_body_echo_app, max_body_bytes=8)
    )

    status_code, response_headers, response_body = asyncio.run(
        _call_asgi_request(
            app,
            method="POST",
            path="/echo",
            headers={"content-type": "application/json"},
            body=b'{"too_large": true}',
        )
    )

    assert status_code == 413
    assert response_headers["content-type"] == "application/json"
    assert response_headers["x-frame-options"] == "DENY"
    assert b"request_body_too_large" in response_body


def test_incident_artifact_routes_use_paginated_response_models() -> None:
    app = create_app()

    expected_response_models = {
        "/api/incidents/{incident_id}/evidence": Page[EvidenceItemRead],
        "/api/incidents/{incident_id}/tool-calls": Page[ToolCallRead],
        "/api/incidents/{incident_id}/hypotheses": Page[RCAHypothesisRead],
        "/api/incidents/{incident_id}/model-calls": Page[ModelCallRead],
        "/api/incidents/{incident_id}/embeddings": Page[IncidentEmbeddingRead],
        "/api/incidents/{incident_id}/remediation-plans": Page[RemediationPlanRead],
        "/api/incidents/{incident_id}/documentation-reports": Page[DocumentationReportRead],
        "/api/incidents/{incident_id}/github-artifacts": Page[GitHubArtifactRead],
        "/api/incidents/{incident_id}/slack-messages": Page[SlackMessageRead],
        "/api/incidents/{incident_id}/audit": Page[IncidentEventRead],
    }
    get_routes = {
        route.path: route for route in app.routes if "GET" in getattr(route, "methods", set())
    }

    for path, response_model in expected_response_models.items():
        assert get_routes[path].response_model == response_model


def test_workflow_state_and_audit_export_routes_use_response_models() -> None:
    app = create_app()
    get_routes = {
        route.path: route for route in app.routes if "GET" in getattr(route, "methods", set())
    }

    assert (
        get_routes["/api/incidents/{incident_id}/workflow/state"].response_model
        == IncidentWorkflowStateRead
    )
    assert (
        get_routes["/api/incidents/{incident_id}/audit/export"].response_model
        == IncidentAuditExportRead
    )


def test_operator_command_routes_use_response_models() -> None:
    app = create_app()
    post_routes = {
        route.path: route for route in app.routes if "POST" in getattr(route, "methods", set())
    }

    assert post_routes["/api/services/refresh"].response_model == OperatorCommandRead
    assert (
        post_routes["/api/incidents/{incident_id}/documentation-reports/{report_id}/republish"]
        .response_model
        == OperatorCommandRead
    )


def test_policy_route_uses_effective_policy_response_model() -> None:
    app = create_app()
    get_routes = {
        route.path: route for route in app.routes if "GET" in getattr(route, "methods", set())
    }

    assert get_routes["/api/policy"].response_model == EffectivePolicyRead


def test_core_list_routes_use_paginated_response_models() -> None:
    app = create_app()
    expected_response_models = {
        "/api/incidents": Page[IncidentRead],
        "/api/services": Page[ServiceRead],
        "/api/repositories": Page[RepositoryRead],
        "/api/workloads": Page[RuntimeWorkloadRead],
        "/api/search/incidents": Page[SearchResult],
    }
    get_routes = {
        route.path: route for route in app.routes if "GET" in getattr(route, "methods", set())
    }

    for path, response_model in expected_response_models.items():
        assert get_routes[path].response_model == response_model


def test_route_role_dependency_wiring() -> None:
    app = create_app()

    assert _route_param_annotation(app, "POST", "/api/services") == AdminPrincipal
    assert _route_param_annotation(app, "GET", "/api/services") == ReadPrincipal
    assert _route_param_annotation(app, "GET", "/api/policy") == AdminPrincipal
    assert _route_param_annotation(app, "POST", "/api/incidents") == SREPrincipal
    assert (
        _route_param_annotation(app, "POST", "/api/incidents/{incident_id}/workflow/signals")
        == SREPrincipal
    )
    assert (
        _route_param_annotation(app, "POST", "/api/approvals/{approval_id}/decision")
        == ApproverPrincipal
    )
    assert _route_param_annotation(app, "GET", "/api/search/incidents") == ReadPrincipal


def test_workflow_state_and_audit_export_schema_shape() -> None:
    now = datetime.now(UTC)
    incident = IncidentRead(
        id="inc-123",
        created_at=now,
        updated_at=now,
        title="Checkout latency spike",
        severity="critical",
        status="validated",
        environment="prod",
        started_at=now,
        metadata={"source": "test"},
    )
    event = IncidentEventRead(
        id="evt-123",
        created_at=now,
        updated_at=now,
        incident_id="inc-123",
        event_type="workflow.step.completed",
        producer="temporal-workflow",
        payload={"step": "rca_hypotheses_generated"},
    )

    workflow_state = IncidentWorkflowStateRead(
        incident_id="inc-123",
        incident_status="validated",
        workflow_id="airp-incident-inc-123",
        workflow_run_id="run-123",
        has_workflow=True,
        latest_workflow_event=event,
    )
    audit_export = IncidentAuditExportRead(incident=incident, events=[event], exported_at=now)

    assert workflow_state.latest_workflow_event.event_type == "workflow.step.completed"
    assert audit_export.format_version == "airp.incident_audit.v1"
    assert audit_export.events[0].producer == "temporal-workflow"


def test_operator_command_request_schema_shape() -> None:
    refresh = DiscoveryRefreshRequest(
        scope="workloads",
        reason="verify AKS inventory",
        filters={"namespace": "shopfast"},
    )
    republish = DocumentationRepublishRequest(
        reason="publish corrected RCA",
        target="wiki",
        metadata={"requested_by": "test"},
    )
    command = OperatorCommandRead(
        operation_id="cmd-123",
        operation="documentation.republish",
        status="disabled_by_policy",
        message="Documentation publishing is disabled by policy.",
        requested_at=datetime.now(UTC),
        payload={"report_id": "report-123"},
    )

    assert refresh.scope == "workloads"
    assert republish.target == "wiki"
    assert command.external_execution_enabled is False


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


def test_incident_embedding_schema_accepts_json_backed_vectors() -> None:
    embedding = IncidentEmbeddingCreate(
        embedding_type="langgraph.graph_text",
        text="Checkout latency spike",
        vector=[0.1, 0.2, 0.3],
    )

    payload = embedding.model_dump(mode="json")

    assert payload["embedding_type"] == "langgraph.graph_text"
    assert payload["vector"] == [0.1, 0.2, 0.3]


async def _call_asgi_get(path: str, *, headers: dict[str, str]) -> dict[str, str]:
    status_code, response_headers, _ = await _call_asgi_request(
        create_app(),
        method="GET",
        path=path,
        headers=headers,
    )
    assert status_code == 200
    return response_headers


async def _body_echo_app(scope, receive, send) -> None:
    body_size = 0
    more_body = True
    while more_body:
        message = await receive()
        body = message.get("body", b"")
        if isinstance(body, bytes):
            body_size += len(body)
        more_body = bool(message.get("more_body", False))

    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [(b"content-type", b"application/json")],
        }
    )
    await send(
        {
            "type": "http.response.body",
            "body": f'{{"received": {body_size}}}'.encode(),
            "more_body": False,
        }
    )


async def _call_asgi_request(
    app,
    *,
    method: str,
    path: str,
    headers: dict[str, str],
    body: bytes = b"",
) -> tuple[int, dict[str, str], bytes]:
    response_headers: dict[str, str] = {}
    response_status = 0
    response_body = bytearray()
    request_sent = False
    request_headers = dict(headers)
    request_headers.setdefault("content-length", str(len(body)))
    raw_headers = [
        (name.lower().encode(), value.encode()) for name, value in request_headers.items()
    ]
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": raw_headers,
        "client": ("testclient", 0),
        "server": ("testserver", 80),
        "state": {},
    }

    async def receive() -> dict[str, object]:
        nonlocal request_sent
        if not request_sent:
            request_sent = True
            return {"type": "http.request", "body": body, "more_body": False}
        await asyncio.sleep(0)
        return {"type": "http.disconnect"}

    async def send(message: dict[str, object]) -> None:
        nonlocal response_status
        if message["type"] == "http.response.start":
            response_status = int(message["status"])
            for name, value in message["headers"]:
                response_headers[name.decode()] = value.decode()
        if message["type"] == "http.response.body":
            body_chunk = message.get("body", b"")
            if isinstance(body_chunk, bytes):
                response_body.extend(body_chunk)

    await asyncio.wait_for(app(scope, receive, send), timeout=5)
    return response_status, response_headers, bytes(response_body)


def _route_param_annotation(app, method: str, path: str):
    for route in app.routes:
        if route.path == path and method in getattr(route, "methods", set()):
            parameters = inspect.signature(route.endpoint).parameters
            parameter_name = "_" if "_" in parameters else "principal"
            return parameters[parameter_name].annotation
    raise AssertionError(f"{method} {path} was not registered")

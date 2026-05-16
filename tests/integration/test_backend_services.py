import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from airp.db.models import Base
from airp.domain.enums import IncidentStatus
from airp.main import create_app
from airp.schemas.catalog import ServiceCreate
from airp.schemas.incidents import (
    ApprovalCreate,
    ApprovalDecisionCreate,
    IncidentCreate,
    IncidentSignal,
)
from airp.services.approval_service import ApprovalService
from airp.services.catalog_service import CatalogService
from airp.services.incident_service import IncidentService


@pytest.fixture
async def session():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as db_session:
        yield db_session

    await engine.dispose()


def test_app_registers_expected_routes() -> None:
    app = create_app()
    paths = {route.path for route in app.routes}

    assert "/api/health" in paths
    assert "/api/incidents" in paths
    assert "/api/services" in paths
    assert "/api/repositories" in paths
    assert "/api/workloads" in paths
    assert "/api/search/incidents" in paths


@pytest.mark.asyncio
async def test_create_service_and_incident(session) -> None:
    catalog = CatalogService(session)
    incident_service = IncidentService(session)

    service = await catalog.create_service(
        ServiceCreate(
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
    )

    incident = await incident_service.create_incident(
        IncidentCreate(
            title="Checkout latency spike",
            description="p95 latency breached SLO",
            service_id=service.id,
            severity="critical",
            environment="prod",
            namespace="shopfast",
            pod_name="checkout-api-abc123",
            image_tag="v1.2.3",
            image_digest="sha256:abc",
        ),
        actor="sre@example.com",
    )

    events = await incident_service.get_events(incident.id)

    assert service.extra == {"tier": "critical"}
    assert incident.title == "Checkout latency spike"
    assert incident.status == "received"
    assert incident.image_digest == "sha256:abc"
    assert events[0].event_type == "incident.created"


@pytest.mark.asyncio
async def test_signal_and_approval_flow(session) -> None:
    incident_service = IncidentService(session)
    approval_service = ApprovalService(session)

    incident = await incident_service.create_incident(
        IncidentCreate(title="Inventory crash loop", severity="critical"),
        actor="sre@example.com",
    )
    updated = await incident_service.signal_incident(
        incident.id,
        IncidentSignal(status=IncidentStatus.WAITING_FOR_APPROVAL, reason="PR needs approval"),
        actor="sre@example.com",
    )

    approval = await approval_service.request_approval(
        incident.id,
        ApprovalCreate(
            requested_action="Create remediation PR",
            requested_by="remediation-agent",
            payload_hash="abc123def456",
        ),
    )
    decided = await approval_service.decide(
        approval.id,
        ApprovalDecisionCreate(decision="approved", approver="sre@example.com"),
    )

    assert updated.status == "waiting_for_approval"
    assert approval.payload_hash == "abc123def456"
    assert decided.decision == "approved"
    assert decided.approver == "sre@example.com"

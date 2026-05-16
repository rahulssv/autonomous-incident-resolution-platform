from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from airp.core.errors import NotFoundError
from airp.db.models.incident import Approval, Incident, IncidentEvent
from airp.schemas.incidents import ApprovalCreate, ApprovalDecisionCreate


class ApprovalService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def request_approval(self, incident_id: str, payload: ApprovalCreate) -> Approval:
        incident = await self.session.get(Incident, incident_id)
        if incident is None:
            raise NotFoundError("incident", incident_id)

        approval = Approval(
            incident_id=incident_id,
            requested_action=payload.requested_action,
            requested_by=payload.requested_by,
            payload_hash=payload.payload_hash,
            expires_at=payload.expires_at,
            extra=payload.metadata,
        )
        self.session.add(approval)
        self.session.add(
            IncidentEvent(
                incident_id=incident_id,
                event_type="approval.requested",
                producer="api",
                payload={
                    "requested_by": payload.requested_by,
                    "payload_hash": payload.payload_hash,
                },
            )
        )
        await self.session.commit()
        await self.session.refresh(approval)
        return approval

    async def decide(self, approval_id: str, payload: ApprovalDecisionCreate) -> Approval:
        approval = await self.session.get(Approval, approval_id)
        if approval is None:
            raise NotFoundError("approval", approval_id)
        approval.decision = payload.decision.value
        approval.approver = payload.approver
        approval.decided_at = datetime.now(UTC)
        approval.extra = {**(approval.extra or {}), **payload.metadata}
        self.session.add(
            IncidentEvent(
                incident_id=approval.incident_id,
                event_type=f"approval.{payload.decision.value}",
                producer="api",
                payload={
                    "approval_id": approval.id,
                    "approver": payload.approver,
                    "payload_hash": approval.payload_hash,
                },
            )
        )
        await self.session.commit()
        await self.session.refresh(approval)
        return approval

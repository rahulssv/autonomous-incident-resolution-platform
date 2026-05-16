from fastapi import APIRouter, status

from airp.api.deps import ApproverPrincipal, DbSession, SREPrincipal
from airp.schemas.incidents import ApprovalCreate, ApprovalDecisionCreate, ApprovalRead
from airp.services.approval_service import ApprovalService

router = APIRouter()


@router.post(
    "/incidents/{incident_id}/approvals",
    response_model=ApprovalRead,
    status_code=status.HTTP_201_CREATED,
)
async def request_approval(
    incident_id: str,
    payload: ApprovalCreate,
    session: DbSession,
    _: SREPrincipal,
) -> ApprovalRead:
    approval = await ApprovalService(session).request_approval(incident_id, payload)
    return ApprovalRead.model_validate(approval)


@router.post("/approvals/{approval_id}/decision", response_model=ApprovalRead)
async def decide_approval(
    approval_id: str,
    payload: ApprovalDecisionCreate,
    session: DbSession,
    _: ApproverPrincipal,
) -> ApprovalRead:
    approval = await ApprovalService(session).decide(approval_id, payload)
    return ApprovalRead.model_validate(approval)

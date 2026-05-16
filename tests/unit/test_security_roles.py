import pytest
from fastapi import HTTPException

from airp.core.security import (
    AIRP_ADMIN_ROLE,
    AIRP_APPROVER_ROLE,
    AIRP_READ_ROLES,
    AIRP_SRE_ROLE,
    AIRP_VIEWER_ROLE,
    Principal,
    require_roles,
)

pytestmark = pytest.mark.asyncio


def _principal(*roles: str) -> Principal:
    return Principal(subject="user-1", roles=list(roles), claims={"sub": "user-1"})


async def test_read_roles_include_all_airp_app_roles() -> None:
    dependency = require_roles(*AIRP_READ_ROLES)

    for role in (AIRP_ADMIN_ROLE, AIRP_SRE_ROLE, AIRP_VIEWER_ROLE, AIRP_APPROVER_ROLE):
        principal = _principal(role)
        assert await dependency(principal) == principal


async def test_require_roles_rejects_insufficient_role() -> None:
    dependency = require_roles(AIRP_ADMIN_ROLE)

    with pytest.raises(HTTPException) as exc:
        await dependency(_principal(AIRP_VIEWER_ROLE))

    assert exc.value.status_code == 403
    assert exc.value.detail == "Insufficient role"

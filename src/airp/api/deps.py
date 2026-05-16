from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from airp.core.security import (
    AIRP_ADMIN_ROLE,
    AIRP_APPROVER_ROLES,
    AIRP_READ_ROLES,
    AIRP_SRE_ROLES,
    Principal,
    get_current_principal,
    require_roles,
)
from airp.db.session import get_db_session

DbSession = Annotated[AsyncSession, Depends(get_db_session)]
CurrentPrincipal = Annotated[Principal, Depends(get_current_principal)]
ReadPrincipal = Annotated[Principal, Depends(require_roles(*AIRP_READ_ROLES))]
SREPrincipal = Annotated[Principal, Depends(require_roles(*AIRP_SRE_ROLES))]
AdminPrincipal = Annotated[Principal, Depends(require_roles(AIRP_ADMIN_ROLE))]
ApproverPrincipal = Annotated[Principal, Depends(require_roles(*AIRP_APPROVER_ROLES))]


async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async for session in get_db_session():
        yield session

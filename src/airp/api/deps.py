from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from airp.core.security import Principal, get_current_principal
from airp.db.session import get_db_session

DbSession = Annotated[AsyncSession, Depends(get_db_session)]
CurrentPrincipal = Annotated[Principal, Depends(get_current_principal)]


async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async for session in get_db_session():
        yield session

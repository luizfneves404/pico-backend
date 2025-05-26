from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.flows.models import Campaign


async def get_eligible_campaigns(
    db_session: AsyncSession, *, user_id: int
) -> list[Campaign]:
    result = await db_session.execute(select(Campaign))
    return list(result.scalars().all())

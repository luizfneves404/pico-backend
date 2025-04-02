from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.quiz.models import UserInfo


async def update_dynamic_score(db_session: AsyncSession, user_id: int, n_answers: int):
    stmt = (
        update(UserInfo)
        .where(UserInfo.user_id == user_id)
        .values(dynamic_score=UserInfo.dynamic_score + n_answers)
    )
    await db_session.execute(stmt)
    await db_session.commit()

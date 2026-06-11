from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.education.models import EducationInfo
from app.flows.models import QuestionArea
from app.users.models import User


async def list_areas(db_session: AsyncSession, *, user_id: int) -> list[QuestionArea]:
    """List all areas"""
    Educ = aliased(EducationInfo)

    stmt = (
        select(QuestionArea)
        .join(User, QuestionArea.country_id == User.country_id)
        .join(Educ, User.current_education)
        .where(
            User.id == user_id,
            QuestionArea.education_level_id == Educ.level_id,
            QuestionArea.course_id.is_not_distinct_from(Educ.course_id),
        )
    )
    result = await db_session.scalars(stmt)
    return list(result)

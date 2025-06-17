from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, selectinload

from app.education.models import EducationInfo
from app.flows.models import Exam
from app.users.models import User


async def list_exams(db_session: AsyncSession, *, user_id: int) -> list[Exam]:
    """List all exams for a user"""
    Educ = aliased(EducationInfo)

    stmt = (
        select(Exam)
        .join(User, Exam.country_id == User.country_id)
        .join(Educ, User.current_education)
        .where(
            User.id == user_id,
            Exam.education_level_id == Educ.level_id,
            Exam.course_id == Educ.course_id,
        )
        .options(selectinload(Exam.country))
    )
    result = await db_session.scalars(stmt)
    return list(result)

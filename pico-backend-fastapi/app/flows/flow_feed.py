import asyncio
import logging
from abc import ABC, abstractmethod
from collections.abc import Awaitable
from typing import Any

from sqlalchemy import and_, delete, func, not_, select
from sqlalchemy.engine import RowMapping
from sqlalchemy.sql import Select
from sqlalchemy.sql.elements import Label

from app.community.models import Community, CommunityUser
from app.database import get_db_session_for_worker
from app.education.models import EducationInfo
from app.flows.models import (
    Flow,
    FlowFeedScore,
    FlowFeedScoreGroupType,
    FlowFeedScoreGroupTypeEnum,
    FlowQuestion,
    FlowQuestionUser,
)
from app.users.models import User

type GroupScoreHandlerCoroutine = Awaitable[None]
type GroupKey = dict[str, Any]
type UserCountsDict = dict[tuple[Any, ...], int]

logger = logging.getLogger(__name__)


class GroupScoreCalculator(ABC):
    """Abstract base class for calculating flow scores by different user groupings."""

    @abstractmethod
    def get_group_columns(self) -> list[Label[Any]]:
        """
        Return the list of labeled SQLAlchemy columns defining the user grouping.
        The labels are crucial as they are used to access row attributes by name.
        Example: `[EducationInfo.level_id.label("level_id")]`
        """
        pass

    @abstractmethod
    def get_user_base_query(self) -> Select[Any]:
        """
        Return the base query that will be used to define the total population of users for each group.
        It will be grouped by the columns returned by `get_group_columns`.
        """
        pass

    @abstractmethod
    def get_answer_base_query(self) -> Select[Any]:
        """
        Return the base query that will be used to count answers for each group. It should join
        all necessary tables to make grouping columns available.
        It will be grouped by the columns returned by `get_group_columns`.
        """
        pass

    def create_group_key_for_storage(self, row: RowMapping) -> GroupKey:
        """
        Extract group values from a result row into a dictionary using the
        column labels defined in `get_group_columns`.
        """
        return {col.key: getattr(row, col.key) for col in self.get_group_columns()}

    def get_user_count_query(self) -> Select[Any]:
        """Build the complete query to count total users per group, excluding groups where all columns are NULL."""
        group_columns = self.get_group_columns()
        base_query = self.get_user_base_query()

        # Add a filter to exclude rows where all grouping columns are NULL
        if group_columns:
            all_null_condition = and_(*(c.is_(None) for c in group_columns))
            base_query = base_query.where(not_(all_null_condition))

        return base_query.add_columns(
            *group_columns, func.count(User.id).label("total_users")
        ).group_by(*group_columns)

    def get_answer_count_query(self) -> Select[Any]:
        """Build the complete query to count answers per flow and group, excluding groups where all columns are NULL."""
        group_columns = self.get_group_columns()
        base_query = self.get_answer_base_query()

        # Add a filter to exclude rows where all grouping columns are NULL
        if group_columns:
            all_null_condition = and_(*(c.is_(None) for c in group_columns))
            base_query = base_query.where(not_(all_null_condition))

        return base_query.add_columns(
            Flow.id.label("flow_id"),
            *group_columns,
            func.count(FlowQuestionUser.id).label("answer_count"),
        ).group_by(Flow.id, *group_columns)

    async def calculate_scores(self, ctx: dict[str, Any], group_type_id: int) -> None:
        """Calculate and save flow scores for this group type."""
        group_col_keys = [col.key for col in self.get_group_columns()]

        async with get_db_session_for_worker(ctx) as db_session:
            # 0. Clear old scores for this group type to avoid stale data
            await db_session.execute(
                delete(FlowFeedScore).where(
                    FlowFeedScore.group_type_id == group_type_id
                )
            )

            # 1. Get total user counts for each group
            user_counts_result = await db_session.execute(self.get_user_count_query())
            user_counts: UserCountsDict = {
                tuple(getattr(row, key) for key in group_col_keys): row.total_users
                for row in user_counts_result.mappings()
            }

            # 2. Get answer counts for each flow and group
            answer_results = await db_session.execute(self.get_answer_count_query())

            # 3. Calculate scores and prepare records for insertion
            score_records: list[FlowFeedScore] = []
            for row in answer_results.mappings():
                lookup_key = tuple(getattr(row, key) for key in group_col_keys)
                logger.debug(f"lookup_key: {lookup_key}")
                total_users = user_counts.get(
                    lookup_key, 1
                )  # Default to 1 to avoid division by zero
                score = row.answer_count / total_users

                score_records.append(
                    FlowFeedScore(
                        group_type_id=group_type_id,
                        group_key=self.create_group_key_for_storage(row),
                        flow_id=row.flow_id,
                        score=score,
                    )
                )

            # 4. Save records to the database
            if score_records:
                db_session.add_all(score_records)


class IntendedEducationGroupScoreCalculator(GroupScoreCalculator):
    """Calculate scores grouped by users' intended education."""

    def get_group_columns(self) -> list[Label[Any]]:
        return [
            EducationInfo.level_id.label("level_id"),
            EducationInfo.institution_id.label("institution_id"),
            EducationInfo.stage_id.label("stage_id"),
            EducationInfo.course_id.label("course_id"),
        ]

    def get_user_base_query(self) -> Select[Any]:
        return (
            select()
            .select_from(User)
            .join(EducationInfo, EducationInfo.id == User.intended_education_id)
            .where(User.intended_education_id.isnot(None))
        )

    def get_answer_base_query(self) -> Select[Any]:
        return (
            select()
            .select_from(Flow)
            .join(FlowQuestion, FlowQuestion.flow_id == Flow.id)
            .join(FlowQuestionUser, FlowQuestionUser.flow_element_id == FlowQuestion.id)
            .join(User, User.id == FlowQuestionUser.user_id)
            .join(EducationInfo, EducationInfo.id == User.intended_education_id)
            .where(User.intended_education_id.isnot(None))
        )


class EducationLevelGroupScoreCalculator(GroupScoreCalculator):
    """Calculate scores grouped by users' education level."""

    def get_group_columns(self) -> list[Label[Any]]:
        return [EducationInfo.level_id.label("level_id")]

    def get_user_base_query(self) -> Select[Any]:
        return (
            select()
            .select_from(User)
            .join(EducationInfo, EducationInfo.id == User.current_education_id)
            .where(User.current_education_id.isnot(None))
        )

    def get_answer_base_query(self) -> Select[Any]:
        return (
            select()
            .select_from(Flow)
            .join(FlowQuestion, FlowQuestion.flow_id == Flow.id)
            .join(FlowQuestionUser, FlowQuestionUser.flow_element_id == FlowQuestion.id)
            .join(User, User.id == FlowQuestionUser.user_id)
            .join(EducationInfo, EducationInfo.id == User.current_education_id)
            .where(User.current_education_id.isnot(None))
        )


class CommunityGroupScoreCalculator(GroupScoreCalculator):
    """Calculate scores grouped by users' community."""

    def get_group_columns(self) -> list[Label[Any]]:
        return [Community.id.label("community_id")]

    def get_user_base_query(self) -> Select[Any]:
        return (
            select()
            .select_from(User)
            .join(CommunityUser, CommunityUser.user_id == User.id)
            .where(CommunityUser.community_id.isnot(None))
        )

    def get_answer_base_query(self) -> Select[Any]:
        return (
            select()
            .select_from(Flow)
            .join(FlowQuestion, FlowQuestion.flow_id == Flow.id)
            .join(FlowQuestionUser, FlowQuestionUser.flow_element_id == FlowQuestion.id)
            .join(User, User.id == FlowQuestionUser.user_id)
            .join(CommunityUser, CommunityUser.user_id == User.id)
            .where(CommunityUser.community_id.isnot(None))
        )


class IntendedCourseGroupScoreCalculator(GroupScoreCalculator):
    """Calculate scores grouped by users' intended course."""

    def get_group_columns(self) -> list[Label[Any]]:
        return [EducationInfo.course_id.label("course_id")]

    def get_user_base_query(self) -> Select[Any]:
        return (
            select()
            .select_from(User)
            .join(EducationInfo, EducationInfo.id == User.intended_education_id)
            .where(
                and_(
                    User.intended_education_id.isnot(None),
                    EducationInfo.course_id.isnot(None),
                )
            )
        )

    def get_answer_base_query(self) -> Select[Any]:
        return (
            select()
            .select_from(Flow)
            .join(FlowQuestion, FlowQuestion.flow_id == Flow.id)
            .join(FlowQuestionUser, FlowQuestionUser.flow_element_id == FlowQuestion.id)
            .join(User, User.id == FlowQuestionUser.user_id)
            .join(EducationInfo, EducationInfo.id == User.intended_education_id)
            .where(
                and_(
                    User.intended_education_id.isnot(None),
                    EducationInfo.course_id.isnot(None),
                )
            )
        )


class InstitutionGroupScoreCalculator(GroupScoreCalculator):
    """Calculate scores grouped by users' current institution."""

    def get_group_columns(self) -> list[Label[Any]]:
        return [EducationInfo.institution_id.label("institution_id")]

    def get_user_base_query(self) -> Select[Any]:
        return (
            select()
            .select_from(User)
            .join(EducationInfo, EducationInfo.id == User.current_education_id)
            .where(
                and_(
                    User.current_education_id.isnot(None),
                    EducationInfo.institution_id.isnot(None),
                )
            )
        )

    def get_answer_base_query(self) -> Select[Any]:
        return (
            select()
            .select_from(Flow)
            .join(FlowQuestion, FlowQuestion.flow_id == Flow.id)
            .join(FlowQuestionUser, FlowQuestionUser.flow_element_id == FlowQuestion.id)
            .join(User, User.id == FlowQuestionUser.user_id)
            .join(EducationInfo, EducationInfo.id == User.current_education_id)
            .where(
                and_(
                    User.current_education_id.isnot(None),
                    EducationInfo.institution_id.isnot(None),
                )
            )
        )


class StageGroupScoreCalculator(GroupScoreCalculator):
    """Calculate scores grouped by users' current education stage (for schoolers)."""

    def get_group_columns(self) -> list[Label[Any]]:
        return [EducationInfo.stage_id.label("stage_id")]

    def get_user_base_query(self) -> Select[Any]:
        return (
            select()
            .select_from(User)
            .join(EducationInfo, EducationInfo.id == User.current_education_id)
            .where(
                and_(
                    User.current_education_id.isnot(None),
                    EducationInfo.stage_id.isnot(None),
                )
            )
        )

    def get_answer_base_query(self) -> Select[Any]:
        return (
            select()
            .select_from(Flow)
            .join(FlowQuestion, FlowQuestion.flow_id == Flow.id)
            .join(FlowQuestionUser, FlowQuestionUser.flow_element_id == FlowQuestion.id)
            .join(User, User.id == FlowQuestionUser.user_id)
            .join(EducationInfo, EducationInfo.id == User.current_education_id)
            .where(
                and_(
                    User.current_education_id.isnot(None),
                    EducationInfo.stage_id.isnot(None),
                )
            )
        )


class CourseGroupScoreCalculator(GroupScoreCalculator):
    """Calculate scores grouped by users' current course (for university students)."""

    def get_group_columns(self) -> list[Label[Any]]:
        return [EducationInfo.course_id.label("course_id")]

    def get_user_base_query(self) -> Select[Any]:
        return (
            select()
            .select_from(User)
            .join(EducationInfo, EducationInfo.id == User.current_education_id)
            .where(
                and_(
                    User.current_education_id.isnot(None),
                    EducationInfo.course_id.isnot(None),
                )
            )
        )

    def get_answer_base_query(self) -> Select[Any]:
        return (
            select()
            .select_from(Flow)
            .join(FlowQuestion, FlowQuestion.flow_id == Flow.id)
            .join(FlowQuestionUser, FlowQuestionUser.flow_element_id == FlowQuestion.id)
            .join(User, User.id == FlowQuestionUser.user_id)
            .join(EducationInfo, EducationInfo.id == User.current_education_id)
            .where(
                and_(
                    User.current_education_id.isnot(None),
                    EducationInfo.course_id.isnot(None),
                )
            )
        )


CALCULATORS: dict[FlowFeedScoreGroupTypeEnum, GroupScoreCalculator] = {
    FlowFeedScoreGroupTypeEnum.COMMUNITY: CommunityGroupScoreCalculator(),
    FlowFeedScoreGroupTypeEnum.INTENDED_EDUCATION: IntendedEducationGroupScoreCalculator(),
    FlowFeedScoreGroupTypeEnum.INTENDED_COURSE: IntendedCourseGroupScoreCalculator(),
    FlowFeedScoreGroupTypeEnum.INSTITUTION: InstitutionGroupScoreCalculator(),
    FlowFeedScoreGroupTypeEnum.EDUCATION_LEVEL: EducationLevelGroupScoreCalculator(),
    FlowFeedScoreGroupTypeEnum.STAGE: StageGroupScoreCalculator(),
    FlowFeedScoreGroupTypeEnum.COURSE: CourseGroupScoreCalculator(),
}


async def task_score_flows_for_feed(ctx: dict[str, Any]) -> None:
    """Main ARQ task that runs all enabled group score calculators."""
    async with get_db_session_for_worker(ctx) as db_session:
        enabled_groups = (
            await db_session.execute(
                select(
                    FlowFeedScoreGroupType.id, FlowFeedScoreGroupType.group_type
                ).where(FlowFeedScoreGroupType.enabled.is_(True))
            )
        ).all()

    tasks: list[GroupScoreHandlerCoroutine] = []
    for group_type_id, group_type_enum in enabled_groups:
        if calculator := CALCULATORS.get(group_type_enum):
            tasks.append(calculator.calculate_scores(ctx, group_type_id))

    await asyncio.gather(*tasks)

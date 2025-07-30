import logging

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import SessionFactory
from app.education.models import EducationInfo
from app.flows.flow_feed import (
    IntendedEducationGroupScoreCalculator,
    task_score_flows_for_feed,
)
from app.flows.flow_service import feed
from app.flows.models import (
    FlowFeedScore,
    FlowFeedScoreGroupType,
    FlowFeedScoreGroupTypeEnum,
    FlowQuestionUser,
    FlowUserFeed,
)
from tests.factories import (
    ChoiceFactory,
    CourseFactory,
    EducationLevelFactory,
    FlowFactory,
    FlowQuestionFactory,
    InstitutionFactory,
    LevelStageFactory,
    User,
    UserFactory,
)

logger = logging.getLogger(__name__)


class TestFlowFeedScoring:
    """Test the flow feed scoring system internals without HTTP overhead."""

    async def test_intended_education_group_score_calculator(
        self,
        session: AsyncSession,
        session_factory: SessionFactory,
    ):
        """Test the IntendedEducationGroupScoreCalculator calculates scores correctly."""
        async with session.begin():
            # Create education components
            level = await EducationLevelFactory.create(session=session)
            institution = await InstitutionFactory.create(session=session)
            stage = await LevelStageFactory.create(level=level, session=session)
            course = await CourseFactory.create(session=session)

            # Create education info
            edu_info = EducationInfo(
                level_id=level.id,
                institution_id=institution.id,
                stage_id=stage.id,
                course_id=course.id,
            )
            session.add(edu_info)

            # Create users with same education
            users_same_edu: list[User] = []
            for _ in range(3):
                user = await UserFactory.create(
                    current_education=None, intended_education=edu_info, session=session
                )
                users_same_edu.append(user)

            # Create users with different education
            other_edu_info = EducationInfo(
                level_id=level.id,
                institution_id=institution.id,
                stage_id=stage.id,
                course_id=None,  # Different course
            )
            session.add(other_edu_info)

            other_user = await UserFactory.create(
                current_education=None,
                intended_education=other_edu_info,
                session=session,
            )

            # Create a flow with questions
            flow = await FlowFactory.create(
                session=session, created_by=users_same_edu[0]
            )
            flow_question = await FlowQuestionFactory.create(flow=flow, session=session)
            choice = await ChoiceFactory.create(
                question=flow_question.question, session=session
            )

            # Have 2 out of 3 users with same education answer the question
            for user in users_same_edu[:2]:
                answer = FlowQuestionUser(
                    flow_element_id=flow_question.id,
                    user_id=user.id,
                    choice_id=choice.id,
                )
                session.add(answer)

            # Have the other user also answer
            other_answer = FlowQuestionUser(
                flow_element_id=flow_question.id,
                user_id=other_user.id,
                choice_id=choice.id,
            )
            session.add(other_answer)

            # Create group type
            group_type = FlowFeedScoreGroupType(
                group_type=FlowFeedScoreGroupTypeEnum.INTENDED_EDUCATION,
                weight=1.0,
                enabled=True,
            )
            session.add(group_type)

        # Run the calculator
        calculator = IntendedEducationGroupScoreCalculator()
        ctx = {"session_factory": session_factory}
        await calculator.calculate_scores(ctx, group_type.id)

        # Check scores were calculated correctly
        async with session.begin():
            scores = await session.execute(
                select(FlowFeedScore).where(
                    FlowFeedScore.group_type_id == group_type.id
                )
            )
            score_records = list(scores.scalars())

            # Should have 2 score records (one for each education group that had answers)
            assert len(score_records) == 2

            # Find the score for the main education group
            main_group_score = next(
                (
                    s
                    for s in score_records
                    if s.group_key["institution_id"] == institution.id
                    and s.group_key["course_id"] == course.id
                ),
                None,
            )
            assert main_group_score is not None
            # 2 answers out of 3 users = 0.67
            assert main_group_score.score == pytest.approx(2 / 3, rel=0.01)

            # Find the score for the other education group
            other_group_score = next(
                (
                    s
                    for s in score_records
                    if s.group_key["institution_id"] == institution.id
                    and s.group_key["course_id"] is None
                ),
                None,
            )
            assert other_group_score is not None
            # 1 answer out of 1 user = 1.0
            assert other_group_score.score == 1.0

    async def test_feed_uses_flow_scores(self, session: AsyncSession):
        """Test that the feed function properly uses FlowFeedScore records."""
        async with session.begin():
            # Create education info
            level = await EducationLevelFactory.create(session=session)
            institution = await InstitutionFactory.create(session=session)
            stage = await LevelStageFactory.create(level=level, session=session)
            course = await CourseFactory.create(session=session)

            edu_info = EducationInfo(
                level_id=level.id,
                institution_id=institution.id,
                stage_id=stage.id,
                course_id=course.id,
            )
            session.add(edu_info)
            await session.flush()

            # Create a user with this education
            user = await UserFactory.create(
                current_education=None, intended_education=edu_info, session=session
            )

            # Create flows with different scores
            flows_db = await FlowFactory.create_batch(session=session, size=3)
            # each needs at least one question to appear on feed
            for flow in flows_db:
                fq = await FlowQuestionFactory.create(flow=flow, session=session)
                choice = await ChoiceFactory.create(
                    question=fq.question, session=session
                )
                answer = FlowQuestionUser(
                    flow_element_id=fq.id, user_id=user.id, choice_id=choice.id
                )
                session.add(answer)

            # Create group type
            group_type = FlowFeedScoreGroupType(
                group_type=FlowFeedScoreGroupTypeEnum.INTENDED_EDUCATION,
                weight=2.0,
                enabled=True,
            )
            session.add(group_type)
            await session.flush()

            # Create FlowFeedScore records
            scores = [
                FlowFeedScore(
                    group_type_id=group_type.id,
                    group_key={
                        "level_id": level.id,
                        "institution_id": institution.id,
                        "stage_id": stage.id,
                        "course_id": course.id,
                    },
                    flow_id=flows_db[0].id,
                    score=0.9,
                ),
                FlowFeedScore(
                    group_type_id=group_type.id,
                    group_key={
                        "level_id": level.id,
                        "institution_id": institution.id,
                        "stage_id": stage.id,
                        "course_id": course.id,
                    },
                    flow_id=flows_db[1].id,
                    score=0.5,
                ),
                FlowFeedScore(
                    group_type_id=group_type.id,
                    group_key={
                        "level_id": level.id,
                        "institution_id": institution.id,
                        "stage_id": stage.id,
                        "course_id": course.id,
                    },
                    flow_id=flows_db[2].id,
                    score=0.1,
                ),
            ]
            session.add_all(scores)

        async with session.begin():
            # Get feed
            flows = await feed(session, user_id=user.id, num_flows=3)

        # Should return flows in score order
        assert len(flows) == 3
        assert flows[0].id == flows_db[0].id
        assert flows[1].id == flows_db[1].id
        assert flows[2].id == flows_db[2].id

        # Check that flows were marked as seen
        async with session.begin():
            seen_records = await session.execute(
                select(FlowUserFeed).where(FlowUserFeed.user_id == user.id)
            )
            seen_flow_ids = {r.flow_id for r in seen_records.scalars()}
            assert seen_flow_ids == {
                flows_db[0].id,
                flows_db[1].id,
                flows_db[2].id,
            }

    async def test_feed_fallback_when_no_education(self, session: AsyncSession):
        """Test feed fallback behavior when user has no intended education."""
        async with session.begin():
            # Create user without intended education
            user = await UserFactory.create(intended_education=None, session=session)

            # Create flows with different answer counts
            popular_flow = await FlowFactory.create(session=session)
            medium_flow = await FlowFactory.create(session=session)
            unpopular_flow = await FlowFactory.create(session=session)

            # Create another user to answer questions
            answerer = await UserFactory.create(session=session)

            # Add questions and answers
            for _ in range(3):
                fq = await FlowQuestionFactory.create(
                    flow=popular_flow, session=session
                )
                choice = await ChoiceFactory.create(
                    question=fq.question, session=session
                )
                answer = FlowQuestionUser(
                    flow_element_id=fq.id, user_id=answerer.id, choice_id=choice.id
                )
                session.add(answer)

            for _ in range(1):
                fq = await FlowQuestionFactory.create(flow=medium_flow, session=session)
                choice = await ChoiceFactory.create(
                    question=fq.question, session=session
                )
                answer = FlowQuestionUser(
                    flow_element_id=fq.id, user_id=answerer.id, choice_id=choice.id
                )
                session.add(answer)

            # unpopular flow needs at least one question to appear on feed
            fq = await FlowQuestionFactory.create(flow=unpopular_flow, session=session)

        # Get feed
        async with session.begin():
            flows = await feed(session, user_id=user.id, num_flows=3)

        # Should use fallback ordering by answer count
        assert len(flows) == 3
        assert flows[0].id == popular_flow.id
        assert flows[1].id == medium_flow.id
        assert flows[2].id == unpopular_flow.id

    async def test_feed_excludes_seen_flows(self, session: AsyncSession):
        """Test that feed excludes flows already seen by the user."""
        async with session.begin():
            # Create user with education
            level = await EducationLevelFactory.create(session=session)
            edu_info = EducationInfo(level_id=level.id)
            session.add(edu_info)
            await session.flush()

            user = await UserFactory.create(
                intended_education=edu_info, session=session
            )

            # Create flows
            seen_flow = await FlowFactory.create(session=session)
            await FlowQuestionFactory.create(flow=seen_flow, session=session)
            unseen_flow1 = await FlowFactory.create(session=session)
            unseen_flow2 = await FlowFactory.create(session=session)
            await FlowQuestionFactory.create(flow=unseen_flow1, session=session)
            await FlowQuestionFactory.create(flow=unseen_flow2, session=session)

            # Mark one flow as seen

            seen_record = FlowUserFeed(user_id=user.id, flow_id=seen_flow.id)
            session.add(seen_record)

            # Create group type and scores for all flows
            group_type = FlowFeedScoreGroupType(
                group_type=FlowFeedScoreGroupTypeEnum.INTENDED_EDUCATION,
                weight=1.0,
                enabled=True,
            )
            session.add(group_type)
            await session.flush()

            scores = [
                FlowFeedScore(
                    group_type_id=group_type.id,
                    group_key={
                        "level_id": level.id,
                        "stage_id": None,
                        "course_id": None,
                        "institution_id": None,
                    },
                    flow_id=seen_flow.id,
                    score=1.0,  # Highest score but already seen
                ),
                FlowFeedScore(
                    group_type_id=group_type.id,
                    group_key={
                        "level_id": level.id,
                        "stage_id": None,
                        "course_id": None,
                        "institution_id": None,
                    },
                    flow_id=unseen_flow1.id,
                    score=0.5,
                ),
                FlowFeedScore(
                    group_type_id=group_type.id,
                    group_key={
                        "level_id": level.id,
                        "stage_id": None,
                        "course_id": None,
                        "institution_id": None,
                    },
                    flow_id=unseen_flow2.id,
                    score=0.3,
                ),
            ]
            session.add_all(scores)

        # Get feed
        async with session.begin():
            flows = await feed(session, user_id=user.id, num_flows=3)

        # Should only return unseen flows
        assert len(flows) == 2
        flow_ids = {f.id for f in flows}
        assert seen_flow.id not in flow_ids
        assert unseen_flow1.id in flow_ids
        assert unseen_flow2.id in flow_ids

    async def test_feed_weighted_scores(self, session: AsyncSession):
        """Test that feed properly applies group type weights to scores."""
        async with session.begin():
            # Create user with education
            level = await EducationLevelFactory.create(session=session)
            edu_info = EducationInfo(level_id=level.id)
            session.add(edu_info)
            await session.flush()

            user = await UserFactory.create(
                intended_education=edu_info, session=session
            )

            # Create flows
            flow1 = await FlowFactory.create(session=session)
            flow2 = await FlowFactory.create(session=session)
            await FlowQuestionFactory.create(flow=flow1, session=session)
            await FlowQuestionFactory.create(flow=flow2, session=session)

            # Create group type with weight 3.0
            group_type = FlowFeedScoreGroupType(
                group_type=FlowFeedScoreGroupTypeEnum.INTENDED_EDUCATION,
                weight=3.0,
                enabled=True,
            )
            session.add(group_type)
            await session.flush()

            # Create scores
            scores = [
                FlowFeedScore(
                    group_type_id=group_type.id,
                    group_key={
                        "level_id": level.id,
                        "stage_id": None,
                        "course_id": None,
                        "institution_id": None,
                    },
                    flow_id=flow1.id,
                    score=0.2,  # 0.2 * 3.0 = 0.6 weighted
                ),
                FlowFeedScore(
                    group_type_id=group_type.id,
                    group_key={
                        "level_id": level.id,
                        "stage_id": None,
                        "course_id": None,
                        "institution_id": None,
                    },
                    flow_id=flow2.id,
                    score=0.3,  # 0.3 * 3.0 = 0.9 weighted
                ),
            ]
            session.add_all(scores)

        # Get feed
        async with session.begin():
            flows = await feed(session, user_id=user.id, num_flows=2)

        # Flow2 should come first due to higher weighted score
        assert len(flows) == 2
        assert flows[0].id == flow2.id
        assert flows[1].id == flow1.id

    async def test_task_score_flows_for_feed(
        self,
        session: AsyncSession,
        session_factory: SessionFactory,
    ):
        """Test the ARQ task that runs all enabled calculators."""
        async with session.begin():
            # Create education components
            level = await EducationLevelFactory.create(session=session)
            institution = await InstitutionFactory.create(session=session)

            edu_info = EducationInfo(level_id=level.id, institution_id=institution.id)
            session.add(edu_info)
            await session.flush()

            # Create users and flows
            user1 = await UserFactory.create(
                intended_education=edu_info, session=session
            )
            _ = await UserFactory.create(intended_education=edu_info, session=session)

            flow = await FlowFactory.create(session=session)
            flow_question = await FlowQuestionFactory.create(flow=flow, session=session)
            choice = await ChoiceFactory.create(
                question=flow_question.question, session=session
            )

            # User1 answers
            answer = FlowQuestionUser(
                flow_element_id=flow_question.id,
                user_id=user1.id,
                choice_id=choice.id,
            )
            session.add(answer)

            # Create enabled group type
            group_type = FlowFeedScoreGroupType(
                group_type=FlowFeedScoreGroupTypeEnum.INTENDED_EDUCATION,
                weight=1.0,
                enabled=True,
            )
            session.add(group_type)

        # Run the task
        ctx = {"session_factory": session_factory}
        await task_score_flows_for_feed(ctx)

        # Check scores were created
        async with session.begin():
            scores = await session.execute(
                select(FlowFeedScore).where(FlowFeedScore.flow_id == flow.id)
            )
            score_records = list(scores.scalars())

            assert len(score_records) == 1
            score = score_records[0]
            assert score.group_key["level_id"] == level.id
            assert score.group_key["institution_id"] == institution.id
            # 1 answer out of 2 users = 0.5
            assert score.score == 0.5

    async def test_feed_partial_education_info(self, session: AsyncSession):
        """Test feed works when user has partial education info (some fields null)."""
        async with session.begin():
            # Create user with partial education info (no institution/stage/course)
            level = await EducationLevelFactory.create(session=session)
            edu_info = EducationInfo(
                level_id=level.id,
                institution_id=None,
                stage_id=None,
                course_id=None,
            )
            session.add(edu_info)
            await session.flush()

            user = await UserFactory.create(
                intended_education=edu_info, session=session
            )

            # Create flows
            flow1 = await FlowFactory.create(session=session)
            await FlowQuestionFactory.create(flow=flow1, session=session)
            flow2 = await FlowFactory.create(session=session)
            await FlowQuestionFactory.create(flow=flow2, session=session)

            # Create group type
            group_type = FlowFeedScoreGroupType(
                group_type=FlowFeedScoreGroupTypeEnum.INTENDED_EDUCATION,
                weight=1.0,
                enabled=True,
            )
            session.add(group_type)
            await session.flush()

            # Create scores with partial group key
            scores = [
                FlowFeedScore(
                    group_type_id=group_type.id,
                    group_key={
                        "level_id": level.id,
                        "stage_id": None,
                        "course_id": None,
                        "institution_id": None,
                    },
                    flow_id=flow1.id,
                    score=0.8,
                ),
                FlowFeedScore(
                    group_type_id=group_type.id,
                    group_key={
                        "level_id": level.id,
                        "stage_id": None,
                        "course_id": None,
                        "institution_id": None,
                    },
                    flow_id=flow2.id,
                    score=0.4,
                ),
            ]
            session.add_all(scores)

        # Get feed - should work with partial education info
        async with session.begin():
            flows = await feed(session, user_id=user.id, num_flows=2)

        assert len(flows) == 2
        assert flows[0].id == flow1.id
        assert flows[1].id == flow2.id

    async def test_score_calculator_clears_old_scores(
        self,
        session: AsyncSession,
        session_factory: SessionFactory,
    ):
        """Test that the score calculator clears old scores before calculating new ones."""
        async with session.begin():
            # Create education and group type
            level = await EducationLevelFactory.create(session=session)
            edu_info = EducationInfo(level_id=level.id)
            session.add(edu_info)
            await session.flush()

            group_type = FlowFeedScoreGroupType(
                group_type=FlowFeedScoreGroupTypeEnum.INTENDED_EDUCATION,
                weight=1.0,
                enabled=True,
            )
            session.add(group_type)
            await session.flush()

            # Create an old score that should be cleared
            old_flow = await FlowFactory.create(session=session)
            old_score = FlowFeedScore(
                group_type_id=group_type.id,
                group_key={
                    "level_id": level.id,
                    "stage_id": None,
                    "course_id": None,
                    "institution_id": None,
                },
                flow_id=old_flow.id,
                score=0.99,
            )
            session.add(old_score)

        # Verify old score exists
        async with session.begin():
            result = await session.execute(
                select(FlowFeedScore).where(
                    FlowFeedScore.flow_id == old_flow.id,
                    FlowFeedScore.group_type_id == group_type.id,
                )
            )
            assert result.scalar_one_or_none() is not None

        # Run calculator (with no new data, so no new scores should be created)
        calculator = IntendedEducationGroupScoreCalculator()
        ctx = {"session_factory": session_factory}
        await calculator.calculate_scores(ctx, group_type.id)

        # Verify old score was cleared
        async with session.begin():
            result = await session.execute(
                select(FlowFeedScore).where(
                    FlowFeedScore.flow_id == old_flow.id,
                    FlowFeedScore.group_type_id == group_type.id,
                )
            )
            assert result.scalar_one_or_none() is None

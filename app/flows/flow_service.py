import logging
import os
import random

from fastapi import UploadFile
from sqlalchemy import (
    desc,
    exists,
    func,
    or_,
    select,
    update,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.arq_client import enqueue_job
from app.community.models import CommunityUser
from app.files.models import create_files
from app.flows import question_service
from app.flows.constants import (
    SYSTEM_MESSAGE_CHECK_MATH_INVOLVEMENT,
)
from app.flows.models import (
    Choice,
    Flow,
    FlowDifficulty,
    FlowElement,
    FlowInputType,
    FlowQuestion,
    FlowQuestionUser,
    FlowSourceType,
    FlowUserFeed,
    OfficialQuestionSource,
    Question,
    QuestionAnswerType,
)
from app.flows.schemas import (
    AddQuestionsToFlowAI,
    AddQuestionsToFlowFull,
    AddQuestionsToFlowOfficial,
    QuestionDensity,
)
from app.notifications.service import (
    notify_communities_flow_posted,
    notify_user_flow_question_done,
)
from app.pagination import PaginationParams, paginate_query
from app.shared.openai_utils import get_completion
from app.users.models import User

NUM_ELEMENTS_TO_LOAD_IN_FEED = 5

REPEATED_CORRECT_ANSWER_XP_MULTIPLIER = 0.1
WRONG_ANSWER_XP_MULTIPLIER = 0.1
logger = logging.getLogger(__name__)

MAJOR_TAGS_WEIGHT = 2.0
MINOR_TAGS_WEIGHT = 1.0


class FlowNotFoundError(Exception):
    """Raised when a flow is not found"""

    pass


class FlowQuestionNotFoundError(Exception):
    """Raised when a flow element is not found"""

    pass


class InvalidAnswerError(Exception):
    """Raised when an invalid answer is submitted"""

    pass


class FlowValidationError(Exception):
    """Raised when flow validation fails"""

    pass


class InvalidFileTypeError(Exception):
    """Raised when an invalid file type is uploaded"""

    pass


async def feed(db_session: AsyncSession, *, user_id: int, num_flows: int) -> list[Flow]:
    """List all flows for a user that they haven't seen in their feed yet.
    Will use a complex algorithm in the future.
    For now, it's just a simple query to the database that excludes already seen flows.
    """

    # Get flows that the user hasn't seen in their feed yet
    seen_flow_ids_query = select(FlowUserFeed.flow_id).where(
        FlowUserFeed.user_id == user_id
    )

    query = (
        select(Flow)
        .join(FlowElement, Flow.id == FlowElement.flow_id)
        .outerjoin(FlowQuestionUser, FlowElement.id == FlowQuestionUser.flow_element_id)
        .where(Flow.id.not_in(seen_flow_ids_query))  # Exclude already seen flows
        .group_by(Flow.id)
        .order_by(func.count(FlowQuestionUser.id).desc(), Flow.created_at.desc())
        .options(*get_flow_loader(num_elements=NUM_ELEMENTS_TO_LOAD_IN_FEED))
        .limit(num_flows)
    )
    result = await db_session.execute(query)
    flows = list(result.scalars())

    # Mark these flows as seen by this user
    for flow in flows:
        flow_user_feed = FlowUserFeed(user_id=user_id, flow_id=flow.id)
        db_session.add(flow_user_feed)

    # Commit the seen records
    await db_session.flush()

    return flows


async def discover_flows(
    db_session: AsyncSession, *, user_id: int, num_flows: int
) -> list[Flow]:
    """Discover flows for the current user"""
    # for now the same algorithm as feed
    return await feed(db_session, user_id=user_id, num_flows=num_flows)


async def list_user_flows(db_session: AsyncSession, *, user_id: int) -> list[Flow]:
    """List all flows that a user has created"""
    query = (
        select(Flow)
        .where(Flow.created_by_id == user_id)
        .order_by(Flow.created_at.desc())
        .options(*get_flow_loader(num_elements=None))
    )
    result = await db_session.execute(query)
    return list(result.scalars())


async def get_flow(db_session: AsyncSession, *, flow_id: int) -> Flow:
    """Get a specific flow"""
    query = select(Flow).where(Flow.id == flow_id)
    result = await db_session.execute(query)
    flow = result.scalar_one_or_none()

    if not flow:
        raise FlowNotFoundError()

    # Load the elements relationship
    await db_session.refresh(flow, ["elements"])

    return flow


async def search_flows(
    db_session: AsyncSession,
    *,
    query: str,
    pagination: PaginationParams,
) -> list[Flow]:
    """
    Full-text search over title, major_tags and minor_tags arrays using PostgreSQL FTS.
    Title matches count highest, major matches count double, minor matches count normal.
    """
    # Turn the tag arrays into searchable text
    major_text = func.array_to_string(Flow.major_tags, " ")
    minor_text = func.array_to_string(Flow.minor_tags, " ")

    # Build tsvector expressions
    title_fts = func.to_tsvector("portuguese", Flow.title)
    major_fts = func.to_tsvector("portuguese", major_text)
    minor_fts = func.to_tsvector("portuguese", minor_text)

    # Build tsquery from the user input
    ts_query = func.plainto_tsquery("portuguese", query)

    # Boolean matches
    match_title = title_fts.op("@@")(ts_query)
    match_major = major_fts.op("@@")(ts_query)
    match_minor = minor_fts.op("@@")(ts_query)

    # If you want a finer-grained rank, you can use ts_rank:
    title_rank = func.ts_rank(title_fts, ts_query)
    major_rank = func.ts_rank(major_fts, ts_query)
    minor_rank = func.ts_rank(minor_fts, ts_query)
    relevance_score = title_rank * 3 + major_rank * 2 + minor_rank

    stmt = (
        select(Flow)
        .where(or_(match_title, match_major, match_minor))
        .order_by(
            desc(relevance_score),
            desc(Flow.id),
        )
        .options(*get_flow_loader(num_elements=None))
    )

    result = await db_session.execute(paginate_query(stmt, pagination))
    return list(result.scalars())


async def get_flow_detail(db_session: AsyncSession, *, flow_id: int) -> Flow:
    """Get a specific flow with details"""
    query = (
        select(Flow)
        .where(Flow.id == flow_id)
        .options(*get_flow_loader(num_elements=None))
    )
    result = await db_session.execute(query)
    flow = result.scalar_one_or_none()

    if not flow:
        raise FlowNotFoundError()

    return flow


# TODO: criar testes


async def create_flow_with_optional_files(
    db_session: AsyncSession,
    *,
    user: User,
    topic: str = "",
    files: list[UploadFile] = [],
) -> Flow:
    """Create a new flow from a topic with optional files - matches Django create_quiz_with_files logic"""
    # Validate inputs - at least one of topic or files must be provided
    if not topic and not files:
        raise FlowValidationError("Either topic or files must be provided")

    if files:
        for file in files:
            content_type = file.content_type

            # ── Debug: log basic metadata coming from the frontend ─────────────────
            try:
                # Using seek/tell instead of read to avoid consuming the stream.
                current_pos = file.file.tell()
                file.file.seek(0, os.SEEK_END)
                size_bytes = file.file.tell()
                file.file.seek(current_pos)
            except Exception as e:  # pragma: no cover – defensive logging only
                size_bytes = "unknown"
                logger.warning(
                    "Could not determine size of file '%s': %s", file.filename, e
                )

            logger.info(
                "Received file '%s' (content_type=%s, size=%s bytes)",
                file.filename,
                content_type,
                size_bytes,
            )

            if not content_type:
                raise InvalidFileTypeError("File has no content type")

            # Match Django's VALID_MIME_TYPES_FOR_TRANSCRIPTION
            if not (
                content_type.startswith("application/pdf")
                or content_type in ["image/jpeg", "image/png", "image/jpg"]
            ):
                raise InvalidFileTypeError(f"Unsupported file type: {content_type}")

    flow_input_type = FlowInputType.FILES if files else FlowInputType.TOPIC

    if files:
        # For now, we'll use a placeholder title since transcription titles aren't available yet
        title = "Gerando título..."  # Will be updated with generate_title_from_transcription_titles
        requires_math = (
            False  # Will be determined later when transcriptions are processed
        )
        logger.info(f"Creating flow with files for user {user.id}")
    else:
        title = topic
        requires_math = await check_if_topic_involves_math_calculations(title)
        logger.info(f"Creating flow with topic for user {user.id}")

    flow = Flow(
        title=title,
        difficulty=FlowDifficulty.ALL,  # Default difficulty
        question_answer_type=QuestionAnswerType.MULTIPLE_CHOICE,  # Default answer type
        flow_input_type=flow_input_type,
        input_topic=topic if topic and not files else "",
        created_by_id=user.id,
        source_type=FlowSourceType.OFFICIAL,  # Default source type for new flows
        has_quantitative_questions=requires_math,
        major_tags=[],
        minor_tags=[],
        is_ready=not files,  # Ready immediately if no files, otherwise set by transcription process
    )

    db_session.add(flow)
    await db_session.flush()

    await db_session.refresh(flow, ["elements", "created_by"])

    logger.info(f"Flow {flow.id} created for user {user.id}")
    if topic and requires_math:
        logger.info(f"Topic {topic} requires math for flow {flow.id}")

    # Start background tasks for question generation
    if files:
        # Persist files to storage first to prevent file closure issues and memory problems
        try:
            logger.info(f"Flow {flow.id}: persisting {len(files)} files to storage")
            file_db_objects = await create_files(db_session, files)
            await db_session.flush()
            file_db_objects_ids = [file.id for file in file_db_objects]
            logger.info(f"Flow {flow.id}: successfully persisted files to storage")
        except Exception as e:
            logger.error(f"Failed to persist files for flow {flow.id}: {e}")
            raise

        await enqueue_job(
            "task_generate_transcriptions",
            file_db_objects_ids,
            flow.id,
            user.id,
        )
    else:
        await enqueue_job(
            "task_generate_flow_cover_image",
            flow.id,
            flow.title,
        )

    return flow


async def community_feed(
    db_session: AsyncSession,
    *,
    community_id: int,
    pagination: PaginationParams,
) -> list[Flow]:
    """Get a list of flows from the community feed created by users in the community."""
    query = (
        select(Flow)
        .join(FlowElement, Flow.id == FlowElement.flow_id)
        .join(User, Flow.created_by_id == User.id)
        .join(CommunityUser, User.id == CommunityUser.user_id)
        .outerjoin(FlowQuestionUser, FlowElement.id == FlowQuestionUser.flow_element_id)
        .where(CommunityUser.community_id == community_id)
        .group_by(Flow.id)
        .order_by(Flow.created_at.desc())
        .options(*get_flow_loader(num_elements=NUM_ELEMENTS_TO_LOAD_IN_FEED))
        .limit(pagination.size)
        .offset((pagination.page - 1) * pagination.size)
    )
    result = await db_session.scalars(query)
    flows = list(result)

    return flows


async def submit_answer_multiple_choice(
    db_session: AsyncSession,
    *,
    user_id: int,
    flow_id: int,
    question_id: int,
    choice_id: int | None,
) -> int:
    """Submit an answer for a multiple choice question in a flow

    Args:
        user_id: ID of the user submitting the answer
        flow_id: ID of the flow containing the question
        question_id: ID of the underlying Question (not FlowQuestion)
        choice_id: ID of the selected choice, or None if no choice selected

    Returns:
        The created FlowQuestionUser entry

    Raises:
        FlowQuestionNotFoundError: If the question is not found in the flow
        InvalidAnswerError: If the choice is invalid for the question or if the user has already answered this question in this flow
    """

    # Find the FlowQuestion by flow_id and underlying question_id
    query = (
        select(FlowQuestion)
        .where(
            FlowQuestion.flow_id == flow_id,
            FlowQuestion.question_id == question_id,
            FlowQuestion.question.has(
                Question.answer_type == QuestionAnswerType.MULTIPLE_CHOICE
            ),
        )
        .options(
            selectinload(FlowQuestion.question).options(selectinload(Question.choices)),
            selectinload(FlowQuestion.flow),
            selectinload(FlowQuestion.multiple_choice_answers),
        )
    )

    result = await db_session.execute(query)
    flow_question = result.scalar_one_or_none()

    if not flow_question:
        raise FlowQuestionNotFoundError()

    if not any(choice.id == choice_id for choice in flow_question.question.choices):
        raise InvalidAnswerError("Invalid choice for this question")

    if any(
        flow_question_user.user_id == user_id
        for flow_question_user in flow_question.multiple_choice_answers
    ):
        raise InvalidAnswerError("You have already answered this question in this flow")

    # check if the user has already answered this question before adding the new answer
    has_answered_correctly_before_query = await db_session.execute(
        select(
            exists().where(
                FlowQuestionUser.user_id == user_id,
                FlowQuestionUser.flow_question.has(
                    FlowQuestion.question_id == flow_question.question_id
                ),
                FlowQuestionUser.choice.has(Choice.is_correct),
            )
        )
    )
    has_answered_correctly_before = has_answered_correctly_before_query.scalar_one()

    # Create flow_question_user entry
    flow_question_user = FlowQuestionUser(
        flow_element_id=flow_question.id,
        user_id=user_id,
        choice_id=choice_id,
    )
    db_session.add(flow_question_user)

    # Increase social score of the user who created the flow if it's not the same user who answered the question
    if flow_question.flow.created_by_id != user_id:
        await db_session.execute(
            update(User)
            .where(
                User.id == flow_question.flow.created_by_id,
            )
            .values(social_score=User.social_score + 1)
        )

    # calculate xp score
    base_xp = get_question_xp()

    if flow_question_user.choice_id == flow_question.question.correct_choice_id:
        if has_answered_correctly_before:
            xp_increase = round(base_xp * REPEATED_CORRECT_ANSWER_XP_MULTIPLIER)
        else:
            xp_increase = base_xp
    else:
        xp_increase = round(base_xp * WRONG_ANSWER_XP_MULTIPLIER)

    # Increase XP score of the user who answered the question
    result = await db_session.execute(
        update(User)
        .where(User.id == user_id)
        .values(xp_score=User.xp_score + xp_increase)
        .returning(User)
    )

    actor = result.scalar_one()

    await notify_user_flow_question_done(
        db_session, actor=actor, flow=flow_question.flow
    )

    return xp_increase


def get_question_xp() -> int:
    if random.random() < 0.02:
        return 50
    else:
        # Draw from N(30, 5) and clamp to [20, 40]
        xp = random.gauss(mu=30, sigma=5)
        return min(40, max(20, round(xp)))


async def delete_flow(
    db_session: AsyncSession,
    *,
    user_id: int,
    flow_id: int,
) -> None:
    """Delete a flow"""
    # Check if flow exists and belongs to user
    flow = await get_flow(db_session, flow_id=flow_id)

    if flow.created_by_id != user_id:
        raise FlowNotFoundError()

    await db_session.delete(flow)


async def add_questions_to_flow_official(
    db_session: AsyncSession,
    user_id: int,
    flow_id: int,
    add_questions_to_flow_official: AddQuestionsToFlowOfficial,
):
    """Add official questions to a flow"""
    flow = await db_session.execute(
        select(Flow).where(Flow.id == flow_id, Flow.created_by_id == user_id)
    )
    flow = flow.scalar_one_or_none()
    if not flow:
        raise FlowNotFoundError()
    flow.source_type = FlowSourceType.OFFICIAL

    # Map question density to number of questions
    flow_input_type = flow.flow_input_type
    n_questions_map = (
        {
            QuestionDensity.LOW: 2,
            QuestionDensity.MEDIUM: 4,
            QuestionDensity.HIGH: 6,
        }
        if flow_input_type == FlowInputType.FILES
        else {
            QuestionDensity.LOW: 10,
            QuestionDensity.MEDIUM: 20,
            QuestionDensity.HIGH: 30,
        }
    )

    mapped_n_questions = n_questions_map[
        add_questions_to_flow_official.question_density
    ]

    if flow_input_type == FlowInputType.TOPIC:
        questions = await question_service.get_topic_query_official_questions(
            db_session,
            flow=flow,
            n_questions=mapped_n_questions,
            question_area_name=add_questions_to_flow_official.question_area_name,
            exam_id=add_questions_to_flow_official.exam_id,
            exam_country_code=add_questions_to_flow_official.exam_country_code,
            exam_education_level_id=add_questions_to_flow_official.exam_education_level_id,
            source_year=add_questions_to_flow_official.source_year,
            question_type=QuestionAnswerType.MULTIPLE_CHOICE,  # Default question type
        )
    elif flow_input_type == FlowInputType.FILES:
        questions = await question_service.get_files_query_official_questions(
            db_session,
            flow=flow,
            n_questions=mapped_n_questions,
            question_area_name=add_questions_to_flow_official.question_area_name,
            exam_id=add_questions_to_flow_official.exam_id,
            exam_country_code=add_questions_to_flow_official.exam_country_code,
            exam_education_level_id=add_questions_to_flow_official.exam_education_level_id,
            source_year=add_questions_to_flow_official.source_year,
            question_type=QuestionAnswerType.MULTIPLE_CHOICE,  # Default question type
        )
    else:
        raise ValueError(f"Unsupported flow input type: {flow_input_type}")

    # Add questions to flow elements
    await question_service.add_questions_to_flow(
        db_session, flow_id, questions, start_order=0
    )

    # Ensure all changes are committed to database
    await db_session.flush()
    # Expunge all objects to force fresh load from database
    db_session.expunge_all()

    loader_options = get_flow_loader(num_elements=None)
    query = select(Flow).where(Flow.id == flow_id).options(*loader_options)
    result = await db_session.execute(query)
    flow = result.scalar_one()

    await notify_communities_flow_posted(db_session, actor=flow.created_by, flow=flow)

    return flow


async def add_questions_to_flow_ai(
    db_session: AsyncSession,
    user_id: int,
    flow_id: int,
    add_questions_to_flow_ai: AddQuestionsToFlowAI,
):
    """Add AI-generated questions to a flow"""
    flow = await db_session.execute(
        select(Flow).where(Flow.id == flow_id, Flow.created_by_id == user_id)
    )
    flow = flow.scalar_one_or_none()
    if not flow:
        raise FlowNotFoundError()

    flow.source_type = FlowSourceType.AI_GENERATED

    # Map question density to number of questions
    flow_input_type = flow.flow_input_type
    n_questions_map = (
        {
            QuestionDensity.LOW: 2,
            QuestionDensity.MEDIUM: 4,
            QuestionDensity.HIGH: 6,
        }
        if flow_input_type == FlowInputType.FILES
        else {
            QuestionDensity.LOW: 10,
            QuestionDensity.MEDIUM: 20,
            QuestionDensity.HIGH: 30,
        }
    )

    mapped_n_questions = n_questions_map[add_questions_to_flow_ai.question_density]

    if flow_input_type == FlowInputType.TOPIC:
        questions = await question_service.get_topic_user_generated_questions(
            db_session,
            flow=flow,
            n_questions=mapped_n_questions,
            prompt_type=add_questions_to_flow_ai.prompt_type,
            extra_instructions=add_questions_to_flow_ai.extra_instructions,
            requires_math=flow.has_quantitative_questions,
        )
    elif flow_input_type == FlowInputType.FILES:
        questions = await question_service.get_files_user_generated_questions(
            db_session,
            flow=flow,
            n_questions=mapped_n_questions,
            prompt_type=add_questions_to_flow_ai.prompt_type,
            extra_instructions=add_questions_to_flow_ai.extra_instructions,
            requires_math=flow.has_quantitative_questions,
        )
    else:
        raise ValueError(f"Unsupported flow input type: {flow_input_type}")

    # Add questions to flow elements
    await question_service.add_questions_to_flow(
        db_session, flow_id, questions, start_order=0
    )

    # Ensure all changes are committed to database
    await db_session.flush()
    # Expunge all objects to force fresh load from database
    db_session.expunge_all()

    loader_options = get_flow_loader(num_elements=None)
    query = select(Flow).where(Flow.id == flow_id).options(*loader_options)
    result = await db_session.execute(query)
    flow = result.scalar_one()

    await notify_communities_flow_posted(db_session, actor=flow.created_by, flow=flow)

    return flow


async def add_questions_to_flow_full(
    db_session: AsyncSession,
    user_id: int,
    flow_id: int,
    add_questions_to_flow_full: AddQuestionsToFlowFull,
):
    """Add AI and official questions to a flow"""
    flow = await db_session.execute(
        select(Flow).where(Flow.id == flow_id, Flow.created_by_id == user_id)
    )
    flow = flow.scalar_one_or_none()
    if not flow:
        raise FlowNotFoundError()

    flow.source_type = FlowSourceType.FULL

    # Map question density to number of questions
    flow_input_type = flow.flow_input_type
    n_questions_map = (
        {
            QuestionDensity.LOW: 2,
            QuestionDensity.MEDIUM: 4,
            QuestionDensity.HIGH: 6,
        }
        if flow_input_type == FlowInputType.FILES
        else {
            QuestionDensity.LOW: 10,
            QuestionDensity.MEDIUM: 20,
            QuestionDensity.HIGH: 30,
        }
    )

    mapped_n_questions = n_questions_map[add_questions_to_flow_full.question_density]

    # Split questions: first half AI-generated, second half official
    ai_questions = mapped_n_questions // 2
    official_questions = mapped_n_questions - ai_questions

    # * Há um potencial de melhora, possivelmente buscando as questões ao mesmo tempo mas esperando as de IA ficarem prontas para adicionar primeiro.
    if flow_input_type == FlowInputType.TOPIC:
        # Generate both AI and official questions based on topic
        # First generate AI questions
        if ai_questions > 0:
            ai_generated_questions = (
                await question_service.get_topic_user_generated_questions(
                    db_session,
                    flow=flow,
                    n_questions=ai_questions,
                    prompt_type=add_questions_to_flow_full.prompt_type,
                    extra_instructions=add_questions_to_flow_full.extra_instructions,
                    requires_math=flow.has_quantitative_questions,
                )
            )
            await question_service.add_questions_to_flow(
                db_session, flow_id, ai_generated_questions, start_order=0
            )
            # Flush to ensure AI questions are persisted before adding official questions
            await db_session.flush()

        # Then get official questions
        if official_questions > 0:
            # Calculate the next available order by getting max order from existing elements
            max_order_query = select(
                func.coalesce(func.max(FlowElement.order), -1)
            ).where(FlowElement.flow_id == flow_id)
            max_order_result = await db_session.execute(max_order_query)
            max_order = max_order_result.scalar_one()
            next_order = max_order + 1

            official_questions_list = await question_service.get_topic_query_official_questions(
                db_session,
                flow=flow,
                n_questions=official_questions,
                question_area_name=add_questions_to_flow_full.question_area_name,
                exam_id=add_questions_to_flow_full.exam_id,
                exam_country_code=add_questions_to_flow_full.exam_country_code,
                exam_education_level_id=add_questions_to_flow_full.exam_education_level_id,
                source_year=add_questions_to_flow_full.source_year,
                question_type=QuestionAnswerType.MULTIPLE_CHOICE,
            )
            await question_service.add_questions_to_flow(
                db_session, flow_id, official_questions_list, start_order=next_order
            )

    elif flow_input_type == FlowInputType.FILES:
        # Generate both AI and official questions based on files
        # First generate AI questions
        if ai_questions > 0:
            ai_generated_questions = (
                await question_service.get_files_user_generated_questions(
                    db_session,
                    flow=flow,
                    n_questions=ai_questions,
                    prompt_type=add_questions_to_flow_full.prompt_type,
                    extra_instructions=add_questions_to_flow_full.extra_instructions,
                    requires_math=flow.has_quantitative_questions,
                )
            )
            await question_service.add_questions_to_flow(
                db_session, flow_id, ai_generated_questions, start_order=0
            )
            # Flush to ensure AI questions are persisted before adding official questions
            await db_session.flush()

        # Then get official questions
        if official_questions > 0:
            # Calculate the next available order by getting max order from existing elements
            max_order_query = select(
                func.coalesce(func.max(FlowElement.order), -1)
            ).where(FlowElement.flow_id == flow_id)
            max_order_result = await db_session.execute(max_order_query)
            max_order = max_order_result.scalar_one()
            next_order = max_order + 1

            official_questions_list = await question_service.get_files_query_official_questions(
                db_session,
                flow=flow,
                n_questions=official_questions,
                question_area_name=add_questions_to_flow_full.question_area_name,
                exam_id=add_questions_to_flow_full.exam_id,
                exam_country_code=add_questions_to_flow_full.exam_country_code,
                exam_education_level_id=add_questions_to_flow_full.exam_education_level_id,
                source_year=add_questions_to_flow_full.source_year,
                question_type=QuestionAnswerType.MULTIPLE_CHOICE,
            )
            # Add official questions to flow elements
            await question_service.add_questions_to_flow(
                db_session, flow_id, official_questions_list, start_order=next_order
            )
    else:
        raise ValueError(f"Unsupported flow input type: {flow_input_type}")

    # Ensure all changes are committed to database
    await db_session.flush()
    # Expunge all objects to force fresh load from database
    db_session.expunge_all()

    loader_options = get_flow_loader(num_elements=None)
    query = select(Flow).where(Flow.id == flow_id).options(*loader_options)
    result = await db_session.execute(query)
    flow = result.scalar_one()
    flow.max_num_questions = (
        flow.max_num_questions * 2
    )  # * As funções chamadas fazem isso mas nesse caso estamos //2 o n_questions -> solução simples, mas pode melhorar

    await notify_communities_flow_posted(db_session, actor=flow.created_by, flow=flow)

    return flow


async def check_if_topic_involves_math_calculations(topic: str) -> bool:
    """Check if a topic involves mathematical calculations using AI."""
    if not topic.strip():
        return False

    try:
        result = await get_completion(
            model="gpt-4.1-nano",
            temperature=0.3,
            messages=[
                {"role": "system", "content": SYSTEM_MESSAGE_CHECK_MATH_INVOLVEMENT},
                {"role": "user", "content": topic},
            ],
            json_mode=False,
            timeout=15,
        )

        response = result.content.strip().upper()
        return response == "SIM"

    except Exception as e:
        logger.error(f"Error checking math involvement for topic '{topic}': {e}")
        return False  # Default to False if there's an error


def get_flow_loader(num_elements: int | None):
    """
    Returns loader options for SQLAlchemy queries to load Flow and related objects.

    Args:
        num_elements: If provided, limits the number of Flow.elements loaded by order. If None, loads all elements.

    Returns:
        A list of loader options for SQLAlchemy queries.
    """
    element_loader = (
        selectinload(
            Flow.elements.and_(FlowElement.order < num_elements).of_type(FlowQuestion)
        )
        if num_elements is not None
        else selectinload(Flow.elements.of_type(FlowQuestion))
    )
    return [
        selectinload(Flow.created_by),
        selectinload(Flow.cover_image),
        element_loader.options(
            selectinload(FlowQuestion.question).options(
                selectinload(Question.choices).selectinload(Choice.image),
                selectinload(Question.source_user),
                selectinload(Question.official_source).selectinload(
                    OfficialQuestionSource.exam
                ),
            ),
            selectinload(FlowQuestion.flow_question_users).options(
                selectinload(FlowQuestionUser.user),
                selectinload(FlowQuestionUser.choice),
            ),
        ),
    ]

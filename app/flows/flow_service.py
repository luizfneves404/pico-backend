import random

from fastapi import UploadFile
from sqlalchemy import exists, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.files.models import create_file
from app.flows.models import (
    Choice,
    Flow,
    FlowElement,
    FlowInputType,
    FlowQuestion,
    FlowQuestionUser,
    FlowUserFeed,
    OfficialQuestionSource,
    Question,
    QuestionAnswerType,
)
from app.pagination import PaginationParams
from app.users.models import User

NUM_ELEMENTS_TO_LOAD_IN_FEED = 5

REPEATED_CORRECT_ANSWER_XP_MULTIPLIER = 0.1
WRONG_ANSWER_XP_MULTIPLIER = 0.1


class FlowNotFoundError(Exception):
    """Raised when a flow is not found"""

    pass


class FlowQuestionNotFoundError(Exception):
    """Raised when a flow element is not found"""

    pass


class FlowValidationError(Exception):
    """Raised when flow validation fails"""

    pass


class InvalidAnswerError(Exception):
    """Raised when an invalid answer is submitted"""

    pass


class InvalidFileTypeError(Exception):
    """Raised when an invalid file type is uploaded"""

    pass


async def feed(db_session: AsyncSession, *, user_id: int, num_flows: int) -> list[Flow]:
    """List all flows for a user that they haven't seen in their feed yet.
    Will use a complex algorithm in the future.
    For now, it's just a simple query to the database that excludes already seen flows."""

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
    area: str,
    source_filter: str,
    pagination: PaginationParams,
) -> list[Flow]:
    """Search for flows based on a query"""
    db_query = (
        select(Flow)
        .where(Flow.title.ilike(f"%{query}%"))
        .order_by(relevance_score)
        .options(*get_flow_loader(num_elements=None))
        .limit(pagination.size)
        .offset((pagination.page - 1) * pagination.size)
    )
    result = await db_session.execute(db_query)
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


async def create_flow(
    db_session: AsyncSession,
    *,
    user: User,
    input_topic: str,
    input_files: list[UploadFile],
    flow_input_type: FlowInputType,
) -> Flow:
    """Create a new flow from a topic"""
    # Create flow
    flow = Flow(
        title=title,
        query=query,
        area=area,
        source_filter=source_filter,
        difficulty=difficulty,
        flow_input_type=flow_input_type,
        input_topic=input_topic,
        created_by_id=user.id,
    )

    db_session.add(flow)
    await db_session.flush()

    # Generate questions based on the topic
    # This would typically call an AI service or query a question bank
    await _generate_flow_questions(
        db_session, flow, 5
    )  # Generate 5 questions by default

    await db_session.commit()
    await db_session.refresh(flow, ["elements"])

    return flow


async def create_flow_with_files(
    db_session: AsyncSession,
    *,
    user: User,
    title: str,
    query: str,
    area: str,
    source_filter: str,
    difficulty: str,
    files: list[UploadFile],
) -> Flow:
    """Create a new flow from uploaded files"""
    # Validate inputs
    if not title:
        raise FlowValidationError("Title is required")

    if not query:
        raise FlowValidationError("Query is required")

    if not files:
        raise FlowValidationError("At least one file is required")

    # Check file types
    for file in files:
        content_type = file.content_type
        if not content_type:
            raise InvalidFileTypeError("File has no content type")
        if not content_type.startswith(
            "application/pdf"
        ) and not content_type.startswith("image/"):
            raise InvalidFileTypeError(f"Unsupported file type: {content_type}")

    # Create flow
    flow = Flow(
        title=title,
        query=query,
        area=area,
        source_filter=source_filter,
        difficulty=difficulty,
        flow_input_type=FlowInputType.FILES,
        created_by_id=user.id,
    )

    db_session.add(flow)
    await db_session.flush()

    # Save files and create flow_input_files
    for i, upload_file in enumerate(files):
        saved_file = await create_file(
            db_session=db_session,
            upload_file=upload_file,
        )

    # Generate questions based on the files
    await _generate_flow_questions(
        db_session, flow, 5
    )  # Generate 5 questions by default

    await db_session.commit()
    await db_session.refresh(flow, ["elements"])

    return flow


async def _generate_flow_questions(
    db_session: AsyncSession,
    *,
    flow: Flow,
    n_questions: int,
) -> None:
    """
    Generate questions for a flow.
    This would typically call an AI service or a question bank.
    For now, it's a placeholder that should be implemented.
    """
    # This is a placeholder for the actual implementation
    # In a real application, this would call a service to generate questions
    # based on the flow's input_topic or files
    pass


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
    await db_session.execute(
        update(User)
        .where(User.id == user_id)
        .values(xp_score=User.xp_score + xp_increase)
    )

    return xp_increase


def get_question_xp() -> int:
    if random.random() < 0.02:
        return 50
    else:
        # Draw from N(30, 5) and clamp to [20, 40]
        xp = random.gauss(mu=30, sigma=5)
        return min(40, max(20, round(xp)))


async def add_elements_to_flow(
    db_session: AsyncSession,
    *,
    user_id: int,
    flow_id: int,
    query: str,
    area: str,
    source_filter: str,
    difficulty: str,
    n_questions: int = 5,
) -> Flow:
    """Add more elements (questions) to an existing flow"""
    # Check if flow exists and belongs to user
    flow = await get_flow(db_session, flow_id=flow_id)

    if flow.created_by_id != user_id:
        raise FlowNotFoundError()

    # Generate additional questions
    await _generate_flow_questions(db_session, flow=flow, n_questions=n_questions)

    await db_session.refresh(flow, ["elements"])

    return flow


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


async def generate_pdf(
    db_session: AsyncSession,
    *,
    user_id: int,
    flow_id: int,
) -> str:
    """Generate a PDF for a flow and return the URL"""
    # Check if flow exists
    flow = await get_flow(db_session, flow_id=flow_id)

    # This would typically call a service to generate a PDF
    # For now, it's a placeholder that returns a fake URL
    return f"https://example.com/flows/{flow.id}/pdf"


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

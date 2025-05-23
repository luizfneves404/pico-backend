from typing import List

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.files.models import create_file
from app.flows.models import (
    Flow,
    FlowElement,
    FlowInputType,
    FlowQuestion,
    FlowQuestionUser,
)
from app.users.models import User


class FlowNotFoundError(Exception):
    """Raised when a flow is not found"""

    pass


class FlowElementNotFoundError(Exception):
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


async def feed(db_session: AsyncSession, user_id: int) -> List[Flow]:
    """List all flows for a user"""
    query = (
        select(Flow)
        .where(Flow.created_by_id == user_id)
        .order_by(Flow.created_at.desc())
    )
    result = await db_session.execute(query)
    return list(result.scalars().all())


async def list_user_flows(db_session: AsyncSession, user_id: int) -> List[Flow]:
    """List all flows for a specific user"""
    query = (
        select(Flow)
        .where(Flow.created_by_id == user_id)
        .order_by(Flow.created_at.desc())
    )
    result = await db_session.execute(query)
    return list(result.scalars().all())


async def get_flow(db_session: AsyncSession, user_id: int, flow_id: int) -> Flow:
    """Get a specific flow"""
    query = select(Flow).where(Flow.id == flow_id)
    result = await db_session.execute(query)
    flow = result.scalar_one_or_none()

    if not flow:
        raise FlowNotFoundError()

    # Load the elements relationship
    await db_session.refresh(flow, ["elements"])

    return flow


async def create_flow(
    db_session: AsyncSession,
    user: User,
    input_topic: str,
    input_files: list[UploadFile],
    flow_input_type: FlowInputType,
) -> Flow:
    """Create a new flow from a topic"""
    # Validate inputs
    if not input_topic and not input_files:
        raise FlowValidationError("Title is required")

    if not query:
        raise FlowValidationError("Query is required")

    if flow_input_type == FlowInputType.TOPIC and not input_topic:
        raise FlowValidationError("Input topic is required for topic-based flows")

    # Check and deduct credits
    credit_cost = 10  # Example cost - adjust as needed
    await check_and_deduct_credits(db_session, user.id, credit_cost, "Flow creation")

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
    user: User,
    title: str,
    query: str,
    area: str,
    source_filter: str,
    difficulty: str,
    files: List[UploadFile],
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

    # Check and deduct credits
    credit_cost = 15  # Example cost - adjust as needed
    await check_and_deduct_credits(
        db_session, user.id, credit_cost, "Flow creation with files"
    )

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
            file=upload_file,
            user_id=user.id,
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
    user_id: int,
    flow_id: int,
    question_id: int,
    choice_id: int | None,
) -> dict[str, str]:
    """Submit an answer for a question in a flow"""
    # Check if flow exists
    flow = await get_flow(db_session, user_id, flow_id)

    # Check if flow element exists
    query = select(FlowElement).where(
        FlowElement.id == question_id, FlowElement.flow_id == flow_id
    )
    result = await db_session.execute(query)
    flow_element = result.scalar_one_or_none()

    if not flow_element:
        raise FlowElementNotFoundError()

    # Check answer type and validate
    if isinstance(flow_element, FlowQuestion):
        if choice_id:
            # For multiple choice question
            # Verify that the choice belongs to the question
            question = flow_element.question
            await db_session.refresh(question, ["choices"])

            valid_choice = False
            for choice in question.choices:
                if choice.id == choice_id:
                    valid_choice = True
                    break

            if not valid_choice:
                raise InvalidAnswerError("Invalid choice for this question")

            # Create flow_question_user entry
            flow_question_user = FlowQuestionUser(
                flow_element_id=flow_element.id,
                user_id=user_id,
                choice_id=choice_id,
            )
            db_session.add(flow_question_user)

        elif submitted_text:
            # For open-ended question
            flow_question_user = FlowQuestionUser(
                flow_element_id=flow_element.id,
                user_id=user_id,
                submitted_text=submitted_text,
            )
            db_session.add(flow_question_user)

        else:
            raise InvalidAnswerError(
                "Either choice_id or submitted_text must be provided"
            )

    else:
        raise InvalidAnswerError("This flow element is not a question")

    await db_session.commit()

    # Return feedback or results
    return {
        "status": "success",
        "message": "Answer submitted successfully",
    }


async def add_elements_to_flow(
    db_session: AsyncSession,
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
    flow = await get_flow(db_session, user_id, flow_id)

    if flow.created_by_id != user_id:
        raise FlowNotFoundError()

    # Check and deduct credits
    credit_cost = 5  # Example cost - adjust as needed
    await check_and_deduct_credits(
        db_session, user_id, credit_cost, "Add elements to flow"
    )

    # Generate additional questions
    await _generate_flow_questions(db_session, flow, n_questions)

    await db_session.commit()
    await db_session.refresh(flow, ["elements"])

    return flow


async def delete_flow(
    db_session: AsyncSession,
    user_id: int,
    flow_id: int,
) -> None:
    """Delete a flow"""
    # Check if flow exists and belongs to user
    flow = await get_flow(db_session, user_id, flow_id)

    if flow.created_by_id != user_id:
        raise FlowNotFoundError()

    await db_session.delete(flow)
    await db_session.commit()


async def generate_pdf(
    db_session: AsyncSession,
    user_id: int,
    flow_id: int,
) -> str:
    """Generate a PDF for a flow and return the URL"""
    # Check if flow exists
    flow = await get_flow(db_session, user_id, flow_id)

    # This would typically call a service to generate a PDF
    # For now, it's a placeholder that returns a fake URL
    return f"https://example.com/flows/{flow.id}/pdf"

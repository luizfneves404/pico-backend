from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, status
from fastapi import File as FastAPIFile

import app.flows.flow_service as flow_service
from app.currency.currency_service import InsufficientFundsError
from app.deps import CurrentUserAnnotated, CurrentUserDep, DBSessionAnnotated
from app.flows.models import FlowInputType
from app.flows.schemas import (
    AddQuestionsToFlowAI,
    AddQuestionsToFlowOfficial,
    FlowDetail,
    FlowInFeed,
    FlowInSearch,
    SubmitAnswerMultipleChoice,
)
from app.pagination import (
    PaginatedResponse,
    PaginationParams,
    get_pagination_params,
    paginate,
)

router = APIRouter(prefix="/flows", tags=["flows"], dependencies=[CurrentUserDep])


@router.get("feed", response_model=PaginatedResponse[FlowInFeed])
async def feed(
    db_session: DBSessionAnnotated,
    current_user: CurrentUserAnnotated,
    pagination: Annotated[PaginationParams, Depends(get_pagination_params)],
) -> PaginatedResponse[FlowInFeed]:
    """Always needs to return different flows. needs to know always what i have returned before, never to return again to the same user
    maybe create realtionship between flow and user"""

    # start of algorithm
    flows = await flow_service.feed(db_session, user_id=current_user.id)
    flows_in_feed = [FlowInFeed.from_orm_model(flow) for flow in flows]
    # end of algorithm

    return paginate(flows_in_feed, pagination)


@router.get("discover", response_model=PaginatedResponse[FlowInFeed])
async def discover_flows(
    db_session: DBSessionAnnotated,
    current_user: CurrentUserAnnotated,
    pagination: Annotated[PaginationParams, Depends(get_pagination_params)],
) -> PaginatedResponse[FlowInFeed]:
    """Discover flows for the current user"""

    flows = await flow_service.discover_flows(db_session, user_id=current_user.id)
    flows_in_feed = [FlowInFeed.from_orm_model(flow) for flow in flows]
    return paginate(flows_in_feed, pagination)


async def search_flows(
    db_session: DBSessionAnnotated,
    current_user: CurrentUserAnnotated,
    query: str,
) -> list[FlowInSearch]:
    """Search flows for the current user"""

    return await flow_service.search_flows(
        db_session, user_id=current_user.id, query=query
    )


@router.get("/{id}", response_model=FlowDetail)
async def flow_detail(
    db_session: DBSessionAnnotated,
    current_user: CurrentUserAnnotated,
    id: int,
):
    """Get details for a specific flow"""

    try:
        return await flow_service.get_flow(db_session, current_user.id, id)
    except flow_service.FlowNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Flow not found"
        )


@router.post("", response_model=FlowDetail, status_code=status.HTTP_201_CREATED)
async def create_flow(
    db_session: DBSessionAnnotated,
    current_user: CurrentUserAnnotated,
    input_topic: Annotated[str, Form()],
    input_files: list[UploadFile] = FastAPIFile(...),
):
    """Create a new flow from a topic"""

    try:
        return await flow_service.create_flow(
            db_session,
            current_user,
            input_topic,
            input_files,
            FlowInputType.TOPIC if not input_files else FlowInputType.FILES,
        )
    except InsufficientFundsError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except flow_service.FlowValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/{id}/add-questions-official", response_model=FlowDetail)
async def add_questions_to_flow_official(
    db_session: DBSessionAnnotated,
    current_user: CurrentUserAnnotated,
    id: int,
    add_questions_to_flow_official: AddQuestionsToFlowOfficial,
):
    """Add questions to a flow"""

    try:
        return await flow_service.add_questions_to_flow_official(
            db_session, current_user.id, id, add_questions_to_flow_official
        )
    except flow_service.FlowNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Flow not found"
        )
    except InsufficientFundsError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/{id}/add-questions-ai", response_model=FlowDetail)
async def add_questions_to_flow_ai(
    db_session: DBSessionAnnotated,
    current_user: CurrentUserAnnotated,
    id: int,
    add_questions_to_flow_ai: AddQuestionsToFlowAI,
):
    """Add questions to a flow"""

    try:
        return await flow_service.add_questions_to_flow_ai(
            db_session, current_user.id, id, add_questions_to_flow_ai
        )
    except flow_service.FlowNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Flow not found"
        )
    except InsufficientFundsError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/{id}/submit", status_code=status.HTTP_200_OK)
async def submit_answer_multiple_choice(
    db_session: DBSessionAnnotated,
    current_user: CurrentUserAnnotated,
    id: int,
    answer: SubmitAnswerMultipleChoice,
):
    """Submit an answer for a question in the flow"""

    try:
        return await flow_service.submit_answer_multiple_choice(
            db_session,
            current_user.id,
            id,
            answer.question_id,
            answer.choice_id,
        )
    except flow_service.FlowNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Flow not found"
        )
    except flow_service.FlowElementNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Flow element not found"
        )
    except flow_service.InvalidAnswerError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_flow(
    db_session: DBSessionAnnotated,
    current_user: CurrentUserAnnotated,
    id: int,
):
    """Delete a flow"""

    try:
        await flow_service.delete_flow(db_session, current_user.id, id)
    except flow_service.FlowNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Flow not found"
        )
    return None


@router.get("/user/{user_id}", response_model=list[FlowInSearch])
async def user_flows(
    db_session: DBSessionAnnotated,
    current_user: CurrentUserAnnotated,
    user_id: int,
):
    """Get all flows for a specific user"""

    return await flow_service.list_user_flows(db_session, user_id)

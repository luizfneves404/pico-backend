import logging
import random
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, status
from fastapi import File as FastAPIFile

import app.flows.area_service as area_service
import app.flows.campaign_service as campaign_service
import app.flows.exam_service as exam_service
import app.flows.flow_service as flow_service
from app.deps import CurrentUserAnnotated, CurrentUserDep, DBSessionAnnotated
from app.flows.models import FlowInputType
from app.flows.schemas import (
    AddQuestionsToFlowAI,
    AddQuestionsToFlowOfficial,
    CampaignFeedItem,
    CampaignInFeed,
    ExamOut,
    FeedItem,
    FlowDetail,
    FlowFeedItem,
    FlowInFeed,
    FlowInSearch,
    QuestionAreaOut,
    SubmitAnswerMultipleChoiceRequest,
    SubmitAnswerMultipleChoiceResponse,
)
from app.pagination import (
    PaginatedResponse,
    PaginationParams,
    get_pagination_params,
    paginate,
)

flows_router = APIRouter(prefix="/flows", tags=["flows"], dependencies=[CurrentUserDep])
exam_router = APIRouter(prefix="/exams", tags=["exams"], dependencies=[CurrentUserDep])
areas_router = APIRouter(prefix="/areas", tags=["areas"], dependencies=[CurrentUserDep])
logger = logging.getLogger(__name__)


@flows_router.get("/feed")
async def feed(
    db_session: DBSessionAnnotated,
    current_user: CurrentUserAnnotated,
    pagination: Annotated[PaginationParams, Depends(get_pagination_params)],
) -> PaginatedResponse[FeedItem]:
    """Always needs to return different flows.
    Needs to know always what i have returned before, never to return again to the same user"""
    # add the campaigns to the feed
    campaign = await campaign_service.select_one_campaign(
        db_session, user_id=current_user.id
    )
    if campaign:
        campaign_item = CampaignFeedItem(
            item_type="campaign", item=CampaignInFeed.from_orm_model(campaign)
        )
    else:
        campaign_item = None

    flows = await flow_service.feed(
        db_session,
        user_id=current_user.id,
        num_flows=pagination.size - 1 if campaign else pagination.size,
    )

    feed_items: list[FeedItem] = [
        FlowFeedItem(item_type="flow", item=FlowInFeed.from_orm_model(flow))
        for flow in flows
    ]

    if campaign_item:
        insert_index = random.randint(0, len(feed_items))
        feed_items.insert(insert_index, campaign_item)

    return paginate(feed_items, pagination)


@flows_router.get(
    "/discover",
)
async def discover_flows(
    db_session: DBSessionAnnotated,
    current_user: CurrentUserAnnotated,
    pagination: Annotated[PaginationParams, Depends(get_pagination_params)],
) -> PaginatedResponse[FlowInFeed]:
    """Discover flows for the current user"""

    flows = await flow_service.discover_flows(
        db_session, user_id=current_user.id, num_flows=pagination.size
    )
    flows_in_feed = [FlowInFeed.from_orm_model(flow) for flow in flows]
    return paginate(flows_in_feed, pagination)


@flows_router.get("/search")
async def search_flows(
    db_session: DBSessionAnnotated,
    current_user: CurrentUserAnnotated,
    query: str,
    pagination: Annotated[PaginationParams, Depends(get_pagination_params)],
) -> PaginatedResponse[FlowInSearch]:
    """Search flows for the current user"""
    flows = await flow_service.search_flows(
        db_session,
        query=query,
        pagination=pagination,
    )
    flows_in_search = [
        FlowInSearch.from_orm_model_for_user(flow, user_id=current_user.id)
        for flow in flows
    ]
    return paginate(flows_in_search, pagination)


@flows_router.get("/{id}/details", response_model=FlowDetail)
async def flow_detail(
    db_session: DBSessionAnnotated,
    current_user: CurrentUserAnnotated,
    id: int,
):
    """Get details for a specific flow"""

    try:
        flow = await flow_service.get_flow_detail(db_session, flow_id=id)
        return FlowDetail.from_orm_model_for_user(flow, user_id=current_user.id)
    except flow_service.FlowNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Flow not found"
        )


@flows_router.post("", response_model=FlowDetail, status_code=status.HTTP_201_CREATED)
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
    except flow_service.FlowValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@flows_router.post("/{id}/add-questions-official", response_model=FlowDetail)
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


@flows_router.post("/{id}/add-questions-ai", response_model=FlowDetail)
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


@flows_router.post(
    "/{id}/submit",
    status_code=status.HTTP_200_OK,
    response_model=SubmitAnswerMultipleChoiceResponse,
)
async def submit_answer_multiple_choice(
    db_session: DBSessionAnnotated,
    current_user: CurrentUserAnnotated,
    id: int,
    answer: SubmitAnswerMultipleChoiceRequest,
) -> SubmitAnswerMultipleChoiceResponse:
    """Submit an answer for a question in the flow"""
    try:
        xp_increase = await flow_service.submit_answer_multiple_choice(
            db_session,
            user_id=current_user.id,
            flow_id=id,
            question_id=answer.question_id,
            choice_id=answer.choice_id,
        )
        return SubmitAnswerMultipleChoiceResponse(xp_increase=xp_increase)
    except flow_service.FlowQuestionNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Flow element not found"
        )
    except flow_service.InvalidAnswerError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@flows_router.delete("/{id}/delete", status_code=status.HTTP_204_NO_CONTENT)
async def delete_flow(
    db_session: DBSessionAnnotated,
    current_user: CurrentUserAnnotated,
    id: int,
):
    """Delete a flow"""

    try:
        await flow_service.delete_flow(db_session, user_id=current_user.id, flow_id=id)
    except flow_service.FlowNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Flow not found"
        )
    return None


@flows_router.get("/user/{user_id}", response_model=list[FlowInSearch])
async def user_flows(
    db_session: DBSessionAnnotated,
    user_id: int,
) -> list[FlowInSearch]:
    """Get all flows for a specific user"""

    flows = await flow_service.list_user_flows(db_session, user_id=user_id)
    return [
        FlowInSearch.from_orm_model_for_user(flow, user_id=user_id) for flow in flows
    ]


@exam_router.get("", response_model=list[ExamOut])
async def list_exams(
    db_session: DBSessionAnnotated,
    current_user: CurrentUserAnnotated,
) -> list[ExamOut]:
    """List exams for a specific user, using country and education level"""

    exams = await exam_service.list_exams(db_session, user_id=current_user.id)
    return [ExamOut.from_orm_model(exam) for exam in exams]


@areas_router.get("", response_model=list[QuestionAreaOut])
async def list_areas(
    db_session: DBSessionAnnotated,
    current_user: CurrentUserAnnotated,
) -> list[QuestionAreaOut]:
    """List areas for a specific user, using country and education level"""
    areas = await area_service.list_areas(db_session, user_id=current_user.id)
    return [QuestionAreaOut.from_orm_model(area) for area in areas]

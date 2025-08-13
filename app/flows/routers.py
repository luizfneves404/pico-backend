import logging
import random
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, status
from fastapi import File as FastAPIFile

import app.files.service as file_service
import app.flows.area_service as area_service
import app.flows.campaign_service as campaign_service
import app.flows.exam_service as exam_service
import app.flows.flow_service as flow_service
from app.deps import CurrentUserAnnotated, CurrentUserDep, DBSessionAnnotated
from app.flows import question_service
from app.flows.schemas import (
    AddQuestionsToFlowAI,
    AddQuestionsToFlowFull,
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
    Needs to know always what i have returned before, never to return again to the same user
    """
    # add the campaigns to the feed
    campaign = await campaign_service.select_one_campaign(
        db_session, user_id=current_user.id
    )
    if campaign:
        campaign_item = CampaignFeedItem(
            item_type="campaign", item=await CampaignInFeed.from_orm_model(campaign)
        )
    else:
        campaign_item = None

    flows = await flow_service.feed(
        db_session,
        user_id=current_user.id,
        num_flows=pagination.size - 1 if campaign else pagination.size,
    )
    image_id_to_file_url = await file_service.pks_to_urls(
        db_session,
        pks=[image_id for flow in flows for image_id in flow.question_image_ids],
    )
    feed_items: list[FeedItem] = [
        FlowFeedItem(
            item_type="flow",
            item=await FlowInFeed.from_orm_model_with_context(
                flow, user_id=current_user.id, image_id_to_file_url=image_id_to_file_url
            ),
        )
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
    image_id_to_file_url = await file_service.pks_to_urls(
        db_session,
        pks=[image_id for flow in flows for image_id in flow.question_image_ids],
    )
    flows_in_feed = [
        await FlowInFeed.from_orm_model_with_context(
            flow, user_id=current_user.id, image_id_to_file_url=image_id_to_file_url
        )
        for flow in flows
    ]
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
        await FlowInSearch.from_orm_model_for_user(flow, user_id=current_user.id)
        for flow in flows
    ]
    return paginate(flows_in_search, pagination)


@flows_router.get("/community-feed/{community_id}")
async def community_feed(
    db_session: DBSessionAnnotated,
    current_user: CurrentUserAnnotated,
    community_id: int,
    pagination: Annotated[PaginationParams, Depends(get_pagination_params)],
) -> PaginatedResponse[FlowInSearch]:
    """Get the community feed"""
    flows = await flow_service.community_feed(
        db_session,
        community_id=community_id,
        pagination=pagination,
    )
    flows_in_feed = [
        await FlowInSearch.from_orm_model_for_user(flow, user_id=current_user.id)
        for flow in flows
    ]
    return paginate(flows_in_feed, pagination)


@flows_router.get("/{id}/details", response_model=FlowDetail)
async def flow_detail(
    db_session: DBSessionAnnotated,
    current_user: CurrentUserAnnotated,
    id: int,
) -> FlowDetail:
    """Get details for a specific flow"""

    try:
        flow = await flow_service.get_flow_detail(db_session, flow_id=id)
        image_id_to_file_url = await file_service.pks_to_urls(
            db_session,
            pks=flow.question_image_ids,
        )
        return await FlowDetail.from_orm_model_with_context(
            flow, user_id=current_user.id, image_id_to_file_url=image_id_to_file_url
        )
    except flow_service.FlowNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Flow not found"
        )


@flows_router.post("", response_model=FlowDetail, status_code=status.HTTP_201_CREATED)
async def create_flow(
    db_session: DBSessionAnnotated,
    current_user: CurrentUserAnnotated,
    topic: Annotated[str, Form()] = "",
    input_files: list[UploadFile] = FastAPIFile(default=[]),
) -> FlowDetail:
    """Create a new flow from a topic with optional files"""

    try:
        flow = await flow_service.create_flow_with_optional_files(
            db_session,
            user=current_user,
            topic=topic,
            files=input_files if input_files else [],
        )
        image_id_to_file_url = await file_service.pks_to_urls(
            db_session,
            pks=flow.question_image_ids,
        )
        return await FlowDetail.from_orm_model_with_context(
            flow, user_id=current_user.id, image_id_to_file_url=image_id_to_file_url
        )
    except flow_service.FlowValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except flow_service.InvalidFileTypeError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@flows_router.get("/{id}/is-ready", response_model=bool)
async def is_flow_ready_for_question_creation(
    db_session: DBSessionAnnotated,
    current_user: CurrentUserAnnotated,
    id: int,
) -> bool:
    """Check if a flow is ready"""
    try:
        flow = await flow_service.get_flow(db_session, flow_id=id)
        return flow.is_ready
    except flow_service.FlowNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Flow not found"
        )


@flows_router.post(
    "/{id}/add-questions-official",
    response_model=FlowDetail,
    name="add_questions_to_flow_from_official",
)
async def add_questions_to_flow_official(
    db_session: DBSessionAnnotated,
    current_user: CurrentUserAnnotated,
    id: int,
    add_questions_to_flow_official: AddQuestionsToFlowOfficial,
) -> FlowDetail:
    """Add questions to a flow"""

    try:
        flow = await flow_service.add_questions_to_flow_official(
            db_session, current_user.id, id, add_questions_to_flow_official
        )
        image_id_to_file_url = await file_service.pks_to_urls(
            db_session,
            pks=flow.question_image_ids,
        )
        return await FlowDetail.from_orm_model_with_context(
            flow, user_id=current_user.id, image_id_to_file_url=image_id_to_file_url
        )
    except flow_service.FlowNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Flow not found"
        )
    except question_service.QuestionAreaNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Question area not found"
        )


@flows_router.post(
    "/{id}/add-questions-ai",
    response_model=FlowDetail,
    name="add_questions_to_flow_from_ai",
)
async def add_questions_to_flow_ai(
    db_session: DBSessionAnnotated,
    current_user: CurrentUserAnnotated,
    id: int,
    add_questions_to_flow_ai: AddQuestionsToFlowAI,
) -> FlowDetail:
    """Add questions to a flow"""

    try:
        flow = await flow_service.add_questions_to_flow_ai(
            db_session, current_user.id, id, add_questions_to_flow_ai
        )
        image_id_to_file_url = await file_service.pks_to_urls(
            db_session,
            pks=flow.question_image_ids,
        )
        return await FlowDetail.from_orm_model_with_context(
            flow, user_id=current_user.id, image_id_to_file_url=image_id_to_file_url
        )
    except flow_service.FlowNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Flow not found"
        )


@flows_router.post(
    "/{id}/add-questions-full",
    response_model=FlowDetail,
    name="add_questions_to_flow_full",
)
async def add_questions_to_flow_full(
    db_session: DBSessionAnnotated,
    current_user: CurrentUserAnnotated,
    id: int,
    add_questions_to_flow_full: AddQuestionsToFlowFull,
) -> FlowDetail:
    """Add AI and official questions to a flow"""

    try:
        flow = await flow_service.add_questions_to_flow_full(
            db_session, current_user.id, id, add_questions_to_flow_full
        )
        image_id_to_file_url = await file_service.pks_to_urls(
            db_session,
            pks=flow.question_image_ids,
        )
        return await FlowDetail.from_orm_model_with_context(
            flow, user_id=current_user.id, image_id_to_file_url=image_id_to_file_url
        )
    except flow_service.FlowNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Flow not found"
        )
    except question_service.QuestionAreaNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Question area not found"
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
) -> None:
    """Delete a flow"""

    try:
        await flow_service.delete_flow(db_session, user_id=current_user.id, flow_id=id)
    except flow_service.FlowNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Flow not found"
        )
    return None


@flows_router.get("/user/{user_id}", response_model=PaginatedResponse[FlowInSearch])
async def list_user_flows(
    db_session: DBSessionAnnotated,
    user_id: int,
    pagination: Annotated[PaginationParams, Depends(get_pagination_params)],
) -> PaginatedResponse[FlowInSearch]:
    """Get all flows for a specific user"""

    flows = await flow_service.list_user_flows(
        db_session, user_id=user_id, pagination=pagination
    )
    flows_in_search = [
        await FlowInSearch.from_orm_model_for_user(flow, user_id=user_id)
        for flow in flows
    ]
    return paginate(flows_in_search, pagination)


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

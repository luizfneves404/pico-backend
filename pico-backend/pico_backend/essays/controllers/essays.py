import essays.essay_service as essay_service
from currency.currency_service import InsufficientFundsError
from essays.schemas.essays import (
    EssayCorrectionIn,
    EssayOut,
    EssayTopicIn,
    EssayTopicOut,
)
from ninja import File, Form, Router, UploadedFile
from ninja.errors import HttpError

router = Router()


@router.get("", response=list[EssayTopicOut], url_name="essay_topic_list")
async def essay_topic_list(request):
    user = request.auth
    return await essay_service.list_essay_topics(user.id)


@router.post("", response={201: EssayTopicOut}, url_name="essay_topic_list")
async def essay_topic_start(request, essay_topic_in: EssayTopicIn):
    # if essay_topic_in.chatroom_id is None:
    #     try:
    #         chatroom = await chatroom_service.aget_official_chatroom(user)
    #     except chatroom_service.OfficialChatroomNotFound:
    #         raise HttpError(404, "No official chatroom found")
    #     except chatroom_service.MultipleOfficialChatroomsFound:
    #         raise HttpError(400, "Multiple official chatrooms found")
    # else:
    #     chatroom = await get_chatroom_or_http_error(essay_topic_in.chatroom_id)

    try:
        return await essay_service.start_essay_topic(essay_topic_in.name)
    except essay_service.EssayTopicNameRequiredError:
        raise HttpError(400, "Name cannot be empty")


@router.get("/{id}", response=EssayTopicOut, url_name="essay_topic_detail")
async def essay_topic_detail(request, id: int):
    user = request.auth
    try:
        return await essay_service.get_essay_topic(user.id, id)
    except essay_service.EssayTopicNotFoundError:
        raise HttpError(404, "Essay topic not found")


@router.post(
    "/{id}/submit", response={201: EssayOut}, url_name="essay_topic_submit_essay"
)
async def essay_topic_submit_essay(
    request, id: int, upload: File[UploadedFile], essay_type: Form[str] = "Enem"
):
    user = request.auth
    essay_topic_id = id
    try:
        return await essay_service.asubmit_essay(
            user, essay_topic_id, essay_type, upload
        )
    except essay_service.EssayTopicNotFoundError:
        raise HttpError(404, "Essay topic not found")
    except essay_service.InvalidContentTypeError as e:
        raise HttpError(400, f"File content type '{e.args[0]}' not supported")
    except essay_service.InvalidMIMETypeError as e:
        raise HttpError(400, f"File type '{e.args[0]}' not supported")
    except InsufficientFundsError as e:
        raise HttpError(400, str(e))


@router.post("/{id}/correct", response=EssayOut, url_name="essay_topic_correct_essay")
async def essay_topic_correct_essay(
    request, id: int, essay_correction_in: EssayCorrectionIn
):
    user = request.auth
    essay_topic_id = id

    try:
        return await essay_service.acorrect_essay(
            user.id,
            essay_topic_id,
            essay_correction_in.essay_type,
            essay_correction_in.user_corrected_text,
        )
    except essay_service.EssayTopicNotFoundError:
        raise HttpError(404, "Essay topic not found")

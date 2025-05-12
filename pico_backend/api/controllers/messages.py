import api.services.message_service as message_service
from api.schemas.chatrooms import ChatroomOut
from api.schemas.messages import ForwardMessageIn, MessageOut
from api.utils import validate_chatroom_membership_members_prefetched
from ninja import File, Form, Router, UploadedFile
from ninja.errors import HttpError

router = Router()


@router.get(
    "chatrooms/{chatroom_id}/messages",
    response=list[MessageOut],
    url_name="chatroom_message_list",
)
async def messages_list(request, chatroom_id: int):
    chatroom = await validate_chatroom_membership_members_prefetched(
        chatroom_id, request.auth
    )
    return await message_service.list_top_level_messages_for_chatroom(chatroom)


@router.post(
    "chatrooms/{chatroom_id}/messages",
    response={201: MessageOut},
    url_name="chatroom_message_list",
)
async def message_create(
    request,
    chatroom_id: int,
    upload: File[UploadedFile | None] = None,
    content: Form[str] = "",
):
    user = request.auth
    chatroom = await validate_chatroom_membership_members_prefetched(chatroom_id, user)

    if not upload and not content.strip():
        raise HttpError(400, "Message content or attachment is required")

    try:
        return await message_service.create_and_send_message(
            sender=user, chatroom=chatroom, content=content, attachment=upload
        )
    except message_service.InvalidContentTypeError as e:
        raise HttpError(400, f"File content type '{e.args[0]}' not supported")
    except message_service.InvalidMIMETypeError as e:
        raise HttpError(400, f"File type '{e.args[0]}' not supported")


@router.post(
    "messages/{message_id}/forward-to-users",
    response={200: list[ChatroomOut]},
    url_name="chatroom_message_forward_to_users",
)
async def message_forward_to_user(
    request, forward_message_in: ForwardMessageIn, message_id: int
):
    try:
        return await message_service.forward_message_to_users(
            request.auth, forward_message_in.to_usernames, message_id
        )
    except ValueError as e:
        raise HttpError(400, str(e))

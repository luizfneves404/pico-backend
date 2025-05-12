import api.services.chatroom_service as chatroom_service
from api.models import User
from api.schemas.chatrooms import (
    ChatroomIn,
    ChatroomNameIn,
    ChatroomOut,
    UserUsernameSchema,
)
from ninja import File, Router, UploadedFile
from ninja.errors import HttpError

chatrooms_router = Router()


@chatrooms_router.get("", response=list[ChatroomOut], url_name="chatroom_list")
async def chatroom_list(request):
    user = request.auth
    return await chatroom_service.list_chatrooms_for_user_with_members_is_admin(user)


@chatrooms_router.post("", response={201: ChatroomOut}, url_name="chatroom_list")
async def chatroom_create(request, data: ChatroomIn):
    user = request.auth
    chatroom = await chatroom_service.create_group_chatroom(
        user, data.name, list(data.members_ids)
    )
    return 201, chatroom


@chatrooms_router.get(
    "/{chatroom_id}",
    response=ChatroomOut,
    url_name="chatroom_detail",
)
async def chatroom_detail(request, chatroom_id: int):
    user = request.auth
    try:
        chatroom = await chatroom_service.aget_chatroom_for_user(user, chatroom_id)
    except ValueError:
        raise HttpError(404, "Chatroom not found for this user")
    return chatroom


@chatrooms_router.patch(
    "/{chatroom_id}",
    response=ChatroomOut,
    url_name="chatroom_detail",
)
async def chatroom_rename(request, chatroom_id: int, data: ChatroomNameIn):
    user = request.auth
    try:
        chatroom = await chatroom_service.rename_chatroom_by_id(
            chatroom_id, user, data.name
        )
    except chatroom_service.ChatroomForUserNotFound:
        raise HttpError(404, "Chatroom not found for this user")
    except chatroom_service.ChatroomPermissionDenied:
        raise HttpError(403, "Only admins can rename the chatroom")
    return chatroom


@chatrooms_router.patch("/{chatroom_id}/join", url_name="chatroom_join")
async def chatroom_join(request, chatroom_id: int):
    user = request.auth
    try:
        await chatroom_service.join_chatroom_by_id(chatroom_id, user)
    except chatroom_service.ChatroomForUserNotFound:
        raise HttpError(404, "Chatroom not found for this user")
    except chatroom_service.AlreadyMember:
        raise HttpError(400, "User is already a member of this chatroom")
    return 200, {"detail": "User joined the chatroom"}


@chatrooms_router.patch("/{chatroom_id}/leave", url_name="chatroom_leave")
async def chatroom_leave(request, chatroom_id: int):
    user = request.auth
    try:
        await chatroom_service.leave_chatroom_by_id(chatroom_id, user)
    except chatroom_service.ChatroomForUserNotFound:
        raise HttpError(404, "Chatroom not found for this user")
    return 200, {"detail": "User left the chatroom"}


@chatrooms_router.patch("/{chatroom_id}/add-member", url_name="chatroom_add_member")
async def chatroom_add_member(
    request, chatroom_id: int, user_username_schema: UserUsernameSchema
):
    added_by_user = request.auth
    added_user_username = user_username_schema.username
    try:
        await chatroom_service.add_member_by_chatroom_id_user_username(
            chatroom_id, added_by_user, added_user_username
        )
    except chatroom_service.ChatroomForUserNotFound:
        raise HttpError(404, "Chatroom not found for this user")
    except chatroom_service.ChatroomPermissionDenied:
        raise HttpError(403, "Only admins can add members")
    except chatroom_service.ToUserNotFound:
        raise HttpError(404, "User to be added not found")
    except chatroom_service.AlreadyMember:
        raise HttpError(400, "User is already a member of this chatroom")
    return 200, {"detail": "User added to the chatroom"}


@chatrooms_router.patch(
    "/{chatroom_id}/remove-member", url_name="chatroom_remove_member"
)
async def chatroom_remove_member(
    request, chatroom_id: int, user_username_schema: UserUsernameSchema
):
    remover_user = request.auth
    removed_user_username = user_username_schema.username
    try:
        await chatroom_service.remove_member_by_chatroom_id_user_username(
            chatroom_id, remover_user, removed_user_username
        )
    except chatroom_service.ChatroomForUserNotFound:
        raise HttpError(404, "Chatroom not found for this user")
    except chatroom_service.ChatroomPermissionDenied:
        raise HttpError(403, "Only admins can remove members")
    except chatroom_service.ToUserNotFound:
        raise HttpError(404, "User to be removed not found")
    except chatroom_service.NotMember:
        raise HttpError(400, "User is not a member of this chatroom")
    except chatroom_service.CannotRemoveCreator:
        raise HttpError(400, "Creator cannot be removed from the chatroom")
    return 200, {"detail": "User removed from the chatroom"}


@chatrooms_router.patch("/{chatroom_id}/make-admin", url_name="chatroom_make_admin")
async def chatroom_make_admin(
    request, chatroom_id: int, user_username_schema: UserUsernameSchema
):
    by_user = request.auth
    to_user_username = user_username_schema.username
    try:
        await chatroom_service.make_admin_by_chatroom_id_user_username(
            chatroom_id, by_user, to_user_username
        )
    except chatroom_service.ChatroomForUserNotFound:
        raise HttpError(404, "Chatroom not found for this user")
    except chatroom_service.ChatroomPermissionDenied:
        raise HttpError(403, "Only admins can make other members admins")
    except chatroom_service.ToUserNotFound:
        raise HttpError(404, "User to be made admin not found")
    except chatroom_service.NotMember:
        raise HttpError(400, "User is not a member of this chatroom")
    except chatroom_service.AlreadyAdmin:
        raise HttpError(400, "User is already an admin of this chatroom")
    return 200, {"detail": "User made admin in the chatroom"}


@chatrooms_router.patch("/{chatroom_id}/remove-admin", url_name="chatroom_remove_admin")
async def chatroom_remove_admin(
    request, chatroom_id: int, user_username_schema: UserUsernameSchema
):
    by_user = request.auth
    to_user_username = user_username_schema.username
    try:
        await chatroom_service.remove_admin_by_chatroom_id_user_username(
            chatroom_id, by_user, to_user_username
        )
    except chatroom_service.ChatroomForUserNotFound:
        raise HttpError(404, "Chatroom not found for this user")
    except chatroom_service.ChatroomPermissionDenied:
        raise HttpError(403, "Only admins can remove other admins")
    except chatroom_service.ToUserNotFound:
        raise HttpError(404, "User to be removed as admin not found")
    except chatroom_service.NotMember:
        raise HttpError(400, "User is not a member of this chatroom")
    except chatroom_service.NotAdmin:
        raise HttpError(400, "User is not an admin of this chatroom")
    except chatroom_service.CannotRemoveAdminCreator:
        raise HttpError(400, "Creator of the chatroom cannot have admin status removed")
    return 200, {"detail": "User removed as admin in the chatroom"}


@chatrooms_router.post(
    "/{chatroom_id}/simulado-uerj", url_name="chatroom_simulado_uerj"
)
async def chatroom_simulado_uerj(request, chatroom_id: int):
    user = request.auth
    try:
        await chatroom_service.send_simulado_uerj(chatroom_id, user)
    except chatroom_service.ChatroomForUserNotFound:
        raise HttpError(404, "Chatroom not found for this user")
    return 200, {"detail": "Simulado UERJ sent on the chatroom"}


chatrooms_with_icon_router = Router()


@chatrooms_with_icon_router.post(
    "", response={201: ChatroomOut}, url_name="chatroom_with_icon_create"
)
async def chatroom_with_icon_create(
    request, data: ChatroomIn, upload: File[UploadedFile | None] = None
):
    user = request.auth
    chatroom = await chatroom_service.create_group_chatroom(
        user, data.name, list(data.members_ids), upload
    )
    return 201, chatroom


dm_chatrooms_router = Router()


@dm_chatrooms_router.get(
    "{user_id}", response=ChatroomOut, url_name="dm_chatroom_get_or_create"
)
async def dm_chatroom_get_or_create(request, user_id: int):
    user = request.auth
    if user.id == user_id:
        raise HttpError(400, "Cannot create a DM chatroom with yourself")

    other_user = await User.objects.filter(id=user_id).afirst()
    if not other_user:
        raise HttpError(404, "User not found")

    return await chatroom_service.get_or_create_dm_chatroom(user, other_user)

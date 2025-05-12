import logging

import api.services.message_service as message_service
import notifications.utils as notifications_utils
import shared.file_utils as file_utils
from api.models import (
    Chatroom,
    DMChatroom,
    GroupChatroom,
    Membership,
    Message,
    OfficialChatroom,
    User,
)
from django.core.files.uploadedfile import UploadedFile as DjangoUploadedFile
from quiz.models import Session

ICON_FILE_VALID_MIME_TYPES = [
    "image/jpeg",
    "image/png",
]

logger = logging.getLogger(__name__)


class ChatroomForUserNotFound(Exception):
    pass


class ToUserNotFound(Exception):
    pass


class ChatroomPermissionDenied(Exception):
    pass


class AlreadyMember(Exception):
    pass


class NotMember(Exception):
    pass


class AlreadyAdmin(Exception):
    pass


class NotAdmin(Exception):
    pass


class CannotRemoveCreator(Exception):
    pass


class CannotRemoveAdminCreator(Exception):
    pass


class CannotLeaveOfficialChatroom(Exception):
    pass


class OfficialChatroomNotFound(Exception):
    pass


class MultipleOfficialChatroomsFound(Exception):
    pass


class OfficialChatroomAlreadyExists(Exception):
    pass


class InvalidContentTypeError(Exception):
    pass


class InvalidMIMETypeError(Exception):
    pass


def _validate_icon_upload(upload: DjangoUploadedFile, mime_type: str):
    logger.debug(f"Validating file upload for chatroom icon: {upload}...")

    if upload and upload.content_type not in ICON_FILE_VALID_MIME_TYPES:
        logger.debug(f"Invalid content type for chatroom icon: {upload.content_type}")
        raise InvalidContentTypeError(upload.content_type)

    if mime_type not in ICON_FILE_VALID_MIME_TYPES:
        logger.debug(f"Invalid MIME type for chatroom icon: {mime_type}")
        raise InvalidMIMETypeError(mime_type)

    logger.info("File upload is valid")


async def list_chatrooms_for_user_with_members_is_admin(user: User) -> list[Chatroom]:
    """
    Retrieves the chatrooms with the members annotated with is_admin.
    """
    return await Chatroom.objects.filter(members=user).with_members_is_admin()


async def aget_chatroom_for_user(user: User, chatroom_id: int) -> Chatroom:
    """
    Retrieves the chatroom for the given user.
    """
    chatrooms = await Chatroom.objects.filter(
        id=chatroom_id, members=user
    ).with_members_is_admin()
    try:
        chatroom = chatrooms[0]
    except IndexError:
        raise ValueError("Chatroom not found for this user")

    return chatroom


async def aget_official_chatroom(user: User) -> OfficialChatroom:
    try:
        official_chatroom = await OfficialChatroom.objects.aget_official(user)
    except Chatroom.DoesNotExist:
        raise OfficialChatroomNotFound
    return official_chatroom


async def asend_notifications_on_create_chatroom(chatroom: Chatroom, creator: User):
    """send notifications to all members of the chatroom on create.
    please pass chatroom with members prefetched"""
    members = [member async for member in chatroom.members.all()]

    await notifications_utils.prepare_add_member_notifications_on_create(
        members, chatroom.id, creator
    ).send_async()


async def create_official_chatroom(name: str, user: User, extra_users: list[User]):
    """
    Creates a chatroom, triggering notifications.
    """
    try:
        chatroom = await OfficialChatroom.objects.acreate_official(
            name, user, extra_users
        )
    except OfficialChatroom.OfficialChatroomAlreadyExists:
        raise OfficialChatroomAlreadyExists

    chatroom = (
        await OfficialChatroom.objects.filter(id=chatroom.id)
        .prefetch_related("members")
        .aget()
    )

    chatroom_with_members_is_admin = await chatroom.annotate_members_is_admin()

    logger.debug(
        f"Official Chatroom with name '{name}' created for user '{user.username}' and extra users {[extra_user.username for extra_user in extra_users]}"
    )

    return chatroom_with_members_is_admin


async def get_or_create_dm_chatroom(user: User, other_user: User) -> DMChatroom:
    return (await get_or_create_dm_chatrooms(user, [other_user]))[0]


async def get_or_create_dm_chatrooms(user: User, users: list[User]) -> list[DMChatroom]:
    """
    Creates DM chatrooms between a user and a list of users, triggering notifications.
    """
    dm_chatrooms_and_created = await DMChatroom.objects.aget_or_create_dms(user, users)

    dm_chatrooms, createds = zip(*dm_chatrooms_and_created)

    dm_chatrooms_with_members_is_admin = await DMChatroom.objects.filter(
        id__in=[dm_chatroom.id for dm_chatroom in dm_chatrooms]
    ).with_members_is_admin()

    system_user = await User.objects.aget_system_user()

    for dm_chatroom, created in zip(dm_chatrooms_with_members_is_admin, createds):
        if created:
            await asend_notifications_on_create_chatroom(dm_chatroom, system_user)

    logger.debug(
        f"DM Chatrooms retrieved or created between user '{user.username}' and users {[user.username for user in users]}"
    )

    return dm_chatrooms_with_members_is_admin


async def create_group_chatroom(
    creator: User,
    name: str,
    members_ids: list[int],
    icon: DjangoUploadedFile | None = None,
) -> GroupChatroom:
    """
    Creates a chatroom, triggering notifications.
    """
    if icon:
        _validate_icon_upload(icon, file_utils.get_mime_type(icon))
    chatroom = await GroupChatroom.objects.acreate(name=name, icon=icon)
    await chatroom.aadd_member(creator, admin=True)

    if members_ids:
        members = User.non_sentinel_objects.filter(id__in=members_ids).exclude(
            id=creator.id
        )
        await chatroom.aadd_members([member async for member in members])

    chatroom = (
        await GroupChatroom.objects.filter(id=chatroom.id)
        .prefetch_related("members")
        .aget()
    )

    await asend_notifications_on_create_chatroom(chatroom, creator)

    chatroom_with_members_is_admin = await chatroom.annotate_members_is_admin()

    logger.debug(
        f"Group Chatroom with name '{name}' created with creator '{creator.username}', members {members_ids} and icon '{icon}'"
    )

    return chatroom_with_members_is_admin


async def _rename_chatroom(
    chatroom: GroupChatroom, by_user: User, new_name: str
) -> GroupChatroom:
    """
    Renames the chatroom, triggering notifications and system message.
    """
    chatroom.name = new_name
    await chatroom.asave(update_fields=["name"])

    members_ids = [
        member async for member in chatroom.members.values_list("id", flat=True)
    ]

    await notifications_utils.prepare_chatroom_rename_notifications(
        members_ids,
        chatroom.id,
        by_user,
        new_name,
    ).send_async()

    await message_service.asend_message(
        sender="system",
        content=f"User {by_user.username} renamed the chatroom to '{new_name}'",
        chatroom=chatroom,
    )

    chatroom_with_members_is_admin = await chatroom.annotate_members_is_admin()

    logger.debug(
        f"Chatroom with id '{chatroom.id}' renamed by user '{by_user.username}' to '{new_name}'"
    )

    return chatroom_with_members_is_admin


async def rename_chatroom_by_id(
    chatroom_id: int, by_user: User, new_name: str
) -> GroupChatroom:
    chatroom = (
        await GroupChatroom.objects.filter(id=chatroom_id, members=by_user)
        .prefetch_related("members")
        .afirst()
    )

    if not chatroom:
        raise ChatroomForUserNotFound
    if not await chatroom.ahas_admin_perms(by_user):
        raise ChatroomPermissionDenied

    return await _rename_chatroom(chatroom, by_user, new_name)


async def _leave_chatroom(chatroom: GroupChatroom, user: User) -> None:
    """
    Removes a user from the chatroom, triggering notifications and system message.
    """

    members_ids = [
        member async for member in chatroom.members.values_list("id", flat=True)
    ]

    await notifications_utils.prepare_leave_notifications(
        members_ids,
        chatroom.id,
        user,
    ).send_async()  # sending notification before leaving so that the user will know

    await message_service.asend_message(
        sender="system",
        content=f"User {user.username} left the chatroom",
        chatroom=chatroom,
    )

    await chatroom.aremove_member(user)

    logger.debug(f"User '{user.username}' left chatroom with id '{chatroom.id}'")


async def leave_chatroom_by_id(chatroom_id: int, user: User) -> None:
    chatroom = (
        await GroupChatroom.objects.filter(id=chatroom_id, members=user)
        .prefetch_related("members")
        .afirst()
    )
    if not chatroom:
        raise ChatroomForUserNotFound

    await _leave_chatroom(chatroom, user)


# TODO: send notification to other members that this user joined. maybe system message
async def join_chatroom_by_id(chatroom_id: int, user: User) -> None:
    chatroom = await GroupChatroom.objects.filter(id=chatroom_id).afirst()
    if not chatroom:
        raise ChatroomForUserNotFound
    if await Membership.objects.filter(chatroom=chatroom, user=user).aexists():
        raise AlreadyMember

    await chatroom.aadd_member(user)

    logger.debug(f"User '{user.username}' joined chatroom with id '{chatroom.id}'")


async def _add_member(chatroom: GroupChatroom, by_user: User, to_user: User) -> None:
    """
    Adds a user to the chatroom, triggering notifications and system message.
    Assumes user should be added, so permissions are correct and user is not sentinel, for example.
    """
    await chatroom.aadd_member(to_user)

    chatroom = await GroupChatroom.objects.prefetch_related("members").aget(
        id=chatroom.id
    )

    members_ids = [
        member async for member in chatroom.members.values_list("id", flat=True)
    ]

    await notifications_utils.prepare_add_member_notifications(
        members_ids,
        chatroom.id,
        by_user,
        to_user,
    ).send_async()  # sending notification after adding so that the added user will know

    await message_service.asend_message(
        sender="system",
        content=f"User {by_user.username} added user {to_user.username}",
        chatroom=chatroom,
    )

    logger.debug(
        f"User '{by_user.username}' added user '{to_user.username}' to chatroom with id '{chatroom.id}'"
    )


async def add_member_by_chatroom_id_user_username(
    chatroom_id: int, by_user: User, to_user_username: str
) -> None:
    chatroom = (
        await GroupChatroom.objects.filter(id=chatroom_id, members=by_user)
        .prefetch_related("members")
        .afirst()
    )

    if not chatroom:
        raise ChatroomForUserNotFound
    if not await chatroom.ahas_admin_perms(by_user):
        raise ChatroomPermissionDenied

    added_user = await User.non_sentinel_objects.filter(
        username__iexact=to_user_username
    ).afirst()

    if not added_user:
        raise ToUserNotFound
    if await chatroom.ais_member(added_user):
        raise AlreadyMember

    await _add_member(chatroom, by_user, added_user)


async def _remove_member(chatroom: GroupChatroom, by_user: User, to_user: User) -> None:
    """
    Removes a user to the chatroom, triggering notifications and system message.
    """

    chatroom = await GroupChatroom.objects.prefetch_related("members").aget(
        id=chatroom.id
    )

    members_ids = [
        member async for member in chatroom.members.values_list("id", flat=True)
    ]

    await (
        notifications_utils.prepare_remove_member_notifications(
            members_ids,
            chatroom.id,
            by_user,
            to_user,
        ).send_async()
    )  # sending notification before removing so that the removed user will know

    await message_service.asend_message(
        sender="system",
        content=f"User {by_user.username} removed user {to_user.username}",
        chatroom=chatroom,
    )

    await chatroom.aremove_member(to_user)

    logger.debug(
        f"User '{by_user.username}' removed user '{to_user.username}' from chatroom with id '{chatroom.id}'"
    )


async def remove_member_by_chatroom_id_user_username(
    chatroom_id: int, by_user: User, to_user_username: str
) -> None:
    chatroom = (
        await GroupChatroom.objects.filter(id=chatroom_id, members=by_user)
        .prefetch_related("members")
        .afirst()
    )

    if not chatroom:
        raise ChatroomForUserNotFound
    if not await chatroom.ahas_admin_perms(by_user):
        raise ChatroomPermissionDenied

    removed_user = await User.non_sentinel_objects.filter(
        username__iexact=to_user_username
    ).afirst()

    if not removed_user:
        raise ToUserNotFound
    if not await chatroom.ais_member(removed_user):
        raise NotMember
    if await chatroom.ais_creator(removed_user):
        raise CannotRemoveCreator

    await _remove_member(chatroom, by_user, removed_user)


async def _make_admin(chatroom: GroupChatroom, by_user: User, to_user: User) -> None:
    """
    Makes a user admin of the chatroom, triggering notifications.
    """
    await chatroom.aset_admin(to_user, True)

    chatroom = await GroupChatroom.objects.prefetch_related("members").aget(
        id=chatroom.id
    )

    members_ids = [
        member async for member in chatroom.members.values_list("id", flat=True)
    ]

    await notifications_utils.prepare_make_admin_notifications(
        members_ids,
        chatroom.id,
        by_user,
        to_user,
    ).send_async()

    logger.debug(
        f"User '{by_user.username}' made user '{to_user.username}' admin of chatroom with id '{chatroom.id}'"
    )


async def make_admin_by_chatroom_id_user_username(
    chatroom_id: int, by_user: User, to_user_username: str
) -> None:
    chatroom = (
        await GroupChatroom.objects.filter(id=chatroom_id, members=by_user)
        .prefetch_related("members")
        .afirst()
    )

    if not chatroom:
        raise ChatroomForUserNotFound
    if not await chatroom.ahas_admin_perms(by_user):
        raise ChatroomPermissionDenied

    to_user = await User.non_sentinel_objects.filter(
        username__iexact=to_user_username
    ).afirst()

    if not to_user:
        raise ToUserNotFound
    if not await chatroom.ais_member(to_user):
        raise NotMember
    if await chatroom.ahas_admin_perms(to_user):
        raise AlreadyAdmin

    await _make_admin(chatroom, by_user, to_user)


async def _remove_admin(chatroom: GroupChatroom, by_user: User, to_user: User) -> None:
    """
    Removes a user from being an admin of the chatroom, triggering notifications.
    """
    await chatroom.aset_admin(to_user, False)

    chatroom = await GroupChatroom.objects.prefetch_related("members").aget(
        id=chatroom.id
    )

    members_ids = [
        member async for member in chatroom.members.values_list("id", flat=True)
    ]

    await notifications_utils.prepare_remove_admin_notifications(
        members_ids,
        chatroom.id,
        by_user,
        to_user,
    ).send_async()

    logger.debug(
        f"User '{by_user.username}' removed user '{to_user.username}' from being admin of chatroom with id '{chatroom.id}'"
    )


async def remove_admin_by_chatroom_id_user_username(
    chatroom_id: int, by_user: User, to_user_username: str
) -> None:
    chatroom = (
        await GroupChatroom.objects.filter(id=chatroom_id, members=by_user)
        .prefetch_related("members")
        .afirst()
    )

    if not chatroom:
        raise ChatroomForUserNotFound
    if not await chatroom.ahas_admin_perms(by_user):
        raise ChatroomPermissionDenied

    to_user = await User.non_sentinel_objects.filter(
        username__iexact=to_user_username
    ).afirst()

    if not to_user:
        raise ToUserNotFound
    if not await Membership.objects.filter(chatroom=chatroom, user=to_user).aexists():
        raise NotMember
    if not await chatroom.ahas_admin_perms(to_user):
        raise NotAdmin
    if await chatroom.ais_creator(to_user):
        raise CannotRemoveAdminCreator

    await _remove_admin(chatroom, by_user, to_user)


async def create_predefined_chatroom_with_messages(
    name: str,
    user: User,
    extra_users: list[User],
    messages_data: list[dict[str, str | int]],
) -> Chatroom:
    """
    Creates a chatroom, adding members and predefined messages to it. First user is creator.
    Reduces the number of queries by fetching all users at once and using bulk_create for messages.
    "messages_data" is a list of dictionaries with the following keys:
    - "content": str, optional
    - "username": str
    - "session_id": int, optional

    if session_id is present, all else is ignored and message with session attached is created. No need to put content if session_id is present
    """
    chatroom = await create_official_chatroom(name, user, extra_users)

    unique_usernames = {message["username"] for message in messages_data}
    users_by_username = {
        user.username: user
        async for user in User.objects.filter(username__in=unique_usernames)
    }

    messages = []
    for message_data in messages_data:
        user_for_message = users_by_username.get(message_data["username"])
        if not user_for_message:
            continue

        if "session_id" in message_data:
            session = await Session.objects.filter(
                id=message_data["session_id"]
            ).afirst()
            if not session:
                logger.error(
                    f"Session with id {message_data['session_id']} could not be found"
                )
                continue
            message = Message(
                chatroom=chatroom,
                content=session.content_str,
                sender=await User.objects.aget_pico_user(),
                session=session,
            )
        else:
            message = Message(
                chatroom=chatroom,
                sender=user_for_message,
                content=message_data["content"],
            )
        messages.append(message)

    await Message.objects.abulk_create(messages)

    return chatroom


async def send_simulado_uerj(chatroom_id: int, user: User) -> None:
    """
    Sends the Simulado UERJ message to the chatroom.
    """
    chatroom = (
        await Chatroom.objects.filter(id=chatroom_id, members__id=user.id)
        .prefetch_related("members")
        .afirst()
    )
    if not chatroom:
        raise ChatroomForUserNotFound

    await message_service.asend_simulado_uerj_messages(chatroom, user.username, user.id)

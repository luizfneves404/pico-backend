import logging
from dataclasses import dataclass

import api.message_tasks as message_tasks
import api.services.chatroom_service as chatroom_service
import api.services.file_service as file_service
import notifications.utils as notifications_utils
import quiz.quiz_service as quiz_service
import shared.file_utils as file_utils
from api.models import (
    PICO_USERNAME,
    Chatroom,
    EmbeddedFile,
    Message,
    OfficialChatroom,
    User,
)
from asgiref.sync import sync_to_async
from django.conf import settings
from django.core.files import File as DjangoFile
from django.core.files.uploadedfile import UploadedFile as DjangoUploadedFile
from django.db import transaction
from essays.models import EssayTopic
from quiz.models import Session

MAX_FILES_TO_PROCESS = 20

TOO_MANY_FILES_MESSAGE = f"Pô, já tem {MAX_FILES_TO_PROCESS} arquivos nesse grupo. Não consigo dar conta de mais!"

WILL_READ_MESSAGE = "Opa, já recebi. Vou tentar dar uma lida…"

NUM_SIMULADO_QUIZ_QUESTIONS = 20

SIMULADO_UERJ_AREA = "Simulado UERJ"

LIVRO_UERJ = "As Mentiras que os Homens Contam"

logger = logging.getLogger(__name__)


class InvalidContentTypeError(Exception):
    pass


class FileTooBigError(Exception):
    pass


class InvalidMIMETypeError(Exception):
    pass


@dataclass
class MessageContext:
    sender: User | str
    chatroom: Chatroom  # should i use chatroom_id instead?
    content: str = ""
    parent_message: Message | None = None
    attachment: DjangoFile | None = None
    essay_topic: EssayTopic | None = None
    session: Session | None = None
    have_embedding: bool = True

    def __post_init__(self):
        if self.session:
            self.content = self.session.content_str
        elif self.essay_topic:
            self.content = self.essay_topic.content_str
        elif not self.content and not self.attachment:
            raise ValueError("Content or attachment is required")


async def forward_message_to_users(
    by_user: User, to_usernames: list[str], message_id: int
):
    to_users = User.non_sentinel_objects.filter(username__in=to_usernames).exclude(
        id=by_user.id
    )
    message = (
        await Message.objects.filter(id=message_id).prefetch_for_notification().afirst()
    )
    if not await to_users.aexists():
        raise ValueError("User not found")
    if not message:
        raise ValueError("Message not found")

    if not await message.chatroom.ais_member(by_user):
        raise ValueError("User is not a member of the chatroom of the message")

    embedded_file = await message.embedded_files.afirst()

    dm_chatrooms = await chatroom_service.get_or_create_dm_chatrooms(
        by_user, [user async for user in to_users]
    )

    for chatroom in dm_chatrooms:
        await asend_message(
            sender=(
                message.sender if message.sender.username == PICO_USERNAME else by_user
            ),
            chatroom=chatroom,
            content=message.content,
            attachment=embedded_file.file if embedded_file else None,
            essay_topic=message.essay_topic,
            session=message.session,
        )

    logger.debug(
        f"Message with id {message_id} forwarded to users {[user.id for user in to_users]} by user {by_user.id}"
    )
    return dm_chatrooms


async def list_top_level_messages_for_chatroom(chatroom: Chatroom) -> list[Message]:
    # Prefetch the EmbeddedFiles using Prefetch object
    messages_with_prefetched_files_and_extra_objects = (
        Message.objects.filter(chatroom=chatroom, parent_message=None)
        .prefetch_for_notification()
        .order_by("timestamp")
    )

    messages = []
    async for message in messages_with_prefetched_files_and_extra_objects:
        embedded_file = (
            message.embedded_files.all()[0] if message.embedded_files.all() else None
        )
        attachment_url = embedded_file.file.url if embedded_file else None
        extra_object_id = (
            message.essay_topic.id
            if message.essay_topic
            else message.session.id
            if message.session
            else None
        )

        setattr(message, "attachment", attachment_url)
        setattr(message, "extra_object_id", extra_object_id)
        messages.append(message)

    return messages


def get_top_level_message(
    top_level_message_id: int | None, chatroom: Chatroom
) -> Message | None:
    if top_level_message_id:
        top_level_message = Message.objects.filter(
            id=top_level_message_id, chatroom=chatroom, parent_message=None
        ).first()
        if not top_level_message:
            raise ValueError("Top-level message not found for this chatroom")
        return top_level_message
    else:
        return None


async def aget_top_level_message(
    top_level_message_id: int | None, chatroom: Chatroom
) -> Message | None:
    if top_level_message_id:
        top_level_message = await Message.objects.filter(
            id=top_level_message_id, chatroom=chatroom, parent_message=None
        ).afirst()
        if not top_level_message:
            raise ValueError("Top-level message not found for this chatroom")
        return top_level_message
    else:
        return None


async def create_and_send_message(
    sender: User | str,
    content: str,
    chatroom: Chatroom,
    attachment: DjangoFile | None = None,
    parent_message: Message | None = None,
) -> Message:
    if attachment:
        mime_type = file_utils.get_mime_type(attachment)
        _validate_attachment_upload(attachment, mime_type)
        message = await asend_message(
            sender=sender,
            content=content,
            chatroom=chatroom,
            attachment=attachment,
            parent_message=parent_message,
        )
        if file_service.check_file_should_be_processed(mime_type):
            await _handle_attachment(message, chatroom)
    else:
        message = await asend_message(
            sender=sender,
            content=content,
            chatroom=chatroom,
            parent_message=parent_message,
        )

    logger.debug(f"Message created in chatroom {chatroom.id} by user {sender.id}")
    return message


def _validate_attachment_upload(upload: DjangoUploadedFile, mime_type: str):
    logger.debug(f"Validating file upload {upload}...")

    if upload and upload.content_type not in settings.CHATFILE_VALID_MIME_TYPES:
        logger.debug(f"Invalid content type: {upload.content_type}")
        raise InvalidContentTypeError(upload.content_type)

    if mime_type not in settings.CHATFILE_VALID_MIME_TYPES:
        logger.debug(f"Invalid MIME type: {mime_type}")
        raise InvalidMIMETypeError(mime_type)

    logger.info("File upload is valid")


async def _process_attachment(
    embedded_file_id: int,
    chatroom: Chatroom,
):
    logger.info(f"Processing file {embedded_file_id} for message...")
    await asend_message(
        sender="pico",
        content=WILL_READ_MESSAGE,
        chatroom=chatroom,
        have_embedding=False,
    )
    await file_service.process_local_file(embedded_file_id)


async def _handle_attachment(message: Message, chatroom: Chatroom):
    files_count = await EmbeddedFile.objects.filter(
        messages__chatroom=chatroom
    ).acount()

    if files_count > MAX_FILES_TO_PROCESS:
        await asend_message(
            sender="pico",
            content=TOO_MANY_FILES_MESSAGE,
            chatroom=chatroom,
            have_embedding=False,
        )
    else:
        embedded_file = await EmbeddedFile.objects.aget(
            messages=message
        )  # will fail for more than one
        await _process_attachment(embedded_file.id, chatroom)


def send_message(
    sender: User | str,
    chatroom: Chatroom,
    content: str = "",
    attachment: DjangoFile | None = None,
    parent_message: Message | None = None,
    essay_topic: EssayTopic | None = None,
    session: Session | None = None,
    have_embedding: bool = True,
) -> Message:
    context = MessageContext(
        sender=sender,
        content=content,
        chatroom=chatroom,
        parent_message=parent_message,
        essay_topic=essay_topic,
        session=session,
        attachment=attachment,
        have_embedding=have_embedding,
    )
    return send(context)[0]


async def asend_message(
    sender: User | str,
    chatroom: Chatroom,
    content: str = "",
    attachment: DjangoFile | None = None,
    parent_message: Message | None = None,
    essay_topic: EssayTopic | None = None,
    session: Session | None = None,
    have_embedding: bool = True,
) -> Message:
    context = MessageContext(
        sender=sender,
        content=content,
        chatroom=chatroom,
        parent_message=parent_message,
        essay_topic=essay_topic,
        session=session,
        attachment=attachment,
        have_embedding=have_embedding,
    )
    return (await asend(context))[0]


async def asend(
    message_context: MessageContext | list[MessageContext],
) -> list[Message]:
    contexts = (
        [message_context]
        if isinstance(message_context, MessageContext)
        else message_context
    )
    logger.debug(
        f"Sending messages to chatrooms {[context.chatroom.id for context in contexts]}"
    )
    messages = await sync_to_async(_bulk_create_messages)(contexts)
    return await aprocess_created_messages(messages, contexts)


async def aprocess_created_messages(
    messages: list[Message], contexts: list[MessageContext]
) -> list[Message]:
    chatrooms = [message.chatroom for message in messages]
    message_ids = [message.id for message in messages]
    embed_message_ids = [
        message.id
        for message, context in zip(messages, contexts)
        if context.have_embedding
    ]

    await _anotify_messages(message_ids)
    await _aembed_messages(embed_message_ids) if embed_message_ids else None

    logger.debug(
        f"Finished sending messages to chatrooms {[chatroom.id for chatroom in chatrooms]}."
    )
    return messages


def send(
    message_context: MessageContext | list[MessageContext],
) -> list[Message]:
    contexts = (
        [message_context]
        if isinstance(message_context, MessageContext)
        else message_context
    )

    logger.debug(
        f"Sending messages to chatrooms {[context.chatroom.id for context in contexts]}"
    )

    messages = _bulk_create_messages(contexts)
    return process_created_messages(messages, contexts)


def process_created_messages(
    messages: list[Message], contexts: list[MessageContext]
) -> list[Message]:
    chatrooms = [message.chatroom for message in messages]

    message_ids = [message.id for message in messages]
    embed_message_ids = [
        message.id
        for message, context in zip(messages, contexts)
        if context.have_embedding
    ]

    _notify_messages(message_ids)
    _embed_messages(embed_message_ids) if embed_message_ids else None
    logger.debug(
        f"Finished sending messages to chatrooms {[chatroom.id for chatroom in chatrooms]}."
    )
    return messages


async def _anotify_messages(message_ids: list[int]):
    if message_ids:
        if len(message_ids) == 1:
            messages = [
                (
                    await Message.objects.prefetch_for_notification()
                    .filter(id__in=message_ids)
                    .afirst()
                )
            ]
            await notifications_utils.prepare_messages_notifications(
                messages
            ).send_async()
        else:
            message_tasks.task_bulk_notify_messages.delay(message_ids).forget()


def _notify_messages(message_ids: list[int]):
    if message_ids:
        if len(message_ids) == 1:
            messages = list(
                Message.objects.prefetch_for_notification().filter(id__in=message_ids)
            )
            notifications_utils.prepare_messages_notifications(messages).send_sync()
        else:
            message_tasks.task_bulk_notify_messages.delay(message_ids).forget()


async def _aembed_messages(message_ids: list[int]):
    if message_ids:
        if len(message_ids) == 1:
            message = (
                await Message.objects.prefetch_for_notification()
                .filter(id__in=message_ids)
                .afirst()
            )
            await message_tasks.add_embedding_to_message_async_workflow(
                message.id, message.content
            )
        else:
            message_tasks.task_bulk_embed_messages.delay(message_ids).forget()


def _embed_messages(message_ids: list[int]):
    if message_ids:
        if len(message_ids) == 1:
            message = Message.objects.prefetch_for_notification().get(
                id__in=message_ids
            )
            message_tasks.add_embedding_to_message_sync_workflow(
                message.id, message.content
            )
        else:
            message_tasks.task_bulk_embed_messages.delay(message_ids).forget()


def _bulk_create_messages(
    messages_context: list[MessageContext],
) -> list[Message]:
    with transaction.atomic():
        # grab distinct users in one go instead of executing n queries for each username
        users = {
            data.sender for data in messages_context if isinstance(data.sender, str)
        }
        users = User.objects.filter(username__in=users)
        users_dict = {user.username: user for user in users}
        messages = [
            Message(
                sender=(
                    data.sender
                    if isinstance(data.sender, User)
                    else users_dict[data.sender]
                ),
                content=data.content,
                chatroom=data.chatroom,
                parent_message=data.parent_message,
                essay_topic=data.essay_topic,
                session=data.session,
            )
            for data in messages_context
        ]
        messages_in_db = Message.objects.bulk_create(messages)
        message_ids = [message.id for message in messages_in_db]
        # Preserve order by using a dict to map ids to messages
        messages_dict = {
            m.id: m
            for m in Message.objects.filter(
                id__in=message_ids
            ).prefetch_for_notification()
        }
        messages_in_db = [messages_dict[mid] for mid in message_ids]

        # Check if all attachments are the same
        first_attachment = messages_context[0].attachment
        if all(data.attachment == first_attachment for data in messages_context):
            # All attachments are the same, create only one EmbeddedFile
            if first_attachment:
                embedded_file = EmbeddedFile.objects.create(file=first_attachment)
                embedded_file.messages.add(*messages_in_db)
                for message in messages_in_db:
                    message.attachment = embedded_file.file.url
            else:
                for message in messages_in_db:
                    message.attachment = None
        else:
            # Handle attachments individually
            for i, message in enumerate(messages_in_db):
                data = messages_context[i]
                if data.attachment:
                    embedded_file = EmbeddedFile.objects.create(file=data.attachment)
                    embedded_file.messages.add(message)
                    message.attachment = embedded_file.file.url
                else:
                    message.attachment = None

        # Set extra_object_id based on either essay_topic or quiz
        for i, message in enumerate(messages_in_db):
            data = messages_context[i]
            message.extra_object_id = (
                data.essay_topic.id
                if data.essay_topic
                else data.session.id
                if data.session
                else None
            )

        return messages_in_db


def send_messages_to_user_official_chatrooms(
    content_users_pairs: list[tuple[str, User]],
    attachment: DjangoFile | None = None,
    essay_topic: EssayTopic | None = None,
    session: Session | None = None,
):
    chatrooms = OfficialChatroom.objects.filter(
        members__in=[user for _, user in content_users_pairs]
    ).prefetch_related("members")

    user_chatroom_map = {
        member: chatroom for chatroom in chatrooms for member in chatroom.members.all()
    }

    messages = [
        MessageContext(
            sender="pico",
            content=content,
            chatroom=user_chatroom_map.get(user),
            attachment=attachment,
            essay_topic=essay_topic,
            session=session,
        )
        for content, user in content_users_pairs
        if user in user_chatroom_map
    ]

    if messages:
        send(message_context=messages)
    else:
        logger.warning("No messages sent as no users have corresponding chatrooms.")

    missing_users = [
        user for _, user in content_users_pairs if user not in user_chatroom_map
    ]
    if missing_users:
        logger.debug(
            f"Users without chatrooms: {', '.join(user.username for user in missing_users)}"
        )


async def asend_simulado_uerj_messages(chatroom: Chatroom, username: str, user_id: int):
    quiz1_configs = [
        {"number": 10, "source_filter": LIVRO_UERJ},
        {"number": 10, "subject": "Português", "source_filter": "UERJ"},
    ]

    quiz2_configs = [
        {"number": 5, "subject": "Matemática", "source_filter": "UERJ"},
        {"number": 5, "subject": "Física", "source_filter": "UERJ"},
        {"number": 5, "subject": "Química", "source_filter": "UERJ"},
        {"number": 5, "subject": "Biologia", "source_filter": "UERJ"},
    ]
    quiz3_configs = [
        {"number": 20, "source_filter": "UERJ", "area": "Ciências Humanas"},
    ]

    quiz1 = await quiz_service.create_compound_multiple_choice_quiz(
        "Linguagens", SIMULADO_UERJ_AREA, username, user_id, "UERJ", quiz1_configs
    )
    quiz2 = await quiz_service.create_compound_multiple_choice_quiz(
        "Exatas",
        SIMULADO_UERJ_AREA,
        username,
        user_id,
        "UERJ",
        quiz2_configs,
        shuffle_science=True,
    )
    quiz3 = await quiz_service.create_compound_multiple_choice_quiz(
        "Humanas", SIMULADO_UERJ_AREA, username, user_id, "UERJ", quiz3_configs
    )

    quizzes = [quiz1, quiz2, quiz3]
    for quiz in quizzes:
        await asend_message(
            sender="pico", chatroom=chatroom, session=quiz, have_embedding=False
        )

    logger.debug(
        f"Simulado UERJ messages sent in chatroom {chatroom.id}, quizzes are {[quiz.id for quiz in quizzes]}"
    )

import logging

import shared.file_utils as file_utils
from api.models import User
from asgiref.sync import sync_to_async
from currency.decorators import currency_transaction
from currency.models import CurrencyAction, CurrencyType
from django.core.files.uploadedfile import UploadedFile as DjangoUploadedFile
from django.db import transaction
from django.db.models import Prefetch

import essays.tasks as essay_tasks
from essays.models import Essay, EssayTopic, EssayType, ExtractedText, Feedback

logger = logging.getLogger(__name__)


class InvalidContentTypeError(Exception):
    pass


class InvalidMIMETypeError(Exception):
    pass


class EssayTopicNameRequiredError(Exception):
    pass


class EssayTopicNotFoundError(Exception):
    pass


class EssayAlreadyCorrectedError(Exception):
    pass


class EssayTypeNotFoundError(Exception):
    pass


ESSAY_FILE_VALID_CONTENT_TYPES = [
    "image/jpeg",
    "image/png",
]


def _validate_essay_upload(upload: DjangoUploadedFile, mime_type: str):
    logger.debug(f"Validating file upload for essay original_file {upload}...")

    if upload and upload.content_type not in ESSAY_FILE_VALID_CONTENT_TYPES:
        logger.debug(f"Invalid content type: {upload.content_type}")
        raise InvalidContentTypeError(upload.content_type)

    if mime_type not in ESSAY_FILE_VALID_CONTENT_TYPES:
        logger.debug(f"Invalid MIME type: {mime_type}")
        raise InvalidMIMETypeError(mime_type)

    logger.info("File upload for essay original_file is valid")


def submit_essay(
    user: User, essay_topic_id: int, essay_type: str, upload: DjangoUploadedFile
):
    mime_type = file_utils.get_mime_type(upload)
    _validate_essay_upload(upload, mime_type)

    essay_topic = EssayTopic.objects.filter(id=essay_topic_id).first()
    if not essay_topic:
        raise EssayTopicNotFoundError()

    essay_type_model = EssayType.objects.filter(name=essay_type).first()
    if not essay_type_model:
        raise EssayTypeNotFoundError()

    with transaction.atomic():
        user_essay, created = Essay.objects.select_for_update().get_or_create(
            author_id=user.id,
            essay_topic=essay_topic,
            defaults={
                "original_file": upload,
                "essay_type_id": essay_type_model.name,
            },
        )
        if created:
            logger.info(f"Essay {user_essay.id} created")
        else:
            logger.info(
                f"Essay {user_essay.id} already exists. Updating original_file and essay_type and deleting extracted_text."
            )
            user_essay.original_file = upload
            user_essay.essay_type = essay_type_model
            user_essay.save()
            ExtractedText.objects.filter(essay_id=user_essay.id).delete()

    extract_and_clean_and_save_and_notify([user_essay.id])

    # refetching essay to get updated feedbacks and essay_type
    user_essay = (
        Essay.objects.prefetch_related("feedbacks__feedback_category")
        .select_related("essay_type")
        .get(id=user_essay.id)
    )

    return user_essay


@currency_transaction(CurrencyAction.ESSAY_CREATION, CurrencyType.PRICE)
async def asubmit_essay(
    user: User, essay_topic_id: int, essay_type: str, upload: DjangoUploadedFile
):
    return await sync_to_async(submit_essay)(user, essay_topic_id, essay_type, upload)


def correct_essay(
    user_id: int, essay_topic_id: int, essay_type: str, user_corrected_text: str
):
    essay_topic = EssayTopic.objects.filter(id=essay_topic_id).first()
    if not essay_topic:
        raise EssayTopicNotFoundError()

    essay_type_model = EssayType.objects.filter(name=essay_type).first()
    if not essay_type_model:
        raise EssayTypeNotFoundError()

    with transaction.atomic():
        user_essay, created = Essay.objects.select_for_update().get_or_create(
            author_id=user_id,
            essay_topic_id=essay_topic_id,
            defaults={
                "essay_type": essay_type_model,
                "user_corrected_text": user_corrected_text,
            },  # will ignore the essay_type provided if the essay already exists
        )
        if created:
            logger.info(f"Essay {user_essay.id} created")
        else:
            logger.info(
                f"Essay {user_essay.id} already exists. Updating user_corrected_text and clearing feedback."
            )
            user_essay.user_corrected_text = user_corrected_text
            user_essay.save()
            Feedback.objects.filter(essay_id=user_essay.id).delete()

    correct_essay_and_save_and_notify([user_essay.id])

    # refetching essay to get updated essay_type and feedback
    user_essay = (
        Essay.objects.select_related("essay_type")
        .prefetch_related("feedbacks__feedback_category")
        .get(id=user_essay.id)
    )
    return user_essay


async def acorrect_essay(
    user_id: int, essay_topic_id: int, essay_type: str, user_corrected_text: str
):
    return await sync_to_async(correct_essay)(
        user_id, essay_topic_id, essay_type, user_corrected_text
    )


async def get_essay_topic(user_id: int, id: int):
    user_essays = (
        Essay.objects.filter(author_id=user_id)
        .prefetch_related("feedbacks__feedback_category")
        .select_related("essay_type")
    )

    essay_topic = (
        await EssayTopic.objects.prefetch_related(
            Prefetch("essays", queryset=user_essays, to_attr="temp_essays")
        )
        .filter(id=id)
        .afirst()
    )
    if not essay_topic:
        raise EssayTopicNotFoundError()

    essay_topic.essay = essay_topic.temp_essays[0] if essay_topic.temp_essays else None

    return essay_topic


async def list_essay_topics(user_id: int) -> list[EssayTopic]:
    user_essays = (
        Essay.objects.select_related("essay_type")
        .prefetch_related("feedbacks__feedback_category")
        .filter(author_id=user_id)
    )

    essay_topics = EssayTopic.objects.prefetch_related(
        Prefetch("essays", queryset=user_essays, to_attr="temp_essays")
    ).filter(essays__author_id=user_id)

    async for essay_topic in essay_topics:
        (
            setattr(essay_topic, "essay", essay_topic.temp_essays[0])
            if essay_topic.temp_essays
            else None
        )

    return [essay_topic async for essay_topic in essay_topics]


async def start_essay_topic(name: str):
    if not name:
        raise EssayTopicNameRequiredError()

    essay_topic, _ = await EssayTopic.objects.aget_or_create(
        name=name,
    )
    # await message_service.asend_message(
    #     sender="pico", chatroom=chatroom, essay_topic=essay_topic
    # )
    return essay_topic


def extract_text_and_save(ids: list[int]):
    for id in ids:
        essay_tasks.task_extract_text_amazon_textract.delay(id).forget()
        essay_tasks.task_extract_text_pen_to_print.delay(id).forget()


def clean_text_and_save(ids: list[int]):
    for id in ids:
        essay_tasks.task_clean_text_by_llm.delay(id).forget()


def extract_and_clean_and_save_and_notify(ids: list[int]):
    essays = Essay.objects.filter(id__in=ids)
    for essay in essays:
        if essay.original_file:
            essay_tasks.extract_and_clean_sync_workflow(
                essay.id, essay.original_file.size > 4 * 1000 * 1000
            )
        else:
            logger.info(f"Skipping essay {essay.id} because original_file has no file")


async def aextract_and_clean_and_save_and_notify(ids: list[int]):
    essays = Essay.objects.filter(id__in=ids)
    async for essay in essays:
        if essay.original_file:
            await essay_tasks.extract_and_clean_async_workflow(
                essay.id, essay.original_file.size > 4 * 1000 * 1000
            )
        else:
            logger.info(f"Skipping essay {essay.id} because original_file has no file")


def correct_essay_and_save_and_notify(ids: list[int]):
    essays = Essay.objects.filter(id__in=ids)
    for essay in essays:
        if essay.user_corrected_text:
            essay_tasks.correct_essay_sync_workflow(essay.id)
        else:
            logger.info(
                f"Skipping essay {essay.id} because user_corrected_text is empty"
            )

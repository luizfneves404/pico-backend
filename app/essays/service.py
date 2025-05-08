import logging

from fastapi import UploadFile
from sqlalchemy import delete, insert, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

import app.files.utils as file_utils
from app.arq_client import enqueue_job
from app.currency.decorators import currency_transaction
from app.currency.models import CurrencyAction, CurrencyType
from app.essays.models import (
    Essay,
    EssayTopic,
    EssayType,
    ExtractedText,
    Feedback,
    get_essay_loader,
    get_essay_topic_loader,
)
from app.files.models import create_file
from app.users.models import User

logger = logging.getLogger(__name__)


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


def _validate_essay_upload(upload: UploadFile, mime_type: str):
    logger.debug(f"Validating file upload for essay original_file {upload}...")

    if upload.content_type not in ESSAY_FILE_VALID_CONTENT_TYPES:
        logger.debug(f"Invalid content type: {upload.content_type}")
        raise InvalidContentTypeError(upload.content_type)

    if mime_type not in ESSAY_FILE_VALID_CONTENT_TYPES:
        logger.debug(f"Invalid MIME type: {mime_type}")
        raise InvalidMIMETypeError(mime_type)

    logger.info("File upload for essay original_file is valid")


@currency_transaction(CurrencyAction.ESSAY_CREATION, CurrencyType.PRICE)
async def submit_essay_with_file(
    db_session: AsyncSession,
    user: User,
    essay_topic_id: int,
    essay_type: str,
    upload: UploadFile,
) -> Essay:
    """Submits an essay to the database, creating a file and initiating the extraction and cleaning process.

    Args:
        db_session (AsyncSession): The database session to use.
        user (User): The user submitting the essay.
        essay_topic_id (int): The ID of the essay topic.
        essay_type (str): The type of essay.
        upload (UploadFile): The uploaded file containing the essay.

    Raises:
        EssayTypeNotFoundError: If the essay type is not found.
        EssayTopicNotFoundError: If the essay topic is not found.

    Returns:
        Essay: The submitted essay.
    """
    # Validate upload and create file in one step
    mime_type = await file_utils.get_mime_type(upload)
    _validate_essay_upload(upload, mime_type)
    file_model = await create_file(db_session, upload)

    await db_session.flush()

    existing_essay = await db_session.execute(
        select(Essay)
        .where(Essay.author_id == user.id, Essay.essay_topic_id == essay_topic_id)
        .options(*get_essay_loader())
    )
    existing_essay = existing_essay.scalar_one_or_none()

    if existing_essay:
        delete_stmt = delete(ExtractedText).where(
            ExtractedText.essay_id == existing_essay.id
        )
        await db_session.execute(delete_stmt)
        existing_essay.original_file = file_model
        existing_essay.essay_type_id = (
            select(EssayType.id).where(EssayType.name == essay_type).scalar_subquery()
        )
        try:
            await db_session.flush()
        except DBAPIError as e:
            if "not-null" in str(e):
                raise EssayTypeNotFoundError()
            raise

        await enqueue_extract_and_clean(existing_essay)
        return existing_essay
    else:
        # Create new essay with insert().returning()
        insert_stmt = (
            insert(Essay)
            .values(
                author_id=user.id,
                essay_topic_id=essay_topic_id,
                original_file_id=file_model.id,
                essay_type_id=select(EssayType.id)
                .where(EssayType.name == essay_type)
                .scalar_subquery(),
            )
            .returning(Essay)
            .options(*get_essay_loader())
        )
        try:
            essay = (await db_session.execute(insert_stmt)).scalar_one()
        except DBAPIError as e:
            if "not-null" in str(e):
                raise EssayTypeNotFoundError()
            elif "fk__essay__essay_topic_id__essay_topic" in str(e):
                raise EssayTopicNotFoundError()
            raise

        await enqueue_extract_and_clean(essay)
        return essay


async def correct_essay(
    db_session: AsyncSession,
    user_id: int,
    essay_topic_id: int,
    essay_type: str,
    user_corrected_text: str,
) -> Essay:
    """If an essay doesn't exist, creates an essay using directly the user_corrected_text.
    If the essay exists, updates the user_corrected_text and clears the feedback.
    In any case, it corrects the essay and saves it.

    Args:
        db_session (AsyncSession): The database session to use.
        user_id (int): The ID of the user.
        essay_topic_id (int): The ID of the essay topic.
        essay_type (str): The type of essay.
        user_corrected_text (str): The user corrected text.

    Raises:
        EssayTopicNotFoundError: If the essay topic is not found.
        EssayTypeNotFoundError: If the essay type is not found.

    Returns:
        Essay: The corrected essay.
    """
    # Find existing essay
    existing_essay = await db_session.execute(
        select(Essay)
        .where(Essay.author_id == user_id, Essay.essay_topic_id == essay_topic_id)
        .options(*get_essay_loader())
    )
    existing_essay = existing_essay.scalar_one_or_none()

    if existing_essay:
        # Clear existing feedback
        delete_stmt = delete(Feedback).where(Feedback.essay_id == existing_essay.id)
        await db_session.execute(delete_stmt)

        # Update essay with user corrected text
        existing_essay.user_corrected_text = user_corrected_text
        existing_essay.essay_type_id = (
            select(EssayType.id).where(EssayType.name == essay_type).scalar_subquery()
        )
        try:
            await db_session.flush()
        except DBAPIError as e:
            if "not-null" in str(e):
                raise EssayTypeNotFoundError()
            raise

        # correct_essay_and_save_and_notify([existing_essay.id])
        print("will not correct and save and notify")
        return existing_essay
    else:
        # Create new essay with insert().returning()
        insert_stmt = (
            insert(Essay)
            .values(
                author_id=user_id,
                essay_topic_id=essay_topic_id,
                user_corrected_text=user_corrected_text,
                essay_type_id=select(EssayType.id)
                .where(EssayType.name == essay_type)
                .scalar_subquery(),
            )
            .returning(Essay)
            .options(*get_essay_loader())
        )
        try:
            essay = (await db_session.execute(insert_stmt)).scalar_one()
        except DBAPIError as e:
            if "not-null" in str(e):
                raise EssayTypeNotFoundError()
            elif "fk__essay__essay_topic_id__essay_topic" in str(e):
                raise EssayTopicNotFoundError()
            raise

        # correct_essay_and_save_and_notify([essay.id])
        print("will not correct and save and notify")
        return essay


async def get_essay_topic(db_session: AsyncSession, user_id: int, id: int):
    essay_topic = (
        await db_session.execute(
            select(EssayTopic)
            .where(EssayTopic.id == id)
            .options(*get_essay_topic_loader(user_id))
        )
    ).scalar_one_or_none()
    if not essay_topic:
        raise EssayTopicNotFoundError()
    return essay_topic


async def list_essay_topics(db_session: AsyncSession, user_id: int) -> list[EssayTopic]:
    essay_topics = await db_session.execute(
        select(EssayTopic)
        .join(Essay, EssayTopic.id == Essay.essay_topic_id)
        .where(Essay.author_id == user_id)
        .options(*get_essay_topic_loader(user_id))
        .distinct()
    )
    return list(essay_topics.scalars().all())


async def start_essay_topic(
    db_session: AsyncSession, user_id: int, name: str
) -> EssayTopic:
    stmt = (
        pg_insert(EssayTopic)
        .values(name=name)
        .on_conflict_do_update(index_elements=["name"], set_={"name": name})
        .returning(EssayTopic)
        .options(*get_essay_topic_loader(user_id))
    )
    result = await db_session.execute(stmt)
    essay_topic = result.scalar_one()
    return essay_topic


async def enqueue_extract_and_clean(essay: Essay):
    await enqueue_job(
        "task_extract_and_clean",
        essay.id,
        essay.original_file.size > 4 * 1000 * 1000,
    )


async def enqueue_correct_essay(essay: Essay):
    await enqueue_job("task_correct_essay", essay.id)

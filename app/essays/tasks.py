import asyncio
import logging
from io import BytesIO
from typing import Any

from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

import app.files.utils as file_utils
from app.database import db_manager
from app.essays.constants import (
    CLEAN_TEXT_MODEL,
    CLEAN_TEXT_SYSTEM_MESSAGE,
    CLEAN_TEXT_TEMPERATURE,
    CLEAN_TEXT_TIMEOUT,
)
from app.essays.models import (
    Essay,
    ExtractedText,
    Feedback,
    FeedbackCategory,
)
from app.fcm import fcm_service
from app.shared import openai_utils, text_extraction
from app.shared.constants import (
    EXTRACT_OPENAI_EXTRACTION_METHOD,
    PEN_TO_PRINT_EXTRACTION_METHOD,
)
from app.ws import notifications as notifications_utils

logger = logging.getLogger(__name__)


class CouldNotCleanTextError(Exception):
    pass


class CouldNotGradeFeedbackError(Exception):
    pass


async def task_extract_and_clean(
    ctx: dict[Any, Any], essay_id: int, compress_image: bool
):
    async with db_manager.session_with_transaction() as db_session:
        essay = (
            await db_session.execute(
                select(Essay)
                .where(Essay.id == essay_id)
                .options(
                    selectinload(Essay.essay_topic),
                    selectinload(Essay.original_file),
                    selectinload(Essay.author),
                )
            )
        ).scalar_one()
        if compress_image:
            await compress_essay_image(essay)

        extraction_methods = [
            extract_text_amazon_textract,
            extract_text_pen_to_print,
        ]
        extraction_method_names = [
            EXTRACT_OPENAI_EXTRACTION_METHOD,
            PEN_TO_PRINT_EXTRACTION_METHOD,
        ]

        extraction_tasks = [method(essay) for method in extraction_methods]
        try:
            texts = await asyncio.gather(*extraction_tasks)

            for text, method_name in zip(texts, extraction_method_names):
                extracted_text = ExtractedText(
                    essay_id=essay.id,
                    text=text,
                    extraction_method=method_name,
                )
                db_session.add(extracted_text)
            await db_session.flush()

            await clean_text_by_llm(db_session, essay)
            await finalize_extract_and_clean(essay)
        except text_extraction.ContentTooBigForPenToPrintError as e:
            await handle_essay_error(
                essay,
                db_session,
                "ContentTooBigForPenToPrint",
                "Desculpe, a imagem da sua redação é muito grande!",
                f"Essa redação é muito grande para ser processada. Tente usar uma nova imagem pra redação {essay.essay_topic.name}",
            )
            logger.warning(
                f"Failed to extract and clean essay {essay_id} because the image is too big: {e}"
            )
        except Exception:
            await handle_essay_error(
                essay,
                db_session,
                "CouldNotExtractText",
                "Desculpa! Não conseguimos extrair o texto da redação!",
                f"Desculpe, tente usar uma nova imagem para a redação {essay.essay_topic.name}",
            )
            raise
    logger.debug(f"Started extract_and_clean_workflow for essay {essay_id}")


async def handle_essay_error(
    essay: Essay,
    db_session: AsyncSession,
    error_type: str,
    notification_title: str,
    notification_body: str,
):
    """Handle common essay processing errors by cleaning up resources and notifying the user.

    Args:
        essay: The essay being processed
        db_session: The database session
        error_type: The type of error for the notification
        notification_title: The title for the FCM notification
        notification_body: The body for the FCM notification
    """
    await essay.original_file.delete()
    await db_session.delete(essay)
    await notifications_utils.prepare_feature_error_notification(
        essay.author.id,
        error_type,
        essay.essay_topic.id,
    ).send()
    await fcm_service.send_notifications(
        [
            fcm_service.NotificationData(
                user_id=essay.author.id,
                title=notification_title,
                body=notification_body,
            )
        ]
    )


async def extract_text_pen_to_print(essay: Essay):
    async with essay.original_file.get_file_like() as file_like:
        return await text_extraction.pen_to_print_api(file_like)


async def extract_text_amazon_textract(essay: Essay):
    return await run_in_threadpool(
        text_extraction.call_amazon_textract_api, await essay.original_file.get_url()
    )


async def compress_essay_image(essay: Essay):
    """Compress an essay image using Tinify API and update the file in storage.

    Args:
        essay_id (int): The ID of the essay to compress.
    """
    logger.debug(
        f"Compressing essay image for essay {essay.id} using tinify API. Size before: {essay.original_file.size}"
    )

    # Get compressed image data
    compressed_content = await file_utils.call_tinify(
        await essay.original_file.get_url()
    )

    file_obj = BytesIO(compressed_content)
    size = len(compressed_content)

    # Update the file with new content
    await essay.original_file.update_file_content(file_obj, size)

    logger.debug(
        f"Compressed essay image for essay {essay.id} using tinify API. Size after: {essay.original_file.size}"
    )


async def clean_text_by_llm(db_session: AsyncSession, essay: Essay):
    extracted_texts = list(
        (
            await db_session.execute(
                select(ExtractedText.text).where(ExtractedText.essay_id == essay.id)
            )
        )
        .scalars()
        .all()
    )
    if len(extracted_texts) == 0:
        raise CouldNotCleanTextError

    user_message = "\n\n".join(
        [
            f"Resultado de extração {i + 1}:\n{extracted_text}"
            for i, extracted_text in enumerate(extracted_texts)
        ]
    )

    chatbot_response = openai_utils.get_completion(
        model=CLEAN_TEXT_MODEL,
        temperature=CLEAN_TEXT_TEMPERATURE,
        messages=[
            {
                "role": "system",
                "content": CLEAN_TEXT_SYSTEM_MESSAGE.format(
                    essay_topic=essay.essay_topic.name
                ),
            },
            {
                "role": "user",
                "content": user_message,
            },
        ],
        json_mode=False,
        timeout=CLEAN_TEXT_TIMEOUT,
    ).content
    if chatbot_response == "Não aplicável.":
        raise CouldNotCleanTextError
    else:
        essay.cleaned_text = chatbot_response
        await db_session.flush()


async def finalize_extract_and_clean(essay: Essay):
    await (
        await notifications_utils.prepare_cleaned_text_notification(
            essay.author.id,
            essay.essay_topic.id,
            essay.cleaned_text,
            essay.essay_topic.name,
        )
    ).send()

    logger.debug(f"Finished extract_and_clean_workflow for essay {essay.id}")


async def correct_essay(db_session: AsyncSession, essay_id: int):
    # Get all required data from database first
    essay_data = (
        await db_session.execute(
            select(Essay.user_corrected_text).where(Essay.id == essay_id)
        )
    ).scalar_one()

    feedback_categories = (
        await db_session.execute(
            select(
                FeedbackCategory.id,
                FeedbackCategory.prompt_template,
                FeedbackCategory.temperature,
            ).where(FeedbackCategory.essay_type.has(essays__id=essay_id))
        )
    ).all()

    # Generate all feedbacks concurrently
    feedback_tasks = [
        get_essay_feedback(essay_data, category.prompt_template, category.temperature)
        for category in feedback_categories
    ]
    feedback_results = await asyncio.gather(*feedback_tasks)

    # Save all feedbacks to database
    for category, (feedback_text, grade) in zip(feedback_categories, feedback_results):
        db_session.add(
            Feedback(
                essay_id=essay_id,
                feedback_category_id=category.id,
                text=feedback_text,
                grade=grade,
            )
        )

    await finalize_feedback(db_session, essay_id)


async def get_essay_feedback(
    essay_text: str, prompt_template: str, temperature: float
) -> tuple[str, float]:
    """Generate feedback for an essay using the given prompt template.

    Args:
        essay_text: The text of the essay to generate feedback for
        prompt_template: The template to use for generating feedback
        temperature: The temperature parameter for the LLM

    Returns:
        A tuple containing (feedback_text, grade)
    """
    response_dict = openai_utils.get_feedback(
        prompt_template,
        essay_text,
        temperature,
    )

    logger.info(
        f"Generated feedback: '{response_dict['feedback']}' with grade '{response_dict['grade']}'"
    )

    return response_dict["feedback"], response_dict["grade"]


async def finalize_feedback(db_session: AsyncSession, essay_id: int):
    essay = (
        await db_session.execute(select(Essay).where(Essay.id == essay_id))
    ).scalar_one()

    feedbacks = list(
        (
            await db_session.execute(
                select(Feedback).where(Feedback.essay_id == essay_id)
            )
        )
        .scalars()
        .all()
    )

    notification = await notifications_utils.prepare_essay_correction_notification(
        essay.author.id,
        essay.essay_topic.id,
        [feedback.text for feedback in feedbacks],
        [float(feedback.grade) for feedback in feedbacks],
        essay.essay_topic.name,
    )
    await notification.send()
    logger.debug(f"Finished task_finalize_feedback for essay {essay_id}")

import base64
import logging
import os

import api.services.fcm_service as fcm_service
import celery.exceptions as celery_exceptions
import notifications.utils as notifications_utils
import requests
from celery import chain as celery_chain
from celery import chord as celery_chord
from celery import shared_task
from django.core.files.base import ContentFile
from essays.constants import (
    CLEAN_TEXT_MODEL,
    CLEAN_TEXT_SYSTEM_MESSAGE,
    CLEAN_TEXT_TEMPERATURE,
    CLEAN_TEXT_TIMEOUT,
    EXTRACT_OPENAI_EXTRACTION_METHOD,
    EXTRACT_OPENAI_MODEL,
    EXTRACT_OPENAI_SYSTEM_MESSAGE,
    EXTRACT_OPENAI_TIMEOUT,
    PEN_TO_PRINT_EXTRACTION_METHOD,
    PEN_TO_PRINT_RAPIDAPI_SESSION,
    PEN_TO_PRINT_RAPIDAPI_URL,
    TEXTRACT_EXTRACTION_METHOD,
)
from essays.models import Essay, ExtractedText, Feedback, FeedbackCategory
from pico_backend.celery import celery_async_workflow
from PIL import Image
from shared import openai_utils
from textractor import Textractor
from textractor.data.constants import (
    TextractAPI,
)

from app.config import Environment, settings
from app.files import utils as file_utils

PEN_TO_PRINT_RAPIDAPI_KEY = settings.pen_to_print_rapidapi_key

logger = logging.getLogger(__name__)


class CouldNotExtractTextError(Exception):
    pass


class CouldNotCleanTextError(Exception):
    pass


class CouldNotGradeFeedbackError(Exception):
    pass


class ContentTooBigForPenToPrintError(Exception):
    pass


class PenToPrintError(Exception):
    pass


def clean_text_user_message(extracted_texts: list[str]):
    return "\n\n".join(
        [
            f"Resultado de extração {i + 1}:\n{extracted_text}"
            for i, extracted_text in enumerate(extracted_texts)
        ]
    )


def get_textractor():
    """
    Function to lazily initialize and return the Textractor instance.
    """
    if settings.environment != Environment.PROD:
        return Textractor(
            profile_name=settings.textract_profile_name,
            region_name=settings.textract_region_name,
        )
    else:
        return Textractor(region_name=settings.textract_region_name)


def mock_call_amazon_textract_api(file_like) -> str:
    logger.debug(f"Mocked call to amazon textract api for file {file_like}")
    return f"This is a mock text extracted from the file {file_like} by Amazon Textract"


def call_amazon_textract_api(file_like) -> str:
    logger.debug(f"Calling amazon textract api for file {file_like}")
    extractor = get_textractor()
    with Image.open(file_like) as image:
        response = extractor.detect_document_text(image)
    extracted_text = response.text
    logger.debug(
        f"From amazon textract api call for file {file_like}, received: '{extracted_text}'"
    )
    return extracted_text


def call_amazon_textract_api_start_detection_s3(pdf_s3_path: str) -> str:
    """
    Inicia o job do Textract para um PDF já armazenado no S3.

    :param pdf_s3_path: Caminho 's3://bucket/prefix/arquivo.pdf'
    :return: O JobId retornado pelo Textract
    """
    logger.debug(f"Calling Amazon Textract API for S3 file {pdf_s3_path}")
    extractor = get_textractor()

    response = extractor.start_document_text_detection(
        file_source=pdf_s3_path,
        s3_output_path="",  # Prefixo para outputs, se quiser
        s3_upload_path="",  # Já está no S3, então não precisamos de upload
        client_request_token="",  # Ex: use algo se quiser reusar a mesma JobId
        job_tag="MeuJobDeTexto",  # Tag customizada
        save_image=False,  # Em PDFs de múltiplas páginas, normalmente não precisamos das imagens
    )

    job_id = response.job_id
    logger.debug(f"Textract job started with JobId {job_id}")
    return job_id


def get_textract_job_results(job_id: str) -> list[str]:
    """
    Aguarda e obtém o resultado do job de Textract para o job_id informado.
    Retorna o texto completo extraído.
    """
    logger.debug(f"Getting Textract results for job {job_id}")

    extractor = get_textractor()
    doc = extractor.get_result(job_id, TextractAPI.DETECT_TEXT)
    page_texts = [page.text for page in doc.pages]

    if not page_texts:
        raise ValueError(f"No text found in job {job_id}")

    logger.debug(f"Retrieved text from job {job_id}: '{page_texts}'")
    return page_texts


def extract_text_amazon_textract(essay_id: int):
    try:
        essay = Essay.objects.get(id=essay_id)
        extracted_text = call_amazon_textract_api(essay.original_file.file)
        ExtractedText.objects.create(
            essay_id=essay_id,
            text=extracted_text,
            extraction_method=TEXTRACT_EXTRACTION_METHOD,
        )
    except Exception:
        essay.original_file.delete(save=False)
        essay.delete()
        notifications_utils.prepare_feature_error_notification(
            essay.author.id,
            "CouldNotExtractText",
            essay.essay_topic.id,
        ).send_sync()
        fcm_service.send_notification(
            essay.author.id,
            "Desculpa! Não conseguimos extrair o texto da redação!",
            f"Desculpe, tente usar uma nova imagem para a redação {essay.essay_topic.name}",
        )
        raise


@shared_task(ignore_result=False)  # false because it's part of a chord
def task_extract_text_amazon_textract(essay_id: int):
    extract_text_amazon_textract(essay_id)


def mock_call_pen_to_print_api(file_like) -> str:
    logger.debug(f"Mocked call to pen to print api for file {file_like}")
    return f"This is a mock text extracted from the file {file_like} by Pen to Print"


def call_pen_to_print_api(file_like) -> str:
    files = {"srcImg": file_like}
    payload = {"Session": PEN_TO_PRINT_RAPIDAPI_SESSION}
    headers = {
        "X-RapidAPI-Key": PEN_TO_PRINT_RAPIDAPI_KEY,
        "X-RapidAPI-Host": "pen-to-print-handwriting-ocr.p.rapidapi.com",
    }
    logger.debug(f"Calling pen to print api for file {file_like}")
    response = requests.post(
        PEN_TO_PRINT_RAPIDAPI_URL, data=payload, files=files, headers=headers
    )
    if response.status_code == 413:
        raise ContentTooBigForPenToPrintError

    response_json = response.json()
    logger.debug(f"Response from pen to print api: {response_json}")

    if "error" in response_json:
        raise PenToPrintError(response_json["error"])

    response.raise_for_status()

    extracted_text = response.json()["value"]

    logger.debug(
        f"From pen to print api call for file {file_like}, received: '{extracted_text}'"
    )

    return extracted_text


def extract_text_pen_to_print(essay_id: int):
    try:
        essay = Essay.objects.get(id=essay_id)
        extracted_text = call_pen_to_print_api(essay.original_file.file)
        ExtractedText.objects.create(
            essay_id=essay_id,
            text=extracted_text,
            extraction_method=PEN_TO_PRINT_EXTRACTION_METHOD,
        )
    except ContentTooBigForPenToPrintError:
        essay.original_file.delete(save=False)
        essay.delete()
        notifications_utils.prepare_feature_error_notification(
            essay.author.id,
            "ContentTooBigForPenToPrint",
            essay.essay_topic.id,
        ).send_sync()
        fcm_service.send_notification(
            essay.author.id,
            "Desculpe, a imagem da sua redação é muito grande!",
            f"Essa redação é muito grande para ser processada. Tente usar uma nova imagem pra redação {essay.essay_topic.name}",
        )
        raise
    except Exception:
        essay.original_file.delete(save=False)
        essay.delete()
        notifications_utils.prepare_feature_error_notification(
            essay.author.id,
            "CouldNotExtractText",
            essay.essay_topic.id,
        ).send_sync()

        raise


@shared_task(ignore_result=False)  # false, because it's part of a chord
def task_extract_text_pen_to_print(essay_id: int):
    extract_text_pen_to_print(essay_id)


def mock_call_extract_openai(file_like) -> str:
    logger.debug(f"Mocked call to openai for file {file_like}")
    return f"This is a mock text extracted from the file {file_like} by OpenAI"


def encode_image(image_file):
    return base64.b64encode(image_file.read()).decode("utf-8")


def call_extract_openai(file_like) -> str:
    base64_image = encode_image(file_like)
    response = openai_utils.get_completion(
        EXTRACT_OPENAI_MODEL,
        0,
        [
            {"role": "system", "content": EXTRACT_OPENAI_SYSTEM_MESSAGE},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Essa é minha foto:"},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{base64_image}",
                            "detail": "high",
                        },
                    },
                ],
            },
        ],
        json_mode=False,
        timeout=EXTRACT_OPENAI_TIMEOUT,
    ).content
    if response == "Não aplicável.":
        raise CouldNotExtractTextError
    return response


def extract_text_openai(essay_id: int):
    try:
        essay = Essay.objects.get(id=essay_id)
        extracted_text = call_extract_openai(essay.original_file.file)

        ExtractedText.objects.create(
            essay_id=essay_id,
            text=extracted_text,
            extraction_method=EXTRACT_OPENAI_EXTRACTION_METHOD,
        )
    except Exception:
        essay.original_file.delete(save=False)
        essay.delete()
        notifications_utils.prepare_feature_error_notification(
            essay.author.id,
            "CouldNotExtractText",
            essay.essay_topic.id,
        ).send_sync()
        fcm_service.send_notification(
            essay.author.id,
            "Desculpe! Não conseguimos extrair o texto da redação!",
            f"Desculpe, tente usar uma nova imagem para a redação {essay.essay_topic.name}",
        )
        raise


@shared_task
def task_extract_text_openai(essay_id: int):
    extract_text_openai(essay_id)


def clean_text_by_llm(essay_id: int):
    try:
        essay = Essay.objects.select_related("essay_topic").get(id=essay_id)
    except Essay.DoesNotExist:  # its because i deleted the essay on a previous step
        logger.debug(f"Essay {essay_id} does not exist. Ignoring.")
        raise celery_exceptions.Ignore

    extracted_texts = list(
        ExtractedText.objects.filter(essay_id=essay_id).values_list("text", flat=True)
    )
    if len(extracted_texts) == 0:
        raise CouldNotCleanTextError

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
                "content": clean_text_user_message(extracted_texts),
            },
        ],
        json_mode=False,
        timeout=CLEAN_TEXT_TIMEOUT,
    ).content
    if chatbot_response == "Não aplicável.":
        essay.original_file.delete(save=False)
        essay.delete()
        notifications_utils.prepare_feature_error_notification(
            essay.author.id,
            "CouldNotCleanText",
            essay.essay_topic.id,
        ).send_sync()
        raise CouldNotCleanTextError
    else:
        essay.cleaned_text = chatbot_response
        essay.save()


@shared_task
def task_clean_text_by_llm(essay_id: int):
    clean_text_by_llm(essay_id)


@shared_task
def task_finalize_extract_and_clean(essay_id: int):
    try:
        essay = Essay.objects.select_related("essay_topic", "author").get(id=essay_id)
    except Essay.DoesNotExist:  # its because i deleted the essay on a previous step
        logger.debug(f"Essay {essay_id} does not exist. Ignoring.")
        raise celery_exceptions.Ignore

    notifications_utils.prepare_cleaned_text_notification(
        essay.author.id,
        essay.essay_topic.id,
        essay.cleaned_text,
        essay.essay_topic.name,
    ).send_sync()

    logger.debug(f"Finished extract_and_clean_workflow for essay {essay_id}")


@shared_task(ignore_result=False)
def task_compress_essay_image(essay_id: int):
    essay = Essay.objects.get(id=essay_id)
    logger.debug(
        f"Compressing essay image for essay {essay_id} using tinify. Size before: {essay.original_file.file.size}"
    )
    buffer = file_utils.call_tinify(essay.original_file.url)
    file_name = os.path.basename(essay.original_file.file.name)
    essay.original_file.save(file_name, ContentFile(buffer))
    logger.debug(
        f"Compressed essay image for essay {essay_id} using tinify. Size after: {essay.original_file.file.size}"
    )


def extract_and_clean_workflow(
    essay_id: int, compress_image: bool, is_async: bool = False
):
    if compress_image:
        workflow = celery_chain(
            task_compress_essay_image.si(essay_id),
            celery_chord(
                [
                    task_extract_text_amazon_textract.si(essay_id),
                    task_extract_text_pen_to_print.si(essay_id),
                ],
                celery_chain(
                    task_clean_text_by_llm.si(essay_id),
                    task_finalize_extract_and_clean.si(essay_id),
                ),
            ),
        )
    else:
        workflow = celery_chord(
            [
                task_extract_text_amazon_textract.si(essay_id),
                task_extract_text_pen_to_print.si(essay_id),
            ],
            celery_chain(
                task_clean_text_by_llm.si(essay_id),
                task_finalize_extract_and_clean.si(essay_id),
            ),
        )

    workflow.apply_async().forget()
    workflow_type = "async" if is_async else "sync"
    logger.debug(
        f"Started extract_and_clean_{workflow_type}_workflow for essay {essay_id}"
    )


def extract_and_clean_sync_workflow(essay_id: int, compress_image: bool):
    extract_and_clean_workflow(essay_id, compress_image)


@celery_async_workflow
def extract_and_clean_async_workflow(essay_id: int, compress_image: bool):
    extract_and_clean_workflow(essay_id, compress_image, is_async=True)


@shared_task(ignore_result=False)  # false because its part of a chord
def task_essay_feedback(essay_id: int, feedback_category_id: int):
    user_corrected_text = Essay.objects.values_list(
        "user_corrected_text", flat=True
    ).get(id=essay_id)
    feedback_category = FeedbackCategory.objects.values(
        "prompt_template", "temperature"
    ).get(id=feedback_category_id)
    response_dict = openai_utils.get_feedback(
        feedback_category["prompt_template"],
        user_corrected_text,
        feedback_category["temperature"],
    )
    feedback = response_dict["feedback"]
    grade = response_dict["grade"]
    Feedback.objects.create(
        essay_id=essay_id,
        feedback_category_id=feedback_category_id,
        text=feedback,
        grade=grade,
    )
    logger.info(
        f"Saved feedback {feedback_category_id} with text '{feedback}' and grade '{grade}' on essay {essay_id}"
    )


@shared_task
def task_finalize_feedback(essay_id: int):
    essay = (
        Essay.objects.select_related("essay_topic", "author", "essay_type")
        .prefetch_related("feedbacks")
        .get(id=essay_id)
    )

    feedbacks = list(Feedback.objects.filter(essay_id=essay_id))

    notifications_utils.prepare_essay_correction_notification(
        essay.author.id,
        essay.essay_topic.id,
        [feedback.text for feedback in feedbacks],
        [float(feedback.grade) for feedback in feedbacks],
        essay.essay_topic.name,
    ).send_sync()
    logger.debug(f"Finished task_finalize_feedback for essay {essay_id}")


def correct_essay(essay_id: int):
    feedback_categories = FeedbackCategory.objects.filter(
        essay_type__essays__id=essay_id
    ).values_list("id", flat=True)
    feedback_tasks = [
        task_essay_feedback.si(essay_id, feedback_category_id)
        for feedback_category_id in feedback_categories
    ]

    workflow = celery_chord(feedback_tasks, task_finalize_feedback.si(essay_id))

    workflow.apply_async().forget()


@celery_async_workflow
def correct_essay_async_workflow(essay_id: int):
    correct_essay(essay_id)
    logger.debug(f"Started correct_essay_async_workflow for essay {essay_id}")


def correct_essay_sync_workflow(essay_id: int):
    correct_essay(essay_id)
    logger.debug(f"Started correct_essay_sync_workflow for essay {essay_id}")

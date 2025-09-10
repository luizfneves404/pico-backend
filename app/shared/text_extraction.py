import logging
from typing import IO, ClassVar, Protocol

import httpx
from textractor import Textractor
from textractor.data.constants import (
    TextractAPI,
)
from textractor.entities.bbox import BoundingBox
from textractor.entities.document import Document, Line, Page, Word
from textractor.entities.lazy_document import LazyDocument

from app.config import Environment, settings
from app.shared.constants import (
    PEN_TO_PRINT_RAPIDAPI_HOST,
    PEN_TO_PRINT_RAPIDAPI_SESSION,
    PEN_TO_PRINT_RAPIDAPI_URL,
)

logger = logging.getLogger(__name__)


class CouldNotExtractTextError(Exception):
    pass


class ContentTooBigForPenToPrintError(Exception):
    pass


class PenToPrintError(Exception):
    pass


class DummyTextractor:
    # Class-level shared memory to store job results
    _job_results: ClassVar[dict[str, dict[str, str]]] = {}

    def _build_document(self, file_source: str) -> Document:
        document = Document(num_pages=1)
        page = Page(id="1", width=100, height=100, page_num=1)
        line = Line(
            entity_id="1",
            bbox=BoundingBox(x=0, y=0, width=100, height=100),
            words=[
                Word(
                    entity_id="1",
                    bbox=BoundingBox(x=0, y=0, width=100, height=100),
                    text=f"Dummy text extracted from {file_source}",
                )
            ],
        )
        page.lines = [line]
        document.pages = [page]
        return document

    def detect_document_text(
        self, file_source: str, _save_image: bool = True
    ) -> Document:
        logger.info(f"[DUMMY] Would extract text from {file_source}")
        return self._build_document(file_source)

    def start_document_text_detection(
        self,
        file_source: str,
        _s3_output_path: str,
        _s3_upload_path: str,
        _client_request_token: str,
        job_tag: str,
        _save_image: bool = True,
    ):
        logger.info(f"[DUMMY] Would start document text detection for {file_source}")
        job_id = f"Dummy job id for {file_source}"
        # Store some result data for this job
        self._job_results[job_id] = {
            "file_source": file_source,
            "text": f"Dummy text for job {job_id}",
            "job_tag": job_tag,
        }
        return LazyDocument(job_id=job_id, api=TextractAPI.DETECT_TEXT)

    def get_result(self, job_id: str, _: TextractAPI):
        logger.info(f"[DUMMY] Would get result for job {job_id}")
        # Retrieve the stored result or use a default if not found
        job_data = self._job_results.get(
            job_id, {"text": f"Default text for unknown job {job_id}"}
        )
        return self._build_document(job_data["file_source"])


class TextractorProtocol(Protocol):
    def detect_document_text(
        self, file_source: str, save_image: bool = True
    ) -> Document: ...

    def start_document_text_detection(
        self,
        file_source: str,
        s3_output_path: str,
        s3_upload_path: str,
        client_request_token: str,
        job_tag: str,
        save_image: bool = True,
    ) -> LazyDocument: ...

    def get_result(self, job_id: str, api: TextractAPI) -> Document: ...


if settings.environment == Environment.PROD:
    textractor: TextractorProtocol = Textractor(
        region_name=settings.textract_region_name
    )
else:
    textractor: TextractorProtocol = DummyTextractor()


def call_amazon_textract_api(filepath: str) -> str:
    logger.debug(f"Calling amazon textract api for file {filepath}")
    response = textractor.detect_document_text(filepath)
    extracted_text = response.text
    logger.debug(
        f"From amazon textract api call for file {filepath}, "
        f"received: '{extracted_text}'"
    )
    return extracted_text


def call_amazon_textract_api_start_detection_s3(pdf_s3_path: str) -> str:
    """
    Inicia o job do Textract para um PDF já armazenado no S3.

    :param pdf_s3_path: Caminho 's3://bucket/prefix/arquivo.pdf'
    :return: O JobId retornado pelo Textract
    """
    logger.debug(f"Calling Amazon Textract API for S3 file {pdf_s3_path}")

    response = textractor.start_document_text_detection(
        file_source=pdf_s3_path,
        s3_output_path="",  # Prefixo para outputs, se quiser
        s3_upload_path="",  # Já está no S3, então não precisamos de upload
        client_request_token="",  # Ex: use algo se quiser reusar a mesma JobId
        job_tag="MeuJobDeTexto",  # Tag customizada
        save_image=False,  # Em PDFs de múltiplas páginas, normalmente
        # não precisamos das imagens
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

    doc = textractor.get_result(job_id, TextractAPI.DETECT_TEXT)
    page_texts = [page.text for page in doc.pages]

    if not page_texts:
        raise ValueError(f"No text found in job {job_id}")

    logger.debug(f"Retrieved text from job {job_id}: '{page_texts}'")
    return page_texts


async def mock_call_pen_to_print_api(file_like: IO[bytes]) -> str:
    logger.debug(f"Mocked call to pen to print api for file {file_like}")
    return f"This is a mock text extracted from the file {file_like} by Pen to Print"


async def call_pen_to_print_api(file_like: IO[bytes]) -> str:
    """Extracts text from handwritten content using the Pen to Print API.

    Args:
        file_like: The file object or URL containing the handwritten content.

    Returns:
        str: The extracted text.

    Raises:
        ContentTooBigForPenToPrintError: If the image is too large for processing.
        PenToPrintError: If the API returns an error.
        httpx.HTTPError: If the API request fails.
    """
    logger.debug(f"Calling Pen to Print API for file {file_like}")

    # Prepare the multipart form data
    files = {"srcImg": file_like}
    data = {"Session": PEN_TO_PRINT_RAPIDAPI_SESSION}
    headers = {
        "X-RapidAPI-Key": settings.pen_to_print_rapidapi_key,
        "X-RapidAPI-Host": PEN_TO_PRINT_RAPIDAPI_HOST,
    }

    # Make the API request
    async with httpx.AsyncClient() as client:
        response = await client.post(
            PEN_TO_PRINT_RAPIDAPI_URL,
            data=data,
            files=files,
            headers=headers,
        )

        if response.status_code == 413:
            logger.error("Content too big for Pen to Print API")
            raise ContentTooBigForPenToPrintError()

        # Process the response
        try:
            response_json = response.json()
        except Exception:
            logger.exception("Failed to parse JSON response")
            response.raise_for_status()
            raise

        logger.debug(f"Response from Pen to Print API: {response_json}")

        if "error" in response_json:
            logger.error(f"Pen to Print API error: {response_json['error']}")
            raise PenToPrintError(response_json["error"])

        response.raise_for_status()
        extracted_text = response_json["value"]

        logger.debug("Successfully extracted text from handwritten content")
        return extracted_text


class PenToPrintProtocol(Protocol):
    async def __call__(self, file_like: IO[bytes]) -> str: ...


pen_to_print_api: PenToPrintProtocol = (
    call_pen_to_print_api
    if settings.environment == Environment.PROD
    else mock_call_pen_to_print_api
)


""" def encode_image(image_file: IO[bytes]) -> str:
    return base64.b64encode(image_file.read()).decode("utf-8")


async def call_extract_openai(file_like: IO[bytes]) -> str:
    base64_image = encode_image(file_like)
    response = await openai_utils.get_completion(
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
    )
    content = response.content
    if content == "Não aplicável.":
        raise CouldNotExtractTextError
    return content


async def extract_text_openai(essay: Essay):
    try:
        extracted_text = await call_extract_openai(essay.original_file.file)
        essay.text = extracted_text

    except Exception:
        essay.original_file.delete()
        essay.delete()
        notifications_utils.prepare_feature_error_notification(
            essay.author.id,
            "CouldNotExtractText",
            essay.essay_topic.id,
        ).send_sync()
        fcm_service.send_notification(
            essay.author.id,
            "Desculpe! Não conseguimos extrair o texto da redação!",
            f"Desculpe, tente usar uma nova imagem para a redação
            {essay.essay_topic.name}",
        )
        raise
"""

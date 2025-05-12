import asyncio
import logging
from urllib.parse import unquote

from asgiref.sync import sync_to_async
from essays.tasks import (
    call_amazon_textract_api_start_detection_s3,
    get_textract_job_results,
)
from ninja.files import UploadedFile
from pylatexenc.latex2text import LatexNodes2Text
from quiz.question_service import FILES_PER_BLOCK
from shared import file_utils, openai_utils

logger = logging.getLogger(__name__)

S3_BUCKET_PREFIX = "https://pico-backend-us-east-1.s3.amazonaws.com/"
S3_BUCKET_NAME = "pico-backend-us-east-1"

VALID_MIME_TYPES_FOR_TRANSCRIPTION = [
    "image/jpeg",
    "image/png",
    "image/jpg",
    "application/pdf",
]


async def generate_transcription(files: list[UploadedFile]) -> list[str]:
    """
    Process uploaded images and generate descriptions asynchronously.
    Returns a list of description blocks, with each block containing up to 5 image descriptions.
    """
    if not files:
        raise ValueError(
            "No files provided for transcription. At least one file is required."
        )

    if not all(
        file.content_type in VALID_MIME_TYPES_FOR_TRANSCRIPTION for file in files
    ):
        raise ValueError(
            "Invalid file type. Only JPEG, PNG, JPG, and PDF files are supported."
        )

    # Separate files by type
    image_files = [f for f in files if f.content_type != "application/pdf"]
    pdf_files = [f for f in files if f.content_type == "application/pdf"]

    if image_files and pdf_files:
        raise ValueError("Cannot process both image and PDF files at the same time")

    if len(pdf_files) > 1:
        raise ValueError("Cannot process more than one PDF file")

    # Process images: upload to S3 and use OpenAI
    image_descriptions = []
    if image_files:
        uploaded_urls = await asyncio.gather(
            *(file_utils.upload_file_as_temp(file) for file in image_files)
        )
        image_results = await asyncio.gather(
            *(openai_utils.transcribe_image(url) for url in uploaded_urls)
        )
        image_descriptions.extend(image_results)

    elif pdf_files:
        # 1) Uploads each PDF file to S3 and gets the URL (currently only one PDF is supported)
        uploaded_urls = await asyncio.gather(
            *(
                file_utils.upload_file_as_temp(file, storage_name="us_east_1")
                for file in pdf_files
            )
        )

        # 2) Converts the URL to an S3 path (ex: s3://bucket/....)
        s3_paths = [convert_url_to_s3_path(url) for url in uploaded_urls]

        # 3) Starts the Textract jobs (async with sync_to_async)
        start_detection_s3 = sync_to_async(call_amazon_textract_api_start_detection_s3)
        job_ids = await asyncio.gather(
            *(start_detection_s3(s3_path) for s3_path in s3_paths)
        )

        # 4) Retrieves the results
        get_results = sync_to_async(get_textract_job_results)
        pdf_results = await asyncio.gather(*(get_results(job_id) for job_id in job_ids))

        for pages in pdf_results:
            image_descriptions.extend(pages)

    # Group descriptions into blocks of FILES_PER_BLOCK
    description_blocks = []
    for i in range(0, len(image_descriptions), FILES_PER_BLOCK):
        block = image_descriptions[i : i + FILES_PER_BLOCK]
        # Clean LaTeX from each description before joining
        cleaned_block = [
            LatexNodes2Text().latex_to_text(desc) for desc in block if desc
        ]
        block_text = "\n\n".join(cleaned_block)
        if block_text:
            logger.info(f"Block combined text: {block_text}")
            description_blocks.append(block_text)

    if not description_blocks:
        raise ValueError("No descriptions generated")

    return description_blocks


def convert_url_to_s3_path(http_url: str) -> str:
    if not http_url.startswith(S3_BUCKET_PREFIX):
        raise ValueError(
            f"Invalid URL: {http_url} does not start with {S3_BUCKET_PREFIX}"
        )

    # 1) Remove any query string after '?'
    url_without_query = http_url.split("?")[0]

    # 2) Remove the HTTP prefix (https://bucket-name.s3.amazonaws.com/)
    path_without_prefix = url_without_query.replace(S3_BUCKET_PREFIX, "")

    # 3) Decode any percent-encoded spaces, etc.
    decoded_path = unquote(path_without_prefix)

    # 4) Build the correct s3://... URI
    return f"s3://{S3_BUCKET_NAME}/{decoded_path}"

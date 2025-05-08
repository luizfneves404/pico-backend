import base64
import logging
from uuid import uuid4

import httpx
from fastapi import UploadFile
from magic import from_buffer

from app.config import settings

logger = logging.getLogger(__name__)


async def get_mime_type(file: UploadFile) -> str:
    chunk = await file.read(2048)
    mime_type: str = from_buffer(chunk, mime=True)
    await file.seek(0)
    return mime_type


async def upload_file_as_temp(file: UploadFile, storage_name: str = "default") -> str:
    """
    Upload the file to the default storage and return its URL.
    """
    file_name = f"temp/{uuid4().hex}_{file.filename}"
    logger.debug(f"Uploading file {file.filename} as {file_name}")
    saved_path = await storages[storage_name].save(file_name, file)
    logger.info(f"File {file.name} uploaded to {saved_path}")
    logger.debug(f"Getting URL for {file_name}")
    url = await storages[storage_name].url(saved_path)
    logger.info(f"URL for {file_name} is {url}")
    return url


async def _call_tinify_api(file_url: str) -> bytes:
    """Internal function that handles the actual Tinify API call.

    Args:
        file_url: URL of the file to compress.

    Returns:
        bytes: The compressed image data.

    Raises:
        httpx.HTTPError: If the API request fails.
    """
    # Create auth header using API key
    auth = base64.b64encode(f"api:{settings.tinify_api_key}".encode()).decode()
    headers = {"Authorization": f"Basic {auth}", "Content-Type": "application/json"}

    async with httpx.AsyncClient() as client:
        # Request compression
        compress_response = await client.post(
            "https://api.tinify.com/shrink",
            headers=headers,
            json={"source": {"url": file_url}},
        )
        compress_response.raise_for_status()

        # Get URL for compressed image
        compressed_url = compress_response.headers["Location"]

        # Download compressed image
        download_response = await client.get(
            compressed_url, headers={"Authorization": f"Basic {auth}"}
        )
        download_response.raise_for_status()

        compressed_content = download_response.content

        logger.debug(
            f"Successfully compressed file {file_url}. "
            f"Original size: {compress_response.json()['input']['size']} bytes, "
            f"Compressed size: {len(compressed_content)} bytes"
        )

        return compressed_content


async def call_tinify(file_url: str) -> bytes:
    """Compresses an image using the Tinify API via HTTP requests.

    Args:
        file_url: URL of the file to compress.

    Returns:
        bytes: The compressed image data.

    Raises:
        httpx.HTTPError: If the API request fails.
    """
    logger.debug(f"Calling tinify API for file {file_url}")
    return await _call_tinify_api(file_url)


async def mock_call_tinify_api(file_url: str) -> bytes:
    async with httpx.AsyncClient() as client:
        response = await client.get(file_url)
        response.raise_for_status()

        logger.debug(
            f"Successfully compressed file {file_url}. "
            f"Original size: {response.headers['Content-Length']} bytes, "
            f"Compressed size: {len(response.content)} bytes"
        )

        return response.content

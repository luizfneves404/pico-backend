import logging
from uuid import uuid4

from asgiref.sync import sync_to_async
from django.core.files import File as DjangoFile
from django.core.files.storage import storages
from magic import from_buffer

logger = logging.getLogger(__name__)


def get_mime_type(file: DjangoFile) -> str:
    chunk = next(file.chunks(2048))
    mime_type = from_buffer(chunk, mime=True)
    file.seek(0)
    return mime_type


async def upload_file_as_temp(file: DjangoFile, storage_name: str = "default") -> str:
    """
    Upload the file to the default storage and return its URL.
    """
    file_name = f"temp/{uuid4().hex}_{file.name}"
    logger.debug(f"Uploading file {file.name} as {file_name}")
    saved_path = await sync_to_async(storages[storage_name].save)(file_name, file)
    logger.info(f"File {file.name} uploaded to {saved_path}")
    logger.debug(f"Getting URL for {file_name}")
    url = await sync_to_async(storages[storage_name].url)(saved_path)
    logger.info(f"URL for {file_name} is {url}")
    return url

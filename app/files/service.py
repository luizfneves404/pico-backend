import asyncio
import logging
from typing import Iterable

from fastapi import UploadFile
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.base import register_rollback_action
from app.files.models import File
from app.files.storage import storage

logger = logging.getLogger(__name__)


async def create_files(
    db_session: AsyncSession, upload_files: list[UploadFile]
) -> list[File]:
    """Upload multiple files to storage and create File records.

    Args:
        db_session: The database session to use
        upload_files: The files to upload

    Returns:
        list[File]: The created file records

    Raises:
        ValueError: If any upload_file has no filename or size
    """
    created_files: list[File] = []
    uploaded_file_ids: list[str] = []

    for upload_file in upload_files:
        if upload_file.filename is None:
            raise ValueError("File name is required")

        file_id = await run_in_threadpool(
            storage.upload,
            upload_file.file,
            upload_file.filename,
        )
        uploaded_file_ids.append(file_id)

        file = File(
            file_id=file_id,
            original_name=upload_file.filename,
            size=upload_file.size,
        )
        db_session.add(file)
        created_files.append(file)

    # Set up rollback cleanup for all uploaded files
    def rollback_cleanup():
        for file_id in uploaded_file_ids:
            storage.delete(file_id)

    register_rollback_action(db_session, rollback_cleanup)
    return created_files


async def create_file(db_session: AsyncSession, upload_file: UploadFile) -> File:
    """Upload a file to storage and create a new File record.

    Args:
        db_session: The database session to use
        upload_file: The file to upload

    Returns:
        File: The created file record

    Raises:
        ValueError: If the upload_file has no filename
    """
    files = await create_files(db_session, [upload_file])
    return files[0]


async def pks_to_urls(db_session: AsyncSession, pks: Iterable[int]) -> dict[int, str]:
    """Get the file URLs for a list of primary keys.

    Args:
        db_session: The database session to use
        pks: The primary keys to get the file URLs for
    """
    files = list(await db_session.scalars(select(File).where(File.id.in_(pks))))
    urls = await asyncio.gather(*[file.get_url() for file in files])
    return {file.id: url for file, url in zip(files, urls)}

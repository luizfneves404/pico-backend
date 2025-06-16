from fastapi import UploadFile
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.ext.asyncio import AsyncSession

from app.base import (
    register_rollback_action,
)
from app.files.models import File
from app.files.storage import storage


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
    if upload_file.filename is None or upload_file.size is None:
        raise ValueError("File name and size are required")

    file_id = await run_in_threadpool(
        storage.upload,
        upload_file.file,
        upload_file.filename,
    )

    file = File(
        file_id=file_id,
        original_name=upload_file.filename,
        size=upload_file.size,
    )
    db_session.add(file)

    def rollback_cleanup():
        storage.delete(file_id)

    register_rollback_action(db_session, rollback_cleanup)
    return file

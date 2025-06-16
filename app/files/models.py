from contextlib import asynccontextmanager
from typing import IO, AsyncGenerator

from fastapi import UploadFile
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import String
from sqlalchemy.ext.asyncio import AsyncSession, async_object_session
from sqlalchemy.orm import Mapped, mapped_column

from app.base import (
    Base,
    auto_now_update_timestamp,
    register_rollback_action,
)
from app.files.storage import storage


class File(Base, kw_only=True):
    """Represents a file stored in the system.

    The file_id is a unique identifier that can be used to reference the file
    in the storage backend. The actual storage location and implementation
    details are abstracted away by the storage backend.
    """

    file_id: Mapped[str] = mapped_column(String(length=255), unique=True)
    original_name: Mapped[str] = mapped_column(String(length=255))
    updated_at: Mapped[auto_now_update_timestamp] = mapped_column(init=False)
    size: Mapped[int] = mapped_column()

    def __str__(self) -> str:
        return self.original_name

    @property
    def url(self) -> str:
        return storage.get_url(self.file_id)

    @asynccontextmanager
    async def get_file_like(self) -> AsyncGenerator[IO[bytes], None]:
        file_like = await run_in_threadpool(storage.get_file_like, self.file_id)
        try:
            yield file_like
        finally:
            file_like.close()

    async def update_file_content(
        self, file_obj_or_path: IO[bytes] | str, size: int
    ) -> None:
        """Update the file content in storage and update the file record.

        Args:
            file_obj_or_path: The new file content as bytes or file path
            db_session: The database session to use for saving changes

        This method:
        1. Uploads the new content to storage
        2. Updates the file record with the new file_id and size
        3. Handles cleanup of the old file in case of errors
        """
        db_session = async_object_session(self)
        if db_session is None:
            raise ValueError("File is not associated with a database session")

        old_file_id = self.file_id

        # Upload new content
        new_file_id = await run_in_threadpool(
            storage.upload, file_obj_or_path, self.original_name
        )

        # Update record
        self.file_id = new_file_id
        self.size = size
        await db_session.flush()

        # Clean up old file
        def rollback_cleanup():
            storage.delete(new_file_id)

        register_rollback_action(db_session, rollback_cleanup)

        # Delete old file after successful update
        await run_in_threadpool(storage.delete, old_file_id)

    async def delete(self):
        db_session = async_object_session(self)
        if db_session is None:
            raise RuntimeError("No session is available for this instance.")

        await db_session.delete(self)

        await run_in_threadpool(storage.delete, self.file_id)


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
    if upload_file.filename is None:
        raise ValueError("File name is required")

    file_id = await run_in_threadpool(
        storage.upload,
        upload_file.file,
        upload_file.filename,
    )
    if not upload_file.size:
        raise ValueError("File size somehow is None")

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

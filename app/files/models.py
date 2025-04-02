from typing import IO

from fastapi.concurrency import run_in_threadpool
from sqlalchemy import String
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.base import (
    Base,
    auto_now_update_timestamp,
    register_rollback_action,
)
from app.config import settings
from app.files.storage import delete_from_s3, get_presigned_url, upload_to_s3


class File(Base):
    key: Mapped[str] = mapped_column(String(length=255))
    updated_at: Mapped[auto_now_update_timestamp]

    async def get_url(self) -> str:
        """Get the presigned URL for the file, based on the key."""
        return await run_in_threadpool(
            get_presigned_url,
            settings.aws_s3_storage_bucket_name,
            self.key,
        )


async def create_file(db_session: AsyncSession, file_like: IO) -> File:
    """Upload a file to S3 and create a new File record."""
    file_key = await run_in_threadpool(
        upload_to_s3,
        file_like,
        settings.aws_s3_storage_bucket_name,
    )
    file = File(key=file_key)
    db_session.add(file)

    def rollback_cleanup():
        delete_from_s3(file_key)

    register_rollback_action(db_session, rollback_cleanup)
    return file

import logging
import shutil
import uuid
from abc import ABC, abstractmethod
from pathlib import Path
from typing import IO

import boto3

from app.config import S3Config, settings

logger = logging.getLogger(__name__)


class StorageBackend(ABC):
    """Abstract base class for storage backends.

    This class defines the interface that all storage backends must implement.
    """

    @abstractmethod
    def upload(self, file_obj_or_path: IO[bytes] | str, file_name: str) -> str:
        """Upload a file to storage.

        Args:
            file_obj_or_path: The file object or file path to upload
            file_name: The name to give the file in storage

        Returns:
            str: A unique identifier for the uploaded file
        """
        pass

    @abstractmethod
    def delete(self, file_id: str) -> None:
        """Delete a file from storage.

        Args:
            file_id: The unique identifier of the file to delete
        """
        pass

    @abstractmethod
    def get_url(self, file_id: str, expiration: int = 3600) -> str:
        """Get a URL to access a file. Can be a blocking method.

        Args:
            file_id: The unique identifier of the file
            expiration: How long the URL should be valid for in seconds

        Returns:
            str: A URL that can be used to access the file
        """
        pass

    @abstractmethod
    def get_file_like(self, file_id: str) -> IO[bytes]:
        """Get a file-like object for reading.

        Args:
            file_id: The unique identifier of the file

        Returns:
            IO[bytes]: A file-like object that can be used to read the file
        """
        pass


class S3Storage(StorageBackend):
    """S3 implementation of the storage backend."""

    def __init__(self, bucket_name: str):
        self.bucket_name = bucket_name
        self.client = boto3.client("s3")  # pyright: ignore[reportUnknownMemberType]

    def upload(self, file_obj_or_path: IO[bytes] | str, file_name: str) -> str:
        file_id = f"{uuid.uuid4()}-{file_name}"
        if isinstance(file_obj_or_path, str):
            self.client.upload_file(file_obj_or_path, self.bucket_name, file_id)
        else:
            file_obj_or_path.seek(0)
            self.client.upload_fileobj(file_obj_or_path, self.bucket_name, file_id)

        logger.info("Uploaded file to S3 storage")
        return file_id

    def delete(self, file_id: str) -> None:
        self.client.delete_object(Bucket=self.bucket_name, Key=file_id)
        logger.info("Deleted file from S3 storage")

    def get_url(self, file_id: str, expiration: int = 3600) -> str:
        return self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket_name, "Key": file_id},
            ExpiresIn=expiration,
        )

    def get_file_like(self, file_id: str) -> IO[bytes]:
        response = self.client.get_object(Bucket=self.bucket_name, Key=file_id)
        return response["Body"]  # pyright: ignore[reportReturnType]


class LocalStorage(StorageBackend):
    """Local filesystem implementation of the storage backend."""

    def __init__(self, storage_dir: str | Path):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def upload(self, file_obj_or_path: IO[bytes] | str, file_name: str) -> str:
        file_id = f"{uuid.uuid4()}-{file_name}"
        file_path = self.storage_dir / file_id

        if isinstance(file_obj_or_path, str):
            shutil.copyfile(file_obj_or_path, file_path)
        else:
            with open(file_path, "wb") as f:
                shutil.copyfileobj(file_obj_or_path, f)

        logger.info("Uploaded file to local storage")
        return file_id

    def delete(self, file_id: str) -> None:
        file_path = self.storage_dir / file_id
        if file_path.exists():
            file_path.unlink()
            logger.info("Deleted file from local storage")

    def get_url(self, file_id: str, expiration: int = 3600) -> str:
        file_path = self.storage_dir / file_id
        if not file_path.exists():
            raise FileNotFoundError(f"File {file_id} not found in storage")
        return f"/files/{file_id}"

    def get_file_like(self, file_id: str) -> IO[bytes]:
        """remember to close the file"""
        file_path = self.storage_dir / file_id
        if not file_path.exists():
            raise FileNotFoundError(f"File {file_id} not found in local storage")
        return open(file_path, "rb")


storage: StorageBackend

# Create storage instances based on configuration
if isinstance(settings.storage, S3Config):
    storage = S3Storage(bucket_name=settings.storage.bucket_name)
else:
    storage = LocalStorage(storage_dir=settings.storage.base_path)

import logging
import uuid
from typing import IO

import boto3
from config import settings

logger = logging.getLogger(__name__)


def upload_to_s3(file_obj: IO, bucket_name: str) -> str:
    s3 = boto3.client("s3")
    s3_key = f"{uuid.uuid4()}-{file_obj.name}"
    s3.upload_fileobj(file_obj, bucket_name, s3_key)
    logger.info("Uploaded file to S3")
    return s3_key


def delete_from_s3(s3_key: str):
    s3 = boto3.client("s3")
    s3.delete_object(Bucket=settings.aws_s3_storage_bucket_name, Key=s3_key)
    logger.info("Deleted file from S3")


def get_presigned_url(bucket_name: str, s3_key: str, expiration: int = 3600) -> str:
    s3 = boto3.client("s3")
    url = s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket_name, "Key": s3_key},
        ExpiresIn=expiration,
    )
    return url

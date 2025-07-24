import os
import sys
from datetime import timedelta
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, BeforeValidator, EmailStr, Field
from pydantic.networks import validate_email
from pydantic_settings import BaseSettings, SettingsConfigDict

# Grabbed from app.shared.validation.py, had to replicate here to avoid circular imports.


def validate_lowercase_email(value: EmailStr) -> EmailStr:
    email = validate_email(value)[1]
    return email.lower()


LowercaseEmailStr = Annotated[str, AfterValidator(validate_lowercase_email)]


class FirebaseJsonServiceKey(BaseModel):
    type: str
    project_id: str
    private_key_id: str
    private_key: str
    client_email: str
    client_id: str
    auth_uri: str
    token_uri: str
    auth_provider_x509_cert_url: str
    client_x509_cert_url: str
    universe_domain: str


class StorageBackend(StrEnum):
    """Enum for storage backend types."""

    S3 = "s3"
    LOCAL = "local"


class S3Config(BaseModel):
    """Configuration for AWS S3 storage backend."""

    backend: Literal[StorageBackend.S3] = StorageBackend.S3
    bucket_name: str = Field(description="Name of the S3 bucket to use for storage")
    region_name: str | None = Field(default=None, description="AWS region name")


class LocalConfig(BaseModel):
    """Configuration for local file storage backend."""

    backend: Literal[StorageBackend.LOCAL] = StorageBackend.LOCAL
    base_path: Path = Field(
        default=Path("storage"),
        description="Base path for local file storage, relative to app root",
    )


def seconds_to_timedelta(time_value: str | int | timedelta) -> timedelta:
    if isinstance(time_value, str):
        return timedelta(seconds=int(time_value))
    elif isinstance(time_value, int):
        return timedelta(seconds=time_value)
    else:
        return time_value


TimedeltaInSeconds = Annotated[timedelta, BeforeValidator(seconds_to_timedelta)]


class Environment(StrEnum):
    DEV = "dev"
    PROD = "prod"
    TEST = "test"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", extra="forbid", env_nested_delimiter="__"
    )
    app_root: Path = Path(__file__).parent.resolve()
    environment: Environment = Field(default=Environment.PROD)
    uvicorn_host: str = Field(default=...)
    uvicorn_port: int = 8000
    uvicorn_reload: bool = False
    uvicorn_timeout_keep_alive: int = 70
    admin_url: str = Field(default=...)
    openapi_url: str = Field(default=...)
    openapi_api_key: str = Field(default=...)
    mock_openai: bool = Field(default=...)
    mock_gemini: bool = Field(default=...)
    docs_url: str = Field(default=...)

    admin_names: list[str] = Field(default=...)
    admin_emails: list[LowercaseEmailStr] = Field(default=...)

    default_phone_number_country: str = "BR"

    secret_key: str = Field(default=...)
    jwt_access_expiration_delta: TimedeltaInSeconds = Field(
        default=timedelta(minutes=5)
    )
    jwt_refresh_expiration_delta: TimedeltaInSeconds = Field(
        default=timedelta(days=180)
    )
    jwt_access_expiration_delta_admin: TimedeltaInSeconds = Field(
        default=timedelta(hours=2)
    )
    jwt_refresh_expiration_delta_admin: TimedeltaInSeconds = Field(
        default=timedelta(days=180)
    )
    local_timezone: str = Field(default="America/Sao_Paulo")

    database_url: str = Field(default=...)

    redis_url: str = Field(default=...)

    aws_ses_region_name: str | None = None
    aws_ses_from_email: str = Field(default=...)

    textract_profile_name: str = Field(default="")
    textract_region_name: str = Field(default=...)

    aws_s3_region_name: str | None = None
    storage: S3Config | LocalConfig = Field(
        default_factory=LocalConfig,
        description="File storage configuration",
        discriminator="backend",
    )
    staticfiles_storage: S3Config | LocalConfig = Field(
        default_factory=LocalConfig,
        description="Static files storage configuration",
        discriminator="backend",
    )
    us_east_1_storage: S3Config | LocalConfig = Field(
        default_factory=LocalConfig,
        description="US East 1 storage configuration",
        discriminator="backend",
    )

    openai_api_key: str = Field(default=...)
    gemini_api_key: str = Field(default=...)

    branch_api_key: str = Field(default=...)
    branch_api_key_test: str = Field(default=...)

    tinify_api_key: str = Field(default=...)

    pen_to_print_rapidapi_key: str = Field(default=...)

    firebase_json_service_key: str = Field(default=...)
    fcm_dry_run: bool = Field(default=False)

    # Social authentication settings
    apple_app_id: str = Field(
        default=..., description="Apple app identifier for ID token verification"
    )

    google_client_id: str = Field(default=...)

    pagination_per_page: int = Field(
        default=20, ge=1, description="Number of items per page"
    )

    @property
    def firebase_service_key(self) -> FirebaseJsonServiceKey:
        cleaned = self.firebase_json_service_key.replace("\n", "\\n")
        return FirebaseJsonServiceKey.model_validate_json(cleaned)


if any("test" in arg for arg in sys.argv) or any("migrate" in arg for arg in sys.argv):
    os.environ["ENVIRONMENT"] = "test"

settings = Settings()

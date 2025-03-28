from datetime import timedelta
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="forbid")
    app_root: Path = Path(__file__).parent.resolve()

    default_phone_number_country: str = "BR"

    secret_key: str = Field(default=...)
    allowed_hosts: list[str] = Field(default=...)
    jwt_access_expiration_delta: timedelta = Field(default=timedelta(minutes=5))
    jwt_refresh_expiration_delta: timedelta = Field(default=timedelta(days=180))
    local_timezone: str = Field(default="America/Sao_Paulo")

    database_url: str = Field(default=...)

    redis_url: str = Field(default=...)

    aws_ses_region_name: str | None = None
    aws_ses_from_email: str = Field(default=...)

    aws_s3_storage_bucket_name: str = Field(default=...)

    uvicorn_host: str = Field(default=...)
    uvicorn_port: int = 8000
    uvicorn_reload: bool = False

    openai_api_key: str = Field(default=...)

    amplitude_track_events: bool = Field(default=True)
    amplitude_api_key: str = Field(default=...)
    amplitude_secret_key: str = Field(default=...)


settings = Settings()

from datetime import timedelta
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    secret_key: str = Field(default=...)
    debug: bool = False
    database_url: str = Field(default=...)
    default_phone_number_country: str = "BR"
    echo_sql: bool = False
    jwt_access_expiration_delta: timedelta = Field(default=timedelta(minutes=5))
    jwt_refresh_expiration_delta: timedelta = Field(default=timedelta(days=180))
    app_root: Path = Path(__file__).parent.resolve()

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()

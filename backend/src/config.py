from typing import Literal
from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    app_env: Literal["development", "demo", "simulation", "test"] = "development"
    operation_mode: Literal["advisory", "simulation"] = "advisory"
    postgres_db: str = "traffic"
    postgres_user: str = "traffic"
    postgres_password: SecretStr = SecretStr("")
    database_url: SecretStr | None = None
    archive_enabled: bool | None = None
    allowed_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    @model_validator(mode="after")
    def validate_db(self):
        if self.database_url:
            url = make_url(self.database_url.get_secret_value())
            if url.drivername != "postgresql+psycopg" and not (
                self.app_env == "test" and url.drivername == "sqlite"
            ):
                raise ValueError("PostgreSQL required outside tests")
        elif not self.postgres_password.get_secret_value():
            raise ValueError("POSTGRES_PASSWORD or DATABASE_URL required")
        return self

    @property
    def durable_archive(self) -> bool:
        return self.archive_enabled if self.archive_enabled is not None else self.app_env != "test"

    def db_url(self):
        if self.database_url:
            return make_url(self.database_url.get_secret_value())
        from sqlalchemy import URL
        return URL.create("postgresql+psycopg", username=self.postgres_user,
                          password=self.postgres_password.get_secret_value(),
                          host="postgres", port=5432, database=self.postgres_db)

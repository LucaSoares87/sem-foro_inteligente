from typing import Literal
from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    app_env: Literal["development", "demo", "simulation", "test", "production"] = "development"
    operation_mode: Literal["advisory", "simulation"] = "advisory"
    postgres_db: str = "traffic"
    postgres_user: str = "traffic"
    postgres_password: SecretStr = SecretStr("")
    database_url: SecretStr | None = None
    archive_enabled: bool | None = None
    video_sources_json: SecretStr = SecretStr('[]')
    video_root: str = './video'
    vision_model_json: SecretStr | None = None
    vision_model_root: str = './models'
    traffic_geometry_json: SecretStr = SecretStr('[]')
    intersection_registry_json: SecretStr = SecretStr('[]')
    allowed_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    auth_mode: Literal["disabled","proxy_headers"] = "disabled"
    auth_user_header: str = "x-si-user"
    auth_roles_header: str = "x-si-roles"
    audit_enabled: bool = True
    validation_evidence_json: SecretStr = SecretStr('[]')

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
        if self.app_env == "production":
            if self.auth_mode != "proxy_headers":
                raise ValueError("AUTH_MODE=proxy_headers required in production")
            origins = {x.strip() for x in self.allowed_origins.split(",") if x.strip()}
            if not origins or "*" in origins:
                raise ValueError("explicit ALLOWED_ORIGINS required in production")
            if not self.audit_enabled:
                raise ValueError("AUDIT_ENABLED=true required in production")
        for header in (self.auth_user_header,self.auth_roles_header):
            if not header or any(ch not in "abcdefghijklmnopqrstuvwxyz0123456789-" for ch in header.lower()):
                raise ValueError("invalid auth header name")
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

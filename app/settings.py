from functools import lru_cache
from urllib.parse import quote_plus

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    devflow_postgres_db: str = "devflow"
    devflow_postgres_user: str = "devflow"
    devflow_postgres_password: SecretStr
    devflow_postgres_host: str = "127.0.0.1"
    devflow_postgres_port: int = 5432
    devflow_github_webhook_secret: SecretStr | None = None
    devflow_jenkins_url: str = "http://127.0.0.1:8080"
    devflow_jenkins_username: str | None = None
    devflow_jenkins_api_token: SecretStr | None = None
    devflow_jenkins_job_name: str = "devflow-pipeline"
    devflow_pipeline_callback_token: SecretStr | None = None

    @property
    def database_url(self) -> str:
        user = quote_plus(self.devflow_postgres_user)
        password = quote_plus(self.devflow_postgres_password.get_secret_value())
        database = quote_plus(self.devflow_postgres_db)
        return (
            f"postgresql+psycopg://{user}:{password}"
            f"@{self.devflow_postgres_host}:"
            f"{self.devflow_postgres_port}/{database}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()

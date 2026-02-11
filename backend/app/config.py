from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    app_name: str = "Finitii"
    app_env: str = "development"
    debug: bool = False
    secret_key: str = "change-me-in-production"

    # Database
    database_url: str = "postgresql+asyncpg://finitii:finitii@localhost:5432/finitii"
    database_url_sync: str = "postgresql://finitii:finitii@localhost:5432/finitii"

    # Server
    host: str = "0.0.0.0"
    port: int = 8000

    # CORS — comma-separated origins (e.g. "https://app.yourdomain.com")
    cors_allow_origins: str = "http://localhost:3000"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_allow_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


settings = Settings()

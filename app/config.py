"""Application configuration loaded from environment / .env."""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    line_channel_access_token: str = ""
    line_channel_secret: str = ""

    turso_database_url: str = ""
    turso_auth_token: str = ""

    app_timezone: str = "Asia/Bangkok"

    # Optional LLM fallback for parsing free-form messages (OpenAI-compatible).
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""

    @property
    def database_url(self) -> str:
        """SQLAlchemy URL. Uses Turso in production, local SQLite otherwise."""
        if not self.turso_database_url:
            return "sqlite:///./data/expense.db"

        url = self.turso_database_url.strip()
        # Normalize libsql:// / https:// into the SQLAlchemy libsql dialect.
        if url.startswith("libsql://"):
            url = "sqlite+libsql://" + url[len("libsql://") :]
        elif url.startswith(("https://", "http://")):
            url = "sqlite+libsql://" + url.split("://", 1)[1]

        if "secure=" not in url:
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}secure=true"
        return url


settings = Settings()

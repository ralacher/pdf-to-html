"""
Centralised configuration via Pydantic Settings.

All environment variables are read once at import time and exposed through the
``settings`` singleton.  Other modules should do::

    from app.config import settings
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application-wide configuration backed by environment variables."""

    # ── Azure Storage ──────────────────────────────────────────────────────
    AZURE_STORAGE_CONNECTION_STRING: str = "UseDevelopmentStorage=true"

    # ── Azure Document Intelligence (OCR) ──────────────────────────────────
    DOCUMENT_INTELLIGENCE_ENDPOINT: str = ""
    DOCUMENT_INTELLIGENCE_KEY: str = ""

    # ── Blob containers ────────────────────────────────────────────────────
    OUTPUT_CONTAINER: str = "converted"
    INPUT_CONTAINER: str = "files"

    # ── Queue ──────────────────────────────────────────────────────────────
    QUEUE_NAME: str = "conversion-jobs"

    # ── Server ─────────────────────────────────────────────────────────────
    PORT: int = 8000
    WORKER_MODE: bool = False
    LOG_LEVEL: str = "INFO"

    # ── Azure Functions compatibility ──────────────────────────────────────
    # Support the legacy env-var names so the same .env works for both
    # Azure Functions and Container Apps deployments.
    AzureWebJobsStorage: str = ""
    AzureWebJobsStorage__accountName: str = ""

    @property
    def storage_connection_string(self) -> str:
        """Return the best available storage connection string."""
        return self.AZURE_STORAGE_CONNECTION_STRING or self.AzureWebJobsStorage or ""

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()

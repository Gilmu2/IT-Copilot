"""Load .env, validate required variables, and expose a single config object.

Supports OpenAI and Azure OpenAI. For Azure OpenAI set OPENAI_API_KEY (your Azure
API key) plus AZURE_OPENAI_ENDPOINT and optionally AZURE_OPENAI_API_VERSION.
"""

from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv
import os


class ConfigError(Exception):
    """Raised when required configuration is missing or invalid."""

    pass


@dataclass(frozen=True)
class AppConfig:
    """Application configuration from environment variables.

    For Azure OpenAI: set openai_api_key (Azure key), azure_openai_endpoint,
    and optionally azure_openai_api_version. Model name in the client is the
    Azure deployment name (e.g. gpt-4o-mini).
    """

    openai_api_key: str  # OpenAI API key or Azure OpenAI API key
    azure_openai_endpoint: str  # If set, client uses Azure OpenAI
    azure_openai_api_version: str
    azure_openai_deployment: str  # Azure deployment name (model name for standard OpenAI)
    azure_tenant_id: str
    azure_client_id: str
    azure_client_secret: str


_config: Optional[AppConfig] = None


def _getenv(key: str, default: str = "") -> str:
    """Get env var, stripped; default if missing."""
    return (os.environ.get(key) or default).strip()


def get_config() -> AppConfig:
    """Load .env, validate required vars, and return config. Cached after first call."""
    global _config
    if _config is not None:
        return _config

    load_dotenv()

    openai_api_key = _getenv("OPENAI_API_KEY") or _getenv("AZURE_OPENAI_API_KEY")
    if not openai_api_key:
        raise ConfigError(
            "OPENAI_API_KEY is missing or empty. Set it in .env "
            "(for Azure OpenAI use your Azure API key and set AZURE_OPENAI_ENDPOINT; "
            "see .env.example)."
        )

    _config = AppConfig(
        openai_api_key=openai_api_key,
        azure_openai_endpoint=_getenv("AZURE_OPENAI_ENDPOINT"),
        azure_openai_api_version=_getenv("AZURE_OPENAI_API_VERSION")
        or "2024-02-15-preview",
        azure_openai_deployment=_getenv("AZURE_OPENAI_DEPLOYMENT") or "gpt-4o-mini",
        azure_tenant_id=_getenv("AZURE_TENANT_ID"),
        azure_client_id=_getenv("AZURE_CLIENT_ID"),
        azure_client_secret=_getenv("AZURE_CLIENT_SECRET"),
    )
    return _config

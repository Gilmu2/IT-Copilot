"""Chat completions client for OpenAI or Azure OpenAI.

Uses Azure OpenAI when AZURE_OPENAI_ENDPOINT is set in config; otherwise uses
the standard OpenAI API. Model argument is the deployment name when using Azure.
"""

from typing import Optional

from openai import AzureOpenAI, OpenAI

from app.config import get_config


class OpenAIClientError(Exception):
    """Raised when an OpenAI or Azure OpenAI request fails. No secrets in message."""

    pass


class OpenAIClient:
    """Chat completions: Azure OpenAI if endpoint configured, else OpenAI."""

    def __init__(self, model: Optional[str] = None) -> None:
        """Initialize from config. model is deployment name for Azure (default gpt-4o-mini)."""
        config = get_config()
        self._model = model if model is not None else config.azure_openai_deployment

        if config.azure_openai_endpoint:
            self._client = AzureOpenAI(
                api_key=config.openai_api_key,
                azure_endpoint=config.azure_openai_endpoint.rstrip("/"),
                api_version=config.azure_openai_api_version,
            )
        else:
            self._client = OpenAI(api_key=config.openai_api_key)

    def generate_response(self, system_prompt: str, user_input: str) -> str:
        """
        Call chat completions (OpenAI or Azure OpenAI) with system + user messages.
        Returns response text only. Empty response returns empty string.
        Raises OpenAIClientError on SDK/network errors (no secrets in message).
        """
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_input},
                ],
            )
        except Exception as e:
            raise OpenAIClientError(
                "OpenAI / Azure OpenAI request failed. Check API key, endpoint, and network."
            ) from e

        choices = response.choices
        if not choices:
            return ""

        message = choices[0].message
        if message is None or message.content is None:
            return ""

        return message.content.strip() or ""

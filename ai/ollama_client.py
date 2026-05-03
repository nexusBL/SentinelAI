from __future__ import annotations

from dataclasses import dataclass

import requests

from config.settings import OllamaSettings


class OllamaClientError(RuntimeError):
    """Base error for Ollama client failures."""


class OllamaConnectionError(OllamaClientError):
    """Raised when SentinelAI cannot reach the Ollama service."""


class OllamaTimeoutError(OllamaClientError):
    """Raised when Ollama does not respond before the configured timeout."""


class OllamaResponseError(OllamaClientError):
    """Raised when Ollama returns an unexpected or invalid response."""


@dataclass(slots=True)
class OllamaGenerateResult:
    model: str
    response_text: str
    raw_payload: dict
    prompt: str
    system_prompt: str


class OllamaClient:
    def __init__(self, settings: OllamaSettings) -> None:
        self.settings = settings

    def generate(
        self,
        *,
        prompt: str,
        system_prompt: str,
        model: str | None = None,
    ) -> OllamaGenerateResult:
        resolved_model = model or self.settings.model
        payload = {
            "model": resolved_model,
            "prompt": prompt,
            "system": system_prompt,
            "stream": False,
            "format": "json",
        }

        try:
            response = requests.post(
                self.settings.endpoint,
                json=payload,
                timeout=self.settings.timeout_seconds,
            )
        except requests.exceptions.ConnectTimeout as exc:
            raise OllamaTimeoutError(
                "Timed out connecting to Ollama. Start the service with `ollama serve` "
                "and verify the endpoint is reachable."
            ) from exc
        except requests.exceptions.ReadTimeout as exc:
            raise OllamaTimeoutError(
                "Ollama did not return a response before the timeout expired."
            ) from exc
        except requests.exceptions.ConnectionError as exc:
            raise OllamaConnectionError(
                "Could not connect to Ollama. Install Ollama from https://ollama.com, "
                "run `ollama serve`, and pull a model such as `ollama pull llama3`."
            ) from exc
        except requests.exceptions.RequestException as exc:
            raise OllamaClientError(f"Unexpected error while calling Ollama: {exc}") from exc

        if response.status_code >= 400:
            raise OllamaResponseError(
                f"Ollama returned HTTP {response.status_code}: {response.text.strip()}"
            )

        try:
            response_payload = response.json()
        except ValueError as exc:
            raise OllamaResponseError(
                "Ollama returned a non-JSON HTTP response."
            ) from exc

        response_text = response_payload.get("response")
        if not isinstance(response_text, str) or not response_text.strip():
            raise OllamaResponseError(
                "Ollama response JSON did not include a non-empty `response` field."
            )

        return OllamaGenerateResult(
            model=resolved_model,
            response_text=response_text.strip(),
            raw_payload=response_payload,
            prompt=prompt,
            system_prompt=system_prompt,
        )

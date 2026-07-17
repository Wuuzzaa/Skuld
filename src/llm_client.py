from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import requests

from config import (
    DEEPSEEK_API_KEY,
    DEEPSEEK_BASE_URL,
    DEEPSEEK_MODEL,
    DEEPSEEK_TIMEOUT_SECONDS,
)

logger = logging.getLogger(__name__)


class LLMProviderError(RuntimeError):
    """Raised when an LLM provider request fails."""


@dataclass
class LLMResponse:
    provider: str
    model: str
    text: str
    usage: dict[str, Any]
    raw: dict[str, Any]


class LLMClient:
    """Generic chat client with provider dispatch.

    This keeps call-sites stable while allowing more providers later.
    """

    def chat_completion(
        self,
        provider: str,
        *,
        system_prompt: str,
        user_prompt: str,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 3500,
    ) -> LLMResponse:
        provider_key = provider.strip().lower()

        if provider_key == "deepseek":
            return self._chat_completion_deepseek(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                model=model or DEEPSEEK_MODEL,
                temperature=temperature,
                max_tokens=max_tokens,
            )

        raise LLMProviderError(f"Unsupported provider: {provider}")

    def _chat_completion_deepseek(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> LLMResponse:
        if not DEEPSEEK_API_KEY:
            raise LLMProviderError(
                "DeepSeek API key missing. Set DEEP_SEEK or DEEPSEEK_API_KEY in .env/deployment secrets."
            )

        base_url = DEEPSEEK_BASE_URL.rstrip("/")
        url = f"{base_url}/chat/completions"

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt.strip()},
                {"role": "user", "content": user_prompt.strip()},
            ],
            # Prefer non-thinking mode for stable structured output parsing.
            "thinking": {"type": "disabled"},
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        headers = {
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
            "Content-Type": "application/json",
        }

        try:
            response = requests.post(
                url,
                json=payload,
                headers=headers,
                timeout=DEEPSEEK_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            logger.exception("DeepSeek request failed")
            raise LLMProviderError(f"DeepSeek request failed: {exc}") from exc

        data = response.json()
        choices = data.get("choices") or []
        if not choices:
            raise LLMProviderError("DeepSeek returned no choices")

        message = choices[0].get("message") or {}
        content = message.get("content")
        if isinstance(content, list):
            content = "\n".join(
                str(part.get("text", "")) if isinstance(part, dict) else str(part)
                for part in content
            )

        if not content:
            # Thinking mode can return empty content and provide reasoning_content.
            content = message.get("reasoning_content") or ""

        content = str(content).strip()
        if not content:
            raise LLMProviderError("DeepSeek returned empty content")

        return LLMResponse(
            provider="deepseek",
            model=data.get("model", model),
            text=content,
            usage=data.get("usage") or {},
            raw=data,
        )

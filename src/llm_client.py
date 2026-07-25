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
    KIMI_API_KEY,
    KIMI_BASE_URL,
    KIMI_MODEL,
    KIMI_TIMEOUT_SECONDS,
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
        web_search: bool = False,
    ) -> LLMResponse:
        """Single-shot completion (system + user). Thin wrapper over
        chat_completion_messages() — kept for existing call-sites."""
        return self.chat_completion_messages(
            provider,
            messages=[
                {"role": "system", "content": system_prompt.strip()},
                {"role": "user", "content": user_prompt.strip()},
            ],
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            web_search=web_search,
        )

    def chat_completion_messages(
        self,
        provider: str,
        *,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 3500,
        web_search: bool = False,
    ) -> LLMResponse:
        """Multi-turn completion: pass a full message history (system/user/
        assistant) that is sent to the provider verbatim.

        web_search=True enables Kimi's built-in $web_search (server-side).
        Ignored by providers that don't support it (currently DeepSeek).
        """
        provider_key = provider.strip().lower()

        if provider_key == "deepseek":
            return self._chat_completion_deepseek(
                messages=messages,
                model=model or DEEPSEEK_MODEL,
                temperature=temperature,
                max_tokens=max_tokens,
            )

        if provider_key == "kimi":
            return self._chat_completion_kimi(
                messages=messages,
                model=model or KIMI_MODEL,
                temperature=temperature,
                max_tokens=max_tokens,
                web_search=web_search,
            )

        raise LLMProviderError(f"Unsupported provider: {provider}")

    def _chat_completion_deepseek(
        self,
        *,
        messages: list[dict[str, str]],
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
            "messages": messages,
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

    # ── Kimi (Moonshot AI) ──────────────────────────────────────────────────
    _WEB_SEARCH_TOOL = {"type": "builtin_function", "function": {"name": "$web_search"}}
    _WEB_SEARCH_MAX_ROUNDS = 5

    def _chat_completion_kimi(
        self,
        *,
        messages: list[dict[str, str]],
        model: str,
        temperature: float,
        max_tokens: int,
        web_search: bool,
    ) -> LLMResponse:
        """Kimi/Moonshot completion (OpenAI-kompatibel).

        Mit web_search=True bietet die Anfrage das eingebaute $web_search-Tool an.
        Kimi generiert nur die Such-Argumente; die Suche läuft serverseitig. Der
        Client muss die tool_call-Argumente UNVERÄNDERT als role=tool-Message
        zurückschicken (Multi-Round), dann liefert Kimi die finale Antwort.
        """
        if not KIMI_API_KEY:
            raise LLMProviderError(
                "Kimi API key missing. Set KIMI_AI (or MOONSHOT_API_KEY) in .env/deployment secrets."
            )

        base_url = KIMI_BASE_URL.rstrip("/")
        url = f"{base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {KIMI_API_KEY}",
            "Content-Type": "application/json",
        }

        # Kopie, damit die Aufrufer-Historie nicht mutiert wird.
        convo: list[dict] = list(messages)

        for _ in range(self._WEB_SEARCH_MAX_ROUNDS):
            payload: dict[str, Any] = {
                "model": model,
                "messages": convo,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            if web_search:
                payload["tools"] = [self._WEB_SEARCH_TOOL]

            try:
                response = requests.post(
                    url, json=payload, headers=headers, timeout=KIMI_TIMEOUT_SECONDS,
                )
                response.raise_for_status()
            except requests.RequestException as exc:
                logger.exception("Kimi request failed")
                raise LLMProviderError(f"Kimi request failed: {exc}") from exc

            data = response.json()
            choices = data.get("choices") or []
            if not choices:
                raise LLMProviderError("Kimi returned no choices")

            choice = choices[0]
            message = choice.get("message") or {}
            finish = choice.get("finish_reason")

            # Web-Search-Runde: Kimi will suchen -> Argumente 1:1 zurückgeben.
            if finish == "tool_calls" and message.get("tool_calls"):
                convo.append(message)  # assistant-Turn mit tool_calls muss dabei bleiben
                for tc in message["tool_calls"]:
                    fn = tc.get("function") or {}
                    if fn.get("name") == "$web_search":
                        # Argumente unverändert zurück (Kimi führt Suche selbst aus).
                        convo.append({
                            "role": "tool",
                            "tool_call_id": tc.get("id"),
                            "name": "$web_search",
                            "content": fn.get("arguments") or "{}",
                        })
                    else:
                        # Unbekanntes Tool -> leeres Ergebnis, damit der Loop nicht hängt.
                        convo.append({
                            "role": "tool",
                            "tool_call_id": tc.get("id"),
                            "name": fn.get("name") or "unknown",
                            "content": "{}",
                        })
                continue  # nächste Runde

            # Normale finale Antwort.
            content = message.get("content")
            if isinstance(content, list):
                content = "\n".join(
                    str(part.get("text", "")) if isinstance(part, dict) else str(part)
                    for part in content
                )
            if not content:
                content = message.get("reasoning_content") or ""
            content = str(content).strip()
            if not content:
                raise LLMProviderError("Kimi returned empty content")

            return LLMResponse(
                provider="kimi",
                model=data.get("model", model),
                text=content,
                usage=data.get("usage") or {},
                raw=data,
            )

        raise LLMProviderError(
            f"Kimi web search exceeded {self._WEB_SEARCH_MAX_ROUNDS} rounds without a final answer."
        )

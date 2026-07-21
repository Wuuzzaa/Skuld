"""Tests für LLMClient — Message-History-Pfad und Rückwärtskompatibilität.

DeepSeek-HTTP-Call wird gemockt (kein echter API-Call, nicht deterministisch/kostet).
Getestet wird das reale Verhalten: Message-Liste -> Payload-Mapping, Response-Parsing,
und dass die alte chat_completion()-Signatur identisches Payload erzeugt wie zuvor.
"""
from unittest.mock import patch, MagicMock

import src.llm_client as llm_mod
from src.llm_client import LLMClient, LLMResponse


def _fake_deepseek_response(content="Antwort"):
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {
        "model": "deepseek-v4-flash",
        "choices": [{"message": {"content": content}}],
        "usage": {"prompt_tokens": 11, "completion_tokens": 7},
    }
    return resp


def test_chat_completion_messages_sends_full_history():
    """Die übergebene Message-Liste landet 1:1 im DeepSeek-Payload."""
    history = [
        {"role": "system", "content": "Du bist Optionshändler."},
        {"role": "user", "content": "Empfehlung bitte."},
        {"role": "assistant", "content": "Stufe 1."},
        {"role": "user", "content": "Warum nicht Stufe 3?"},
    ]
    with patch.object(llm_mod, "DEEPSEEK_API_KEY", "test-key"), \
         patch.object(llm_mod.requests, "post", return_value=_fake_deepseek_response()) as mock_post:
        result = LLMClient().chat_completion_messages(
            "deepseek", messages=history, temperature=0.4, max_tokens=900,
        )

    assert isinstance(result, LLMResponse)
    assert result.text == "Antwort"
    _, kwargs = mock_post.call_args
    sent = kwargs["json"]["messages"]
    assert sent == history                      # ganze Historie, unverändert
    assert kwargs["json"]["temperature"] == 0.4
    assert kwargs["json"]["max_tokens"] == 900


def test_chat_completion_backward_compatible_payload():
    """Alte chat_completion() erzeugt weiterhin system+user als 2-Element-Liste."""
    with patch.object(llm_mod, "DEEPSEEK_API_KEY", "test-key"), \
         patch.object(llm_mod.requests, "post", return_value=_fake_deepseek_response("OK")) as mock_post:
        result = LLMClient().chat_completion(
            "deepseek", system_prompt="SYS", user_prompt="USR",
        )

    assert result.text == "OK"
    sent = mock_post.call_args.kwargs["json"]["messages"]
    assert sent == [
        {"role": "system", "content": "SYS"},
        {"role": "user", "content": "USR"},
    ]

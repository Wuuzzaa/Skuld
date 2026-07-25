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


# ── Kimi (Moonshot) ────────────────────────────────────────────────────────
def _fake_kimi_response(content="Kimi-Antwort", model="kimi-k3"):
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {
        "model": model,
        "choices": [{"message": {"content": content}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 20, "completion_tokens": 9},
    }
    return resp


def test_kimi_simple_completion_sends_history_and_model():
    """Kimi ohne Web-Search: Historie 1:1 im Payload, Default-Modell kimi-k3."""
    history = [
        {"role": "system", "content": "Du bist Optionshändler."},
        {"role": "user", "content": "Empfehlung bitte."},
    ]
    with patch.object(llm_mod, "KIMI_API_KEY", "test-kimi-key"), \
         patch.object(llm_mod.requests, "post", return_value=_fake_kimi_response()) as mock_post:
        result = LLMClient().chat_completion_messages(
            "kimi", messages=history, temperature=0.3, max_tokens=800,
        )
    assert isinstance(result, LLMResponse)
    assert result.provider == "kimi"
    assert result.text == "Kimi-Antwort"
    _, kwargs = mock_post.call_args
    assert kwargs["json"]["model"] == "kimi-k3"
    assert kwargs["json"]["messages"] == history
    # Ohne web_search -> KEIN tools-Feld im Payload.
    assert "tools" not in kwargs["json"]


def test_kimi_web_search_multi_round_echoes_tool_args():
    """web_search=True: 1. Runde liefert tool_calls, Client echoed Args als role=tool,
    2. Runde liefert finale Antwort (finish_reason=stop)."""
    # Runde 1: Kimi will suchen.
    round1 = MagicMock()
    round1.raise_for_status = MagicMock()
    round1.json.return_value = {
        "model": "kimi-k3",
        "choices": [{
            "message": {
                "role": "assistant",
                "content": "",
                "tool_calls": [{
                    "id": "call_abc",
                    "type": "function",
                    "function": {"name": "$web_search", "arguments": "{\"query\": \"PLTR earnings\"}"},
                }],
            },
            "finish_reason": "tool_calls",
        }],
        "usage": {"prompt_tokens": 30, "completion_tokens": 5},
    }
    # Runde 2: finale Antwort nach serverseitiger Suche.
    round2 = _fake_kimi_response("Mit Web-Recherche: ...")

    with patch.object(llm_mod, "KIMI_API_KEY", "test-kimi-key"), \
         patch.object(llm_mod.requests, "post", side_effect=[round1, round2]) as mock_post:
        result = LLMClient().chat_completion_messages(
            "kimi",
            messages=[{"role": "user", "content": "PLTR analysieren"}],
            web_search=True,
        )

    assert result.text == "Mit Web-Recherche: ..."
    assert mock_post.call_count == 2
    # Runde 1 muss das $web_search-Tool anbieten.
    tools_sent = mock_post.call_args_list[0].kwargs["json"]["tools"]
    assert tools_sent == [{"type": "builtin_function", "function": {"name": "$web_search"}}]
    # Runde 2 muss eine role=tool-Message enthalten, die die Argumente zurückgibt.
    round2_msgs = mock_post.call_args_list[1].kwargs["json"]["messages"]
    tool_msgs = [m for m in round2_msgs if m.get("role") == "tool"]
    assert len(tool_msgs) == 1
    assert tool_msgs[0]["tool_call_id"] == "call_abc"
    assert tool_msgs[0]["name"] == "$web_search"
    assert "PLTR earnings" in tool_msgs[0]["content"]


def test_kimi_missing_key_raises():
    from src.llm_client import LLMProviderError
    with patch.object(llm_mod, "KIMI_API_KEY", None):
        try:
            LLMClient().chat_completion_messages("kimi", messages=[{"role": "user", "content": "x"}])
            assert False, "should have raised"
        except LLMProviderError as e:
            assert "Kimi" in str(e)

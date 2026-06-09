from __future__ import annotations

from signalgate.app import _build_upstream_payload
from signalgate.routing import Candidate
from signalgate.security import SecurityConfig


def test_chat_only_strips_tool_fields_before_upstream(monkeypatch) -> None:
    monkeypatch.setenv("SIGNALGATE_USER_SALT", "test-salt")
    cand = Candidate(
        key="openai_bal",
        provider="openai",
        model_id="gpt-4.1-mini",
        supports={"tools": True, "json_schema": True, "streaming": True},
        limits={},
        pricing={},
        routing={},
    )
    payload = {
        "model": "signalgate/chat-only",
        "messages": [{"role": "user", "content": "hello"}],
        "tools": [{"type": "function", "function": {"name": "x"}}],
        "tool_choice": "auto",
        "user": "raw-user",
    }

    out = _build_upstream_payload(
        payload=payload,
        candidate=cand,
        security=SecurityConfig(),
        virtual_model="signalgate/chat-only",
    )

    assert out["model"] == "gpt-4.1-mini"
    assert "tools" not in out
    assert "tool_choice" not in out
    assert out["user"] != "raw-user"

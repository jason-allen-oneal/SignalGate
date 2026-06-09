from __future__ import annotations

import pytest

from signalgate.errors import SGError
from signalgate.security import (
    SecurityConfig,
    enforce_bind_auth,
    maybe_forward_user,
    tokens_equal,
)


def test_tokens_equal_accepts_only_exact_match() -> None:
    assert tokens_equal("secret-token", "secret-token")
    assert not tokens_equal("secret-token", "secret-token-x")


def test_non_loopback_bind_requires_auth() -> None:
    with pytest.raises(SGError) as exc:
        enforce_bind_auth("0.0.0.0", sec=SecurityConfig(auth_enabled=False))

    assert exc.value.code == "SG_INTERNAL"


def test_loopback_bind_without_auth_is_allowed() -> None:
    enforce_bind_auth("127.0.0.1", sec=SecurityConfig(auth_enabled=False))


def test_hash_forwarding_requires_salt(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SIGNALGATE_TEST_SALT", raising=False)
    sec = SecurityConfig(forward_user_mode="hash", user_hash_salt_env="SIGNALGATE_TEST_SALT")

    with pytest.raises(SGError) as exc:
        maybe_forward_user("user-1", sec)

    assert exc.value.code == "SG_INTERNAL"


def test_hash_forwarding_uses_salt(monkeypatch: pytest.MonkeyPatch) -> None:
    sec = SecurityConfig(forward_user_mode="hash", user_hash_salt_env="SIGNALGATE_TEST_SALT")
    monkeypatch.setenv("SIGNALGATE_TEST_SALT", "salt-a")
    a = maybe_forward_user("user-1", sec)
    monkeypatch.setenv("SIGNALGATE_TEST_SALT", "salt-b")
    b = maybe_forward_user("user-1", sec)

    assert a
    assert b
    assert a != b
    assert "user-1" not in a
    assert "user-1" not in b

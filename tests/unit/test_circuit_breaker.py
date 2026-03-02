from __future__ import annotations

import time

import pytest

from signalgate.circuit_breaker import BreakerConfig, CircuitBreaker
from signalgate.errors import SGError


def test_breaker_trips_on_consecutive_failures(monkeypatch: pytest.MonkeyPatch):
    cfg = BreakerConfig(consecutive_failures=3, min_samples=999, cooldown_seconds=60)
    br = CircuitBreaker(cfg)

    # 3 failures trip breaker
    br.record_failure(is_timeout=True)
    br.record_failure(is_timeout=True)
    br.record_failure(is_timeout=True)

    with pytest.raises(SGError) as e:
        br.allow()
    assert e.value.code == "SG_BREAKER_OPEN"


def test_breaker_half_open_trial(monkeypatch: pytest.MonkeyPatch):
    cfg = BreakerConfig(consecutive_failures=1, min_samples=1, cooldown_seconds=1)
    br = CircuitBreaker(cfg)

    br.record_failure(is_timeout=False)
    with pytest.raises(SGError):
        br.allow()

    # After cooldown, allow one trial.
    time.sleep(1.05)
    br.allow()  # enters half-open and marks trial in flight

    # Second concurrent should be blocked.
    with pytest.raises(SGError) as e2:
        br.allow()
    assert e2.value.code == "SG_BREAKER_OPEN"

    # Success closes breaker.
    br.record_success()
    br.allow()  # should be allowed again

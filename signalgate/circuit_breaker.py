from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from typing import Deque, Literal, Tuple

from .errors import sg_breaker_open

State = Literal["closed", "open", "half_open"]


@dataclass
class BreakerConfig:
    rolling_window_seconds: int = 120
    min_samples: int = 20
    consecutive_failures: int = 5
    error_rate: float = 0.30
    timeout_rate: float = 0.20
    cooldown_seconds: int = 120


@dataclass
class Event:
    ts: float
    kind: Literal["ok", "error", "timeout"]


class CircuitBreaker:
    def __init__(self, cfg: BreakerConfig):
        self.cfg = cfg
        self.state: State = "closed"
        self.open_until: float = 0.0
        self._events: Deque[Event] = deque()
        self._consecutive_failures: int = 0
        self._half_open_trial_in_flight: bool = False

    def is_available(self) -> bool:
        """Non-mutating availability check.

        - open: unavailable until cooldown elapses
        - half_open: unavailable if a trial is already in flight
        - closed: available

        Note: unlike allow(), this does not transition open -> half_open.
        """

        now = time.time()
        if self.state == "open" and now < self.open_until:
            return False
        if self.state == "half_open" and self._half_open_trial_in_flight:
            return False
        return True

    def _prune(self, now: float) -> None:
        cutoff = now - float(self.cfg.rolling_window_seconds)
        while self._events and self._events[0].ts < cutoff:
            self._events.popleft()

    def allow(self) -> None:
        now = time.time()
        if self.state == "open":
            if now < self.open_until:
                raise sg_breaker_open()
            # cooldown elapsed
            self.state = "half_open"
            self._half_open_trial_in_flight = False

        if self.state == "half_open":
            # allow exactly one trial request at a time
            if self._half_open_trial_in_flight:
                raise sg_breaker_open("Circuit breaker half-open (trial in flight)")
            self._half_open_trial_in_flight = True

    def record_success(self) -> None:
        now = time.time()
        self._events.append(Event(ts=now, kind="ok"))
        self._prune(now)
        self._consecutive_failures = 0
        if self.state == "half_open":
            self.state = "closed"
            self._half_open_trial_in_flight = False

    def record_failure(self, *, is_timeout: bool) -> None:
        now = time.time()
        self._events.append(Event(ts=now, kind="timeout" if is_timeout else "error"))
        self._prune(now)
        self._consecutive_failures += 1

        if self.state == "half_open":
            # fail fast: reopen
            self.state = "open"
            self.open_until = now + float(self.cfg.cooldown_seconds)
            self._half_open_trial_in_flight = False
            return

        # closed -> decide if we should trip
        if self._consecutive_failures >= self.cfg.consecutive_failures:
            self._trip(now)
            return

        total = len(self._events)
        if total < self.cfg.min_samples:
            return

        errors = sum(1 for e in self._events if e.kind == "error")
        timeouts = sum(1 for e in self._events if e.kind == "timeout")

        err_rate = errors / total if total else 0.0
        to_rate = timeouts / total if total else 0.0

        if err_rate >= self.cfg.error_rate or to_rate >= self.cfg.timeout_rate:
            self._trip(now)

    def _trip(self, now: float) -> None:
        self.state = "open"
        self.open_until = now + float(self.cfg.cooldown_seconds)

    def snapshot(self) -> Tuple[State, float, int]:
        now = time.time()
        self._prune(now)
        return self.state, self.open_until, len(self._events)

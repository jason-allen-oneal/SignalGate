from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple

from .circuit_breaker import BreakerConfig, CircuitBreaker, State
from .persistence import SQLiteKV


class PersistentCircuitBreaker(CircuitBreaker):
    def __init__(self, cfg: BreakerConfig, *, store: SQLiteKV, key: str):
        super().__init__(cfg)
        self._store = store
        self._store_key = key
        saved = store.get_json("breakers", key)
        if saved:
            state = saved.get("state")
            if state in ("closed", "open", "half_open"):
                self.state = state
            self.open_until = float(saved.get("open_until", 0.0))
            self._consecutive_failures = int(saved.get("consecutive_failures", 0))
            self._half_open_trial_in_flight = False

    def _save(self) -> None:
        self._store.put_json(
            "breakers",
            self._store_key,
            {
                "state": self.state,
                "open_until": self.open_until,
                "consecutive_failures": self._consecutive_failures,
            },
        )

    def allow(self) -> None:
        super().allow()
        self._save()

    def record_success(self) -> None:
        super().record_success()
        self._save()

    def record_failure(self, *, is_timeout: bool) -> None:
        super().record_failure(is_timeout=is_timeout)
        self._save()


@dataclass
class HealthManager:
    cfg: BreakerConfig
    breakers: Dict[str, CircuitBreaker]
    store: SQLiteKV | None = None

    @classmethod
    def from_config_raw(cls, cfg_raw: dict) -> "HealthManager":
        b = cfg_raw.get("breakers", {}) or {}
        cfg = BreakerConfig(
            rolling_window_seconds=int(b.get("rolling_window_seconds", 120)),
            min_samples=int(b.get("min_samples", 20)),
            consecutive_failures=int(b.get("consecutive_failures", 5)),
            error_rate=float(b.get("error_rate", 0.30)),
            timeout_rate=float(b.get("timeout_rate", 0.20)),
            cooldown_seconds=int(b.get("cooldown_seconds", 120)),
        )
        persistence = cfg_raw.get("persistence", {}) or {}
        store = None
        if bool(persistence.get("enabled", False)):
            path = str(persistence.get("sqlite_path", "./data/signalgate-state.sqlite3"))
            store = SQLiteKV(path)
        return cls(cfg=cfg, breakers={}, store=store)

    def _key(self, provider: str, model: str) -> str:
        return f"{provider}:{model}"

    def breaker(self, provider: str, model: str) -> CircuitBreaker:
        k = self._key(provider, model)
        if k not in self.breakers:
            if self.store:
                self.breakers[k] = PersistentCircuitBreaker(self.cfg, store=self.store, key=k)
            else:
                self.breakers[k] = CircuitBreaker(self.cfg)
        return self.breakers[k]

    def snapshot(self) -> Dict[str, Tuple[State, float, int]]:
        return {k: b.snapshot() for k, b in self.breakers.items()}

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple

from .circuit_breaker import BreakerConfig, CircuitBreaker


@dataclass
class HealthManager:
    cfg: BreakerConfig
    breakers: Dict[str, CircuitBreaker]

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
        return cls(cfg=cfg, breakers={})

    def _key(self, provider: str, model: str) -> str:
        return f"{provider}:{model}"

    def breaker(self, provider: str, model: str) -> CircuitBreaker:
        k = self._key(provider, model)
        if k not in self.breakers:
            self.breakers[k] = CircuitBreaker(self.cfg)
        return self.breakers[k]

    def snapshot(self) -> Dict[str, Tuple[str, float, int]]:
        return {k: b.snapshot() for k, b in self.breakers.items()}

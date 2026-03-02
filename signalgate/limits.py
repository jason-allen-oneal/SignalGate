from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Dict


@dataclass
class LimitManager:
    global_sem: asyncio.Semaphore
    provider_sems: Dict[str, asyncio.Semaphore]
    model_sems: Dict[str, asyncio.Semaphore]

    @classmethod
    def from_config_raw(cls, cfg_raw: dict) -> "LimitManager":
        lim = cfg_raw.get("limits", {}) or {}
        g = int(lim.get("max_in_flight_global", 16))
        int(lim.get("max_in_flight_per_provider", 8))
        int(lim.get("max_in_flight_per_model", 4))
        return cls(
            global_sem=asyncio.Semaphore(g),
            provider_sems={},
            model_sems={},
        )

    def provider(self, provider: str, *, max_in_flight: int) -> asyncio.Semaphore:
        if provider not in self.provider_sems:
            self.provider_sems[provider] = asyncio.Semaphore(max_in_flight)
        return self.provider_sems[provider]

    def model(self, provider: str, model: str, *, max_in_flight: int) -> asyncio.Semaphore:
        k = f"{provider}:{model}"
        if k not in self.model_sems:
            self.model_sems[k] = asyncio.Semaphore(max_in_flight)
        return self.model_sems[k]

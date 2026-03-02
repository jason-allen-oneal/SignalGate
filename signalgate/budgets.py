from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict


@dataclass
class BudgetStats:
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0


@dataclass
class BudgetManager:
    enabled: bool = False
    window: str = "day"  # "hour" or "day"
    # Map of "tier:premium" or "provider:openai" to USD limit
    limits: Dict[str, float] = field(default_factory=dict)
    # Map of "key:timestamp_bucket" to BudgetStats
    _usage: Dict[str, BudgetStats] = field(default_factory=dict)

    def _get_bucket(self) -> int:
        now = time.time()
        if self.window == "hour":
            return int(now // 3600)
        return int(now // 86400)

    def check_and_record(self, *, tier: str, provider: str, cost: float) -> bool:
        """Check if budget allows request and record it.
        Returns True if budget exceeded (should degrade).
        """
        if not self.enabled:
            return False

        bucket = self._get_bucket()
        keys = [f"tier:{tier}", f"provider:{provider}"]
        exceeded = False

        for k in keys:
            limit = self.limits.get(k)
            if limit is None:
                continue

            usage_key = f"{k}:{bucket}"
            current = self._usage.get(usage_key, BudgetStats())
            if current.cost_usd >= limit:
                exceeded = True

            # Record (optimistic / post-hoc)
            current.cost_usd += cost
            self._usage[usage_key] = current

        return exceeded

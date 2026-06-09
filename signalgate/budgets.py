from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict

from .persistence import SQLiteKV


@dataclass
class BudgetStats:
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0

    @classmethod
    def from_dict(cls, data: dict) -> "BudgetStats":
        return cls(
            tokens_in=int(data.get("tokens_in", 0)),
            tokens_out=int(data.get("tokens_out", 0)),
            cost_usd=float(data.get("cost_usd", 0.0)),
        )

    def to_dict(self) -> dict:
        return {
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "cost_usd": self.cost_usd,
        }


@dataclass
class BudgetManager:
    enabled: bool = False
    window: str = "day"  # "hour" or "day"
    # Map of "tier:premium" or "provider:openai" to USD limit
    limits: Dict[str, float] = field(default_factory=dict)
    # Map of "key:timestamp_bucket" to BudgetStats
    _usage: Dict[str, BudgetStats] = field(default_factory=dict)
    store: SQLiteKV | None = None

    def _get_bucket(self) -> int:
        now = time.time()
        if self.window == "hour":
            return int(now // 3600)
        return int(now // 86400)

    def _load_usage(self, usage_key: str) -> BudgetStats:
        if usage_key in self._usage:
            return self._usage[usage_key]
        if self.store:
            stored = self.store.get_json("budgets", usage_key)
            if stored:
                current = BudgetStats.from_dict(stored)
                self._usage[usage_key] = current
                return current
        return BudgetStats()

    def _save_usage(self, usage_key: str, current: BudgetStats) -> None:
        self._usage[usage_key] = current
        if self.store:
            self.store.put_json("budgets", usage_key, current.to_dict())

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
            current = self._load_usage(usage_key)
            if current.cost_usd >= limit:
                exceeded = True

            # Record (optimistic / post-hoc)
            current.cost_usd += cost
            self._save_usage(usage_key, current)

        return exceeded

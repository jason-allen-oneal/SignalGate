from __future__ import annotations

import hashlib
import json
from typing import Any


def stable_hash(obj: Any) -> str:
    data = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )
    return hashlib.sha256(data).hexdigest()


def rough_token_estimate(text: str) -> int:
    # Heuristic: ~4 chars per token. Clamped at 1.
    return max(1, (len(text) + 3) // 4)

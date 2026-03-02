from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class MetricsConfig:
    enabled: bool = False
    jsonl_path: str = ""


def append_jsonl(path: str, obj: dict[str, Any]) -> None:
    """Append a single JSON object as one line.

    Intentionally synchronous: line-sized writes, low volume.
    """

    if not path:
        return

    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(obj, separators=(",", ":"), ensure_ascii=False)
    with p.open("a", encoding="utf-8") as f:
        f.write(line + "\n")

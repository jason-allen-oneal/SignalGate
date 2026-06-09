from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np

from signalgate.classifier import KNNTierClassifier

TIERS = ("budget", "balanced", "premium")


def load_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        label = rec.get("label")
        emb = rec.get("embedding")
        if label in TIERS and isinstance(emb, list) and len(emb) >= 8:
            rows.append(rec)
    return rows


def norm(values: list[float]) -> np.ndarray:
    arr = np.asarray(values, dtype=np.float32)
    n = np.linalg.norm(arr)
    return arr if n == 0 else arr / n


def final_label(raw: str, top1: float, margin: float, sim_threshold: float, margin_threshold: float) -> str:
    if top1 < sim_threshold or margin < margin_threshold:
        return "balanced"
    return raw


def evaluate(path: Path, sim_threshold: float, margin_threshold: float) -> dict[str, Any]:
    rows = load_rows(path)
    confusion: dict[str, Counter[str]] = {tier: Counter() for tier in TIERS}
    counts = Counter()
    correct = 0

    for idx, row in enumerate(rows):
        train_rows = rows[:idx] + rows[idx + 1 :]
        if not train_rows:
            continue
        tmp = path.parent / f".{path.name}.tmp.jsonl"
        tmp.write_text("\n".join(json.dumps(x) for x in train_rows) + "\n", encoding="utf-8")
        try:
            clf = KNNTierClassifier.from_jsonl(tmp)
            pred = clf.predict(norm(row["embedding"]), sim_threshold=sim_threshold, margin_threshold=margin_threshold)
            got = final_label(pred.tier, pred.top1, pred.margin, sim_threshold, margin_threshold)
        finally:
            tmp.unlink(missing_ok=True)

        expected = str(row["label"])
        counts[expected] += 1
        confusion[expected][got] += 1
        correct += int(got == expected)

    total = sum(counts.values())
    return {
        "dataset": str(path),
        "total": total,
        "accuracy": correct / total if total else 0.0,
        "counts": dict(counts),
        "confusion": {k: dict(v) for k, v in confusion.items()},
        "thresholds": {"sim_threshold": sim_threshold, "margin_threshold": margin_threshold},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--sim-threshold", type=float, default=0.75)
    parser.add_argument("--margin-threshold", type=float, default=0.05)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    report = evaluate(args.dataset, args.sim_threshold, args.margin_threshold)
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.out:
        args.out.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

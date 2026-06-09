from __future__ import annotations

import json

from scripts.eval_knn import evaluate


def test_eval_knn_reports_basic_metrics(tmp_path) -> None:
    dataset = tmp_path / "dataset.jsonl"
    rows = [
        {"label": "budget", "embedding": [1, 0, 0, 0, 0, 0, 0, 0]},
        {"label": "budget", "embedding": [0.99, 0.01, 0, 0, 0, 0, 0, 0]},
        {"label": "balanced", "embedding": [0, 1, 0, 0, 0, 0, 0, 0]},
        {"label": "balanced", "embedding": [0.01, 0.99, 0, 0, 0, 0, 0, 0]},
        {"label": "premium", "embedding": [0, 0, 1, 0, 0, 0, 0, 0]},
        {"label": "premium", "embedding": [0, 0.01, 0.99, 0, 0, 0, 0, 0]},
    ]
    dataset.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")

    report = evaluate(dataset, sim_threshold=0.1, margin_threshold=0.0)

    assert report["total"] == 6
    assert report["accuracy"] == 1.0
    assert set(report["confusion"]) == {"budget", "balanced", "premium"}

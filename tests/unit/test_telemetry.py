from __future__ import annotations

from signalgate.telemetry import latency_snapshot


def test_latency_snapshot_reports_percentiles() -> None:
    snap = latency_snapshot([10, 20, 30, 40, 50])

    assert snap["count"] == 5
    assert snap["p50"] == 30
    assert snap["p95"] == 50
    assert snap["p99"] == 50


def test_latency_snapshot_handles_empty_values() -> None:
    snap = latency_snapshot([])

    assert snap == {"count": 0, "p50": None, "p95": None, "p99": None}

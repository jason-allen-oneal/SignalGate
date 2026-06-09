from __future__ import annotations

from signalgate.budgets import BudgetManager
from signalgate.health import HealthManager
from signalgate.persistence import SQLiteKV


def test_sqlite_kv_round_trip(tmp_path) -> None:
    store = SQLiteKV(str(tmp_path / "state.sqlite3"))
    store.put_json("ns", "item", {"value": 1})
    assert store.get_json("ns", "item") == {"value": 1}


def test_budget_manager_can_reload_usage_from_store(tmp_path) -> None:
    store = SQLiteKV(str(tmp_path / "state.sqlite3"))
    first = BudgetManager(enabled=True, limits={"tier:premium": 1.0}, store=store)
    assert first.check_and_record(tier="premium", provider="provider-a", cost=0.75) is False

    second = BudgetManager(enabled=True, limits={"tier:premium": 1.0}, store=store)
    assert second.check_and_record(tier="premium", provider="provider-a", cost=0.10) is False
    assert second.check_and_record(tier="premium", provider="provider-a", cost=0.20) is False
    assert second.check_and_record(tier="premium", provider="provider-a", cost=0.01) is True


def test_health_manager_restores_breaker_state(tmp_path) -> None:
    cfg = {
        "persistence": {"enabled": True, "sqlite_path": str(tmp_path / "state.sqlite3")},
        "breakers": {"consecutive_failures": 1, "cooldown_seconds": 30},
    }
    first = HealthManager.from_config_raw(cfg)
    breaker = first.breaker("provider-a", "model-a")
    breaker.record_failure(is_timeout=False)
    assert breaker.snapshot()[0] == "open"

    second = HealthManager.from_config_raw(cfg)
    restored = second.breaker("provider-a", "model-a")
    assert restored.snapshot()[0] == "open"

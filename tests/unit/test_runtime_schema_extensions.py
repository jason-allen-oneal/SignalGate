from __future__ import annotations

import copy

import jsonschema

from signalgate.runtime import _patch_config_schema_runtime_extensions


def test_runtime_schema_accepts_incident_and_persistence_keys() -> None:
    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "classifier": {
                "type": "object",
                "additionalProperties": False,
                "properties": {"enabled": {"type": "boolean"}},
            }
        },
    }
    patched = copy.deepcopy(schema)
    _patch_config_schema_runtime_extensions(patched)

    jsonschema.validate(
        {
            "classifier": {
                "enabled": False,
                "incident_pin_tier": "balanced",
                "incident_disable_classifier": True,
            },
            "persistence": {"enabled": True, "sqlite_path": "./data/state.sqlite3"},
        },
        patched,
    )

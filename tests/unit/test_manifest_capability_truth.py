from __future__ import annotations

import json
from pathlib import Path


def test_gemini_example_does_not_claim_unimplemented_tool_or_schema_adapter() -> None:
    manifest = json.loads(Path("docs/manifest.example.json").read_text(encoding="utf-8"))

    for key in ("gemini_flash", "gemini_flash_preview"):
        supports = manifest["models"][key]["supports"]
        assert supports["tools"] is False
        assert supports["json_schema"] is False
        assert supports["streaming"] is True


def test_balanced_tier_has_openai_candidate_for_tools_and_json() -> None:
    manifest = json.loads(Path("docs/manifest.example.json").read_text(encoding="utf-8"))
    balanced = manifest["tiers"]["balanced"]

    assert "openai_bal" in balanced
    assert manifest["models"]["openai_bal"]["supports"]["tools"] is True
    assert manifest["models"]["openai_bal"]["supports"]["json_schema"] is True

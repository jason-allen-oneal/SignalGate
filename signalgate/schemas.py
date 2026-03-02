from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema

from .errors import SGError


def load_json(path: str | Path) -> Any:
    p = Path(path)
    return json.loads(p.read_text(encoding="utf-8"))


def validate_json(instance: Any, schema: Any, *, what: str) -> None:
    try:
        jsonschema.validate(instance=instance, schema=schema)
    except jsonschema.ValidationError as e:
        raise SGError(
            code="SG_BAD_REQUEST",
            message=f"Invalid {what}: {e.message}",
            status_code=500,
            retryable=False,
        ) from e

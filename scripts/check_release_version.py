from __future__ import annotations

import sys
import tomllib
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: check_release_version.py <expected-version>", file=sys.stderr)
        return 2

    expected = sys.argv[1]
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    actual = pyproject["project"]["version"]
    if actual != expected:
        print(f"version mismatch: tag={expected} pyproject={actual}", file=sys.stderr)
        return 1
    print(f"version ok: {actual}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

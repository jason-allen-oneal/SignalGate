import json
import os
import sys

import atheris

# Ensure local imports work if the package install fails.
sys.path.insert(0, os.getcwd())

from signalgate.app import _sanitize_for_client  # noqa: E402


def TestOneInput(data: bytes) -> None:
    try:
        s = data.decode("utf-8", errors="ignore")
        obj = json.loads(s)
    except Exception:
        return

    _sanitize_for_client(obj)


def main() -> None:
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()


if __name__ == "__main__":
    main()

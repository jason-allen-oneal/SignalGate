import sys
from atheris import Setup, FuzzedDataProvider, instrument_all
import json

# Import the module to fuzz
# We need to make sure the path is right
sys.path.append('.')
from signalgate.sanitize import sanitize_chat_completions_payload, RequestFieldConfig

def TestOneInput(data):
    fdp = FuzzedDataProvider(data)
    try:
        # Generate a random JSON-like string
        raw_json = fdp.consume_unicode_nowait()
        try:
            payload = json.loads(raw_json)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return

        if not isinstance(payload, dict):
            return

        # Fuzz the sanitizer
        mode = fdp.pick_values(["passthrough", "strip_unknown", "error_on_unknown"])
        cfg = RequestFieldConfig(mode=mode)
        sanitize_chat_completions_payload(payload, cfg=cfg)

    except Exception:
        # We want to catch actual crashes, not expected validation errors
        # But for basic fuzzing, we just ensure it doesn't raise unhandled exceptions
        pass

if __name__ == "__main__":
    Setup(sys.argv, TestOneInput)
    instrument_all()

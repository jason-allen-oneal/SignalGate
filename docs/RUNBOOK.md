# SignalGate - Runbook (internal)

## Start

### 1) Create a runtime config
- Copy `docs/config.example.json` to `config.json` in the repo root (or anywhere).
- Set `paths.manifest_path` to point at your capability manifest JSON.

### 2) Set upstream credentials
SignalGate never stores secrets in config files.

For OpenAI upstream:
- Export the env var named in `upstreams.openai.api_key_env` (default: `OPENAI_API_KEY`).

### 3) Run
From the repo root:

```bash
uv sync --extra dev --extra embed
SIGNALGATE_CONFIG_PATH=./config.json uv run signalgate
```

Default bind: `127.0.0.1:8765`

## Health checks

```bash
curl -s http://127.0.0.1:8765/healthz
curl -s http://127.0.0.1:8765/readyz
curl -s http://127.0.0.1:8765/v1/models
```

## Common failures

### Invalid config/manifest
- Symptom: service fails at startup.
- Fix: validate your JSON against:
  - `docs/config.schema.json`
  - `docs/manifest.schema.json`

### Missing OpenAI API key
- Symptom: requests error with `SG_INTERNAL` saying env var missing.
- Fix: `export OPENAI_API_KEY=...` (or change `api_key_env`).

### SG_NO_CANDIDATES
- Symptom: request requires tools/JSON/streaming/context that no manifest candidate supports.
- Fix: update manifest pools and capability flags, or request a different virtual model/tier.

### SG_QUEUE_FULL
- Symptom: 429 from SignalGate.
- Fix: increase `limits.max_queue_depth`, reduce load, or scale out (multiple instances behind a local LB).

## Stop
Ctrl-C (or stop the systemd unit if you wrap it).

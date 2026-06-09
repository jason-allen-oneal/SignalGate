# Container deployment

SignalGate includes a runtime Dockerfile for service deployment.

## Build

```bash
docker build -t signalgate:local .
```

## Runtime layout

- `/app/config` is for mounted runtime config.
- `/app/data` is for metrics, local datasets, and SQLite state.
- The image exposes port `8765`.
- The image runs as a non-root user.
- A `/healthz` healthcheck is included.

Mount a config file at `/app/config/config.json` or set `SIGNALGATE_CONFIG_PATH` to another mounted path.

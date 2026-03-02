# SignalGate - OpenClaw Integration Guide

## Overview
SignalGate acts as a virtual provider for OpenClaw. You point OpenClaw at SignalGate's local port, and SignalGate handles the semantic tiering and failover.

## 1) OpenClaw Configuration

Add SignalGate as a provider in your `openclaw.json` (or via the UI).

Notes on auth:
- If `security.auth.enabled=true`, set `security.auth.header` to `authorization` (recommended for OpenClaw) and export `SIGNALGATE_TOKEN`.
- SignalGate accepts either a raw token or `Bearer <token>`.

```json
{
  "models": {
    "providers": {
      "signalgate": {
        "baseUrl": "http://127.0.0.1:8765/v1",
        "apiKey": "${SIGNALGATE_TOKEN}",
        "api": "openai-completions"
      }
    }
  }
}
```

## 2) Set SignalGate as Primary

Update your default agent or specific agents to use SignalGate:

```json
{
  "agents": {
    "defaults": {
      "model": {
        "primary": "signalgate/auto"
      }
    }
  }
}
```

## 3) Virtual Model Options

- `signalgate/auto`: Semantic routing (budget/balanced/premium).
- `signalgate/budget`: Force budget tier or higher.
- `signalgate/balanced`: Force balanced tier or higher.
- `signalgate/premium`: Force premium tier.
- `signalgate/chat-only`: Disable tool-calling support for this request.

## 4) Operational Management

### Logs
Check standard output or your process manager logs (systemd/pm2). Look for `_signalgate` blocks in response metadata or the decision trace.

### Incident Mode
If the classifier is misbehaving, update `config.json`:
```json
{
  "classifier": {
    "incident_pin_tier": "balanced",
    "incident_disable_classifier": true
  }
}
```
Then restart or reload SignalGate.

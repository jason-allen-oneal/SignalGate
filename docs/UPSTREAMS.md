# Upstreams (providers)

SignalGate is provider-agnostic at the routing layer.

- Provider names come from your manifest (`models.*.provider`) and `providerPreference`.
- Provider configs live under `upstreams.<provider>` in runtime config.

SignalGate currently supports two upstream kinds:

- `kind: openai_compat` - any OpenAI-compatible Chat Completions endpoint
- `kind: gemini` - Gemini generateContent / streamGenerateContent

Anthropic can be used in two ways:

1) Recommended: put Anthropic behind an OpenAI-compatible gateway (LiteLLM, OpenRouter, etc) and configure it as `openai_compat`.
2) Native Anthropic upstream kind is not implemented in this repo yet.

## Example runtime config (Gemini + OpenAI + Anthropic via LiteLLM)

```json
{
  "version": "0.1.0",
  "server": {"host": "127.0.0.1", "port": 8765},
  "paths": {"manifest_path": "./manifest.json"},
  "upstreams": {
    "openai": {
      "kind": "openai_compat",
      "base_url": "https://api.openai.com/v1",
      "api_key_env": "OPENAI_API_KEY"
    },
    "gemini": {
      "kind": "gemini",
      "base_url": "https://generativelanguage.googleapis.com",
      "api_version": "v1beta",
      "api_key_env": "GEMINI_API_KEY"
    },
    "anthropic": {
      "kind": "openai_compat",
      "base_url": "http://127.0.0.1:4000/v1",
      "api_key_env": "LITELLM_API_KEY"
    }
  }
}
```

Notes:
- In this example, `anthropic` is a provider name that SignalGate uses internally.
- The upstream behind `anthropic` must accept OpenAI `POST /chat/completions`.

## Example manifest entries

The provider keys below must match the runtime config keys under `upstreams`.

```json
{
  "version": "0.1.0",
  "providerPreference": ["gemini", "openai", "anthropic"],
  "models": {
    "gemini_bal": {
      "provider": "gemini",
      "model_id": "gemini-3-flash",
      "eligible_tiers": ["balanced"],
      "supports": {"tools": true, "json_schema": true, "streaming": true},
      "limits": {"context_window_tokens": 1000000, "max_output_tokens": 8192},
      "pricing": {"input_usd_per_1m": 0.0, "output_usd_per_1m": 0.0}
    },
    "openai_bal": {
      "provider": "openai",
      "model_id": "gpt-4.1-mini",
      "eligible_tiers": ["balanced"],
      "supports": {"tools": true, "json_schema": true, "streaming": true},
      "limits": {"context_window_tokens": 128000, "max_output_tokens": 16384},
      "pricing": {"input_usd_per_1m": 0.0, "output_usd_per_1m": 0.0}
    },
    "anthropic_bal": {
      "provider": "anthropic",
      "model_id": "claude-3-5-sonnet-20241022",
      "eligible_tiers": ["balanced"],
      "supports": {"tools": true, "json_schema": true, "streaming": true},
      "limits": {"context_window_tokens": 200000, "max_output_tokens": 8192},
      "pricing": {"input_usd_per_1m": 0.0, "output_usd_per_1m": 0.0}
    }
  },
  "tiers": {
    "budget": ["gemini_bal"],
    "balanced": ["gemini_bal", "openai_bal", "anthropic_bal"],
    "premium": ["openai_bal", "anthropic_bal"]
  }
}
```

## About pricing

SignalGate does not fetch prices from provider APIs.

To keep cost accounting real:
- Use real token usage from upstream responses (`usage`), and
- Keep `pricing.input_usd_per_1m` / `pricing.output_usd_per_1m` updated in your manifest.

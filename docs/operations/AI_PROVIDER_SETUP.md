# SULY AI provider setup

This guide configures the existing server-side AI gateway. It does not enable a provider automatically.

## Supported modes

| `AI_PROVIDER` | API contract | API key |
|---|---|---|
| `disabled` | No model calls; default | Not used |
| `openai-compatible` | `POST {AI_BASE_URL}/chat/completions` | Required |
| `ollama` | `POST {AI_BASE_URL}/api/chat` | Not required |

The gateway applies the same authenticated chat flow, persisted `ai.provider.run` approval, message validation, response-size limit, and request timeout to both active provider modes.

## Local Ollama

1. Install Ollama on a machine that can be reached privately by the SULY API runtime.
2. Pull a model suitable for the available CPU/RAM/GPU. Smaller quantized models use fewer resources but may produce weaker results.
3. Keep Ollama on a private interface/network. Do not expose port `11434` to the public internet.
4. Configure the API service environment:

```dotenv
AI_PROVIDER=ollama
AI_BASE_URL=http://ollama:11434
AI_API_KEY=
AI_MODEL=qwen2.5:3b
AI_TIMEOUT_SECONDS=90
AI_MAX_OUTPUT_TOKENS=1200
```

Use the actual private hostname/IP reachable from the API service. Do not put an Ollama URL, provider key, or model credential in the Expo client bundle.

5. Restart the API service and verify `/health` and `/ready`. These endpoints check API liveness and required Supabase configuration; they do not prove that Ollama is reachable.
6. Sign in to SULY, open the Agent area, and grant the explicit `ai.provider.run` permission. Then send a test message. Revoke the permission to stop future provider calls.

## OpenAI-compatible providers

Set `AI_PROVIDER=openai-compatible`, `AI_BASE_URL` to the provider's API base URL, `AI_API_KEY` to its server-side key, and `AI_MODEL` to a supported model identifier. The provider must implement the chat-completions request/response shape. Check its pricing and free-tier limits before use.

## Release and security notes

- `AI_PROVIDER` remains `disabled` by default.
- Keep `AI_API_KEY` in server environment secrets only. Never commit real values or use an Expo `EXPO_PUBLIC_*` variable for provider credentials.
- Ollama has no API key requirement in this integration; network isolation is therefore essential.
- Do not enable task workers or Hermes as a side effect of configuring chat.
- Provider calls may be slow or resource-intensive. Use bounded timeouts and output limits, and monitor the host's memory/CPU.
- CI uses mocked HTTP transports. A passing test suite is not a live model/provider smoke test.
- Production readiness still requires a real authenticated end-to-end test, provider health verification, usage accounting, rate limits, and a reviewed deployment.

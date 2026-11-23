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

## Owner-managed provider key

The app includes **Settings → AI provider** for the application owner. Configure `SULY_OWNER_EMAIL` in the API service environment with the owner's verified Supabase Auth email; owner access is denied when the email is missing, unverified, or different. The project must also have its server-only Supabase secret configured so the API can call the restricted Vault RPCs. Apply `supabase/migrations/20261122130000_suly_ai_provider_vault.sql` before enabling this page.

The owner submits an OpenAI-compatible HTTPS base URL, model identifier, and API key over the authenticated HTTPS API. The API writes the configuration to Supabase Vault, where the secret is encrypted at rest. The app receives only safe status fields; it never reads back the key. The API uses the Vault configuration for conversation replies, ahead of any legacy environment configuration. The key is not included in logs, client storage, or this repository.

The provider must implement the chat-completions request/response shape. Check its pricing and limits before entering a key. From the same owner-only screen, **Delete Vault config** removes the centrally stored secret through the service-role-only clear RPC. If server environment fallback settings are present, they remain active and the status response reports `source=environment`; remove those values from the hosting secret manager separately to leave AI unconfigured. The UI never claims that deleting the Vault entry disabled an environment-backed provider. `AI_PROVIDER`, `AI_BASE_URL`, `AI_API_KEY`, and `AI_MODEL` remain supported as server-only fallback settings; never put their values in the Expo client or Git. To leave AI disabled, keep both Vault and provider environment settings empty. Render's `/health` verifies API liveness only; `/ready` verifies the required Supabase values are present, not that Auth, PostgreSQL, or the AI provider is reachable.

## Client/API connection

The Expo app sends authenticated requests to the API origin configured as `EXPO_PUBLIC_API_BASE_URL`. Set it in the client's build environment to the actual HTTPS service URL shown by the hosting provider (no `/v1` suffix), then rebuild the web/mobile client. This value is public; Supabase server secrets and provider credentials are not. For local testing, set the same variable in `apps/client/.env` to an API origin reachable from the device or browser. The repository example intentionally leaves it blank because no deployed API URL is committed.

After setting server and client configuration, verify `/health` and `/ready`, then sign in, open a conversation, grant `ai.provider.run` consent in SULY AI, and send a message in the actual conversation screen. A live verification requires a valid Supabase user and applied conversation/approval migrations plus a reachable configured provider; passing the mocked tests below does not establish a live model response.

## Release and security notes

- `AI_PROVIDER` remains `disabled` by default.
- Keep `AI_API_KEY` in server environment secrets only. Never commit real values or use an Expo `EXPO_PUBLIC_*` variable for provider credentials.
- Ollama has no API key requirement in this integration; network isolation is therefore essential.
- Do not enable task workers or Hermes as a side effect of configuring chat.
- Provider calls may be slow or resource-intensive. Use bounded timeouts and output limits, and monitor the host's memory/CPU.
- CI uses mocked HTTP transports. A passing test suite is not a live model/provider smoke test.
- Production readiness still requires a real authenticated end-to-end test, provider health verification, usage accounting, rate limits, and a reviewed deployment.


## Usage token telemetry (read-only)

- عند إرجاع OpenAI-compatible provider لحقل `usage` يحتوي `prompt_tokens` و`completion_tokens`، أو Ollama لحقلَي `prompt_eval_count` و`eval_count`، يحفظ chat counts bounded في assistant message metadata ويعرضها في المحادثة.
- Counts هي أرقام provider-report فقط؛ missing/malformed usage لا يضيف metadata. إجمالي tokens يتم جمع input/output validated.
- هذه telemetry لا تقدّر التكلفة ولا تخصم credits ولا تنشئ ledger مالي. Provider calls ما زالت تحتاج إعداد server-side وموافقة `ai.provider.run`.

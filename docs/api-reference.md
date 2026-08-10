# 9Router API Reference

9Router exposes an **OpenAI-compatible** API surface at `/v1`, plus an
Anthropic-compatible `POST /v1/messages`, and a set of dashboard APIs under
`/api`.

## Base URL

```
http://localhost:20128/v1
```

The port defaults to `20128` and can be changed with the `PORT` env var.
All `/v1` endpoints accept CORS from any origin.

## Authentication

Every `/v1` request needs an API key. Keys are created in the dashboard
(**Dashboard → Endpoint → API Keys**) or via the API itself:

```bash
curl -X POST http://localhost:20128/api/keys \
  -H "Content-Type: application/json" \
  -d '{"name":"my-tool"}'
# → 201 {"key":"sk-...","name":"my-tool","id":1,"machineId":"..."}
```

Send the key as a `Bearer` token or `x-api-key` header:

```
Authorization: Bearer sk-...
x-api-key: sk-...
```

| Status | Meaning |
|---|---|
| `401` | Missing or invalid API key (`{"error":{"message":"Missing API key"/"Invalid API key","type":"authentication_error","code":"invalid_api_key"}}`) |

## Endpoints

### `POST /v1/chat/completions`

OpenAI-compatible chat completions. Request:

```json
{
  "model": "kr/claude-sonnet-4.5",
  "messages": [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "Hello!"}
  ],
  "stream": false
}
```

Non-streaming response:

```json
{
  "id": "chatcmpl-...",
  "object": "chat.completion",
  "model": "kr/claude-sonnet-4.5",
  "choices": [
    {"index": 0, "message": {"role": "assistant", "content": "Hi there!"}, "finish_reason": "stop"}
  ],
  "usage": {"prompt_tokens": 12, "completion_tokens": 4, "total_tokens": 16}
}
```

With `"stream": true` the server returns SSE chunks
(`data: {"object":"chat.completion.chunk",...}` terminated by `data: [DONE]`).

**Model ids** use the form `<provider-alias>/<model>` (e.g. `kr/claude-sonnet-4.5`).
Requesting a model with no active provider credentials returns `404`/`503`
(see error table below). Requests with no `model` field return `400`.

### `POST /v1/messages`

Anthropic Messages API format (used by Claude Code via `ANTHROPIC_BASE_URL`):

```json
{
  "model": "kr/claude-sonnet-4.5",
  "max_tokens": 1024,
  "messages": [{"role": "user", "content": "Hello!"}]
}
```

The request is translated into the same internal chat pipeline as
`/v1/chat/completions`.

### `GET /v1/models`

Lists available models:

```bash
curl http://localhost:20128/v1/models \
  -H "Authorization: Bearer sk-..."
```

Returns a JSON object with a `data` array of `{id, object: "model", ...}`
entries (OpenAI shape). Live catalogs are resolved per provider when possible.

### Other `/v1` endpoints

| Endpoint | Purpose |
|---|---|
| `POST /v1/audio/*` | Speech-to-text / text-to-speech |
| `POST /v1/embeddings` | Embeddings |
| `POST /v1/images` | Image generation |
| `POST /v1/videos` | Video generation |
| `POST /v1/search` | Web search |
| `POST /v1/web` | Web/content tools |
| `POST /v1/responses` | OpenAI Responses-format endpoint |
| `POST /v1/api` | Generic provider passthrough |

All require the same API-key auth.

## Errors

All endpoints return OpenAI-compatible error bodies:

```json
{
  "error": {
    "message": "Model not found",
    "type": "invalid_request_error",
    "code": "model_not_found"
  }
}
```

| HTTP | type | code | Meaning |
|---|---|---|---|
| `400` | `invalid_request_error` | `bad_request` | Malformed request / missing model |
| `401` | `authentication_error` | `invalid_api_key` | Missing or invalid key |
| `402` | `billing_error` | `payment_required` | Quota/payment issue |
| `403` | `permission_error` | `insufficient_quota` | Quota exhausted |
| `404` | `invalid_request_error` | `model_not_found` | Unknown model / no credentials |
| `406` | `invalid_request_error` | `model_not_supported` | Model not supported by provider |
| `429` | `rate_limit_error` | `rate_limit_exceeded` | Provider rate limit (transient) |
| `5xx` | `server_error` | `internal_server_error` / `bad_gateway` / `service_unavailable` / `gateway_timeout` | Upstream or gateway failure |

Streaming requests surface errors as `data: {"error": {...}}` SSE events before
the stream closes.

## Rate limiting

9Router does not apply a global request-rate limiter on `/v1`. Provider-level
rate limits (e.g. Copilot/Codex subscriptions) are handled internally with
cooldowns and are reported to clients as `429`/`503`.

## Dashboard APIs (`/api`)

| Endpoint | Purpose |
|---|---|
| `GET /api/health` | Health check |
| `POST /api/auth/login` | Dashboard login (JWT cookie) |
| `GET/POST /api/keys` | List / create API keys |
| `GET/POST /api/combos` | List / create combos (model routing rules) |
| `GET /api/settings` | Runtime settings |
| `GET /api/federation/status` | Federation mode status (edge/central) |

Dashboard routes require the JWT session cookie; `/v1` routes require an API key.

## See also

- [Integrations guide](integrations/README.md) — Claude Code, Cursor, and other tools.
- [Federation docs](FEDERATION.md) — edge/central deployment.

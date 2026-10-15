# HTTP-Contract Probing — streaming/serialization defects at the wire seam

Companion to `api-surface-probing.md` (which probes whether documented features
exist at all). This file covers the seam where a gateway/router hands a payload
to the CLIENT: shape, content-type, and framing. Tests pass here the least
often because every test pins one client shape while real consumers span several.

## The missing-stream-key contract (run the full matrix, never one row)

For any endpoint with a `stream` boolean, drive ALL FOUR cells before filing a
streaming verdict — one cell per run, same payload otherwise:

| `stream` key | Expected contract |
|---|---|
| absent | single JSON body, `content-type: application/json` (the OpenAI documented default — what every SDK, curl, and "wrap the base URL" integration sends) |
| `stream: false` | single JSON body, `content-type: application/json` |
| `stream: true` | SSE frames, `content-type: text/event-stream`, exactly ONE terminal sentinel |
| `Accept: application/json` header with no stream key | forces the JSON branch in most implementations — its own cell |

Reading `body.stream` loosely (an omitted key read as "streaming") puts the
router on the SSE path end to end while the client sent no flag — the response
comes back as an SSE-shaped body behind a 200 and every strict `JSON.parse` /
SDK `res.json()` fails with "Extra data" / "Unexpected non-whitespace character
after JSON". The 200 + plausible-looking body is why the defect survives green
tests: nothing throws server-side.

## Framing-leak signatures — read the raw TAIL, not the parsed body

Read the response tail (`tail -c 60 … | od -c`), never just `jq` it — jq fails
too late and hides where. Leaks that read as parse errors but are framing
bugs:
- a trailing `data: [DONE]\n\n` glued onto a JSON body (SSE terminator written
  into the non-stream response);
- a DUPLICATED terminal sentinel on a real stream (two `[DONE]` frames —
  downstream aggregators that treat the first as final truncate or double-count);
- event-stream `content-type` on a body that is one JSON object, or vice versa —
  a consumer that trusts the header parses the wrong shape.

File the leak as ONE row per surface the same client-shape drives: the identical
omitted-stream payload through each of the product's client surfaces (its
`/chat/completions`, its Claude-format twin, its Responses twin, per edge/replica
instance) proves systemic vs path-local — a defect fixed in one handler while
its siblings leak is a multi-row fix nobody files from a single curl.

## SDK-consumer equivalence without installing the SDK

A real consumer's failure is `res.text()` then `JSON.parse` — reproduce it with
a fetch, no dependency install (sandboxed surfaces often block `npm i`; stage
the script as a file instead of a `-e` one-liner to avoid approval pends):

```js
const res = await fetch(url, {method:'POST', headers:{authorization:`Bearer ${k}`,'content-type':'application/json'}, body});
const text = await res.text();
try { JSON.parse(text); console.log('SDK-style OK'); }
catch (e) { console.log('SDK-style FAILS:', e.message, JSON.stringify(text.slice(-40))); }
```

The failing tail snippet in the output is the row's evidence verbatim. Raw curl
proves the bytes; this proves the CLIENT experience — file the row quoting both.

## Error-path and credential-ladder probing (fail-closed contract)

- Drive the auth/credential ladder end to end: no credential (expect a correct
  auth error envelope naming the problem), a revoked/foreign credential (expect
  401), and a valid credential against a route with no backing provider (expect
  a model/route error — grep the message: one that blames a DIFFERENT provider
  or a generic class misroutes the user's diagnosis; the fix is naming the id
  the caller asked for).
- Read the product's own store for the credential under test before concluding
  'auth broken': an env var is not a client credential on most gateways — the
  mintable, DB-issued key is the credential class real users hold. Mint through
  the product's own flow; testing with the wrong class produces a false 401
  ladder.
- A rate-limit/cooldown error must carry its reset budget visibly (header or
  body). A cooldown with NO budget anywhere burns blind retries.
- Error-envelope CONSISTENCY across status classes is a contract of its own:
  drive the same endpoint through its failure classes (rate-limit 429,
  validation 422, auth 401) and diff the JSON envelope shapes. A rate-limiter
  middleware commonly predates the standardized error envelope and returns
  `{"status":"error",...}` where every handler returns `{"success":false,...}`
  — scripted consumers keying on `.success` (or on `.error.code`) silently miss
  the whole 429 class while their error handling passes every test written
  against the standard envelope. File the envelope drift as ONE row naming the
  middleware as the producer (with the middleware's own wrapper file:line),
  not N separate responses.

# Web-UI render-layer pitfalls (dogfood)

Lessons from driving a product's own SPA in a real browser. The API underneath is
usually proven; the render layer is where the fresh defects live.

## Drive the UI's own fetch calls, not just its visible output

Wrap `window.fetch` BEFORE clicking anything to capture status + body of every
UI-initiated call — the UI's own requests are the contract evidence, and bodies
the UI swallows are only visible that way. Two reads this pattern produces:

- A UI that keys its feedback on the HTTP status alone renders a SUCCESS contract
  as failure: a 409 body carrying the documented dedup shape
  (`status:"deduplicated"`, submission_id present) is the API saying the
  submission EXISTS, while the UI prints 'Submission failed'. File the
  render-layer mislabel as its own row — the UI twin of a CLI/REST contract
  divergence — with fix direction 'branch on the body's status field, not the
  status code'. Never re-file the API contract itself.
- Sweep `performance.getEntriesByType('resource')` for `responseStatus >= 400`
  as part of the same pass; a favicon 404 is cosmetic, a 4xx on a data route
  the UI never surfaces is not.

## A UI tree that stops one level short is usually a JS argument-shift, not missing data

When a drill-down renders at every level except the last, confirm the API
payload carries the children BEFORE filing 'feature missing' — fetch the backing
endpoint directly. The usual root cause: a per-level render dispatcher calls a
child render function with the PARENT's arity (4-arg call site, 2-arg
declaration); the answers array lands in a string parameter, `answers.forEach`
throws inside the click listener, and the exception vanishes silently — the row
simply never renders. File the call-site/signature mismatch (quote both from the
served JS) with fix direction 'a render test that expands every level and
asserts leaf nodes exist'. This is the SPA twin of the struct-JSON-tag trap: at
the render layer the call-argument contract between two hand-written functions
is an untested API.

## 'Flaky' chat/WebSocket: probe the socket raw before blaming the server

A pile-up of duplicate connect banners (one appended per reconnect) riding a
reconnect loop says nothing about the server. Hand-roll a WS handshake (open
tcp, send GET with Sec-WebSocket-Key/Version, read the 101, time it, then read
frames) — if the raw socket upgrades in ~0s and delivers exactly ONE banner, the
flap, the banner pile-up, and a sent message that never renders are all
CLIENT-side findings: the connect status should REPLACE the existing banner, not
append; and the user's own message should echo into the transcript on send
regardless of socket state. Keep the raw probe under a tool-safe timeout (a
promise-based js() probe can outlive the harness response window); a separate
script socket is cheaper and gets the same evidence.

## A 500 on the WS upgrade route is server-side — a middleware wrapper ate Hijack()

A real WebSocket upgrade that returns 500 whose response carries only
`Sec-Websocket-Version: 13` (no 101, no error body) is a MIDDLEWARE defect, not
flaky networking: Go middleware that wraps `http.ResponseWriter`
(security-headers, gzip, rate-limit wrappers) must forward the Hijacker
interface, and a wrapper implementing only Header/WriteHeader/Write fails the
upgrader's `http.Hijacker` type assertion — every upgrade 500s, on every
origin, with or without a valid token, while every REST route behind the same
chain stays 200. Grep the middleware chain between router and handler for
ResponseWriter-embedding structs and check each for a Hijack() forward before
filing anything else about the socket.

- **Only FULL handshake requests reproduce it.** A hand-typed GET (no
  Sec-WebSocket-Key/Version) gets the 400/401 from the upgrade validator before
  the upgrader runs, and a valid-token bare GET can 401 — a probe battery of
  bare GETs proves nothing about the upgrade path. The minimum evidence is a
  raw-socket handshake with real Sec-WebSocket-* headers plus the token, and
  the 500 (or 101) first line verbatim. Reproduce on a fresh install too: the
  same 500 on the ephemeral box proves the defect ships, not that your scratch
  instance is special.
- **The real-time route is a THREE-layer parity surface — diff all three.** The
  UI client's dial URL (grep the SPA's WS constructor), the server's registered
  route, and the README/API-docs URL can all three disagree. The signature that
  the real-time layer was never integration-tested end to end: the client dials
  a URL nothing registers (404) while the registered URL is one no client uses
  — and the registered one itself 500s. Each mismatch is its own row; also
  check whether the consuming component is even reachable in the shipped UI (a
  panel no route renders is dead code — scope the finding to that), and cite
  the doc line that documents the URL shape no code path uses.

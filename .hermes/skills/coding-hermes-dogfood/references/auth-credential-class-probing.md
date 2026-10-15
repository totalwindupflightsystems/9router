# Auth probing: credential classes and the enablement triad

Distilled from real-use runs where 'auth is broken' was filed wrongly. The
refusals are usually correct; the probe was aimed at the wrong credential class.

## Enablement triad — the credential env var alone enables nothing

An auth credential env var usually pairs with a documented enablement flag;
re-read the config loader before filing. A server can bind healthy with the key
exported but auth off, serving every endpoint unauthenticated with zero
warnings — that silent-open inverse (credential present, auth disabled, no
warning) is itself a real finding. Prove the guard with the triad on a guarded
endpoint: 401 no key / 401 wrong key / 200 valid key. `/models`-style discovery
routes are commonly unguarded by design — probe a guarded route.

## Credential CLASS — a deployment env secret is not a client credential

Before filing 'valid credential rejected', identify the credential class the
route consumes: an API key in the compose/env block (admin secret, signing key)
is not the same class as a key minted in the product's own credential table.
The guard can be perfectly correct rejecting the env key while a DB-minted
client key authenticates cleanly. Mint a client credential through the product's
OWN flow (login → create key → use it) and retry the triad with that — if it
passes, the finding is a docs/UX gap ('nothing tells the user where to get a
client key or that the env value will not work'), never 'auth is broken'.

On fresh installs the same shape is onboarding, not auth: the DB is empty, no
client key exists yet, and the 401 is correct. Drive the product's first-user
flow and grade THAT chain; a first-user path that dead-ends (password
undocumented, error text never names the credential source) is a P2
onboarding/docs finding, and the guard passing the triad afterwards is the
evidence line that closes 'auth broken'.

Same corollary on the multi-instance (federation/relay) shape: a shared
instance-pair token is the inter-node secret, not a client key — a 401 on the
edge that turns 200 with the primary's client key is the same docs/UX gap.

## The dual-token deadlock triad

The triad can return three DIFFERENT errors (401 middleware / 403 handler / 403
handler) and still mean no request can ever pass: middleware demands token A,
the handler's second gate demands token B, and one header cannot equal both.
Send each candidate token alone AND both Authorization headers at once (Go's
Header.Get takes the first — this distinguishes 'middleware wins' from 'handler
wins'); grep the config loader for validation of the combination; re-grade the
deployment where the surface IS reachable (e.g. a single-token posture) as the
workaround, filing the deadlock as the P0. The triad's job is to characterize
refusals, not to prove reachability — a three-error triad with no 200 path IS
the finding. The fix direction to check first: exempt the gated routes from the
shared middleware so the handler's own admin gate is the sole authority, plus a
config-load error when two secrets are set equal (never silently serve one
credential in two roles).

## Management surfaces: prove reachability, then look for the read half

After a deadlock fix lands, re-drive the write path end to end (mint/bind/class
with the admin token, refusals with the message token). Then ask the question
the operator asks next: is there ANY read route? A management surface with
writes only (GET on principals/bindings/class all 405) leaves the JSONL store
as the only audit view — file that as its own row. And watch strictness drift:
an endpoint that strictly rejects unknown fields on one body type while
silently accepting them on a sibling body of the same API class is a
consistency finding.

# PRD: `h3-forge` — Provider Key Rotation & Lane-Health Authority

**Project:** get-h3 · agent-ops line · **Item:** B7 (added) · **Author:** Kara-agent · **Date:** 2026-09-17
**Status:** proposed · **Effort:** M (~2 weeks) · **Depends on:** B1 (logsey) for failure-signal mining · **Feeds:** B4 digest (lane health), B3 runbooks

---

## The one-liner

The single place that knows every provider lane a fleet talks to — key age, quota posture, failure signals, rotation state — and does the two things fleets always postpone: **rotate keys before they expire, and prove lanes healthy before the fleet needs them.**

## The problem, measured

**Case file 1 — the expired key that kept "working" (2026-09):** an OpenRouter key shipped in a project expired mid-flight; the first symptom was a 401 deep inside a scheduled run (`API key expired.`), and the working fallback only survived because someone had wired it *earlier, by hand, after another expiry*. Key inventory lived in six `.env` files and one person's memory.

**Case file 2 — the dead-lane month:** SambaNova keys went 401 across the board; the lanes stayed "configured" but dead for weeks because nothing distinguished *configured* from *proven-healthy* — the fleet mandates "test EVERY model live" but enforcement was a human reading usage pages.

**Case file 3 — the misroute tell:** rows in the billing surface for a model the provider's own usage page never showed — caught by hand during a value quorum. The signature (ledger rows for models absent from the provider's usage page = misroute) was documented, then left as prose.

**Case file 4 — the rotation scramble:** every real key-compromise/expiry event triggers the same ad-hoc dance: find every copy, update six `.env` files, restart three daemons, hope nothing hardcodes the old value. The fleet's own doctrine says "rotation > purge" — but nothing makes rotation *cheap*.

## User stories

**US-1 (the registrar):** As the fleet operator, I register a lane once: `forge add xkiro --base-url ... --env XKIRO_API_KEY --plan 200usd --test 'ping z-ai/glm-5.3-flash'` — and forge answers "what lanes exist, what are they for, when did each last prove healthy."

**US-2 (the prover):** As the agent about to wire a project to a lane, I run `forge check xkiro` — a live probe runs *now* (the registered test command), and the result with latency is appended to the lane's health log. Configured ≠ healthy; only a receipt proves healthy.

**US-3 (the rot watcher):** As the fleet, scheduled probes (daily? per-lane cadence) catch rot before consumers do: a lane failing its probe N consecutive times flips `degraded` in `forge status` and fires one escalation — B4's digest carries the flag; the 401-at-2am class dies.

**US-4 (the rotator):** As the responder to "key X is compromised/expiring", I run `forge rotate xkiro --from XKIRO_API_KEY --to XKIRO_API_KEY_2` — forge updates the registered env files, runs the probe, flips the lane, and reports per-consumer rewiring status. The six-file scramble becomes one audited transaction.

**US-5 (the misroute hunter):** As the cost auditor, `forge reconcile --provider xkiro --window 7d` diffs observed lane usage against the provider's own usage surface and flags ledger rows for models the provider never served — the quorum's hand-found signature, mechanized.

## What it tracks (per lane)

| Field | Source |
|---|---|
| base URL, auth dialect, env-file locations | registration |
| key metadata: created, last-rotated, expiry-if-known, copies (grep of registered paths) | forge inventory |
| health log: probe receipts (ts, model, latency, verdict) | scheduled + on-demand probes |
| plan posture: quota windows, usage limits as declared | registration (honest labels: declared vs measured) |
| consumers: which projects/daemons reference the lane | registered consumer list |

**Design rules:**
- **Receipts, not config:** a lane's status is derived from its last *probe receipt*, never from "it's in the .env" — the configured-vs-healthy distinction is the product's spine.
- **Rotation is a transaction:** env files updated → probe on new key → flip → report; abort on failed probe (old key restored). Atomicity doctrine from CHT-004 applied to credentials.
- **Declared vs measured, labeled:** plan quotas are whatever the operator declared; forge never guesses billing posture — it only measures reachability and latency (the cost-truth doctrine: never fabricate cost figures).
- **Secrets discipline:** keys are referenced by env-var name and file path, never stored, displayed, or logged by forge (0600 profiles, redaction pass on all output).

## Interface

```
forge add <lane> --base-url URL --env VAR --test <probe-cmd> [--plan "..."] [--consumers ...]
forge check <lane> [--model M]            # live probe now, receipt appended
forge status [--lane ...] [--json]        # healthy | degraded | unproven | rotated-out
forge rotate <lane> --to VAR [--test ...] # audited key rotation transaction
forge reconcile <provider> --window 7d    # usage-vs-ledger misroute diff
forge audit                               # whole-fleet lane matrix (B4 digest section)
```

## Success criteria

1. **Expiry replay:** a lane whose key reaches expiry/invalid status is `degraded` within one scheduled probe cycle — before any consumer hits the 401 (verified by injecting an invalid key on a test lane).
2. Rotation drill: rotating a test lane across three registered env files completes with zero plaintext key exposure in forge output/logs, and aborts cleanly on a failed probe.
3. Misroute detection: seeded ledger rows referencing a never-served model are flagged by `reconcile` within one window.
4. Fleet adoption: ≥6 lanes registered on this box in week one (xkiro ×2, opencode-go ×2, commandcode ×2 at minimum), each with a probe receipt trail.

## Why get-h3 / why open

Agent fleets are multi-provider by nature — lanes are their blood supply, and every fleet manages key rot with grep and luck. The product isn't key storage (1Password et al. own that); it's **lane-health truth**: probe receipts, rotation transactions, misroute reconciliation. That's operational intelligence only a running fleet generates, and it's missing from every stack.

## Risks

- Probe cost/limits (probes consume quota) → per-lane cadence + tiny registered probe payloads; probes are declared, honest, and budgeted.
- Env-file write risk (rotation touches secrets) → file updates are the only writes forge ever makes, path-registered, diff-audited, abort-on-fail; keys never pass through forge's stdout/logs.
- Stale consumer lists → `reconcile` cross-checks declared consumers against observed usage; unregistered consumers surface (the registry-completeness law from B6, reused).

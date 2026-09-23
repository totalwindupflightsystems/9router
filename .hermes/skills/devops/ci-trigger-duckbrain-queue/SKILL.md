---
name: ci-trigger-duckbrain-queue
description: Use when wiring a forge-free CI trigger queue.
version: "1.0.0"
license: MIT
metadata:
  audience: developers
  category: devops
  hermes:
    tags: [ci, duckbrain, git, trigger, self-hosted, runners]
---

# Forge-free CI trigger: DuckBrain is the queue, fetch-by-SHA is the proof

The pattern (Bane 2026-09-23): **a push adds an entry to DuckBrain; DuckBrain's scheduler tries to
pull the commit — http, https or ssh — without a tree and without a dry run; only a provably
retrievable commit becomes eligible to schedule on a runner.**

Why it matters: it removes the forge from the critical path. GitHub can billing-block us (proven:
row INT-CI-002, "GitHub Actions jobs NOT STARTED"), and a node behind NAT can still pull. No part of
this pattern needs a webhook, a public address, or an inbound port.

## 1. The queue is a DECLARED TABLE, not a new store

DuckBrain serves a declared table at `/api/ns/<ns>/tables/<t>` with PostgREST-style semantics.
Declare it by writing `~/duckbrain/namespaces/<ns>/tables/<t>.table.json`:

```json
{"name":"trigger","format":"jsonl-objects","primary":"id","glob":"tables/trigger.jsonl",
 "columns":[{"name":"id","type":"varchar"},{"name":"repo","type":"varchar"},
            {"name":"sha","type":"varchar"},{"name":"status","type":"varchar"}]}
```

Then create the namespace directory on disk (`manifest.json` + `config/`, `event/`, `concept/`,
`raw_note/` partitions + `.gitignore` with `/.search/`). DuckBrain discovers it by directory — no
registration call is needed, and `POST /api/namespaces {name}` answers CONFLICT for a namespace that
already exists on disk. Auth is `x-api-key` (from `~/.duckbrain/foreman-status.token`); **Bearer is
rejected with 401**, and the API rate-limits, so retry 429 with a short backoff.

### The write sharp edge that costs a debugging round

- `GET` filters are generous: `?status=eq.pending&order=created_at.asc&limit=5`.
- **`PATCH`/`DELETE` require the PRIMARY KEY filter**: `?pk=eq.<id>` → `{"updated":1}`.
  `?id=eq.<id>` — which works for GET — is refused on writes:
  `VALIDATION_ERROR: PATCH/DELETE require a primary key filter: ?pk=eq.<value>`.
- `POST` takes one object or an array → `{"inserted":N}`.

The `primary` field in the `.table.json` is what `pk` means.

### Row lifecycle

```
pending --(claim)--> fetching --(fetch ok)--> ready --> scheduled --> done | failed
                          \--(fetch fail)--> pending (attempts+1) | failed (at max)
```

**Claim before you work.** Write `status=fetching` + `lease_node` + `lease_until` before the fetch, so
a crashed poller never leaves a row looking untouched. Release the lease on completion. A second
poller run must find nothing to do — idempotence is the test, not a nicety.

## 2. The readiness proof: fetch exactly one SHA

`git fetch --depth=1 --no-tags <remote> <sha>` **into a bare mirror**. Measured against a real repo
(hermes-dagger, 201 M of history) on 2026-09-23:

| command | bytes | contents | time |
|---|---|---|---|
| full history `.git` | 201 M | everything | — |
| `--depth=1` | 6.0 M | one snapshot: 1459 blobs + 509 trees | 2.3 s |
| `--depth=1 --filter=tree:0` | 252 K | tree graph, **0 blobs** | 1.4 s |

Both transports work and were verified: `git@github.com:…` (ssh, BatchMode) and
`https://github.com/…`. In the poller the two legs measured 722 ms (https, small repo) and 2261 ms
(ssh, large repo).

**Use the cheapest form that answers the question.** `--filter=tree:0` fetches no blobs and is ~24×
smaller than a snapshot — the right choice for "is this sha retrievable". A full snapshot is only
needed when a job will actually build.

### Why not the obvious alternatives

- **`git ls-remote`** proves a REF exists, not that a specific commit is fetchable — the sha may be
gone (force-push, GC) while the branch is fine.
- **`git fetch --dry-run`** still negotiates and can pull objects; it is not a cheap probe.
- **A full clone** on every trigger is the thing being avoided.

### Verifying the object landed — do not be fooled by a partial clone

`git cat-file -e <sha>` **lazily fetches missing objects** when the remote is a promisor, so a
"PRESENT" answer does not prove the object came in the first fetch. To census what actually arrived,
read the pack instead of the object database:

```bash
git verify-pack -v <mirror>/objects/pack/*.pack | awk 'NF>3{print $2}' | sort | uniq -c
```

That is how the 0-blobs claim above was proven. (A bare repo with only `FETCH_HEAD` also reports
`rev-list --count --all` = 0 and `count-objects` = 0 loose: the objects are in the pack, not loose,
and no ref points at them. Those two numbers are artifacts, not evidence.)

## 3. The poller contract

`~/.hermes/scripts/ci-trigger-poller.py` is the reference implementation (stdlib only): read
`status=eq.pending` → claim with `pk=eq.` → `git fetch --depth=1 --no-tags <repo> <sha>` into
`/var/tmp/ci-mirrors/<slug>` → verify `cat-file -e <sha>^{commit}` → PATCH `status=ready` with
`fetched_at`, `fetch_ms`, `local_mirror`; on failure PATCH back to `pending` with
`attempts+1` and `last_error`, or `failed` at `CI_MAX_ATTEMPTS`.

## Pitfalls

- **Write a real SHA, never `HEAD`.** The pusher resolves the sha at push time. A literal `HEAD` in
the row makes the readiness proof meaningless (it proves a ref, and fetch-by-`HEAD` bypasses the
whole point).
- **https against a PRIVATE repo works only where credentials are configured.** It silently succeeds
on the mother host (credential helper present) and will 401 on a fresh node. Either push a scoped
short-lived token per job, or make ssh the default leg. Never park a long-lived token in the queue.
- **`GIT_TERMINAL_PROMPT=0`** on the node, or a credential-less fetch hangs on a prompt instead of
failing.
- **`GIT_SSH_COMMAND` with `BatchMode=yes` and `StrictHostKeyChecking=accept-new`** — otherwise the
first ssh fetch to a new host stops for a host-key prompt.
- **The hub must never dial the node.** If a design needs the server to reach the runner, the design
is wrong; the runner long-polls.
- **Never store secrets in the queue rows.** Credentials live on the node or arrive per-job, scoped
and short-lived. A hub holding other people's tokens is an attack surface, not a feature.

## Related

- `duckbrain-http-access` — the general DuckBrain HTTP access procedure (auth, routes).
- `github-actions-ci-ops`, `coding-hermes-releng` — CI and release operations on the existing stacks.

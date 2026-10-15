---
name: coding-hermes-traceability
description: "Use when writing/reviewing fleet work — the ch:trace link graph (row→spec→wave→test→evidence→witness→verdict→commit→memory), how to TAG each data source we use daily (boards, waves, verdicts, DuckBrain, specs, films, ledger, scheduler DB, sessions, Hilo, backups), and the one-call context surface."
version: 2.1.2
author: totalwindupflightsystems
license: MIT
metadata:
  hermes:
    tags: [traceability, coding-hermes, foreman, worker, evidence, witness, duckbrain, hilo, tagging]
    related_skills:
      - coding-hermes-quorum
      - boardctl
      - duckbrain-memory
      - hermes-fleet-ops
---

# coding-hermes Traceability (照合 Chōgō — the cross-reference)

**Load before writing a board row, commit, test, memory or completion claim in the fleet.**
Public contract: `docs/traceability-doctrine.md` in the owning repo. This skill is the **operational** side
(real paths, real recipes) and stays local — it is not for public repos.

## The marker

```
ch:trace row=<ID> spec=<path#anchor> wave=<manifest#step> test=<path::test> doc=<path> prompt=<path> \
         evidence=<path> witness=<locator> verdict=<id> commit=<sha> memory=<key>
```

`row=` is required. Six hard rules, of which two are ours and both come from measured failure:

1. `row=` mandatory.
2. **Nothing closes by reference** — `evidence=` is an artifact or a witness, never another row/verdict/report.
   (Box-in-a-box is how 222 rows became "complete" with nothing behind them.)
3. No witness → `witness=none:<reason>`. Stated reason fine, silence not.
4. `memory=` accompanies a repo-local reference, never replaces it; only resolved records are cited.
5. `verdict=` must bind to `commit=`, reachable from the published tip (pre-merge verdicts are not evidence).
6. The auditor is not the author. The referee is an out-of-band scan; an external reading outranks anything we wrote.

## Evidence pointer syntax

Use a repository-relative artifact path, a resolvable bare or `verdict:<id>` verdict, a resolvable commit SHA, or a prefixed external pointer such as `run:<id>`, `live:<locator>`, or `github:<locator>`. Bare external run labels are ambiguous and fail the gate; absent evidence must be `none:<reason>`.

## Worker dispatch and closeout (mandatory)

Before dispatch, the foreman loads `worker-brief-authoring` and this skill, resolves the canonical board row and its spec/use-case anchor, then places those exact references in the worker's one-message brief. Preload `coding-hermes-worker,coding-hermes-traceability` only when the worker launch does not pass `--ignore-rules` (that flag suppresses preloaded skills); the one-message brief must still carry the full contract because workers do not inherit the foreman's skills, board, or memory.

Require the worker's final report to include a single-line `ch:trace` marker with all eleven fields (`row`, `spec`, `wave`, `test`, `doc`, `prompt`, `evidence`, `witness`, `verdict`, `commit`, `memory`) and a `STATUS` / `TIER` / `EVIDENCE` closeout block. Values are single tokens; every absent value is an explicit `none:<reason>`, never a blank or bare `none`. Keep stable QA/dogfood `UC-...` and `REG-...` IDs in the spec/test/history pointers; a fixed regression stays in future coverage with its failure, fix commit, and permanent test recorded.

Before `gitreins task complete`, the foreman validates the worker marker against the owning row, spec, test/manual procedure, evidence, and landed commit; writes it and the `STATUS` / `TIER` / `EVIDENCE` block into the row's `worker_summary`; and adds a Tier 2 criterion that checks the trace links. Where a pre-eval gate binds task IDs, use the owning board-row ID as the GitReins task ID or record an explicit mapping. After the judge, update the final row/closeout event with the verdict bound to that commit. A missing or unresolved marker blocks row closure; CI status alone is not traceability evidence.

## HOW TO TAG EACH SOURCE (the piece that matters day to day)

Every source below is one we touch weekly. Column 4 is what goes in the marker.

| source | where it lives | answers | tag it as |
|---|---|---|---|
| **board rows** | `<repo>/.coding-hermes/board/tasks.jsonl` + `events.jsonl`; write via `boardctl` | what work exists, what we claim | `row=TR-251` |
| **wave manifests** | `<repo>/.coding-hermes/waves/<tick>.json` | which dispatch produced this | `wave=task-router-2026-09-30-01-14-11#task-2` |
| **verdicts** | `gitreins task list`, per-task `verdict.json` | what an independent judge ruled | `verdict=<job-or-task-id>` (always with `commit=`) |
| **DuckBrain** | HTTP API + MCP; namespaces | what we decided/learned, long-term | `memory=/project/<project>/<slug>` |
| **specs / docs** | `<repo>/docs/`, `<repo>/specs/`, `reports/` | what we promised | `spec=docs/x.md#anchor`, `doc=reports/y.html` |
| **x-ray films** | `reports/xray/<project>-xray.html` + `-latest.json` | what the outside sees, right now | `evidence=reports/xray/…` and/or `witness=tag:v0.2.0@origin` |
| **router ledger** | `task-router/data/state/outcomes.jsonl`, `outcomes-averages.jsonl` | what actually ran, on which lane, at what cost | `witness=ledger:router-proxy/rows>0` |
| **scheduler DB** | `~/.hermes/coding-hermes/scheduler.db` (projects, namespaces, ticks, tick_workers, deferrals) | what is scheduled, cooldowns, admission | `row=` + `evidence=<query output>` |
| **session transcripts** | `~/.hermes/state.db` (messages, session_model_usage) | which lane truly served a seat/job | `evidence=state.db:<session_id>` |
| **Hilo / WarpFS** | `hilo` binary, `.vfs/graph/edges.jsonl`, MCP tools | code structure, dependencies, blast radius | input, not a marker — cite the query in `doc=`/`evidence=` |
| **running services** | proxy :9391, server :9092 `/health` | is it up, which commit is loaded | `witness=live:<endpoint>` |
| **git origin** | tags, releases, CI conclusions | what actually shipped | `witness=tag:*`, `release:*` |
| **provider consoles** | usage/billing pages | what a lane really consumed | `witness=provider:<page>` |
| **skills (this dir)** | `~/.hermes/skills/<name>/SKILL.md` | the procedure that was followed | `prompt=~/.hermes/skills/<name>/SKILL.md` |
| **backups** | backup prefix + `MANIFEST.txt` | what is recoverable | `evidence=<prefix/MANIFEST.txt>` |

Rule of thumb: **state → `row=`, promise → `spec=`, claim → `witness=`, judgement → `verdict=`, history → `memory=`.**

## DuckBrain integration (tagging, writing, citing)

- **Tag form:** `memory=/project/<project>/<slug>` — the leading slash is part of the key.
- **Write recipe:** `POST /api/memories` with `{key, domain, content}`; the author is taken from the token.
  Domains: `raw_note | person | event | concept | message | config`. There is no update route — append a new
  key version instead of editing history.
- **When to write a memory:** a decision with a reason, a lesson from a failure, a durable fact about a lane or
  provider. Not for task progress — that belongs on the board.
- **How to cite:** the marker's `memory=` field. Cite only keys that resolve; never invent a key shape.
- **Never make memory load-bearing.** A memory key is an *additional* citation; a reference inside the
  repository (`spec`/`test`/`doc`/`evidence`/`witness`) must accompany every memory citation. Unverified records do not appear at all.
- **Key conventions in use:** `/project/<project>/<event>-<YYYY-MM-DD>` for findings, `/sync/<project>/last-success`
  for sync markers, `/project/<project>/window-<stamp>` for time-bounded summaries.
- **Namespace choice is a trust boundary** — write into the namespace that owns the work, not a convenient one.

## Witness kinds (surfaces we cannot write)

`tag:<v>@origin` · `release:<v>` · `http:<code>+sha256:<digest>` · `path@origin:<path>` · `ledger:<predicate>` ·
`provider:<usage-page>` · `live:<endpoint resolves with >=1 hop>`

Prefer a witness over prose whenever the claim is about the world rather than about our own output.

## One call, four surfaces

| surface | source | question |
|---|---|---|
| code structure | Hilo graph (edges JSONL + query engine; 17 MCP tools) | what exists, what depends on what, blast radius |
| memory | DuckBrain namespaces | what we decided/learned (cited records only) |
| contracts | specs, docs, reports | what we promised |
| state | boards, manifests, verdicts | what we claim and what was judged |

Hilo's own design rules are binding while doing this: **index beside the source, never inside it**; edges are
append-only lines; the query engine is rebuildable cache, never the record. Heavy builds for it belong on its
designated build host, not the shared agent box.

**Report contradictions instead of merging them.** Board says complete / outside says untagged is the single most
valuable output this surface produces.

## Pre-completion checklist

- [ ] Every claim has a marker with `row=`.
- [ ] Every claim names a `witness=` or `witness=none:<reason>`.
- [ ] Nothing closes by reference.
- [ ] `verdict=` exists and binds to a `commit=` reachable from the published tip.
- [ ] The witness is visible in the most recent film; if not, the claim is stale whatever the row says.
- [ ] Any `memory=` citation resolves and is accompanied by a repo-local reference.

## Pitfalls (each observed in this fleet)

- **Filing non-completion as a completed task** — rows marked complete whose own text says no-go/absent.
- **Component-green masking outcome-red** — CI green while ~1% of traffic reached the router.
- **A stored digest read back as proof** — replay the command instead of trusting the digest.
- **A criterion authored by the completer** — a row with four criteria and a passing guard was still false.
- **Envelope-only thinking** — measuring only what we listed; take a film of the surfaces instead.
- **Text-as-state** — success strings and log greps are diagnostics, never truth.

---
name: coding-hermes-tools-usage
description: Use when editing code by hand — pick the toolsd verb.
version: 1.0.0
author: Bane + Hermes
---

# coding-hermes-tools — when to reach for them

`toolsd` is a small standalone toolkit of **code-modification primitives** (stdlib-only
Go, installed on PATH). The primitives are deliberately separate from any agent
harness: plain tools you can invoke from a shell, an agent, a script or a cron job.

**Nothing forces you to use them.** They are offered because each one is the best
answer to a specific task shape, and each exists because a silent failure mode is
otherwise common. Read the task you actually have, find it in the table, and decide.
If the plain way is genuinely better for your case, use the plain way.

## The decision table — task shape → tool

| Your task looks like… | reach for | why it is the right tool |
|---|---|---|
| a diff you did not generate, that might not apply cleanly | `toolsd patch` | strict parse, **no fuzz** — it refuses instead of corrupting |
| a change spanning **several files** | `toolsd apply` | atomic, all-or-nothing, with rollback — either all files land or none |
| two edited versions of the same text, common base | `toolsd diff3` | three-way merge, so you reconcile instead of picking a winner |
| change one known literal string, exactly once | `toolsd replace` | unique-match by default — no silent multi-hit replace |
| a long task that will touch files a sibling might also touch | `toolsd lease` | cross-session edit registry (`acquire`/`renew`/`release`/`status`) |
| work that must not disturb another checkout | `toolsd session` | one git worktree per agent (`start`/`end`/`list`) |
| an edit made blind to the codebase's symbols | `toolsd lsp` | `definition` / `references` / `check` |
| an edit whose success must be provable | `toolsd narrate` | turns a unified diff into a JSON/Markdown evidence block |
| before claiming an endpoint works | `toolsd probe` | bounded concurrency, rate cap, failures-as-data |
| file-system path surgery done by hand | `toolsd fsops` | the same operations, with guards |

## Discover the surface from the tool itself

Do not work from a stale list — ask the tool:

```
toolsd --help              # every verb, one line each
toolsd <verb> --help       # usage, WHEN TO USE, settings, examples, outcomes
toolsd describe --json     # the whole surface as data
```

## Two surfaces, same tools

The verbs reach you two ways. **Pick whichever is in front of you:**

- **CLI** — `toolsd <verb> …` on PATH. Always available, works in any shell, script or
  cron job. This is the surface that never disappears.
- **MCP tools** — in sessions whose toolset includes them, each verb is also a tool named
  `mcp__toolsd__toolsd_<verb>` (e.g. `mcp__toolsd__toolsd_patch`). Same verbs, invoked
  from the agent's tool list.

**MCP call shape** (this is what trips people up): every `mcp__toolsd__toolsd_<verb>` tool
takes exactly two arguments:

- `args` — the argv **after** the verb, one string per shell word, required.
  `toolsd apply edits.json` → `{"args": ["edits.json"]}`.
- `cwd` — optional working directory; defaults to the server's cwd.

So `mcp__toolsd__toolsd_replace` with `{"args": ["file.txt", "old", "new"]}` replaces one
occurrence in `file.txt`.

**If the tool is not directly in your list** (large sessions keep MCP tools behind the
`tool_search` bridge), reach it in three steps:

```
tool_search("strict diff apply")            # find the tool by what you want to do
tool_describe(["mcp__toolsd__toolsd_patch"]) # load its schema
tool_call({calls:[{name:"mcp__toolsd__toolsd_patch", arguments:{args:["change.diff"]}}]})
```

`tool_search` is mandatory before the first use of a bridge-deferred tool; after
`tool_describe` the schema is loaded and you call it. The CLI needs none of this — when
in doubt, a shell `toolsd <verb>` is one call instead of three.

## Two things that look like failure and are not

- **A refusal is a win.** `patch` refusing an inexact diff, or `apply` rolling back a
  partial multi-file write, is the tool doing its job: a corrupt or half-edited tree was
  prevented. Report it as an outcome, never as an error to retry blindly.
- **No-lease / no-conflict is a real answer.** `lease renew` on a holder with no record,
  or `probe` against a dead port returning `status: 0`, are truthful results — the tool
  tells you what is true rather than manufacturing a success.

## What this skill is NOT

Not a routing rule and not a required step. It exists so that when you look at a task —
*edit this file*, *edit this core* — the tool is **visible**, its purpose **legible**, and
you can choose it because it is genuinely the best fit. If the fleet uses these, it
should be because they earn it, and `toolsd metrics` (CHT-038) should show that rather
than a mandate.

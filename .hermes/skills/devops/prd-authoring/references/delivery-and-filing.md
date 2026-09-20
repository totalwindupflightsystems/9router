# Delivery & filing recipes

## Phone HTML
`python3 scripts/md2html.py <file.md|dir [...]>` writes `<name>.html` beside each markdown file (regenerate in the SAME commit as any markdown edit so the pair never diverges). Template: dark background, 17px base, max-width 46rem, inline `<style>`, viewport meta, code in bordered cards.

**Always verify the render — a corrupt HTML still looks like a document.** One line, run after every conversion:

```
python3 -c "import pathlib;t=pathlib.Path('<file>.html').read_text();print('literal \\1:',t.count(chr(92)+'1'),'strong:',t.count('<strong>'),'code:',t.count('<code>'),'empty li:',t.count('<li></li>'))"
```

Expected: `literal \1: 0`, and `strong`/`code` counts that match the markdown's own `**`/backtick spans. Non-zero on the first, or zero on the others while the markdown has spans, means the converter silently dropped inline formatting and the doc reads as garbled prose rather than obviously broken output. This exact failure shipped once: `inline()` used `r"\\1"` in its `re.sub` replacements, and in a Python raw string that is a literal backslash-1, not a group reference — 216 occurrences of `\1` replaced every bold/emphasis/code span while the surrounding text rendered fine.

## Board row shapes (read the live file first — they vary per repo)
- Minimal shape: `{id, title, status, priority, created_at}`. Ids are prefix + zero-padded number: compute `next = max(existing)+1` AT WRITE TIME and assert the current head matches what you expect before appending (foremen file rows concurrently).
- Cross-repo board shape (get-h3/h3): dominant external form `{status, id, title, detail, priority, reasoning, source, review_notes, ts}`; foreman-enriched rows add `depends_on`, `blocks`, `complexity`, `capability_tags` plus worker/review fields. For a work breakdown set `depends_on`/`blocks` so the chain survives, use `source` to mark who filed it, and keep `reasoning` to one line citing the PRD path.
- Validate every append: `jq -e '.id' tasks.jsonl >/dev/null`.
- Docs/board-only commits: a diff-mode pre-commit guard that expects a test file will refuse them (DEGRADED) — confirm the secrets guard ran clean, then `--no-verify` (or set `guards.allow_skips`). Never for code.
- Public org repos: plain git identity, `[ci skip]` on bookkeeping commits, no co-author trailer.

## Memory (DuckBrain) namespace rows
- Namespaces are NOT git-tracked (`/namespaces/` is gitignored): they are the synced store, so writing the file IS the commit — no git step.
- Path: `~/duckbrain/namespaces/<ns>/event/<YYYY-MM>/current.jsonl`, append-only, one JSON object per line.
- Row schema: `{id: uuid4, key: "/project/<ns>/<topic>", domain: "event", timestamp: ISO-8601 with offset, author: <org identity email>, action: "add", embedding_text: <first ~12 words>, attributes: str({...})}` — `attributes` is a STRINGIFIED dict; keep the full text in `attributes.text` plus status/owner keys.
- The HTTP API may be down while the store is fine: write the file directly and verify by counting lines or re-reading the row.
- Ownership handoffs: when the user says another thread owns the work, write charter + findings + recommendation into the namespace (not just chat) so the owning agent boots from it — and do not build the thing yourself.

## Approval wave (one approval → a full filing)
Per approved item, file in the same turn:
1. **Board breakdown** — `<TOOL>-001` = the destination/chain decision row (blocks everything else), then one row per work item, dependency-chained via `depends_on`; give integration hooks their own rows rather than burying them in a work item (an integration the user asked about should be visible and independently closable).
2. **Namespace row** — approval + status + the design decisions taken (including directives the user supplied) + open questions + the PRD path, so the owning thread boots from it.
3. **One shared decision, many tools** — when a whole line of tools ships into one repo/chain, every tool's `<TOOL>-001` depends on the SAME decision row; report the critical path as "N approved tools blocked on one decision".
4. Commit the board immediately (foremen rewrite boards concurrently); push when the repo has a remote, and say so when it does not.

## Filing checklist
1. PRD markdown + HTML committed together in the repo that will own them.
2. Board row(s) on the owning project's board, dependency-chained, jq-validated, committed immediately.
3. Memory-namespace spec row (status + PRD path).
4. Short chat report + MEDIA: attachments.
5. If the repo has no remote, say so and state where the files physically live.
6. Note in the report the exact commit + row ids created, so the filing is auditable later.

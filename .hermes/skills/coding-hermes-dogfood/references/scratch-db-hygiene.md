# Scratch-DB Hygiene for Real-Use Probes

Real use of an API-backed project routinely means rows land in the project's
actual database (a workspace, a group, test cards, a tenant). The run must not
corrupt the dev environment's standing data — but you also must not skip the
probe, because DB-visible state is exactly where the interesting defects hide
(orphan rows, non-atomic creates, unbounded accumulations). The contract:

## Scope every probe row to a throwaway parent

1. Before probing a create/class surface, create a dedicated parent object
   (workspace/project/tenant) whose name marks it as disposable — a fixed,
   greppable prefix like `df-<lane>-ws`, never a random name you will forget.
2. Drive every create through that parent id. Rows you cannot scope (global
   settings, channels) get at most read probes plus one delete/undo attempt.
3. Record the parent id in the scratch notes file at creation time — the
   cleanup step at the end of the run depends on it surviving to then.

## Clean orphans you created; disclose what you touched

4. After any 500/failure from a create endpoint, check the backing store for
   partially-inserted rows before retrying (see the SKILL.md pitfall on
   non-atomic creates). Deleting YOUR scratch-parent's orphans is part of the
   probe, not a rules violation — the never-fix-code rule bars editing source,
   not cleaning data you caused in a throwaway scope.
5. Do NOT touch orphan or standing rows outside your parent scope, even when
   they look like the same bug: photograph them (`SELECT … LIMIT 5`), cite the
   count in the finding row, and let the foreman clean/fix. Your cleanup is
   scoped; theirs is authoritative.
6. Name every DB mutation in the report's closing line ("scratch DB mutations
   confined to workspace df-…") so a reviewer can audit the run's footprint
   from the report alone.

## Read DBs through the project's own plumbing

7. Prefer `docker exec <db-container> psql/…` (or the project's CLI) over
   host psql with guessed credentials — the container already has the right
   connection context, and guessing host credentials both wastes time and can
   read the WRONG instance when several compose stacks share a host.
8. Keep the query read-only by default. The only writes are: the scoped probe
   rows themselves, and deletion of rows you created.

## Isolate the scratch environment the way the product resolves roots

9. **Verify the isolation env var actually redirected the store before writing
   anything.** Start the scratch daemon, issue one create, and check WHERE the
   row landed (ls the expected scratch dir; read the response's path field)
   before continuing — a docs-taught env var can be dead at HEAD while the
   config resolver honors a different knob entirely, and your 'scratch' data
   then lands in the project's real store paths. Grep the config-resolution
   source (resolve-root/resolve-paths functions) for which env vars the
   resolver actually reads; docs and examples are not authoritative — the
   resolver is. If pollution landed before you noticed: remove only the
   rows/dirs you created, restore any file the run touched, and disclose the
   incident in the report.
10. **A namespace/workspace auto-created by a write is often INVISIBLE to the
   caller** — the 201 response may not name the effective parent, and the only
   trace is a server-side log line. Create the parent explicitly through the
   documented create endpoint before writing, and on a fresh box never assume
   the default parent name matches your dev box's — query the parent you
   WROTE to, not the one you meant.

## Event-sourced stores: the commit window gates every past-state probe

11. **Stamp the past-timestamp AFTER the write AND after its commit window.**
   Event-sourced/git-backed stores land writes on a batching timer, not
   inline: an as-of/time-travel query at or before the write instant
   correctly errors ('no commit found at or before') because the commit does
   not exist yet. Wait out the documented batching window (config, not
   guesswork) before freezing any timestamp you will query, or every smoke
   arm 400s and reads as a product defect. Derive the script's operation
   sequence from the LOCAL proven run, never from memory — skipping a create
   step or mis-stamping one timestamp burns a full remote arm per mistake;
   write the arm script once, locally verified, then transfer it.

## Scale-check the headline surface at production size

12. **A toy-scale green proves correctness, not performance — re-run the
   headline operation read-only against the production-size store before the
   verdict.** The same endpoint that answers in 180ms on a 2-row scratch can
   take 7s p50 warm at the prod row count, and only the real-scale number
   makes the verdict's 'is it fast enough' answer honest. Use real auth and
   the real daemon, read-only operations only, n>=10 timings, and check the
   binary's version stamp (`--version` vs `git rev-parse HEAD`) first — a
   stale installed binary measures old code, not the product.

## Honest re-verification rows

13. **A row filed as 'prior defect re-verified' must claim only what this
   run's smoke actually exercised.** When a prior run's finding shows
   complete on the board and your fresh-box smoke drives a different arm, the
   new row says 'install channel green + that surface UNVERIFIED this run',
   never 'still broken' — and if a row was drafted over-broad, rewrite it
   before commit. The board is the evidence base for later runs' angle
   selection; an over-claimed row makes the next run skip a defect that is
   actually live.

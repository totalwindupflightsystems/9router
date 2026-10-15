# Run Setup Integrity — Target Resolution, Binary Freshness, Install Walls

Depth for three run-setup failure modes that cost a whole tick when hit blind.

## 1. Misseeded lane prompts: which target is real?

A dogfood tick's target identity can come from three places, and they can disagree:

1. The tick header (`<lane>-dogfood-<timestamp>` in the scheduler tick row) — names the LANE, not the target.
2. The prompt's executor block ("You are the X-dogfood lane… Target project: Y… Workdir: Z") — copied along with the body.
3. The stored `prompt` in the scheduler DB `projects` row for the named lane — what the scheduler actually serves.

Decision rule: when 2 and 3 disagree (or the executor block names a different project than the lane name implies), the stored `prompt` for BOTH candidate lanes is the authority — a prompt body copied between lanes makes the header and the executor block lie together, and the body the DB actually carries names the real target. Verify with:

```sh
sqlite3 ~/.hermes/coding-hermes/scheduler.db "select prompt from projects where name='<candidate-lane>'"
```

The misseeded prompt itself is a config finding: report it to the config owner (lane prompts are fleet-config territory); never edit scheduler state from a dogfood lane.

## 2. Binary freshness for re-proofs

A fix-row re-proof needs a binary whose build stamp is at-or-after the fix commit. Rules:

- Read the binary's `--version` build stamp before crediting ANY verdict to "HEAD" — HEAD moves mid-run (sibling lanes commit between your HEAD read and your build), and a stale binary proves the pre-fix world, not the fix.
- A stale binary is not waste: it is the A-side of the A/B re-proof. Reproduce the filed defect on it first; the post-fix side must then show corrected behavior on the same corpus, same commands.
- When no fresh HEAD binary exists anywhere and local is the only path, build incrementally into the repo's OWN target cache: scoped (`-p <crate>`), with stray env target-dir overrides unset (`env -u CARGO_TARGET_DIR`) — a harness-level override silently redirects the build to a cold cache and recompiles the heavy dependency tree (duckdb-class, tens of minutes) from zero, burning the tick.
- Run the build as a background terminal from the start; poll cheaply. Never hold a foreground timeout open on a Rust workspace build.
- Prefer building on the designated CI/build host per the repo's own AGENTS.md when the local box policy forbids heavy builds — the ephemeral-bunker install agent can also be the fresh-machine builder when its memory allows (see §3 for when it does not).

## 4. Resume ownership: grade /tmp-recovered artifacts and live processes BEFORE adopting them

A mid-tick context compaction leaves the resumed turn with /tmp artifacts and running processes
it cannot attribute from the transcript. Adopting a sibling lane's work as your own files
another lane's findings on this project's board; adopting a sibling's server as 'your prior
turns' work' drives probes against the wrong instance.

- **Grade every /tmp row file for OWNERSHIP before appending it.** Sibling lanes share /tmp and
  stage lookalike row JSON next to your own artifacts. Check each staged row's `actor`/
  `created_by` field and its id family against the target board's own namespace (grep the board
  for the id prefix — e.g. a board whose dogfood rows are `DF-<PROJ>-<n>` should reject a staged
  `DF-<date>-<n>` family); an id that does not continue the board's family names a different
  lane's finding, and landing it cross-files work the target board's foreman cannot own.
- **Confirm a running server/spawn is YOUR earlier-turn work before reusing it.** Match the
  scheduler tick row's `session_id` to this tick's id (a zombie-looking 'running' tick that
  carries your session id is this very session, not a stranded sibling), and only then restart
  /re-probe the process it left. A sibling's agents on a shared bunker host are likewise not
  yours — verify by id before probing or destroying.
- **Disclose the resume handoff in the log entry.** An entry that says 're-proof run; earlier
  turns same day committed <sha>' lets the next reader know the run spanned a compaction, so
  the foreman does not double-count two runs.


A fresh-source build that dies mid-dependency with a bare compiler-driver abort (cc-rs: `signal 6 (SIGABRT) (core dumped)`, no error text) on a memory-capped agent or container is a finding about the documented install path, not a flake to silently retry:

- Mechanism: agent/container memory caps OOM-kill the compiler; cc-rs swallows the kill and surfaces SIGABRT with no hint. The user sees a build that dies at an arbitrary TU with no cause.
- Grade by same-host sibling comparison before filing: a sibling run's install PASS on the SAME host near the same time means the wall is non-deterministic (memory/contention dependent) — file "install premise unproven on ≤N-GB-memory hosts" and cite the sibling PASS in the row. Never report it as a universal failure; never quietly re-run on a bigger host and pass.
- No sibling PASS exists → the failure stands on its own; file it with the exact abort line and the host's memory cap.
- Fix directions for the row: a documented minimum build memory in the install docs, a low-parallelism build recipe (fewer parallel jobs / split uber-TU feature), and build tooling that names its likely cause instead of a bare signal.
- Report install/build seconds only when host load was clean; a wall-clock from a loadavg-saturated host is not a number — say the measurement is polluted instead of quoting it.
- Cleanup discipline still applies: destroy the ephemeral agent, then re-verify via the list/status surface and the residue counters before writing any cleanup claim.

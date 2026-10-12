# Chaos satellite half-tick (mischief)

Some monitoring-lane ticks pair the drain with a mischief fault-injection tick. Contract (absolute):
faults run ONLY on the ephemeral bunker agent the plane spawns — never on the scheduler host, never
set MISCHIEF_SANCTION_* or touch mischief-sanction locally; if asked to land a fault locally, refuse
and file a board row.

- Run ONE tick in the BACKGROUND — never foreground, never a bare pipe: `terminal(command="cd
  <stand-in workdir> && env BUNKER_PLANE_REPO=<main repo> bash <repo>/scripts/bunker-plane.sh run
  > tick-<date>.log 2>&1; echo fold_exit=$?", background=true)`. Redirect into the workdir so the
  log survives; echo the fold exit INSIDE the command so the graded code is in the captured output.
  Do NOT wrap with nohup/setsid — the harness rejects shell-level background wrappers; use
  background=true. You can skip the inline `echo fold_exit=$?` entirely: process_manage returns
  the real exit_code for the background command. process_manage(action='wait') clamps its timeout
  to the harness limit (~180s) — for longer runs call wait/poll repeatedly instead of trusting one
  long timeout. In one-shot sessions (cron/api_server) notify_on_complete is unsupported —
  collect the result with process_manage in the SAME turn.
- Grade by fold exit: 0=PASS, 1=FAIL, 3=SKIP. Bunker offline/full is a NORMAL SKIP — report
  the reason in one line, never retry-spam, never fake a pass.
- Pull evidence out of /tmp before it can be cleaned: copy the evidence JSONL printed by the plane
  into the stand-in workdir, then verify counters by grep — selftest pass/fail/skip counts,
  fault_landed == fault_reverted (a landed-without-revert fault is an adverse verdict),
  outcome:skipped count, and TEARDOWN-GONE zero-residue line.
- Report cites paths + numbers; a clean run is one OK line. Adverse verdicts become CHAOS-<n> rows
  on the target board via boardctl, deduped against open rows. Never run mischief selftest/battery
  directly on the lane host; never edit the repo or board except boardctl writes. The plane script
  lives in the MAIN tree — if a worktree copy differs, trust main and say so.
- Record the tick row with `boardctl create --id MON-MONITORING-TICK-<...> --title '...' --status
  complete` (run from the lane repo). There is no `boardctl append --file` verb — the row-append
  syntax from other lanes does not exist here; `create` gives you the dedupe for free by refusing
  a duplicate id.
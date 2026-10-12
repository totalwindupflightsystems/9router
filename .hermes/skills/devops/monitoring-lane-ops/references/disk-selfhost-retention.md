# DiskWillFillIn24h when the firing instance is the scheduler host itself

Context: 2026-10-12, alert fired on `karahermes-mde-7840hs`. Root cause was Hermes state
retention, not a leak. This page is the attribution ladder for that case.

## The signature

`~/.hermes/state-backups` is an UNBOUNDED zst snapshot ring: each snapshot is ~9.8-10.6 GB,
written on a 6h cadence, with no pruning. 13 files = 125 GB seen 2026-10-12. Alongside it
`~/.hermes/state.db` itself grows un-vacuumed (~29.8 GB, mtime tracking the last gateway write).
Secondary contributors rewritten in the same window: `task-router/data/metrics.jsonl` (~4.3 GB)
and `~/.hermes/coding-hermes/scheduler.db` (~2.8 GB). `~/.hermes` was ~188 GB of a 717 GB `/home`.

## Attribution ladder

1. Read avail at `offset 6h` / `offset 24h` / `offset 3d`, and `deriv(...[1h])` / `[6h]` / `[24h]`.
   A steep 6h deriv next to a flat 24h deriv means predict_linear is extrapolating ONE write burst.
2. Name who actually wrote inside the rule's window — this is the step `du` cannot do:

   find /home/kara -xdev -type f -newermt '-6 hours' -size +500M -printf '%s %p\n' | sort -rn | head

3. Then size the ring: `du -sh ~/.hermes/state-backups` and `ls | wc -l`.

## How to report it honestly

The rule is `predict_linear(node_filesystem_avail_bytes[6h], 86400) < 0`. If the 6h window holds a
snapshot write, the projection goes deeply negative (-384 GB observed) while the 24h deriv is flat.
Say both facts: it is NOT a true 24h-to-full emergency, AND it IS a real finding — an unbounded
retention ring on a live disk. Do not close it as a false positive.

## Action boundary — OWNER GATED

`state.db` is live gateway state and the snapshots are the restore path. Vacuuming or pruning
touches production agent state, so this lane files the row and stops. Pair the finding with the
restore-before-delete rule (see RESTORE-RUNBOOK.md): prove the newest snapshot restores BEFORE
deleting older ones. Suggested fix for owner approval: cap the ring by count or age, VACUUM
state.db outside a tick window, and stop duplicating the ring into the host backup-stage copy.

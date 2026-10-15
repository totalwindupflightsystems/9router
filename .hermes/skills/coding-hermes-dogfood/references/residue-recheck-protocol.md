# Post-destroy residue recheck protocol

The ephemeral install leg ends with destroy; the host's reconciler lags, and the
recheck has distinct failure shapes that need different filings.

## Procedure

1. Destroy, confirm the CLI reports removal (and the local key removal).
2. Recheck `bunker status` (or the host's own residue line) after ~90s — the
   reconciler sweeps on a ~60s cadence, so the first post-destroy read
   over-reports.
3. Read AGAIN after a further interval (~2min). Two reads minimum.

## Attribute the numbers, then file

- Your agent's entries VANISHING across reads = the reconciler working. Normal.
  No finding.
- Orphans that SURVIVE all rechecks = the classic residue finding (survivors of
  your or prior legs). File with the counts.
- The count RISING across rechecks with none of your own spawns in the window =
  accumulation from elsewhere on the host. That is a host-hygiene observation,
  NOT a failed destroy of your agent: your own entries were removed. File it as
  P2/P3 for the bunker owner, carrying the numbers from EACH recheck read
  (timestamped) as evidence, and state explicitly that your agent's artifacts
  were gone.
- Never collapse these into 'residue present' — the filing semantics differ and
  the bunker owner triages on the shape.

# get-h3 Agent-Ops Line — PRD Index

Eight tools that turn a fleet's operational exhaust into queryable, provable truth. Same spine: evidence-first, honesty-labeled, pocket-scale. Each PRD: value case, user stories, success criteria replayed against real fleet incidents.

| # | Tool | The question it answers | Effort |
|---|---|---|---|
| B1 | [logsey — log-corpus indexer](B1-log-corpus-indexer.html) | "What happened on this box?" (one query, not six greps) | M |
| B2 | [pulse — metric-log correlator](B2-metric-log-correlator.html) | "What was the machine doing when it failed?" | M |
| B3 | [lore — runbook compiler](B3-runbook-compiler.html) | "How did we fix this last time — and does it still work?" | M-L |
| B4 | [digest — fleet digest builder](B4-fleet-digest-builder.html) | "What needs me today?" (one artifact, not ten boards) | S-M |
| B5 | [sentinel — config-drift sentry](B5-config-drift-sentry.html) | "Which config drifted from blessed — before the restart?" | M |
| B6 | [relay — cron & delivery authority](B6-cron-delivery-authority.html) | "Did the artifact ARRIVE — not just, did cron exit 0?" | M |
| B7 | [forge — lane-health authority](B7-lane-health-authority.html) | "Which provider lanes are proven healthy — and rotate keys in one transaction" | M |
| B8 | [evidence — session evidence vault](B8-session-evidence-vault.html) | "Which agents/models/lanes ship VERIFIED work?" | M-L |

**The line composition:** logsey proves the box · pulse proves the moment · forge proves the lanes · relay proves delivery · sentinel proves config · lore compiles the lessons · digest carries it to humans · evidence proves the work.

Each is standalone; pairs compound (pulse joins logsey, digest cites everything, evidence feeds lore and digest).

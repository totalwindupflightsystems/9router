# 11 — Human-in-the-loop inventory

The normal hourly path contains no approval. Human steps are configuration, escalation review, and fault response; none is left as an unowned question.

| Step | Who | SLA/trigger | Absent behavior | Audit |
|---|---|---|---|---|
| provide/approve watched root ids and paths | operator | before first enablement; on root lifecycle change | config validation fails fast; no empty/default root | config plus lifecycle command event |
| close ESC-01 transient-file guarantee | product owner | before implementation acceptance | D-017 retained-file default remains provisional; handoff NOT-READY | escalation status and replacement/supersession decision |
| close ESC-02 whole-host alert coverage | product owner | before production acceptance | D-023 local-only failure coverage remains provisional; handoff NOT-READY | escalation status and monitoring config |
| select/probe digest destination U-002 | integration owner | before live posting | durable local outbox accumulates; no remote-delivery claim | redacted endpoint probe and config version |
| classify filename disclosure U-003 | security/product owner | before live posting | `count-only` mode | approved path_mode and sample classification |
| run target capacity/platform probes U-001/U-004 | implementation/operations owner | before build/production gates named in rows | Python choice and numeric thresholds remain provisional/unset | captured probe transcript |
| respond to critical store/root/service alert | operator | on receipt; no unstated 24/7 SLA | condition remains open, retries stay bounded, pending data is not purged | incident id, journald, delivery attempt, recovery transition |
| approve explicit abandonment of a pending digest/root state | operator | exceptional, by exact id with reason | data remains pending/retained | append-only operator-action record |

Contact/escalation map: one operator is the only inferred responder. No second person, paging vendor, or 24/7 SLA is invented. The absence of an external observer is itself ESC-02, not a hidden human dependency.

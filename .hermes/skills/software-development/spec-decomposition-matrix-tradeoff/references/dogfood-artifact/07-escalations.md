# 07 — Escalation envelopes

Autonomous mode is active. Both defaults are the most reversible containment options and are recorded as provisional decisions; neither question was handed back as a questionnaire.

## ESC-01

ESC-01: Must “do not lose anything” include a file created and deleted entirely while the process or host is down?

  Option A — Retained-file reconciliation: favours one-process simplicity. Costs loss of downtime-transient create/delete events. Commits you to a guarantee covering committed records and files still present. Breaks any workflow where a short-lived file is itself the only evidence.
  Option B — Independent durable change journal/producer manifest: favours event completeness. Costs a privileged kernel/audit component or a producer-side durable manifest, another lifecycle, more disk, and a migration/test surface. Commits you to operating an additional observation mechanism. Breaks the strict reading of “one box and no extra services” if implemented externally.

  Our read: risk appetite for short-lived evidence is the hinge. The seed strongly favours simplicity and only asks for an hourly digest, so we would pick A unless transient files carry business evidence.
  If unanswered by implementation start: proceed with Option A (D-017, `provisional: true`) because it is explicit, reversible, and does not pretend a stopped observer can see events.
  Risk of that default: a file can appear and disappear during downtime without any record.

Status: PENDING-OWNER. Links: T-007, C-001, D-001, D-002, D-017, D-024.

## ESC-02

ESC-02: Must “tell me when it has stopped working” include total host/power/network loss, not only daemon crash, hang, and boot failure?

  Option A — Local systemd supervision plus one-shot failure notifier: favours one-box simplicity. Costs a blind spot when the entire host or its network is gone. Commits you to process/service-level coverage only. Breaks a promise of universal outage notification.
  Option B — External dead-man heartbeat: favours host-level coverage. Costs an external endpoint/service, credential, egress, heartbeat policy, and its own false-positive/runbook burden. Commits you to one external dependency. Breaks the strict no-extra-service preference.

  Our read: coverage versus simplicity is the hinge. The seed explicitly prefers one box, so we would pick A while naming its limit; B is required if silent host loss is materially harmful.
  If unanswered by production acceptance: proceed with Option A (D-023, `provisional: true`) because an external heartbeat can be added without changing the local state model.
  Risk of that default: the operator receives no remote signal when the box itself cannot run the notifier.

Status: PENDING-OWNER. Links: T-008, C-001, D-011, D-012, D-023, D-024.

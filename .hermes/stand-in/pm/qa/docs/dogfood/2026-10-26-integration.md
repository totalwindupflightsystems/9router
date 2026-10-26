# qa-audit dogfood integration report — 2026-10-26

Tick: qa-audit-dogfood-2026-10-26-15-11-01
Lane: qa-audit-dogfood
Resolved scheduler product workdir: /home/kara/.hermes/stand-in/pm/qa
Resolved owning board: /home/kara/.hermes/stand-in/pm/qa/.coding-hermes/board
Resolved git root: /home/kara
HEAD at verification: c4b6a56e702a258a2576ddaef6aa079938d944e0

Verdict: UNKNOWN-VALUE for qa-audit itself; PROMISING-BUT-ROUGH for the underlying bunker-qa harness.

Promise

A fleet operator can run the QA pipeline against the scheduler-resolved qa-audit target, install it on an ephemeral bunker machine, and receive a correctly identified, complete, durable battery verdict.

What a user actually did

1. Read the existing usage skill and dogfood records. The public entry points are qa_discover.py, bunker-qa.sh status, bunker-qa.sh launch, and bunker-qa.sh collect.
2. Ran `python3 ~/.hermes/scripts/qa_discover.py 1`: rc=0; it returned one candidate, auger-foreman, and excluded qa-audit-foreman as workdir-not-git. This confirms discovery is a scheduler-wide selector, not a qa-audit product test.
3. Ran `bash ~/.hermes/scripts/bunker-qa.sh status`: rc=0; `bunkerd=active docker=yes act=no uidmap=yes` on bunker-mvp.
4. Ran the required target path literally: `bash ~/.hermes/scripts/bunker-qa.sh launch /home/kara/.hermes/stand-in/pm/qa`. It refused before spawning: the path is a subdirectory of `/home/kara`, and syncing the parent would grade the wrong product. rc=1; no battery was run.
5. Ran the documented scope workaround to determine whether it preserves target identity: `BUNKER_QA_SUBDIR=.hermes/stand-in/pm/qa BUNKER_QA_EVIDENCE=/tmp/qa-audit-dogfood-20261026-1511-scoped.jsonl bunker-qa.sh launch /home/kara`. Launch completed rc=0 in 29.76s, but identified the project as `kara`, not `qa-audit`, and spawned agent acdd91d8.
6. Collected that battery: `bunker-qa.sh collect --evidence /tmp/qa-audit-dogfood-20261026-1511-scoped.jsonl` returned rc=0 in 54.51s, 19 rows. Agent acdd91d8 was absent from `bunker info` and the subsequent `bunker list --status all` census, so teardown was verified.

Battery result and boundary

The scoped run is not a qa-audit product verdict. It is evidence for the existing open row QA-AUDIT-HARNESS-002 because the runner graded the parent as project `kara` rather than preserving `qa-audit` identity.

Observed cells from the 19-row collection:

- repo-head: OK, HEAD c4b6a56e702a258a2576ddaef6aa079938d944e0
- fresh-install: INFO / ENV-BLOCKED, pnpm missing and no sudo on the agent
- ci-pass: UNVERIFIED, native runner missing; suite never ran
- upgrade: FAIL, previous-release command used npm but npm was missing
- docker-deploy and chaos-shutdown: N/A, no compose file
- ui-probe: N/A, no web UI detected
- chaos-disconnect: UNVERIFIED, prerequisite suite did not run
- chaos-corruption: N/A, no database/state files
- chaos-resource: UNVERIFIED, runner missing under the cap
- chaos-errorpath: INFO, no start command detected
- collect: OK, 19 rows pulled, deduplicated, and the agent destroyed

This is not a product failure for qa-audit. The evidence is a target-resolution failure plus an agent environment that could not run the detected pnpm/npm surface. The original no-override command is the valid product-target probe and did not reach any cell.

Install leg

PARTIAL, not PASS and not silently skipped. The standard skill host bunker3 / las-bunker-03 timed out. bunker2 was reachable and reported bunkerd active; bunker4 timed out; bunker-mvp was reachable and active. Therefore the fleet had a usable alternate host and the explicit SKIPPED-install-bunker condition was not met. The alternate bunker run still did not prove qa-audit installability: it ran the parent project as `kara`, and the agent lacked pnpm/npm. No credentials, permissions, repository visibility, or scheduler state were changed.

Performance

- `bunker-qa.sh status`: cold one-shot 0.42s real; warm hyperfine, 5 runs after 2 warmups, mean 427.9ms ± 1.6ms, range 425.9–429.8ms.
- Literal target refusal: 0.03s real; this is a fast and useful fail-closed guard.
- Scoped launch: 29.76s real. The launch process used 0.24s user and 0.29s system time; the wait was bunker transfer/provisioning, not local compute.
- Scoped collect: 54.51s real. The collector used 0.07s user and 0.10s system time; the wait was agent pull/teardown, not local compute.

No PERF row was filed. The slow portions are remote provisioning and teardown, with near-zero local CPU; profiling a local hot path would not explain the user-visible wait. The target-identity defect is already owned by QA-AUDIT-HARNESS-002.

Findings and existing ownership

QA-AUDIT-HARNESS-002 — re-proved, no duplicate row. The required scheduler-resolved target path refuses as a subdirectory; the scope workaround changes the evidence identity to `kara` and does not produce a qa-audit battery. Fresh evidence: `docs/dogfood/evidence/2026-10-26/qa-audit-scoped.jsonl` and `docs/dogfood/evidence/2026-10-26/target-resolution.txt`.

No new row was minted because this is the same defect already owned by QA-AUDIT-HARNESS-002. This read-only lane did not edit board rows or events.

Harness identity caveat

The home checkout had unrelated in-flight changes at verification time, including a modified `.hermes/scripts/bunker-qa.sh`. The committed HEAD blob sha256 was baf98edf6646aeb01db31f8bf3570d2d5ea8947885fa8544dc1747d3550b21f5; the live script used for the battery was 76559a9e3a399d484b95a04ea4d92041c5cceba8133d3b2c131d22a3aee9f9b1. The fail-closed target guard is present in the committed HEAD source, but the cell results must be treated as evidence from the live dirty harness, not as a clean committed-harness release verdict.

Trace

ch:trace row=QA-AUDIT-HARNESS-002 spec=none:no-shipped-spec wave=qa-audit-dogfood-2026-10-26-15-11-01 test=live:literal-target-and-scoped-bunker-battery doc=docs/dogfood/2026-10-26-integration.md prompt=~/.hermes/skills/coding-hermes-dogfood/SKILL.md evidence=docs/dogfood/evidence/2026-10-26/qa-audit-scoped.jsonl witness=live:bunker-mvp verdict=none:read-only-dogfood-no-judge commit=106396116f0568767b87315a88e650c18fa157d3 memory=none:no-duckbrain-write-this-tick

Closeout

The foreman was not woken. No code, board row, board event, repository visibility, permission, credential, or scheduler state was changed. The only intended repository write-back is this integration report, the durable evidence copy, the diagnostics addendum, the usage-skill addendum, and the canonical dogfood-log entry.

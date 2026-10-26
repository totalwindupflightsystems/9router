# 9Router dogfood — current HEAD real-use run

Date: 2026-10-26 15:11 UTC
Target: 9router, federation branch
HEAD: e6003215bf35d0ca1031dac6aaeb463d640dc369
Promise: a user can install 9Router, start the gateway, authenticate, discover usable models, and send OpenAI-compatible requests through `/v1`.

## Verdict

PROMISING-BUT-ROUGH / PARTIAL. The current tree starts and serves the health, version, model-discovery, login, and embedding-discovery routes. A fresh instance reports the current version (`0.5.111`) and a single model (`mmf/mimo-auto`). The real completion path was not proven because the only advertised model has no configured provider on the clean instance and the current host requires an API key for `/v1`; no provider credential was minted or changed for this run.

## Real-use path

A detached worktree at the target HEAD was used for the clean local leg. `npm ci` completed and produced a 925 MB `node_modules` tree. The isolated server was started with `HOME=/tmp/9router-df-home`, `DATA_DIR=/tmp/9router-df-data`, and port 20226.

Observed on the isolated current-HEAD server:

- `/api/health`: HTTP 200, `{"ok":true}`.
- `/api/version`: HTTP 200, `currentVersion=0.5.111`, `latestVersion=0.5.111`, `hasUpdate=false`.
- `/v1/models`: HTTP 200 with one advertised model, `mmf/mimo-auto`.
- `/v1/models/embedding`: HTTP 200 with an empty data list.
- `/v1/models/info?id=mmf/mimo-auto`: HTTP 200 with the model metadata.
- Login with the documented source fallback password on the isolated empty data directory: HTTP 200, `success=true`, `mustChangePassword=false`.
- Unauthenticated `/v1/chat/completions`: HTTP 401 with an OpenAI-shaped `authentication_error` / `invalid_api_key` envelope.
- Invalid-key `/v1/models` on the isolated instance: HTTP 200 with response times of 106 ms, 14 ms, 13 ms, 12 ms, and 15 ms across five calls. This arm is not a valid auth check because the isolated environment does not pin `REQUIRE_API_KEY`.

The clean server process exited before the authenticated key-and-completion continuation could be completed. No provider node, provider credential, client key, or persistent user data was changed in the target checkout or its real data directory.

## Install leg

The required `bunker-qa.sh` leg ran on `bunker-mvp`, agent `e660f02d`, against QA-HEAD `e6003215bf35d0ca1031dac6aaeb463d640dc369`. The battery completed and the agent was verified absent afterwards (`bunker info e660f02d` returned `not_found`; the server census no longer listed it).

The evidence file is `/tmp/bunker-qa-evidence-20261026T152349Z-1329715.jsonl`.

Relevant cells:

- repo-head: OK, exact target SHA recorded.
- toolchain-bootstrap: OK for Go 1.27.3, Node 22.22.3, npm 10.9.8, gcc/g++, make, jq, and Docker Compose.
- fresh-install: FAIL from the harness detector, despite install rc=0 and 46 packages added in 2 seconds: `no artifact found (toolsd not in PATH, PREFIX/bin/toolsd missing, or zero-size)`. `toolsd` is not the 9Router artifact, so this does not prove a 9Router install failure; it leaves the product install result unverified by this battery.
- ci-pass: FAIL with `no triggerable workflow` / native rc=228.
- upgrade: FAIL before product use because the previous release tree would not build in the streamed battery (`npm ci ...` rc=228).
- ui-probe: FAIL from the harness during Next `/login` compilation (`307` to `/login`), not a completed UI assertion.
- chaos-disconnect: UNVERIFIED because ci-pass failed first.
- Docker lifecycle cells: SKIPPED by the controller-live-host safety gate.

This is an explicit partial install result, not a silent install pass. The target's own install/smoke path needs a follow-up on a clean agent or a battery detector that understands the Node/Next artifact.

## Performance

No performance row was warranted. Warm localhost route calls were in the low-millisecond range after startup; the first `/v1/models` call was under one second and subsequent calls were about 20 ms. Nothing measured was slow enough for a user to notice, and no profile was justified. The install battery's 2-second npm step is a harness timing, not a complete product-install proof.

## Findings for the owning foreman

No new board rows were written because this is a read-only dogfood lane and the observed install/CI/UI failures are not yet attributable to product code. Existing open release/install work remains relevant:

- REL-9ROUTER-017: current release readiness is still pending/no-go; this run adds exact-HEAD evidence that the fresh QA battery has no triggerable workflow and an ungradeable artifact detector.
- SUP-CRED-20261020-9R: OpenCode Go credential remains an external live-state blocker; not exercised or changed here.
- The previously closed fresh-install catalog findings should not be reopened from this run: current HEAD's isolated empty instance advertised one model rather than the older 824-model catalog, so the earlier published-package recurrence was not reproduced on this tree.

## Friction

Friction count: 4. A new user must distinguish the source fork from the published package, understand that `/v1` auth may be enabled independently of dashboard login, configure a provider before the one advertised model can complete, and work around an install battery whose artifact detector targets `toolsd` rather than 9Router.

The exact command/evidence trail is recorded in `docs/dogfood/diagnostics.md` and the canonical run history in `.coding-hermes/dogfood-log.md`.

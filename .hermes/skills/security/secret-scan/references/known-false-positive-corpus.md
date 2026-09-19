# Known False-Positive Corpus (verified)

Recurring scanner flags that have been verified FALSE POSITIVES multiple times (as of 2026-08-21, scanner-v2, 24h diff-window). When a flag matches one of these, re-confirm with the listed probe and move on — do NOT re-investigate from scratch.

## How the scanner re-flags FPs

- The scanner matches **diff-ADDED lines within the 24h window** (pickaxe semantics), not just working-tree content. A known FP re-flags whenever its **carrier commit** (or a newer commit whose diff re-adds the line, e.g. board rewrites) stays in-window. Working-tree content may be byte-identical.
- **Attribution probe** — find which in-window commit carries the re-flag:
  ```bash
  git -C <repo> log --since="<SCAN_TIME minus 24h>" --format="%H %ci %s" -- <file>
  # then per commit:
  git -C <repo> show <commit> -U0 -- <file> | grep -c "<match-string>"
  ```
  Commits with >0 added lines carry the flag; siblings with 0 are context-only.
- **Exit code 1 = findings present** (normal scanner behavior), not a crash. Off-slot fires happen; SCAN_TIME is authoritative for file naming and scan numbering.

## Active FP classes (re-flagging as of 2026-08-20)

### 1. off-by-one answer-corpus prose dummy keys (openai_key / aws_key)
- **File**: `data/answers/1133-gitreins-judge-tier1-scans-retired-parquet-mirrors.json` (mirrored rows in `data/answers.jsonl`)
- **Values**: `sk-a1b2c3d4e5f6g7h8i9j0` — 20-char sequential dummy (real OpenAI keys are `sk-` + 48 random chars), explicitly described in the same solution text as "the literal dummy key … in a test fixture" (answer documents replacing it with `REDACTED_FAKE_KEY`). Older: `AKIAQWERTYUIOPASDFGH` (QWERTY keyboard row, answer 1065 evidence), `sk-abcdef0123456789abcdef` (sequential hex), `sk-abcdefghijKLMNOPQRSTU` (20-char mixed-case sample; class-1265 solution text explicitly calls it "a real mixed-case key sample" used to exercise the scanner's regex), `sk-premise-verification` (all-lowercase prose quote).
- **Carrier**: "data: sync answer corpus" commits (e.g. `5042899`, 2026-08-18 04:00:14Z) — re-flags until the carrier ages out of the 24h window. Latest: `b918ed9` 2026-08-25 04:00:30Z (class 1265 `gitreins-secrets-board-commit-builtin-scanner`, scan #41 — flagged in BOTH the `data/answers.jsonl` record AND the `data/answers/1265-….json` mirror).
- **Probe**: `search_files` for `sk-[A-Za-z0-9]{40,}` across the repo → **0 matches** = confirmed dummy. The dummy appears only in prose quoting a test fixture.
- **Sibling value in the same class — GR-GAP-005 planted AWS key (scan #98, 2026-09-18)**: row `GR-GAP-005` ("P0 SECRETS HOLE: guard misses non-`sk-` secrets … Reproduced: planted `AWS_ACCESS_KEY_ID=<value>` in a staged `.env`") carries `AKIA1234567890ABCDEF` — `AKIA` + 10 sequential digits + `ABCDEF`, i.e. a self-describing planted fixture, not an AWS id (`AKIA` + random base32). Both values re-entered the window together on the en-masse board rewrite `07ef86e` (2026-09-18, 209 added lines, one commit) — note that `git log -S <value>` does NOT show that commit, because a rewrite drops and re-adds the identical text (occurrence count unchanged); use `git log --since=<cutoff> -p -U0 -- <board file>` to see the re-add.
- **Scanner hardening (scan #98)**: rules `AKIA1234567890` and `ghp_1234567890` added (55 → 57 FP rules), marker-keyed like the existing `sk-(or-v1-)?1234567890` / `ghp_ABCDEFGHI` precedents. Canary (pre-patch vs patched, side by side): 2/2 live flags suppressed, 6/6 real-material controls (`AKIA3F9KQ…`, mixed-case `ghp_…`, `sk-or-v1-…`, Telegram, plus the two pre-existing example rules) still detected with unchanged verdicts; full re-run → 1 finding / 0 critical = suppression, not window drift. The `ghp_123…456` half had been hand-carried for many scans; #98 is the first fire that suppresses the pair at the scanner level.

### 2. gitreins-poc board-task prose (github_token)
- **File**: `.coding-hermes/board/tasks.jsonl` line ~126, task GR-GAP-007 title: ".gitleaks.toml allowlists `.env` files: … ANY secret (even GitHub PATs gitleaks CAN detect)…"
- **Match**: the words "GitHub PAT" — descriptive prose about gitleaks allowlists, no token value. Re-flags on every in-window board commit whose diff re-adds the row — BOTH stand-in PM cycles AND routine foreman ticks can carry it (carriers seen: `8f90e25` PM cycle 2026-08-18 ×4 added lines, `f97f57a` PM cycle 2026-08-19 ×2, `943c53d` Tick 215 2026-08-20 ×4). Sibling commits usually carry 0 (e.g. Tick 214 `59a5789`, Tick 216 `2a910fb` 2026-08-20 18:02:37Z — both probed ×0), but do NOT assume ticks are clean — probe EVERY in-window board commit with `git show <c> -U0 -- .coding-hermes/board/tasks.jsonl | grep -c GR-GAP-007`.
- **Probe**: search `ghp_[A-Za-z0-9]{10,}|github_pat_[A-Za-z0-9_]{10,}|sk-[A-Za-z0-9]{40,}` in tasks.jsonl → only hit is the synthetic sequential repro token `ghp_123…456` inside the pass-criteria command of the same task = confirmed FP.
- ⚠️ GR-GAP-013 title mentions "live GITREINS_LLM_API_KEY (sk-0ffcc4...)" — a **truncated** reference (9 chars, doesn't match 40+ rules). Do not expand it into a real key; the live key lives in the gitignored repo-local `.env` (deliberate, documented in the task).

### 3. HTTP header / env-var NAME constants (credential / token)
- hivemind-work `pkg/plugin/constants.go:208` — `StrXAuthToken = "X-Auth-Token"` (header name, `//nolint:gosec // G101: HTTP header name, not a credential`; flagged twice = same line with/without nolint comment).
- off-by-one `site/classes/0288-go-testing-env-contamination-missingkey.html` — `const envAPIKey = "OPENROUTER_API_KEY"` (env-var name in answer-page code).
- helix `cmd/helix-identity/main.go:56` — `envAdminToken = "FORGEJO_ADMIN_TOKEN"` (resolver constant).
- hermes-dagger `demo/stand-in-pm-run.sh` — `GATEWAY_API_KEY="$GATEWAY_KEY"` (key read at runtime from `~/.hermes/.env`, nothing literal).
- imhotep `docs/consensus-setup.md` — `DEEPSEEK_API_KEY="$DEEPSEEK_API_KEY"` (docker run docs).
- crier `examples/hermes-gateway-demo/run-demo.sh:137` — `[ -n "$DEEPSEEK_KEY" ] && ADAPTER_ENV+=(DEEPSEEK_API_KEY="$DEEPSEEK_KEY")` (demo script; key read at runtime from `~/.hermes/.env` via grep on line 121, nothing literal; carrier `5ab23fc` CR-FEAT-008 webhook-demo commit 2026-08-20; first flagged scan #34 2026-08-21 10:00Z — same fire the gitreins-poc class #2 stopped re-flagging; re-flagged scans #35 16:00Z AND #36 22:00Z (identical content, carry-forward; carrier `5ab23fc` = 2026-08-20 23:28:37 -0500 / 08-21 04:28:37Z — stays in-window until ~08-22 04:28Z cutoff, so further re-flags are EXPECTED before it ages out); live key confirmed present in gitignored `~/.hermes/.env`, outside repo — correct practice).
- **Probe**: grep repo-wide for the literal value form (e.g. `sk-` + 40 chars); zero matches + the hit is an identifier/name = FP. For demo-dir hits: `grep -rnE "(sk-[a-zA-Z0-9]{20,}|AIza[a-zA-Z0-9_-]{20,}|ghp_[a-zA-Z0-9]{20,}|xox[baprs]-[a-zA-Z0-9-]{10,})" <dir>` → 0 hits + the flagged line's value is `$VAR` = confirmed FP.
- **Plaintext `~/.hermes/skills` instances (scan #39, 2026-08-22)** — the plaintext skills-dir scan re-flags these EVERY run (no 24h diff-window aging; carrier = the file itself):
  - comfyui `scripts/_common.py:45` — `ENV_API_KEY = "COMFY_CLOUD_API_KEY"` (env-var NAME const).
  - speclang-user `references/pi-agent-openrouter-setup.md:45` + speclang-aws-docs-wiring `references/openrouter-owl-alpha-setup.md:20` — `apiKey: "$OPENROUTER_API_KEY"` (env interpolation, no literal key).
  - coding-hermes/helix-foreman-ops `SKILL.md:34` — META-FP: the line documents the helix `envAdminPassword = "FORGEJO_ADMIN_PASSWORD"` env-var NAME const FP itself ("Secrets-scan false positive … an env-var NAME const"); skill docs that DESCRIBE FP classes get flagged by the plaintext scan.
  - coding-hermes-foreman `references/golangci-lint-v2-counting-and-goconst-slice.md:156` — `StrXAuthToken = "X-Auth-Token"` (Go const, HTTP header name; same constant as the hivemind-work entry above).

### 4. Test fixtures / docs placeholders
- totalstack ACM test PEMs (commit 53320cac9): `TEST_KEY_PEM` synthetic RSA in `development/test_inputs/acm.py`, auto-generated into Speclang assembled `specs/aws/.speclang/assembled/_tests/test_acm_integration.py`, plus a deliberately-invalid `"PrivateKey": "...test..."` PEM feeding a `pytest.raises(ValidationException)` negative test — structurally impossible as a real key.
- chimera-v2 `docs/INTEGRATION.md` — `sk-prod-abc123` placeholder (3 lines, one fake value).
- totalstack `docs/API.md` — `IdempotencyToken="walkthrough-001"` (ACM docs example, idempotency marker).
- hivemind-work `specs/ALL_SPECS_MERGED.md` — `AKIAIOSFODNN7EXAMPLE` (AWS docs example) + `# OPENVPN_PASSWORD="vpn_password"` (commented placeholder).
- totalstack-testing `SKILL.md:653` AND `:694` — `"AKIARZPUZDIKGB2VALC4" => "123456789012"` (LocalStack `localstack/aws/accounts.py` test fixtures, explicitly documented in the skill as "test fixtures, not real credentials"; flagged by the PLAINTEXT skills scan — BOTH lines, flag type aws_access_key; account ID `123456789012` = canonical AWS docs example; the skill even names the gitreins-secrets-ignore workaround). **Upstream confirmation (scan #43, 2026-08-26)**: the exact mapping is the docstring EXAMPLE in LocalStack's own `localstack-core/localstack/aws/accounts.py` (`"AKIARZPUZDIKGB2VALC4" => "123456789012"`). Probe: web-search the bare key (`"AKIARZPUZDIKGB2VALC4" localstack`) — first hit is the upstream source on the fossies.org mirror = fixture confirmed in seconds, no in-repo digging. Structural tell: it's an access-key **ID** only (20 chars, AKIA prefix) with no secret half — an ID alone can't authenticate.
- gitreins-workflow `references/precommit-hook-pitfalls.md:26` + `templates/agent-update-and-tier2-prompt.md:33` + `templates/agent-update-prompt.md:422` — `sk-1234567890abcdef1234567890abcdef` in `test_secret.py` gitleaks-test fixtures (canonical sequential dummy, class-1 value; each line double-flags as credential+openai_key — count as ONE FP).
- gitleaks-doc trio (added 2026-09-02, scan #44, plaintext skills scan — verified in-file + live-probed):
  - devops/gitreins-guard-troubleshooting `references/gitleaks-builtin-cross-check-merge-2026-08.md:16,17` — `sk-A1A1A1A1A1A1A1A1A1A1A1A1A1` inside a LITERAL QUOTED gitleaks verbose-output block (Finding:/Secret: lines, DF-016 planning doc). Fake value; line double-flags openai_key+credential-adjacent = ONE FP.
  - devops/gitreins-guard-troubleshooting `references/gitleaks-builtin-cross-check-merge-2026-08.md:41` — `ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghij` = the low-entropy alphabetical DECOY token from the entropy-filter-asymmetry section (structurally invalid, 52 sequential chars). Same value also in development/gitreins `references/gitleaks-secrets-guard-failure-path.md:29`.
  - development/gitreins `references/gitleaks-secrets-guard-failure-path.md:32` — `ghp_6RbYzOo4Td3rQEtzVccCToOBCSiOrgwUIjmu` = the documented random-chars repro token ("A random-chars token IS caught by gitleaks"). LIVE-PROBED 2026-09-02: GitHub API `Authorization: token …` → **HTTP 401 Bad credentials** = not a live credential.
- duckbrain `docs/PRD-s3-native.html` — base64 **PNG data-URI** matched as gcp_api_key (scan #41, 2026-08-25): flagged line is `data:image/png;base64,iVBORw0KGgo…` (iVBORw0KGgo = PNG magic bytes) — an embedded mockup image in the PRD HTML; scanner matched the base64 charset, no `AIza…` literal anywhere. **Probe**: flagged line starts with `data:image/png;base64,iVBORw0KGgo` = embedded image, not a credential.

### 5. UI/i18n translation strings & field-key NAME constants (credential type)
- hermes-webui `static/i18n.js` — German UI labels whose English source contains `password`/`api_key`: L9253 `settings_aux_advanced_api_key: 'API-Key-Override'`, L9304 `settings_label_password: 'Zugangspasswort'`, L10044 `onboarding_check_password: 'Passwortschutz'`, L10096 `auth_status_password: 'Passwort-Authentifizierung'`. Probe: it's a localization file — neighbor lines are other German labels (`'Vorhandenen API-Key-Override löschen'` at 9256); no credential values.
- hermes-webui `api/route_approvals.py:49` — `_GATEWAY_MIRROR_TOKEN = "_gateway_mirror_token"` (module constant whose VALUE is a JSON field/key NAME, not a token; used as `pending._gateway_mirror_token` in `static/messages.js:7495/7504/7624` + tests with dummy values `'mirror-1'`/`'mirror-owner-1'`). Probe: grep the string — it's a key name, and call sites carry dummy values.

### 6. Stable skills-plaintext flag signature (SCAN_VERSION 3, verified scans #39–#43, 2026-08-26)

The `~/.hermes/skills` plaintext scan has NO 24h diff-window aging — the carrier is the file itself, so documented-FP lines re-flag EVERY run, byte-identically. **Current stable set (scans #41–#43): 14 flags** — skills plaintext only (11 unique lines; the two gitreins-workflow `sk-1234567890abcdef…` template lines double-flag credential+openai_key = count as ONE FP each). The hermes-webui release-diff group ×5 (`_GATEWAY_MIRROR_TOKEN` + 4 German i18n labels, carrier commit `df65251d`) was a git-DIFF group, NOT plaintext — it aged out with its carrier after scan #40 and is not part of the stable signature. Note the plaintext 14 are a signature, not a constant count: if a flagged line's content ever changes, or a NEW file/line appears, verify it fully — only byte-identical carries get the short path. After 2 consecutive byte-identical fires, treat the whole set as a known signature: probe ONE line in-file (e.g. totalstack-testing AKIA fixture), map the rest to classes §3–§5, and write "byte-identical carry-forward of scan #N" in the report section AND dashboard row — no per-finding re-verification. NEW instances (different file/line than the last fire) still get full verification. Members added 2026-08-23:
- coding-hermes/heading-foreman-ops `SKILL.md:34` — META-FP (helix-foreman-ops sibling): prose documenting the gitreins guard's staged-diff behavior (`staged_only=True`; manual guard before `git add` sees zero staged files) — scanner-pattern words in prose, no literal credential.
- code-quality-gates/acceptance-criteria-verification `references/off-by-one-obgap062-deploy-judge-case.md:63` — prose quoting the class-1 answer-corpus dummy pair (`sk-a1b2c3d4e5f6g7h8i9j0`, `sk-abcdef0123456789abcdef`) as "pre-existing at the base commit" while explaining introduced-vs-historical leak detection (judge-case doc). Verified scan #48 (2026-08-30), carried #51 byte-identical.
- devops/cloudflare-seo-prerender `SKILL.md:70` — the sentence literally reads "contain example credentials (`sk-abcdef0123456789abcdef`, `ghp_invalid`, 32-char hex keys)" — self-describing examples, class-1 values.

## Dashboard update gotchas (Security/Security Dashboard.md)

- **Dual-list structure** (verified 2026-08-20): the ACTIVE Recent Critical Findings list is the heading-less bullet block directly under `_Last updated` at the top of the file — the `## Recent Critical Findings` heading deeper in the file is a legacy duplicate that recent scans do NOT touch. The cron prompt's instruction to patch "the Recent Critical Findings section" means the TOP list.
- **Update pattern** (3 edits): (1) replace the `_Last updated:` line; (2) insert the new 🟢/🟡/🔴 bullet immediately after line 1 (before the previous newest bullet); (3) insert a new row at the TOP of the Scan History table (after the `---` separator preceding the previous newest row; rows start with `|| ` — double pipe + ONE space — keep the leading pipe). ⚠️ search_files output indents matched lines by 2 spaces, so the real `|| ` row prefix displays as `||| ` in search results; a patch old_string built from that display fails with "Could not find a match". Read the table region with read_file to confirm the true prefix before patching (hit on scan #36, 2026-08-21 — the read_file view showed `|| ` correctly).
- **If unsure which list is live**: verify where the previous scan's update landed — `git -C <vault> show <last-vault-sync-commit> -- KaraHermes-MDE/Security/Security Dashboard.md` (vault is git-tracked; the last sync commit shows the prior bullet/table edits exactly).
- **Commit the audit trail**: after writing the dated report + the 3 dashboard edits, `git add` both files and commit `chore: vault sync <SCAN_TIME YYYY-MM-DDTHHMMZ> — secret scan #N (CLEAN, 1/1 FP)` from the vault repo root — matches the prior sync-commit convention (author `KaraHermes <duckbrain@localhost.localdomain>`; verified scan #32 → `7ede3bd`, 2 files, 33 insertions). Leaving changes uncommitted breaks the git-verification workflow this corpus relies on.
- **REPOS_TOTAL drift is benign**: totals shift between scans (104 → 101, scans #31 → #32; active count flat at 46) — repo-discovery variance, NOT a finding. Report the script's own REPOS_TOTAL/REPOS_ACTIVE verbatim in the report/dashboard; never flag the delta or chase it.

## Non-FP watch item
- gitreins-poc repo-local gitignored `.env` held a live `GITREINS_LLM_API_KEY` — resolved by tick 145 (removed from .env, commit 1534fa2); guard now injects via shell env. Any NEW flag of an actual 40+ char `sk-` value anywhere = real finding, rotate immediately.

### 7. deepseek-harness shallow-clone boundary artifact (scan #50, 2026-09-02) + sk-or-v1- scanner gap

- **Repo**: `/home/kara/deepseek-harness` — a `--depth 1` SHALLOW clone of the PUBLIC upstream `deepseek-ai/deepseek-harness` (cloned 2026-09-02, HEAD = upstream merge `49a606b` 2026-09-02 17:47 +0800, no local commits, working tree CLEAN). The scanner's `git log -p --since=24h` hits the shallow boundary and renders the ENTIRE upstream tree as diff-ADDED lines while the boundary commit is in-window → ~9 CRITICAL flags of **upstream's own keyless-mode fixtures**: `api_key="sk-keyless-smoke"` ×8 (scripts/smoke-python-runtime.py L935/967/999/1042/1075/1156/1192/1244 + L1291 env form) and `environment.DEEPSEEK_API_KEY = 'keyless-installed-web-no-call'` (scripts/publish-npm-baseline.ts:918). The harness's keyless adapter invokes no provider; the dummy key satisfies client SDKs before the adapter short-circuits. Repo-local `.env` (real DEEPSEEK_API_KEY) is gitignored (`.gitignore:2`) + mode 600 — correct practice.
- **Probe**: `git -C /home/kara/deepseek-harness rev-parse --is-shallow-repository` = `true` + `git status --short` empty + value grep shows the flagged strings are in HEAD's committed tree (upstream authorship) = FP. Ages out after the boundary commit exits the 24h window (~2026-09-03 09:47Z) or when the repo is deepened.
- ⚠️ **Scanner regex gap (2nd report, scan #50)**: `sk-[A-Za-z0-9]{20,}` does NOT match `sk-or-v1-…` keys (hyphens break the alnum run) — this is how 3 REAL LIVE OpenRouter keys hid from the scanner in scans #49 AND #50 and were only caught by the agent's literal `sk-or-v1-` probe. Fix landed scan #50: SECRET_PATTERNS gained `sk-or-v1-[A-Za-z0-9-]{20,}` (type openrouter_key). Expected re-flag fallout until remediated: workspace-provisioning.md:57 + friend-deletion.md:48 + openrouter-key-provisioning.md:32 + gateway-shutdown-diag.log:649 (REAL keys, pending rotation/scrub from #49/#50) and june2026-pitfalls.md:55 (`sk-or-v1-1234567890abcdef…` echo'd pre-commit-hook test fixture — sequential dummy, HTTP 401, FP) + wiring-pattern-verified.md:23 (`sk-0123456789…` sequential dummy, HTTP 401, FP).

**Fallout realized scan #51 (2026-09-03 04:00Z)**: the 3 REAL key lines + june2026-pitfalls:55 + the NEW pre-update/state-snapshots backup dirs all flag natively now (7 openrouter_key flags). **4th LIVE key surfaced**: `sk-or-v1-735…281` (2026-05-24 pre-update backup of the pre-auth-flip main OpenRouter key, in `~/.hermes/20260524-181118-pre-update/auth.json:32` + `.env:11` + state-snapshots mirror) — probed HTTP 200, $11.85 usage, absent from current env/auth stores → orphaned, never revoked. **NEW exposure surface**: `~/.hermes/recovery/` (96 GB state.db copy/repair artifacts: `state.db.copy*`, `state_new*.db`, `state_recovered*.sql`) contains ALL FOUR live keys — the 96 GB dir is the standing disk-hog cleanup candidate; deleting it scrubs the keys too. **chimera-v2 PUBLIC GitHub (`totalwindupflightsystems/chimera`) verified CLEAN**: key-bearing commit `895368e` is NOT an ancestor of `github/main` (merge-base exit 1); zero key-shaped literals in github/main tracked files or local HEAD. Key `849…972` stays confined to the PRIVATE gitlab remote.

### 8. Scan #52 (2026-09-04 10:00Z) — rotation STILL pending + 2 NEW live keys via dogfood doc

**Live-probe re-verified ALL six REAL keys HTTP 200** (`/api/v1/auth/key` for OR keys, `/user/balance` for DS): the 4 keys above were flagged scans #49–#51 as "pending rotation/scrub" but were NEVER rotated — they remain live in the SAME unscrubbed files (`openrouter-workspace-provisioning.md:57` = `sk-or-v1-849…972`, `friend-deletion.md:48` MGMT key = `sk-or-v1-8fd…2cb`, `chimera-development openrouter-key-provisioning.md:32` = `sk-or-v1-b34…ee7`, pre-update backup = `sk-or-v1-735…281`). **These are REAL, still-live findings — escalation class, not carry-forward FPs.**

**2 NEW live keys (scan #52, file created 2026-09-04)**: `software-development/dogfood-use-phase/references/ai-plays-poke-use2-2026-09-04.md:13-14` contains `OPENROUTER_API_KEY=sk-or-v1-cc2…ccf` (live, $10/day limit, $0.18 used) + `DEEPSEEK_API_KEY=sk-c610…a74` (live, **$190.13 balance**). ⚠️ The doc's own text claims "These look like real keys but return 401 on every call" — **FALSE, disproven by live probe**. Provenance: values match the live gitignored `~/.hermes/.env` OPENROUTER_API_KEY and `ai_plays_poke/.env` DEEPSEEK_API_KEY (both gitignored, mode 600) — a dogfood USE run copy-pasted REAL env keys into a skill reference and mislabeled them invalid. Public `wojons/ai_plays_poke` verified CLEAN: `.env.example` at HEAD/history NEVER contained these keys (git -S search = 0 commits), repo has placeholders only. **Lesson: never trust a doc's "returns 401/invalid" claim — probe liveness; dogfood/field-note writers must redact env captures.**

**Scan #53 (2026-09-05 10:00Z) — 5th consecutive 🔴, ALL 6 keys STILL HTTP 200**: 849…972, 8fd…2cb (MGMT), b34…ee7, 735…281 + dogfood pair cc2…ccf (still = current production ~/.hermes/.env OR key; $10 limit, $0.18 used) + c610…a74 (DeepSeek balance $183.96, fell from $190.13 → actively used). Doc's "401" claim disproven a 2nd time. **New class-2 carrier**: GR-GAP-007 prose + synthetic `ghp_123…456` repro token now also lives in gitreins-poc committed `.coding-hermes/board/tasks.jsonl.bak-20260904` (commit e6842c5, in sync w/ github remote) — same 401-probed dummy, FP. Rotation still pending since #49 (2026-08-31).

### 9. Scans #54–#56 (2026-09-05 16:00Z → 2026-09-06 10:01Z) — 6th–8th consecutive 🔴, rotation STILL pending, DS spend accelerating

All six keys re-probed HTTP 200 every fire (7th–8th consecutive verification): 849…972, 8fd…2cb (is_management_key + is_provisioning_key re-confirmed #56), b34…ee7, 735…281, cc2…ccf (still = current production `~/.hermes/.env` OR key), c610…a74 (DeepSeek). **DeepSeek balance trajectory: $183.96 (#53) → $183.26 (#54) → $182.23 (#55) → $165.86 (#56)** — the #55→#56 window dropped **−$16.37 in ~12h**, ~16× steeper than prior ~6h deltas (−$0.70/−$1.03) = spending sharply accelerated (fleet on deepseek-payg). Flag count settled at 30 (gitreins-poc `.bak-20260904` aged out at #55). Same unscrubbed files, chimera.yaml still tracked (private gitlab), gateway-shutdown-diag.log:649 unfixed, recovery/ ~96 GB still holds all 6. ⚠️ For next fires: the ai-plays-poke doc's "returns 401" claim has been live-disproven 4 consecutive fires — do not re-argue provenance, just re-probe liveness + record DS balance.

### 10. Scans #57–#58 (2026-09-07 04:00Z + 10:00Z) — 9th–10th consecutive 🔴, rotation STILL pending

**#57 (04:00Z fire, cross-day appended to 2026-09-06.md per protocol; dashboard row/bullet dated 2026-09-06 04:00 UTC)**: 115 repos (49 active), 30 flags byte-identical carry; 6/6 keys HTTP 200; DS balance $159.81 (−$6.05/18h since #56 — pace normalized after the −$16.37/12h burst). **#58 (10:00Z, first section in new 2026-09-07.md)**: 115 repos (48 active), 30 flags byte-identical carry; 6/6 keys HTTP 200 (~10:05Z): 849…972 usage $0.054/$5, 8fd…2cb mgmt+prov, b34…ee7 usage $0.027/$50, 735…281 usage $11.85/$50, cc2…ccf = current production OR key usage $0.215/$10 (climbing from $0.18), c610…a74 DS balance **$156.49** (−$3.32/6h — spend continues). ⚠️ **recovery/ measured ~47 GB at #58 (was ~96 GB through #57) — roughly half deleted, but `state_new4.db` + `state_recovered4.sql` STILL hold all 6 keys**; finish deletion. ⚠️ **Chimera provisioning doc holds TWO sk-or-v1-b34… keys**: line 32's key (b347e2ff…, the flagged one) is LIVE; a DIFFERENT older b34… key elsewhere in the doc returns 401 "User not found" — probe the line-32 occurrence specifically, never the file's first match. Same unscrubbed files across #49→#58 (~7 days, zero remediation); chimera.yaml still tracked (private gitlab), gateway-shutdown-diag.log:649 unfixed.

### 11. Scans #59–#60 (2026-09-07 22:01Z + 2026-09-08 04:00Z cross-day) — 11th–12th consecutive 🔴, rotation STILL pending

**#59 (22:01Z, 09-07 file second section)**: 115 repos / 49 active, 30 flags byte-identical carry of #58; 6/6 keys HTTP 200 (~22:05Z); DS balance $152.98 (−$3.51/12h). **#60 (04:00Z 09-08 fire = 09-07 23:00 CT, cross-day appended to 2026-09-07.md; dashboard row/bullet dated 2026-09-07 04:00 UTC)**: 115 repos / 49 active, 30 flags byte-identical carry; 6/6 keys HTTP 200 (~04:10Z): 849…972 usage $0.054/$5 (flat), 8fd…2cb mgmt (usage $0.000), b34…ee7 usage $0.027/$50 (flat), 735…281 usage $11.846/$50 (flat), cc2…ccf = current production OR key usage $0.216/$10 (flat vs #59), c610…a74 DS balance **$151.44** (−$1.54/6h — spend continues, pace normalized after the −$16.37 burst at #56). recovery/ still ~47 GB holding all 6 (state_new4.db + state_recovered4.sql); deletion stalled since #58's partial cleanup. chimera.yaml still tracked (private gitlab); gateway-shutdown-diag.log:649 unfixed. Zero remediation across #49→#60 (~8 days). Vault synced 0f30d58.

### 12. Scans #61–#62 (2026-09-08 10:01Z + 16:01Z) — 13th–14th consecutive 🔴, rotation STILL pending

**#61 (10:01Z, first section on 2026-09-08.md)**: 115 repos (48 active), 30 flags byte-identical carry of #60; 6/6 keys HTTP 200 (~10:06Z); usage flat: 849…972 $0.054/$5, 8fd…2cb mgmt $0.000, b34…ee7 $0.027/$50, 735…281 $11.846/$50, cc2…ccf $0.216/$10; DS balance **$150.76** (−$0.68/6h). ⚠️ **CORRECTION to #51–#60**: 735…281 is NOT orphaned — it is the `uncensored` profiles CURRENT live OR key (`~/.hermes/profiles/uncensored/.env`); the 2026-05-24 pre-update backup dirs hold a live key, not a stale one. **#62 (16:01Z, this fire)**: 30 flags byte-identical; 6/6 keys HTTP 200 (~16:05Z); DS balance **$150.57** (−$0.19/6h — spend continues, pace modest); 14th consecutive 🔴; zero remediation across #49→#62 (~8.7 days). Scan #61 vault writes were uncommitted (sync had stopped at #60s 0f30d58); committed with #62s sync. Next fires: re-probe 6 keys + record DS balance; do NOT re-argue provenance or the docs "returns 401" claim (disproven 5×); expected next state = same 30 flags, same 6 keys.

### 13. Scan #63 (2026-09-08 22:01Z) — 15th consecutive 🔴; STATE CHANGE: cc2…ccf EXPIRED

**#63 (22:01Z, third section on 2026-09-08.md; vault commit 791ae96, pushed s3sync)**: 115 repos / **41 active**, 30 flags byte-identical carry of #62; probe ~22:10Z → **5/6 keys HTTP 200; sk-or-v1-cc2…ccf now HTTP 401 "API key expired"** — first provider-side change since #49. Live set now: 849…972 ($0.0544/$5), 8fd…2cb (mgmt+prov, $0.000), b34…ee7 ($0.0269/$50), 735…281 ($11.846/$50, uncensored-profile key), c610…a74 (DS balance **$150.31**, −$0.26/6h). ⚠️ cc2…ccf sha-verified **STILL = current `~/.hermes/.env` OPENROUTER_API_KEY value** → the production .env copy is dead at provider level (revoked at console or hit expiry date); any OR-routed workload now 401s until .env gets a fresh key. Dogfood doc :13 line still unscrubbed (dead literal now). Next fires: probe the 5 live keys + DS balance; probe cc2…ccf ONCE to confirm it stays 401 (if it ever returns 200, .env copy is live again — escalate); do NOT re-argue provenance; report cc2…ccf as EXPIRED-not-live in REAL counts (real=5, not 6).

### 14. Scan #64 (2026-09-09 10:00Z) — 16th consecutive 🔴; cc2…ccf EXPIRED confirmed 2nd fire; .env still dead

**#64 (10:00Z, first section on 2026-09-09.md — 04:00Z slot did not fire; vault commit b47735f, pushed s3sync)**: 115 repos / **11 active** (active-count drop from 41 at #63 — report verbatim, benign per dashboard doctrine), 30 flags byte-identical carry of #63 (all 21 FP lines re-verified in-file at exact flagged lines; all 7 key files re-verified carrying their keys); probe ~10:08Z → **5/6 keys HTTP 200; cc2…ccf STILL HTTP 401 "API key expired" (2nd consecutive fire — stays expired, .env copy stays dead)**. Live set unchanged: 849…972 ($0.054/$5), 8fd…2cb (mgmt+prov, $0.000), b34…ee7 ($0.027/$50), 735…281 ($11.846/$50, uncensored-profile key — sha-match to `~/.hermes/profiles/uncensored/.env` re-confirmed), c610…a74 (DS balance **$149.51**, −$0.80/12h — spend continues). cc2…ccf sha-verified STILL = `~/.hermes/.env` OPENROUTER_API_KEY → main-profile OR egress dead until .env refreshed. recovery/ still ~47 GB holding all keys (state.db.copy3/copy4 + state_new4.db + state_recovered4.sql grep-verified this fire). Next fires: probe the 5 live keys + DS balance; probe cc2…ccf ONCE per fire (401 expected until .env refreshed — if it 200s again, escalate: key was re-issued); do NOT re-argue provenance.

### 15. Scans #65–#69 (2026-09-09 16:01Z → 2026-09-10 16:01Z) — 17th consecutive 🔴; VAULT-WRITE GAP #65–#68; NEW hotspots (skills.bak live copies + recovery/ regrown 88 GB)

**⚠️ Vault-write gap**: fires **#65–#68** (09-09 16:00Z / 22:00Z / 09-10 04:00Z / 10:00Z) produced chat briefings ONLY — NO vault report and NO dashboard write (Secret Scans/2026-09-09.md still holds only the #64 section; dashboard was stuck at `_Last updated: 2026-09-09 10:00 UTC`). Scan **#69** (09-10 16:01Z, first section in new `Secret Scans/2026-09-10.md`) resumed the full workflow: report + 3 dashboard edits + vault commit `1369ffa` (2 files, +65/−1) pushed `s3sync`. Global counter mapping: **#65=09-09 16:01Z, #66=09-09 22:00Z, #67=09-10 04:01Z, #68=09-10 10:00Z, #69=09-10 16:01Z**. Future fires: if a prior slot left no vault/dashboard write, note the gap in the report Note line and continue numbering from the newest written section + 1.

**Scan #69**: 116 repos / **53 active** (was 11 at #64 — report verbatim, benign). 30 flags = **21 FP** (stable skills-plaintext signature, byte-identical #49→#69) **+ 9 REAL = 6 distinct keys**. Live probes (~16:05Z): **5/6 HTTP 200** — 849…972 ($0.0544/$5 daily), 8fd…2cb (mgmt+provisioning), b34…ee7 ($0.0269/$50 daily), 735…281 ($11.846/$50 weekly, = uncensored profile's current OR key), c610…a74 (DeepSeek **balance $142.56, −$6.95 since #64 ≈ −$5.5/day = still spending**); **cc2…ccf HTTP 401 "API key expired" 3rd consecutive fire** (still = `~/.hermes/.env` OPENROUTER_API_KEY sha-value). Zero remediation across #49→#69 (~10.3 days). No public-GitHub exposure.

**NEW exposure surface — un-scanned hotspot**: `~/.hermes/skills.bak-2026-08-23/` STILL EXISTS and holds **LIVE key copies** grep-verified at #69: `sk-or-v1-849ac09a…` ×1, `sk-or-v1-8fd54df6…` ×2, `sk-or-v1-b347e2ff…` ×1 (plus FP fixtures `ghp_xxx…`, `sk-1234567890…`, `sk-0123456789…`). It is **NOT in the scanner's 3-dir plaintext list** (only `skills/`, `20260524-181118-pre-update/`, `state-snapshots/`) — a coverage gap first flagged at #65. **Fix: add `~/.hermes/skills.bak-2026-08-23/` to PLAINTEXT_DIRS AND delete the dir.**

**recovery/ REGROWN**: **88 GB** at #69 (was ~96 GB #51 → ~47 GB #58–#64). A **NEW `state_new5.db`** appeared alongside `state_new4.db` / `state.db.copy3` / `state.db.copy4` / `state_recovered4.sql`; grep confirms **all 6 keys present** in recovery/. The disk-reclaim + key-scrub cleanup has regressed — re-check size every fire.

**FP re-verified byte-identical at #69**: totalstack-testing `SKILL.md:653,694` (`AKIARZPUZDIKGB2VALC4 => 123456789012`, LocalStack upstream `localstack/aws/accounts.py` docstring example — web-search the bare ID confirms), gitreins-workflow `sk-1234567890abcdef…` templates, `comfyui/scripts/_common.py:45`, `ghp_ABCDEF…` + `ghp_6RbYzOo4…` (401-probed) repro tokens.

**Next fires**: probe the 5 live keys + DS balance; probe cc2…ccf ONCE (401 expected — if it returns 200, the key was re-issued → escalate); check `skills.bak-2026-08-23/` still-not-deleted and `recovery/` size; do NOT re-argue provenance.

### 16b. Scan #74 (2026-09-11 22:01Z) — 20th consecutive 🔴; byte-identical carry, zero key remediation ~11.5 days

**#74**: 117 repos / **30 active** (was 38 — report verbatim, benign). **31 findings = 30 CRITICAL + 1 INFO** (`/home/kara/hermes-observatory` repo timed out — recurring benign class, no finding; note it in the report but do not escalate). The 30 CRITICAL = **byte-identical carry of the stable signature: 21 FP + 9 REAL flag lines = 6 distinct keys**. Probes ~22:02Z: **5/6 HTTP 200** — 849…972 ($0.0544/$5 daily flat), 8fd…2cb (mgmt+provisioning, $0), b34…ee7 ($0.0269/$50 daily flat), 735…281 ($11.846/$50 weekly, sha-matched to `~/.hermes/profiles/uncensored/.env`), c610…a74 (DeepSeek **balance $116.83, −$6.89/6 h since #73's $123.72**); **cc2…ccf 401 "API key expired" 6th consecutive fire**, still = `~/.hermes/.env` OPENROUTER_API_KEY. Surfaces unchanged: `skills.bak-2026-08-23/` (207 MB, live copies 849×1/8fd×2/b34×1, 4th fire, still outside PLAINTEXT_DIRS), `recovery/` 13 GB w/ `state_new6.db` (13.4 GB) re-grep-confirmed to hold all 6 keys, `gateway-shutdown-diag.log` 1 occurrence, `chimera.yaml` still tracked. Vault commit `77916a4`, pushed s3sync. Zero key remediation across #49→#74.

### 16. Scans #70–#73 (2026-09-10 22:01Z → 2026-09-11 16:01Z) — 18th–19th consecutive 🔴; disk improved, keys untouched

**⚠️ Vault-write gap #71–#72**: fires 09-11 04:00Z + 10:00Z wrote chat briefings only (job `last_run_at` = 09-11 10:05 CT, status ok — slots DID fire). Newest written section = #70; numbering continues on the global slot counter, so the 16:01Z fire = **#73** (same precedent as #65–#68). Vault commit `b5521c7` pushed `s3sync`.

**#73**: 116 repos / **38 active** (was 54 — report verbatim, benign). **30 flags = byte-identical stable signature; #70's deepseek-harness fixture aged out (31→30)**; 21 FP + 9 REAL = 6 distinct keys; probes ~16:05Z **5/6 HTTP 200** — 849…972 ($0.0544/$5), 8fd…2cb (mgmt+provisioning), b34…ee7 ($0.0269/$50), 735…281 ($11.846/$50, uncensored-profile key), c610…a74 (DS **balance $123.72, −$16.32/18 h — spend re-accelerated**); cc2…ccf 401 "API key expired" **5th consecutive fire**, still = `~/.hermes/.env` OPENROUTER_API_KEY. ~11.3 days zero key remediation.

**⚠️ FLAGGED-LINE DRIFT (new class-let)**: `coding-hermes/heading-foreman-ops/SKILL.md` now flags at **:40** (was :34) — the skill file was edited; text is still the same gitreins-guard `staged_only=True` scanner-prose, no literal credential. When a known-FP file's line number moves, verify the NEW line's text before re-using the short path (it did match here).

**✅ PARTIAL REMEDIATION — `recovery/` cleaned 131 GB → 13 GB**; root disk **96 % → 58 %** (746 GB free). Remaining: `state_new6.db` (13.4 GB) which **still grep-contains all 6 keys** (280/218/215/260/106/210 hits) + `SKILL.md` + `test_recover.sql`. Disk half done, key-scrub half NOT. `skills.bak-2026-08-23/` (207 MB, live 849×1 / 8fd×2 / b34×1) still un-scanned 3rd fire. `chimera.yaml` still tracked; `gateway-shutdown-diag.log` still holds 1 key occurrence.

### 17. Scan #79 (2026-09-13 04:01Z = 23:01 CT 09-12; appended to local-date file `2026-09-12.md`) — 24th consecutive 🔴; byte-identical carry, zero remediation ~12.5 days

**#79**: 118 repos / **26 active**; 30 findings (30 CRITICAL) = 28 unique flagged lines (2 FP lines double-flag credential+openai_key) → **21 FP + 9 REAL findings = 6 distinct keys**. Exit code 1 = findings-present behavior (normal). Probes ~04:10Z: **5/6 HTTP 200** — 849…972 ($0.0544/$5 flat), 8fd…2cb (**is_management_key=True + is_provisioning_key=True**, no limit, $0), b34…ee7 ($0.0269/$50 flat), 735…281 ($11.846/$50, sha-match to `~/.hermes/profiles/uncensored/.env`), c610…a74 (DeepSeek **balance $90.41, −$5.32 since #77's $95.73**); **cc2…ccf 401 "API key expired" 8th consecutive fire**, still sha- = `~/.hermes/.env` OPENROUTER_API_KEY. Surfaces unchanged: `skills.bak-2026-08-23/` (207 MB; 849×1 / 8fd×2 / b34×1; **6th fire**, still outside PLAINTEXT_DIRS), `recovery/` 13 GB with `state_new6.db` (13.4 GB) grep-re-confirmed all 6 keys (282/222/213/267/208/132 hits), `gateway-shutdown-diag.log` (1× b34), `telegram-archive/karahermes-chats.json` (735×2, c610×2), `chimera.yaml` still TRACKED (`.gitignore` lists it at lines 27 + 33 but `git check-ignore` rc=1 → **ineffective while tracked**; HEAD `8f4ce89` unpushed; the key is in pushed `5b25ae9` on the private GitLab). **Public-GitHub exposure: NONE** (full clones: `coding-hermes/skills` 271 files / 53 commits → 0 hits; **PUBLIC** `totalwindupflightsystems/chimera` → placeholders only — `sk-or-v1-...` Dockerfile comments + `sk-or-v1-test-key` in `tests/test_gateway.py` — no 60+ char key in any commit). Vault commit `7538a48`, pushed `s3sync`.

**Vault-write gap**: #78 (09-12 22:11Z = 17:11 CT; job `last_run_at` = `2026-09-12T17:11:38-05:00`, status ok) wrote a chat briefing only — no vault/dashboard write.

### 18. Scan #84 (2026-09-14 10:01Z) — coverage gap FIXED; three residual surfaces still hold key material

**#84**: 119 repos (28 active), **4 plaintext dirs**, 48 flags (48 CRITICAL) = 36 FP + 12 REAL flag lines = 6 distinct values (5 live + cc2…ccf expired). Probes ~10:0xZ 5/6 HTTP 200; DS balance $81.22 (−$0.94). 29th consecutive red; zero key remediation ~15 days.

- ✅ **Coverage-gap FIXED (PLAINTEXT_DIRS 3→4)**: `~/.hermes/scripts/scan-git-secrets.py` lines ~307–312 now include `~/.hermes/skills.bak-2026-08-23` (added 2026-09-13, first walked scan #82). The dir contributes **18 of 48 flags** (15 FP corpus values + 3 REAL live-key copies: 849×1, 8fd×1, b34×1). The dir is still NOT deleted (207 MB) — do not re-flag the coverage gap, flag the deletion.
- ⚠️ **`~/.hermes/recovery/` (13.4 GB) STILL EXISTS**: `state_new6.db` (13.42 GB) + `SKILL.md` + `test_recover.sql`. The #82 note "`/home/kara/recovery/` no longer exists" is true for the HOME path only; `.hermes/recovery/` (named #69→#81) survives. Per-file probe cap = skip >2 GB and cite the #79 grep instead.
- ⚠️ **`~/.hermes/.curator_backups/blobs/` (30 blobs)** holds: OR-b34 ×1, OR-cc2 ×1, DS-c610 ×1, dead `ghp_6RbYzOo4…` ×8 blobs, AWS doc/placeholder AKIA fixtures, and **2 blobs with PEM private keys**. #83's "blobs/ now gone" referred to `skills/.curator_backups/blobs` — the `.hermes/.curator_backups/blobs/` store remains.
- ⚠️ **`~/telegram-archive/`** holds live OR (735, 052, 3d1) + DS (c610, 258293a7, +9) literals and **5 Telegram bot tokens** (`8588537442…`, `8777516602…`, `8836655992…`, `8878678442…`, `8507178697…`) across `.tsv`/digests/index.db.
- ✅ **`cron/output/` re-sweep: 0 live secrets.** Every hit is corpus-class FP: `AKIAIOSFODNN7EXAMPLE`, `AKIAQWERTYUIOPASDF`, the dead `ghp_6RbYzOo4…` token, and totalstack PEM fixtures (job `15800dfe698b`). A grep regex `sk-[0-9a-f]{30,}` DOES match the sequential dummies — classify by prefix before claiming a hit.

**Cross-day labeling precedent (new, deviate deliberately)**: the 23:00-CT slot's true UTC time lands on the NEXT UTC day (09-13 04:01Z) while the local date is 09-12. The section is appended to the **local-date file** (`2026-09-12.md`, per the #51/#57/#60 precedent), but the dashboard row + `_Last updated` were labeled with the **TRUE UTC timestamp (2026-09-13 04:01 UTC)** instead of the older local-date+UTC-clock form, so the newest-first table stays monotonic (the older form put a 04:01 label above a 16:01 label of the same date). Future 23:00-CT fires: same rule.

### 19. Scan #86 (2026-09-14 22:01Z = 17:01 CT) — 31st consecutive 🔴; surfaces re-measured, flag set stable

**#86**: 121 repos / **27 active**; 4 plaintext dirs; **48 findings = 48 CRITICAL** (byte-identical carry of #84/#85) → **36 FP + 12 REAL flag lines = 6 distinct values (5 live + cc2…ccf expired)**. Exit code 1 = findings-present (normal). Probes ~22:0xZ **5/6 HTTP 200** — 849…c972 ($0.054431909/$5 daily flat), 8fd…2cb (mgmt+provisioning, no limit, $0), b34…ee7 ($0.0268725/$50 daily flat), 735…281 ($11.846432356/$50 weekly = `uncensored` profile key), c610…a74 (DeepSeek **balance $76.54, −$2.40 since #85's $78.94**); **cc2…ccf 401 "API key expired" — 15th consecutive fire**, still sha- = `~/.hermes/.env` OPENROUTER_API_KEY. Zero key remediation across #49→#86 (~15.5 days). Vault commit `36f2064`, pushed `s3sync`.

**Independent literal delta sweep (re-run each fire; pattern set = `sk-or-v1-`20+, `sk-`20+, `ghp_`/`github_pat_`, `tskey-`, `\d{8,}:AA…`, `AKIA…`, PEM headers): 0 unknown live-looking values.** The residual unmatched hits are all documented synthetic strings whose carriers were located in-file this fire — `AKIAJG7KQ4M3N6P2R5TU` (gitreins-workflow `tier2-self-testing-2026-06.md:44` + this skill's `key-prefix-cheat-sheet.md:7`), `ghp_x1234567890abcdefghijklmnopqrstuvwxyz` (secrets-precommit-hook `SKILL.md:120`), `sk-dogfood013regress…` (gitreins `gitleaks-secrets-guard-and-lsp-skips.md:98`), `sk-0123456789abcdef…` (gitreins-workflow `wiring-pattern-verified.md:23`). Add these to the FP map so future delta sweeps don't re-open them.

**⚠️ SURFACE FIGURES CORRECTED (carried wrong since #80)**: `~/.hermes/.curator_backups/blobs/` is **13,380 blobs / 170 MB** — NOT "~30 blobs". Key-carrying blobs (grep -rl per key): 849×5, 8fd×5, b34×10, cc2×1, c610×1, plus **22 `-----BEGIN` PEM-bearing blobs**. Sweep it with `grep -rl <key-openrouter-key-shape> <blobs-dir> | wc -l` per key, not by name count.

**✅ IMPROVEMENT — `logs/gateway-shutdown-diag.log` now 0 full-key residual**: the single `sk-or-v1-` occurrence at `:649` reads `sk-or-v1-b34…<redacted:73>` (redaction held; #82–#84 cited b34×1 there). Stop carrying that surface as a live leak.

**Unchanged surfaces**: `skills.bak-2026-08-23/` 207 MB — 4th fire as the 4th PLAINTEXT_DIR (18 flags incl. 3 live copies), still not deleted; `~/.hermes/recovery/` 13 GB with `state_new6.db` (13.42 GB) holding all 6 keys (per-file probe cap skips >2 GB — cite the #79 grep 282/222/213/267/208/132 instead of re-grepping); `~/telegram-archive/` (~20 MB) with live OR/DS literals across `.tsv` + `digests/*.md` + `karahermes-chats.json` + index.db and **5 distinct Telegram bot-token values** (8588537442, 8507178697, 8777516602, 8836655992, 8878678442) — no PLAINTEXT_DIR covers it; `/home/kara/chimera/chimera.yaml` still TRACKED on private GitLab `master` (`git check-ignore` rc=1, 1 unpushed). **No public-GitHub exposure.**

### 20. Scan #87 (2026-09-15 04:01Z = 23:01 CT 09-14, cross-day fire appended to `2026-09-14.md`) — 32nd consecutive 🔴; NEW 7th live key found in `cron/output/`

**#87**: 122 repos / 28 active; 4 plaintext dirs; 48 findings (48 CRITICAL) = byte-identical carry of #84–#86 → **36 FP + 12 REAL flag lines = 6 distinct values (5 live + cc2…ccf expired)**. Probes ~04:0xZ 5/6 HTTP 200 (849…c972 $0.054431909/$5 flat, 8fd…2cb mgmt+provisioning $0, b34…ee7 $0.0268725/$50 flat, 735…281 $11.846432356/$50 weekly = `uncensored` profile key, c610…a74 DeepSeek **$69.85, −$6.69 since #86**); cc2…ccf 401 expired (16th fire). Vault commit `a87ab67`, pushed `s3sync`.

- 🔴 **NEW 7th LIVE KEY — `sk-or-v1-cde63…dbb1` (73 chars), HTTP 200, `usage 200.01235491` / $200 limit (exhausted).** Carrier: `~/.hermes/cron/output/0f5a163f0fb8/2026-07-15_09-19-35.md` — the **memoryd crash-loop report** (job `0f5a163f0fb8`, 2026-07-15) which prints `**Key in use:** \`sk-or-v1-cde63…\``; sibling `2026-07-15_09-22-53.md` names the same key with the root cause "HTTP 403 Key limit exceeded". Not in any PLAINTEXT_DIR and predates every 24h window → **the scanner can never flag it**; it surfaced only from an explicit `sk-or-v1-` literal sweep of the `cron/output/` tree. Prefix grep across `cron/`, `logs/`, `env-file`, `config.yaml`, `profiles/`, dexdat repos = those 2 files only. **Scrubbed in place** (`2026-07-15_09-19-35.md` 1 occurrence → `sk-or-v1-cde63…<redacted:73>`, mode 600; the sibling already carried the truncated form). **Revocation still pending.**
- **Lesson (new surface class): archive/report dirs are blind spots.** `cron/output/` is outside all PLAINTEXT_DIRS, so a key pasted into a run record at write time is invisible forever (the #80 fix scrubbed the secret-scan job's own archive once, but nothing re-sweeps it). Each fire should keep running the literal `sk-or-v1-`/`sk-c610` sweep over `~/.hermes/cron/output/` and treat any 40+-char hit as REAL unless it is a known sequential dummy (the only benign hit: `sk-or-v1-1234…` echoed in `fd09dc919926/2026-09-13_05-12-04.md` = the june2026-pitfalls fixture).
- Surface deltas at #87: `.curator_backups/blobs/` **13,586 blobs / 176 MB** (was 13,380/170 MB); `skills.bak-2026-08-23/` 207 MB, **5th fire** as the 4th PLAINTEXT_DIR (4 files carry `sk-or-v1-` 40+ forms = 3 REAL copies + the sequential dummy), still not deleted; `~/.hermes/recovery/` 13 GB, `state_new6.db` 13.42 GB (mtime Sep 10) still holds all 6 keys; `~/telegram-archive/` live OR/DS literals + 5 bot tokens; `chimera.yaml` still TRACKED (`check-ignore` rc=1, ahead 1); `logs/gateway-shutdown-diag.log` **0 full-key residual** (redaction holds, 2nd fire). No public-GitHub exposure.

## /home/kara/trouble: the scrubber spec's own PEM BEGIN-marker table — new FP source (scan #90, 2026-09-16)

`/home/kara/trouble` — Bane's scrubbing/telemetry project (created 2026-09-16). Commit `73322a8` ("specs: SPEC-01..12 + SPEC-TYPES + INDEX", 10:22Z) added 12 spec files; `specs/SPEC-02-scrubbing.md` lines **225–227** are the spec's OWN detection-pattern table:

```
   BEGIN markers (literal, case-sensitive, multi-line span to the end of the block):
     "-----BEGIN PRIVATE KEY-----"          "-----BEGIN RSA PRIVATE KEY-----"
     "-----BEGIN DSA PRIVATE KEY-----"      "-----BEGIN EC PRIVATE KEY-----"
     "-----BEGIN OPENSSH PRIVATE KEY-----"  "-----BEGIN ENCRYPTED PRIVATE KEY-----"
```

- **Why FP**: the lines ARE the scanner's subject matter — the spec defines the `private_key_block` rule by quoting the PEM headers it must detect. Headers only, **no body**; a key cannot exist without one. Same class as the gitreins-poc `specs/04-Guard-System.md` detection-regex table (scan #32/2026-08-13) and the chained "spec's own pattern table" family.
- **Verification probes (all cheap)**: (1) `git log --all -p -- . | grep -cE '^\+[A-Za-z0-9+/]{60,}={0,2}$'` → **0** = no PEM body line anywhere in history; (2) `git grep -c -- '-----BEGIN' HEAD` → **6**, all inside that one spec table; (3) `git remote -v` → **empty** = local-only, never published. The repo's own Go test vectors (`internal/scrub/*_test.go`, untracked) embed the same headers with truncated dummy bodies (`MIIEow`, `MIIEowIBAAKCAQEAx3Zk`) plus `AKIAIOSFODNN7EXAMPLE` — fixtures by construction.
- **Fix shipped**: new scanner FP rule (quoted, complete PEM BEGIN-header literal with no base64 body on the line) — the pre-existing rule covered only backtick-wrapped headers, so quoted header strings in detection tables and Go string literals fell through. 7-case canary pre-patch 3 FAIL → post-patch ALL_OK; real forms (quoted header + escaped-`\n` body, bare committed-key diff line, `TEST_KEY_PEM = """-----BEGIN RSA…`) still flag; targeted re-scan of the repo → 0 findings.
- **Re-flag expectation**: any new commit to that spec (or a sibling spec quoting the same headers) re-enters the file in the 24h diff window — future fires carry forward with the three probes above, no re-investigation. If the project keeps committing spec churn, consider a path-level allowlist for detection-pattern tables.

## Scan #92 (2026-09-17 04:01Z) — SPEC-02 scrub-spec family, four extra carriers

The `/home/kara/trouble` SPEC-02 scrub-spec marker text (suppressed in `specs/SPEC-02-scrubbing.md`
by scan #90's quoted-header rule) re-flagged CRITICAL via four carriers the rule did not cover.
All four are documented-example / test-fixture material — **no key material anywhere**:

| Carrier | Line | Rule gap | New rule |
|---|---|---|---|
| `docs/specs-review.html` (generated review copy, `docs/build_specs_review.py`) | 2664–2666 | quotes HTML-escaped → `&quot;-----BEGIN …`, never a literal `"` | `&quot;-----BEGIN [A-Z ]*(?:PRIVATE KEY\|…)-----` |
| same file, §7 vector table | 3401 | header wrapped in `<code>…</code>`, no quotes | `<code>-----BEGIN [A-Z ]*…` |
| `internal/scrub/testdata/vectors/vectors.txt` | 9 (P7) | unquoted TSV field; `/testdata/` not matched by the `/tests?/` path rule | path+content pair `/scrub/testdata/.*(private_key_block\|\[REDACTED:)` |
| `internal/scrub/spans.go` | 174 | `setToken = "<alphabet run>"` — byte-set const (no `_`, so the env-var-NAME rule misses) | `"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz` |

Re-confirmation probes (any future re-flag):

```bash
grep -c MII /home/kara/trouble/docs/specs-review.html          # expect 0  -> no key body in 20,874 lines
sed -n '9p' /home/kara/trouble/internal/scrub/testdata/vectors/vectors.txt   # body = 28 base64 chars (real 2048-bit RSA = ~1,600+)
sed -n '172,176p' /home/kara/trouble/internal/scrub/spans.go   # setBearer/setJWT/setToken/setInline/setEntropy = byte-SET constants
git -C /home/kara/trouble remote -v                            # empty -> local-only, nothing published
```

Canary that must stay green after any rule edit: 6/6 suppressed **and** 5/5 real-material controls still
detect (bare committed-key header diff line · header + escaped-base64 body one-liner (JSON) ·
real-shaped `sk-or-v1-…` key · Telegram bot token · `ghp_` PAT). Full re-run after patching:
`scan-git-secrets.py --hours 24` → 0 findings / exit 0.

## Scan #93 (2026-09-17 10:01Z) — secret-store KEY-NAME constants + the shallow-clone whole-tree artifact

**Two new lessons, one FP class.**

### FP class: secret-store lookup-key / auth-method-ID constants

```ts
// apps/server/src/cloud/config.ts            (public upstream pingdotgg/t3code)
export const RELAY_URL_SECRET = "cloud-relay-url";
export const RELAY_ISSUER_SECRET = "cloud-relay-issuer";
export const RELAY_ENVIRONMENT_CREDENTIAL_SECRET = "cloud-relay-environment-credential";
export const PUBLISH_AGENT_ACTIVITY_SECRET = "cloud-publish-agent-activity";
// apps/server/src/cloud/CliState.ts
export const CLOUD_CLI_DESIRED_LINK_SECRET = "cloud-cli-desired-link";
// apps/server/src/cloud/CliTokenManager.ts
const CLOUD_CLI_OAUTH_TOKEN_SECRET = "cloud-cli-oauth-token";
// apps/server/src/provider/acp/GrokAcpSupport.ts
const GROK_AUTH_METHOD_CACHED_TOKEN = "cached_token";
```

The value is the **key you pass to the secret store**, not the secret:
`readSecretString(PUBLISH_AGENT_ACTIVITY_SECRET)`, `secrets.set(CLOUD_CLI_OAUTH_TOKEN_SECRET, …)`,
`secrets.get(CLOUD_CLI_OAUTH_TOKEN_SECRET)`. The real credential lives in the OS keychain
behind `ServerSecretStore`. Sibling constants on the same lines prove the convention —
`CLOUD_MINT_PUBLIC_KEY = "cloud-mint-ed25519-public-key"` (unflagged),
`GROK_AUTH_METHOD_API_KEY = "xai.api_key"` directly above the flagged `..._CACHED_TOKEN = "cached_token"`.

**Fast re-confirmation probe** (5 s, no rule archaeology):

```bash
grep -n 'secrets\.\(get\|set\)\|readSecretString(' <repo>/apps/server/src/cloud/config.ts | head
```

If the flagged constant is a *name* argument to a get/set/read call, it is an identifier, full stop.

### Why the whole tree looked "added": a depth-1 clone

`/home/kara/t3code` is a fresh **shallow** clone (`.git/shallow` present). The shallow boundary
commit is also the `origin/main` tip, and a boundary commit has **no parent** — so
`git show <boundary>` / `git log -p` report the ENTIRE tree as added lines
(**21,925 files / 4,254,638 added lines** for that repo alone). Any identifier-shaped constant
anywhere in the upstream tree therefore looks like a new in-window finding.

Detection is one command:

```bash
cd <repo> && git rev-list --parents -1 HEAD   # a single hash (no parent) on an UP-TO-DATE repo = shallow boundary
cat .git/shallow                              # names the boundary commit
git rev-parse origin/main                     # boundary == origin/main tip -> content is published upstream code
```

Do **not** read the boundary commit's output as Bane's work. Separate the local commits with
`git log --since=<cutoff> --oneline` and check reachability of each
(`git branch -r --contains <sha>` / `git ls-remote --heads origin | grep <branch>`): in #93, 6 of 7
flags came from the boundary commit (upstream author), and only 1 came from the local branch
`feat/generic-acp-driver`, which has **no upstream and does not exist on origin** → nothing published.
Sweep the boundary tree with own patterns before calling it clean; #93 found 4 value-shaped hits,
all inside a vendored upstream `alchemy-effect` test tree (2× AKIA example keys, one
`{"databaseUrl":"postgres://localhost"}` fragment, one Fly test-cert body) plus 88 `-----BEGIN`
marker lines with **0** base64 bodies.

### Scanner rules added (49 → 51)

```python
# (a) keychain key NAME constants
re.compile(r'[A-Z0-9_]{2,}_SECRET\s*[:=]\s*"[a-z]+(?:[-_.][a-z]+)+"'),
# (b) ACP/auth-method IDs
re.compile(r'AUTH_METHOD[A-Z0-9_]*\s*[:=]\s*"[a-z]+(?:[._-][a-z]+)+"'),
```

Narrow by construction: the assigned value must be a COMPLETE quoted chain of **lowercase letters**
joined by `-`/`_`/`.` — no digits, no uppercase. Real key material is base64/hex and carries digits,
so `OPENROUTER_API_SECRET = "sk-or-v1-73504d…"` still detects (`v1` has a digit, and the value must
run to the closing quote). Canary procedure that must stay green after any rule edit: **7/7 live flags
suppressed AND 9/9 real-material controls still DETECTED with pre-patch verdicts unchanged** — the
`old==new` comparison (loading the `.bak` module and diffing verdicts per line) is what proves the new
rules narrow to the identifier shape and change nothing else.

Gotcha when building that canary: `importlib.util.spec_from_file_location` refuses a backup whose
filename doesn't end in `.py` (raises `'NoneType' object has no attribute 'loader'`) — copy the
backup to `/tmp/<name>.py` first, or load it with `importlib.machinery.SourceFileLoader(name, path)`
+ `spec_from_loader` (works on the `.bak-<ts>` filename directly).

## Scan #96 (2026-09-18 10:02Z) — status/sentinel string constants (Go camelCase `*Token`)

**1 CRITICAL flag, FP.** `/home/kara/bunker` `internal/agent/manager_lifecycle.go:41`
`stoppedToken = "agent_stopped"` (13 chars), carrier `948ebf4` ("feat(lifecycle): add
StopAgent/StartAgent/RestartAgent lifecycle RPCs and CLI", 2026-09-18 00:08:12 -0500 = 05:08Z,
single in-window commit for the file).

- **Why FP**: the value is the **status/sentinel error token** — `var ErrAgentStopped =
errors.New(stoppedToken)` and the RPC message `"%w: agent %q is stopped; run 'bunker start %s'"`;
the file's own comment calls it "the stable token \"agent_stopped\"". Same shape as its
const-block siblings `StatusAlreadyStopped = "already_stopped"` / `StatusStopped = "stopped"`.
Live bunkerd credential is unrelated (random 48-hex in `/etc/bunkerd/config.yaml`).
- **Scanner quirk**: the finding prints `File: +++ b/internal/agent/manager_lifecycle.go` — the
repo's diff-header path rather than the bare path; read the working-tree line, not the header.
- **Rule added (52 → 53 FP rules)** — the pre-existing fixture rule keys on `[A-Z0-9_]*TOKEN`
(uppercase names only), so camelCase status consts fell through:
  ```python
  re.compile(r'[A-Za-z0-9_]*[Tt]oken\s*[:=]\s*"(?!(?:sk|gh[opsur]|github_pat|tskey|xox|AKIA|AIza|eyJ|glpat)[-_A-Za-z0-9]*")[a-z][a-z._-]*"')
  ```
  Narrow: value must be a whole quoted chain of **lowercase letters** joined by `-`/`_`/`.` (no
digits, no uppercase) **and** must not open with a known key prefix. Canary pre=`68d072e4…`
(`/tmp/scan-git-secrets-prepatch.py`, `/tmp/canary-scan-1002z.py`): 4/4 sentinel cases suppressed
(live flag, sibling const, generic camelCase sentinel, #94 `test-regression-token`) and **12/12
real-material controls still DETECT old==new**, including a real `sk-or-v1-` key ON a `*Token`
name, an **all-lowercase** `ghp_…` (prefix guard), `xoxb-`/telegram/`tskey-api-`/PEM-header.
Full re-run → 0 findings / exit 0 with the carrier still in-window. Independent sweep: 14,027
added lines in the repo's 24h window, 8 own patterns → 0 value-shaped hits, 0 PEM markers.

**Labelled live-key re-probe (OpenRouter `/api/v1/auth/key` `data.label` — report keys by the
provider's own label, never by value)**: `849…972` $0.054431909/$5 in git-tracked
`~/chimera/chimera.yaml` · `735…281` $11.846432356/$50 (`profiles/uncensored/.env` +
world-readable `~/.hermes/backups/n100-configs/.env`) · `8fd…2cb` mgmt+provisioning `$0`
(`OR_MANAGEMENT_KEY`) · `d8c…df5` $33.993702341/**$10 over limit** (`GITREINS_OPENROUTER_KEY`) ·
`022…20f` $23.825306031 no limit (`MYTHOS_OPENROUTER_KEY`) · `052…48d` mgmt+provisioning `$0`
(`OPENROUTER_MANAGEMENT_KEY`) · `cc2…ccf` **401 expired, 19th consecutive fire** = main-profile
`OPENROUTER_API_KEY` (`~/.hermes/.env` + `ai_plays_poke/.env`) · DeepSeek **account balance
$422.66** (−$116.02 since #89's $538.68; `/user/balance` is ACCOUNT-level, so every DS key in a
file reports the same figure — identify DS keys by env-var NAME, not by balance). `b34…ee7` has no
live copy (4th fire). Vault commit `7a45e90` (2 files, +144/−1), pushed `s3sync`.

## bunker: documented E2E test-fixture tokens in `e2e-full-battery.sh` — new FP source

Discovered 2026-09-17 16:01Z (scan #94, 125 repos / 30 active). Carrier `f3d8543`
(`fix(e2e): explicit daemon inputs and an isolated CLI config so the E2E gate is reproducible
(INT-CI-010)`, 2026-09-17 11:21Z) — 2 CRITICAL `credential` flags, both in
`/home/kara/bunker/e2e-full-battery.sh`:

- **Line 160** — `BUNKER_TOKEN="test-regression-token"` (21 chars): the battery's **documented input
  default** (`README.md:620` env table), applied by `resolve_inputs()` only when the caller left
  `BUNKER_TOKEN` unset/blank, and recorded as `BUNKER_TOKEN_SOURCE=default` (vs `env`).
- **Line 772** — `ST_EXPLICIT="$( … export BUNKER_TOKEN="selftest-token-explicit"; resolve_inputs;
  printf … )"` (23 chars): an **input-precedence self-test literal**, existing only to prove an
  exported `BUNKER_TOKEN` wins over the default (asserts `18080|env|http://localhost:18080`).

**Why FP** (verified, not inferred): the live daemon token is unrelated — `/etc/bunkerd/config.yaml`
(`auth.enabled: true`) carries a random 48-hex value and every `~/.bunker/*` client config a random
48-hex token (GAP-014 rotated the daemon off the test token; the old value is gone from
`config.yaml.bak-t236`). The repo documents the convention itself:
`skills/bunker-usage/SKILL.md:87` — *"Never commit real tokens — the test token
`test-regression-token` (in e2e scripts) is fine for the MVP."* Sibling fixtures: `e2e-jwt.sh:19`,
`e2e-tls.sh:56/117/160`, `regression-tests.sh:251`, `internal/cli/client_test.go`. Shape: lowercase
word chains (no digits/uppercase/base64, no live-key prefix), and the battery prints only
`token_fingerprint()` = `sha256[:8]` (line 994), never the value.

**Attribution probe**: 5 in-window commits touched the file; `git show <c> -U0 -- <file> |
grep -c '^+.*<value>'` → 2 / 1 added lines for `f3d8543`, **0** for
`d157156`/`cdd8b29`/`4623699`/`0edfb11` = single carrier (so the flags age out with it even
without the rule).

**Independent sweep**: all 8,564 added lines of every in-window commit in the repo, swept with own
patterns (`sk-or-v1-`, `sk-` 20+, `ghp_/gho_/ghu_/ghs_/ghr_`, `github_pat_`, `AKIA`+16,
`tskey-api-`, Telegram `\d{5,12}:AA…`, `xox[baprs]-`, `AIza…{35}`, `eyJ`) → **0 value-shaped hits**,
0 `-----BEGIN` markers, 0 lines with a 200+ char base64 run; the 17 unique quoted ≥20-char values are
commit SHAs or snake_case identifiers.

### Scanner rule added (51 → 52)

```python
# (c) self-describing fixture TOKENs: value = lowercase word chain that spells "token"
re.compile(r'[A-Z0-9_]*TOKEN\s*[:=]\s*"[a-z][a-z._-]*token[a-z._-]*"'),
```

Narrow by construction: the whole quoted value must be **lowercase letters joined by `-`/`_`/`.` and
must itself spell `token`**. Real key material is base64/hex (digits or uppercase), so a genuine leak
on the same name still fires — `BUNKER_TOKEN="sk-or-v1-73504d…"` cannot match (`v1` is a digit).
Canary (scan #94): **2/2 live flags suppressed AND 10/10 real-material controls unchanged (old==new,
all DETECTED)** — including the two controls that matter most: a real-shaped `sk-or-v1-` key ON a
`*_TOKEN` name, and a mixed-case/digit value on a `*_TOKEN` name. Full re-run → 0 findings / exit 0
with the carrier still in-window (= suppression, not window drift).

## Scan #100 (2026-09-19 16:05Z) — the secret-scrubber's OWN fixture battery; xKiro store rows redacted; log-file blind spot

**4 CRITICAL, 4/4 FP, 0 real secrets in-window** — a NEW FP carrier class, and the first fire where the two
INFO timeouts were closed in-run.

### FP class: the scrubber's own test battery (`~/.hermes/scripts/test_secret_scrub.py`)

Carriers `8edba9f` (create, 2026-09-19 09:18:17 -0500) + `a559877` (ghpou_ line, 09:27:11 -0500) — both
in-window. The file is the SEC-001 battery for `secret_scrub.py`: it plants ONE credential-shaped dummy per
provider so it can assert `scrub()` redacts each. Its docstring says it outright: *"All planted values are
SYNTHETIC (same shape as real secrets, never real values) — do not paste real keys into this file."*
Four values flagged CRITICAL: `sk-or-v1-fake0fa…` (openrouter_key), `ghp_FakeToken…` / `gho_FakeOAuth…`
(github_token), `xoxb-123456789012-123456789012-FaKeToKeN…` (slack_token). Self-describing tells: the
literal `fake`/`Fake`/`FAKE` inside the body, `github_pat_11FAKE…`, `tskey-api-kFAKE…`,
`sk-xt-fake…`, `AKIAIOSFODNN7EXAMPLE`, and the sequential `1234567890` blocks. `~/.hermes` has **no git
remote** → nothing published. Independent sweep agreed independently (32 distinct hits, 8 of them this file).

**Scanner rules added (57 → 59 FP rules)**:

```python
# (a) 'fake' spelled inside the body right after a real-key prefix
re.compile(r'(?i)(?:sk-[A-Za-z0-9-]{0,7}|gh[pousr]_[A-Za-z0-9]{0,4}|'
           r'github_pat_[A-Za-z0-9]{0,4}|tskey-[a-z-]{0,6})fake'),
# (b) the canonical sequential Slack placeholder (xoxb-1234567890123 / xoxb-123456789012-…)
re.compile(r'xox[baprs]-1234567890\d*'),
```

Canary (`/tmp/canary-scan-100b.py`, pre-patch copy `/tmp/scan-git-secrets-prepatch-100.py`): the four
actually-flagged battery lines flip `fp=False → True` (suppressed) while **10/10 real-material and
narrowness controls keep an IDENTICAL (matched-type, fp=False) verdict** — real `sk-or-v1-`, real
`sk-xt-`, `ghp_`/`gho_`/`ghr_`, Telegram bot token, `xoxb-` random body, PEM header diff line, plus two
narrowness probes (`sk-or-v1-<30 hex>fake<20 hex>` = marker too far from the prefix → still detected;
`xoxb-<6 digits>1234567890…` = sequential digits not at body start → still detected). Full re-run with the
carriers still in-window: **1 finding = 1 INFO timeout / 0 critical, exit 0** = suppression, not drift.

### Remediation verified: xKiro rows in the chat-archive namespace store

`~/duckbrain/namespaces/chat-archive` HEAD now carries `sk-xt-[REDACTED]` in `_audit/current.jsonl` +
`message/2026-09/0091.jsonl`; `git log --all -G 'sk-xt-[0-9a-f]{16,}'` → **0 commits**, `rev-list
--count @{u}..HEAD` → **0** (upstream `s3daily/master` matches HEAD), and `.git/filter-repo` is present
= the store was history-rewritten and force-pushed after #97. #97's carrier hash `818339a` no longer exists
in the repo. **Still open**: the full value of `sk-xt-4a00…ed37` (sha `e76eda5ea9`, identical to #97's)
sits in `~/.hermes/logs/gateway.log.2` + `agent.log.5` — logs are OUTSIDE every PLAINTEXT_DIR.

**xKiro liveness probe (learned this fire)**: a UA-less `POST /v1/chat/completions` returns
**HTTP 403 `error code: 1010`** (Cloudflare UA ban) — that is NOT evidence of revocation. Retry with a
browser `User-Agent`; the auth check then works and is decisive:
`sk-xt-…ed37` → **404 `Model "xkiro/auto" does not exist`** (auth ACCEPTED ⇒ key VALID + LIVE),
garbage control → 401 `Invalid or disabled ClientApiKey`, `sk-xt-…3569` (len 50, sha `be5e68c178`,
agent.log.5) → **401 disabled**. Probe a real model id or treat 404-model as the auth-pass signal.

---
name: models-dev-registry-crosscheck
description: >-
  Use when cross-checking routing registry against models.dev.
version: 1.0.0
platforms: [linux]
metadata:
  hermes:
    tags: [models.dev, routing-registry, cross-check, catalog, pricing]
    related_skills:
      - task-router
      - model-intelligence
      - task-router-ops
---

# Models.dev ↔ Routing Registry Cross-Check

## The pipeline (Bane 2026-08-27 — crons + commands, self-improving)

- `router_modelsdev.py sync` — models.dev → text DB: `model_catalog.jsonl`
  metadata sidecar + NEW models added with price NULL (gaps flagged, never
  silently missing). Stickers are catalog REFERENCE only — never normalized
  prices. **2026-08-27 fix: opencode-go (31 models), crof (21) and synthetic
  (8) ARE on models.dev — they were wrongly mapped to None and their whole
  catalogs (hy3, mimo variants, qwen3.7 family…) never loaded. PROVIDER_MAP
  now maps them. clinepass is NOT on models.dev — its 417-model catalog comes
  from its OWN API (https://api.cline.bot/api/v1/models, CLINEPASS_API_KEY);
  API-callable ids are `cline-pass/<bare>` (the org/model ids in /models are
  Cline-product-surface ONLY, 403 on raw API).**
- `router_pricing.py` — NORMALIZED (subscription-aware) pricing: plan_terms
  per provider (per_token / per_request / per_minute / official-points /
  **flat_subscription** → effective $/M). Cline Pass = flat $9.99/mo, 2-5x
  usage vs API rate: effective $/M = models.dev blended sticker ÷ multiplier
  for INCLUDED models only; non-included = PAYG gap. **Temporary discounts
  (`temporary_discounts.jsonl`): {provider, model ('*' = provider-wide),
  discount_type (percent|free), value, valid_from, valid_to (null = open),
  source, note} — applied on top of the base price, evidence gains
  '+discount(...)', `discount_valid_to` stamped on the row; expired rows
  auto-ignored. The 18 clinepass `:free` lanes are discount rows (free until
  revoked).** Never overwrite existing evidence rows.
- `router_gaps.py` — per-model missing-dimension report: price / catalog /
  benchmark / perf / tiers(n/24) / sentiment / notes. `--json` for agents,
  `--lacking N` / `--top N` filters.
- **`quality_estimates.jsonl` (data file, loaded by router_seed.py — Bane
  2026-08-27 no-hardcoding):** model-keyed {model, guard?, mock?,
  multilingual?, note?} survey estimates. The research agent may UPDATE this
  file with newly surveyed scores (source in note) — it is the dynamic
  replacement for the old hardcoded QUALITY_ESTIMATES dict in seed code.
  Missing file = warning + skip (visible gap), never a code fallback.
- **BLANK default (Bane)**: a model with no data in a category has NO perf/
  tier row and resolves as **-1** (clears lenient bars, fails 0+). No
  fabricated plus/minus, no neutral 0.50 fills.
- **Metrics ONCE PER MODEL (Bane 2026-08-27)**: model_perf/model_tier are
  keyed by (model, category) — evidence describes the WEIGHTS, not the lane.
  Quantiles run over unique models (per-lane duplication silently shifted
  tiers). Every provider lane inherits the same tier. **Lane-disable is an
  EXPLICIT opt-in** (models.disabled + disabled_reason for bad deployments),
  never the default.
- **PLAN SWEEP (Bane 2026-08-27 v2 — keep the list cut down)**: lanes that
  are expensive for us (high API pricing outside the flat plan) or shit
  models get DISABLED. `router_plan_sweep.py` mechanically disables every
  active lane of a flat_subscription provider that is (a) NOT in
  included_models AND (b) NOT covered by an active temporary discount —
  same treatment as the openai-codex archive. clinepass: 404 -> 29 active
  (11 in-plan + 18 :free lanes) as of 2026-08-27. **QUALITY SWEEP (v2)**:
  superseded-generation lanes (old model versions, unpriced, never in
  chains) get disabled with reason 'superseded generation — fleet uses
  <newer>'; 18 done 2026-08-27 (zai glm-4.x/5.x, ollama-cloud old gens,
  neuralwatt Qwen3.5/K2.5). Quality disables are the research agent's
  judgment (persistent complaints / failed evals / superseded gens) with
  disabled_reason = finding + source. Re-enable when plan economics change
  (model added to included_models, new discount). Disabled lanes: skipped by
  spawn/pricing/gaps, stay auditable in the registry.
- **per_request budget-unknown fallback (2026-08-27)**: when a per_request
  plan lacks per-model req rates, price = 0.96×sticker-in + 0.04×sticker-out
  (blended est, evidence 'normalized:sub-bucket(blended est)') — the
  registry-maintenance.md design; opencode-go 32/32 lanes priced this way.
- Cron `model-registry-data-quality` (a26c4522cfb1, daily 05:30, continuity):
  script step (sync+pricing+gaps) → research agent (benchmarks + sentiment
  → evidence rows in benchmarks.jsonl / model_notes.jsonl / plan_terms.jsonl)
  → seed → export → commit. Each run fills a slice; the next run continues.
- **LEARNING MEMORY (Bane 2026-08-27):** `scripts/router_learn.py` dump runs
  FIRST in the cron pipeline — doctrine (/doctrine/*), provider understanding
  (/providers/*) and lessons (/lessons/<date>-<slug>) load into the agent's
  context from duckbrain ns `task-router` before it acts; the agent writes a
  lesson + refreshes provider understanding at the end of each run. The
  seeded doctrines: SUBSCRIPTION-FIRST (sub is the price basis, normalized
  MUST beat PAYG sticker), NO-HARDCODING (provider facts live in
  data/tables/*.jsonl, never code), BLANK-DEFAULT (-1, never excludes).
- **Regime tests (56 as of 2026-08-27):** test_plan_included_lanes_never_disabled
  (plan lanes can't be disabled; scripts can't hardcode included lists),
  test_subscription_normalized_beats_payg_sticker (sub price < sticker),
  test_unpriced_sub_lanes_are_documented_gaps (NULL only with model_notes),
  test_p0_fore_has_no_tool_use_bar (Bane 2nd correction), fallback tests
  (always-run deepseek-v4 when subs down), fail-closed gates all eligible hops.

## When to Use

- Bane asks "what should be in the database" / registry coverage questions.
- Adding, removing, or vetting models/providers in routing.duckdb.
- Any phantom-model suspicion (registry row with no catalog backing).
- Building or running the `router_modelsdev.py` cross-check tool.

Bane's directive (2026-08-27): keep the registry's model list honest against
the **models.dev catalog** — what should be in the database. This skill is the
method + the spec; the script (`router_modelsdev.py`) becomes part of the
task-router runtime system (repo `scripts/`, wired via `sync_runtime.sh`).

## Why models.dev

- The catalog of what EXISTS in the world (204 providers as of 2026-08-27).
- **Sub plans appear as their own providers** with `$0/$0` pricing
  (`zai-coding-plan`, `minimax-coding-plan`, `stepfun-ai-step-plan`,
  `zhipuai-coding-plan`, `alibaba-coding-plan`, `tencent-coding-plan`,
  `umans-ai-coding-plan`, …) — these are the flat-rate lanes the registry
  must carry as (provider, model) rows.
- Registry rows are CLAIMS; models.dev + live probes are TRUTH (same doctrine
  as TR-008: a model that exists in neither place must not head a chain).

## The two stores (architecture answer)

- **Routing registry = gitignored TEXT file** — `/home/kara/task-router/registry.json`
  (version 3: `{"version", "generated_at", "tables": {name: [record...]}}`, all 11
  tables). Written by `router_seed.py` (which computes derivations in an in-memory
  duckdb engine), read by `router_spawn.py` (pure python — no duckdb needed).
  The old binary `~/reports-repo/routing.duckdb` is RETIRED (archived at
  `~/.hermes/model-router/archive/routing.duckdb.retired-2026-08-27`).
- **DuckBrain = separate system** (git-backed memory, own DuckDB + HTTP :3000
  + MCP). The `routing`/`task-router` namespaces under `~/duckbrain/namespaces/`
  are **git repos of JSONL exports** (each with an s3daily remote) — versioned
  snapshots for backup/audit, NOT the live queryable store. Never query the
  registry through duckbrain; never hand-edit those JSONL tables (regenerate +
  export + commit).

## Registry inventory (query recipes)

```bash
~/.hermes/venvs/board/bin/python3 - <<'EOF'
import duckdb
db = duckdb.connect('/home/kara/reports-repo/routing.duckdb', read_only=True)
q = db.sql
print('providers :', q('SELECT count(*) FROM providers').fetchone()[0])
print('models    :', q('SELECT count(*) FROM models WHERE NOT archive').fetchone()[0])
print('archived  :', q('SELECT count(*) FROM models WHERE archive').fetchone()[0])
print('categories:', q('SELECT count(DISTINCT category) FROM model_perf').fetchone()[0])
print('perf rows :', q('SELECT count(*) FROM model_perf').fetchone()[0])
print('profiles  :', q('SELECT count(*) FROM task_profiles').fetchone()[0])
EOF
```

Known good (2026-08-28): 15 providers · 626 model rows (34 archived, 480
quality/plan-sweep disabled, 112 active, 103 priced, 9 unpriced = all
documented gaps with notes) · 24-category taxonomy (22 evidenced) · 8
profiles. clinepass 404
lanes: 13 in-plan (official docs 08-27) + 18 :free lanes active; the rest
PAYG-disabled (prices unpublished → NULL, never guess). grok-build: SuperGrok
$30/mo sub — 7 lanes priced sticker/3.0 (0.50–1.3333), validated < PAYG.
Sanity:
model_perf is model-keyed (metrics ONCE PER MODEL) — lane perf_* columns in
models.jsonl feed it via unpivot; the gaps report flags LANES whose own
perf_* are blank (fill from family values).
Schema note: `providers.id` is the key (no `name` column); `models` PK is
(provider, model, valid_from); both tables carry `archive` + `valid_to`;
`disabled` + `disabled_reason` = intentional exclusion (plan/quality sweep).

## models.dev access

- Endpoint: `https://models.dev/api.json` (browser UA required:
  `curl -H "User-Agent: Mozilla/5.0 ..."`). No API key.
- **Fresh cache already in the system**: `~/.chimera/models-dev-cache.json`
  (7.4 MB, auto-refreshed by the chimera project — verify mtime before
  fetching; a cache <24h old is fine for cross-checks).
- Model entry shape: `id` (provider-scoped, e.g. `deepseek/deepseek-v4-flash`
  → within provider dict the key is `deepseek-v4-flash`), `name`, `family`,
  `cost` = `{"input": $/M, "output": $/M, "cache_read": ..., "cache_write": ...,
  "reasoning"?: ...}` (sub-plan providers: all zeros), `limit.context`,
  `reasoning`, `tool_call`, `release_date`.
- Price source caveat: models.dev prices are THEIR catalog; the registry's
  `normalized_price` for deepseek comes from the OpenRouter spot-check
  (or-family-spot-check.py). The two can disagree (models.dev deepseek-v4-flash
  0.14/0.28 vs OR spot 0.0795) — models.dev is the LIST cross-check; OR is the
  repricing source. Never overwrite `normalized_price` from models.dev without
  noting the source in `price_evidence`.

## Provider mapping (registry ↔ models.dev) — the hard part

| Registry provider | models.dev provider(s) |
|---|---|
| deepseek | `deepseek` |
| zai-glm | `zai` (payg) + `zai-coding-plan` (sub $0) |
| ollama-cloud | **ON models.dev since 2026-08-28 (`ollama-cloud`, 21 models — catalog metadata only, all costs None); own catalog via ollama api remains the roster source** |
| opencode-go | **ON models.dev (`opencode-go`, 31 models)** — loaded since 2026-08-27 |
| clinepass | NOT on models.dev — own API (api.cline.bot, 417 models, `cline-pass/` ids) |
| kimi-for-coding | `moonshotai` / sub-plan lanes (ToS-gated, batch BANNED) |
| neuralwatt | **ON models.dev (`neuralwatt`, 25 models)** — loaded since 2026-08-27 (was wrongly marked NOT-on-models.dev; cache check 08-27 confirmed 25/25 with costs) |
| minimax | `minimax` + `minimax-coding-plan` + `minimax-cn-coding-plan` |
| stepfun | `stepfun` / `stepfun-ai-step-plan` |
| groq | `groq` |
| openai-codex | NOT on models.dev — codex platform serves ONLY codex-family models (gpt-5.x-codex, 5.6-luna/sol/terra); the full `openai` API catalog was archived (33 rows) — do NOT re-map to `openai` |
| synthetic | **ON models.dev (`synthetic`, 8 hf: models)** — loaded since 2026-08-27 |
| grok-build | `xai` (grok family, 7 chat models; grok-imagine-* image/video correctly filtered) — gated in quota-state anyway |
| crof | **ON models.dev (`crof`, 21 models)** — loaded since 2026-08-27 |
| muse-spark | `muse-spark` (contributor plan) — 0 models loaded (no catalog source; flag) |

Rule: for providers NOT on models.dev, the cross-check's verdict is
"verify via live probe" (provider_health_probe.py + /models endpoint), never
"missing → remove".

## Provider data sources & billing map (Bane 2026-08-27 — the cron's cheat sheet)

For each provider: where to get the REAL data, the billing structure, and quirks.
Billing understanding beats sticker prices: find the subscription economics
(included models, windows, caps, multipliers, promos), then price.

| Provider | Data source(s) | Billing model | Rules / quirks |
|---|---|---|---|
| clinepass | `GET https://api.cline.bot/api/v1/models` (417) + `/plans` (CLINEPASS_API_KEY) — `router_clinepass.py sync` does all of it + **docs.cline.bot/getting-started/clinepass.md = OFFICIAL reference table (13 included models, per-1M rates)** | flat_subscription $9.99/mo, 2-5x usage vs API rate; **effective $/M = docs reference / 3.0**; included list = 13 (docs 08-27: kimi-k3, glm-5.2, glm-5.3, kimi-k2.6, kimi-k2.7-code, mimo-v2.5, mimo-v2.5-pro, minimax-m3, qwen3.7-plus/max, qwen3.8-max, deepseek-v4-pro/flash) | caps $1B/5h $2.5B/7d $5B/30d; callable ids `cline-pass/<bare>` (org/model = product-only 403); `:free` lanes = temporary discounts; deepseek-v4-flash lane flaky 500; deepseek peak/off-peak reference variants published (v4-pro 1.32/3.96 peak vs 0.66/1.98 off; v4-flash 0.44/1.32 vs 0.22/0.66); qwen3.7-plus tiered ≤256K 0.40/1.60 vs >256K 1.20/4.80; API /models carries NO cost fields (id/created/owned_by only) → PAYG prices for non-included models UNPUBLISHED → NULL + note, never guess |
| opencode-go | models.dev `opencode-go` (31 models); pricing on opencode.ai | per_request $12/5h lane (31,250 tok/req assumption) | 5h + weekly + monthly credit windows. **hy3 = Tencent Hy3-preview (295B A21B MoE, 192 experts top-8, hy.tencent.com/research/hy3) — vendor SWE-bench Verified 74.4 / Terminal-Bench 2.0 54.4 / BrowseComp 67.1 / WideSearch 70.2; cheap-workhorse lane (research 2026-08-29)** |
| crof | models.dev `crof` (21 models) | unknown — research (wrapping reseller) | quota GATED (inflation 328x measured, canary pending) |
| synthetic | models.dev `synthetic` (8 hf: models); synthetic.new/pricing + dev.synthetic.new/docs/api/models | **per_token (usage-based rates published) — priced at sticker as conservative cap; subscription packs ALSO exist ($1/day or $30/mo, 500 req/5h per pack, all always-on included, no per-token billing on sub)** | hf: prefix kept in model names; fleet runs packs (5-pack ceiling 35 concurrent per quota-state) — pack marginal cost ~0, but no multiplier published → sticker used; syn:* aliases (syn:large:text → hf:zai-org/GLM-5.2, syn:small:text → GLM-4.7-Flash, syn:large:vision → Kimi-K3, syn:small:vision → Qwen3.8-27B) resolve to always-on models |
| ollama-cloud | models.dev `ollama-cloud` (21 models, costs None — catalog cross-check only) + ollama.com/pricing page + own API; per-model $/M only on JS-rendered library pages (NOT scrapable via plain HTTP — research gap) | **flat_subscription: grandfathered Max $100/mo (NEW sign-ups PAUSED 08-27), Pro $20/mo; usage-bucket plan (10 concurrent models, 5× Pro usage) — no per-model included list** | ceiling UNDER TEST; concurrency free; per-model rates unpublished → 9 lanes NULL + note (measured estimates for 14 lanes); catalog name mismatch: registry `gemma-4:31b` vs models.dev `gemma4:31b` |
| zai-glm | models.dev `zai` (16); api.z.ai coding paas v4; **docs.z.ai/guides/overview/pricing.md + devpack/*.md (official)** | official-points (points/M × $0.03); **official multipliers 08-27: glm-5.3 6.9/1.7/24, glm-5-turbo 5.7/1.5/21, glm-4.7 4.6/1.2/16, glm-4.6v 1.2/0.3/2.7, glm-5.3-flash 2.3 (3× quota vs 5.3); glm-5.2/5.1 NO multiplier — AUTO-ROUTED to glm-5.3 billed at 5.3 rates (0.207)** | off-peak lanes cheaper; glm-5.3-flash-offpeak exists; ONLY callable on plan: glm-5.3, glm-5.3-flash, glm-5-turbo, glm-4.7, glm-4.6v; legacy lanes (glm-4.5*, glm-4.6, glm-4.7-flash/x, glm-5, glm-5v-turbo) NOT callable → NULL + note; glm-4.7-flash & glm-4.5-flash FREE on API (0/0); GLM-5.3-Flash 50% API promo ends 2026-09-09 24:00 UTC+8 |
| deepseek | models.dev `deepseek` (3); api.deepseek.com | per_token PAYG (or-spot repriced) | legitimate fallback hop, never primary over healthy sub |
| groq | models.dev `groq` (15) | per_token PAYG | sticker = price; free-tier rate limits; whisper/audio filtered; `groq/compound` + `groq/compound-mini` = router alias lanes (NO published price → NULL + note); bare `gpt-oss-120b`/`gpt-oss-20b`/`qwen3.6-27b` lanes = FREE-tier 0.0 alongside priced `openai/...` namespaced lanes |
| kimi-for-coding | models.dev `kimi-for-coding` (4) + `moonshotai` | subscription (weekly quota) — **membership from $19/mo (CN Andante ¥49), weekly-refreshed Kimi Code credits (plan_terms 2026-08-29)** | 7-day quota window; batch/BYOK BANNED (ToS); 403 when exhausted; alias lanes `kimi-for-coding`/`-highspeed` = plan aliases resolving to k3/k3-256k, NOT models (price NULL + note) |
| minimax | models.dev `minimax` (7) | per_token PAYG (MiniMax API) | — |
| stepfun | models.dev `stepfun` (8) | per_token PAYG | tts/asr/audio filtered |
| neuralwatt | models.dev `neuralwatt` (25); portal.neuralwatt.com/pricing + docs/api/models | **per_token (pay per token OR per kWh — user choice); models.dev sticker = effective per-token price** | kWh rate conflict $10 vs $5 — support ticket (quota-state 08-24); cached_input_per_million = input × 0.25 platform default (models may override); energy methodology — prompt-size band grid on pricing page; superseded generations get quality-disabled (models.disabled) |
| grok-build | models.dev `xai` (12; 7 chat loaded); grok.com/plans + ofox.ai/felloai analyses | **flat_subscription: SuperGrok $30/mo (Bane's sub) — Grok Build agent unlocked May 24 2026 for ALL SuperGrok; ONE shared weekly usage pool across Chat/Imagine/Voice/Build (per-2h caps retired June 2026), tracked Settings→Usage; pool size NOT published → 3.0x multiplier ESTIMATE (ofox break-even ~1,875 turns/mo clears $30; steady ~85 turns/day). Normalized = blended sticker ÷ 3.0 (grok-build-0.1 $0.50, grok-4.3 $0.625, grok-4.5/4.6 $1.3333)** | quota GATED (pool unpublished); grok-imagine-* filtered; PAYG twins: grok-build-0.1 $1/$2, grok-4.3 $1.25/$2.5, grok-4.5/4.6 $2/$6 (cached $0.20); SuperGrok ladder: Lite $10, SuperGrok $30, X Premium+ $40, Plus $100, Heavy $300 |
| openai-codex | NOT on models.dev — codex platform only | codex subscription (OAuth JWT) | serves ONLY codex-family (5.3-codex, 5.6-luna/sol/terra); full OpenAI catalog archived 08-27 |
| muse-spark | NO source found yet — 0 models; models exist via clinepass `meta/muse-spark-1.2*` + opencode-go | unknown | needs research — flag, don't fabricate |

## SUBSCRIPTION-FIRST DOCTRINE (Bane, repeated 2026-08-27 — THE core rule)

The user pays for subscriptions. A provider Bane has a sub with is NEVER priced
"no published price → NULL" — **the subscription IS the price basis**. Rules:

1. For every sub provider, find: plan cost, interval, what the sub REPORTS
   (usage pool / credits / windows / caps — check usage/settings docs + plan
   page), how billing works (weekly pool, per-request windows, points), then
   derive normalized $/M = plan economics ÷ usable tokens, or sticker ÷
   usage_multiplier when the pool size isn't published.
2. "Not every provider puts their price down, and that is not to be trusted
   for a subscription" (Bane verbatim). Published per-token stickers are the
   PAYG basis for deriving the sub discount — never the sub's own price.
3. VALIDATE: normalized sub price MUST be cheaper than the PAYG sticker (why
   pay $30/mo if the effective price equals on-demand?). If normalized ≥
   sticker, the multiplier/pool assumption is wrong — redo it.
4. NULL is only for genuine PAYG providers with no discoverable terms (research
   hard first) or gated/deprecated lanes — and even then with a model_note.
5. Provider facts (plan lists, prices, multipliers, included models) live in
   data/tables/*.jsonl — NEVER hardcoded in scripts. Missing data = visible
   gap + warning, never a code fallback (regime lock: test_plan_included_lanes_never_disabled).

## How to price a lane you don't have terms for: find the provider's official
pricing page / plans API / announcement → extract plan cost + included usage →
write plan_terms.jsonl with billing_model + the math fields → run
router_pricing.py. If the structure can't be found, leave price NULL (visible
gap) and note it in model_notes — never guess.

## Cross-check workflow (manual today, script tomorrow)

1. **Inventory the registry** (queries above) → set A: active (provider, model).
2. **Load models.dev** (cache or fresh fetch) → set B: catalog ids.
3. **Diff:**
   - `B − A` = **gaps** (should be in the DB): new providers/lanes (e.g. a
     coding-plan lane not yet seeded), new models of families already carried.
     Each gap → decision: seed (with perf estimates from a benchmarked
     sibling per the task-router registry-data-loading recipe) or defer with
     reason.
   - `A − B` = **phantoms/suspects**: registry rows with no catalog entry.
     NOT auto-remove — check archive flag, live probe, and the not-on-models.dev
     mapping table first (ox-alpha-free precedent: phantom → archive + exclude
     from seed regeneration).
   - **Price drift** (same family, both priced): report only; repricing source
     stays the OR spot-check.
4. **Act:** seed changes go through `router_seed.py` (never hand-edit exports),
   then export + commit BOTH namespaces, regenerate `chains/<date>.md`,
   re-run `sync_runtime.sh` if scripts changed.

## Script spec — `router_modelsdev.py` (part of the system, to build)

Lives in `/home/kara/task-router/scripts/`, wired by `sync_runtime.sh` (symlink
into `~/.hermes/scripts/`, same topology as router_maintain.py).

- `fetch` — refresh `~/.chimera/models-dev-cache.json` (browser UA, fail-open:
  cache >24h → warn + use stale, never hard-fail).
- `diff [--json]` — the cross-check: registry inventory vs catalog; output
  sections GAPS / PHANTOM-SUSPECTS / PRICE-DRIFT with the mapping table applied;
  exit 0 always (fail-open doctrine).
- `report` — markdown report → task-router ns `docs/modelsdev-<date>.md`,
  commit convention follows the namespace repos.
- `--dry-run` on any mutating future subcommand; no writes without it.
- Consumers: operator CLI + future fleet cron (hourly is too hot — daily
  cross-check; the health probe already covers availability hourly).

## HEAD-DRIFT GUARD — run after EVERY evidence slice (mandatory, 2026-09-01)

Evidence slices move quantile boundaries (a 0.01 boundary move silently
excluded the fleet workhorse from P0_FORE for a full day). After re-seed +
export, ALWAYS diff the profile heads against the pre-slice state and REPORT
any change in the run summary:

```bash
PY=~/.hermes/venvs/board/bin/python3
# BEFORE slicing: snapshot heads
for p in muster uhlp hermes-dagger coding-hermes-scheduler duckbrain-sync; do
  $PY ~/.hermes/scripts/router_spawn.py $p --format json 2>/dev/null \
    | python3 -c "import json,sys;d=json.load(sys.stdin);h=d.get('head') or {};print('$p',h.get('provider'),h.get('model'),h.get('usd_1m'))"
done > /tmp/heads-before.txt
# ... run the slice (syncs + pricing + evidence rows + seed + export) ...
# AFTER: same loop → /tmp/heads-after.txt, then:
diff /tmp/heads-before.txt /tmp/heads-after.txt   # any diff = explain it in the run summary
```

A head change is not automatically wrong — but it MUST be explained by the
evidence that caused it ("kimi-k3 review 0.85 landed → review q10 boundary
0.60→0.61 → deepseek-v4-flash review tier -1→-2 → filtered"). An unexplained
head change = stop and root-cause before committing the slice.

ROUTER-MISS telemetry (shipped 2026-09-01): router_spawn.py now prints
`ROUTER-MISS: <provider>/<model> fails <cat>>=<lvl> (tier=N)` to STDERR for
every profile-requirement filter. Requirement failures NEVER appear in
exclusions/gate_reasons (they're filtered pre-gate) — stderr is the only
trace. If a formerly-head model is missing from a chain, grep stderr for its
ROUTER-MISS line first.

- **STALE GATE REASONS PROBE-FIRST (2026-09-05, kimi-for-coding 9-day stale
  gate)**: quota-state gate reasons citing WINDOW EXHAUSTION are snapshot
  state, not live truth — kimi-for-coding sat gated "weekly quota EXHAUSTED
  (403, 08-27)" for 9 days while all 3 lanes answered HTTP 200 (window resets
  weekly upstream; the gate file does not self-heal). Rule: before trusting
  any exhaustion reason older than a few days, run a 1-token chat probe;
  flip the gate only on today's response code. Same-day counter-example:
  clinepass 429 INFERENCE_CAP_ERROR = account-wide weekly cap, gate correct
  as of that probe (put the reset ETA in the reason). Probe beats assumption
  in both directions.
- **CLINEPASS CHAT IDS ≠ GET-/models IDS — evidence hierarchy for
  probe_fixes (2026-09-05)**: GET /models lists org/model ids
  (`deepseek/deepseek-v4-flash`) but chat completions REQUIRE
  `cline-pass/<bare>` — org-prefixed ids answer 403 "only available via
  Cline product surfaces", several vendor-prefixed ids answer 500
  empty-response. The 08-31 probe_fixes rows derived chat ids from the
  GET-/models listing and were wrong; a chat probe showed `cline-pass/<bare>`
  returning real quota semantics (429 = id valid, cap reached). Rule:
  probe_fixes for chat-callable ids must cite CHAT-probe evidence, never a
  GET-/models listing; append corrected rows (never edit history).

## Pitfalls (proven)

- **STALE-ESTIMATE PITFALL (2026-09-01, the deepseek review-0.60 incident)**:
  corrections to OLD-category perfs (review/reasoning/long_doc/delegation/
  agent_tick/debug/schema/e2e_vision/guard/mock — the columns models.jsonl
  rows already carry) MUST be written into data/tables/models.jsonl rows.
  PROFILE_TAGS in router_seed.py only fills NEW categories — for OLD columns
  it is dead code, and the documented correction silently never reaches the
  data. The stale fill (deepseek review 0.60) sat for 5 days, then a boundary
  move (0.60→0.61) flipped the fleet head with zero log lines. Symptom to
  watch: a model that "used to head chains" vanishes from every chain at once
  → `grep ROUTER-MISS` on spawn stderr, then check the category quantile
  boundary in category_levels vs the model's perf value.
- **UNSOURCED PRICE ESTIMATES DECIDE HEADS (2026-09-01)**:
  price_evidence="estimate" lanes (ollama-cloud glm-5.2 $0.05) can outrank
  sticker-backed lanes and take heads. The daily gap report must list
  estimate-priced lanes on head-eligible models as probe targets — a real
  probe either confirms the price or re-ranks the chain honestly.

- **BENCHMARK-ROW OVERFLOW CLASS (2026-09-03, glm-5.2 SWE-rebench)**: a
  benchmarks.jsonl row with `score == max_score` on an ABSOLUTE percentage
  (62.9/62.9) computes rel=1.0 and, via BENCH_OVERLAY (SWE-rebench→code_gen),
  silently inflated glm-5.2 code_gen/debug perf to tier 5 since entry. Guards:
  (a) percent scales MUST carry max_score=100 at entry; (b) the overlay is
  upward-only (measured beats estimate), so an APPENDED corrected row cannot
  repair an inflated one — fix the offending row IN PLACE (stale-estimate
  pitfall applies). Symptom: a mid-tier model at tier 5 on one category with
  no plausible source score behind it.
- **STICKER CORRECTION NEEDS A MANUAL RECOMPUTE (2026-09-03,
  grok-4.20-multi-agent-0309)**: router_pricing.py never overwrites existing
  evidence rows, so fixing a lane's public sticker in models.jsonl
  (1.25/2.5 → 2.0/6.0 after research) leaves the OLD normalized_price in
  place. After any sticker correction on an existing lane, recompute
  normalized manually (kimi manual-formula precedent) and say so in
  price_evidence — flat-sub: (0.96×in + 0.04×out) ÷ multiplier = 2.16/3.0 =
  0.72. Verify the value in registry.json after seed.

- **INERT-BENCHMARK + INFLATED-DENOMINATOR CLASS (2026-09-04, GPQA)**: 10
  GPQA Diamond rows sat inert in benchmarks.jsonl — measured reasoning
  evidence never reached model_perf (same evidence-trap class as deepseek
  review-0.60: evidence present, mechanism missing). Fix: `BENCH_OVERLAY['GPQA']
  = ['reasoning']` in router_seed.py. Two related repairs: (a) legacy GPQA rows
  used `max_score=94.9` (best-known-score denominator) instead of the true
  absolute scale 100 → rel=1.0 tier-5 overflow (benchmark-row overflow class);
  (b) `openai-codex/gpt-5.6-sol` data-row `perf_reasoning=1.0` (hand-planted
  estimate) BLOCKED the measured 0.949 because apply_overlay only upgrades
  upward — the MIRROR IMAGE of the stale-estimate pitfall: a correction to an
  INFLATED estimate must land in data/tables/models.jsonl itself.
  CHECKLIST after every bench append: does the source pattern exist in
  BENCH_OVERLAY? is max_score the TRUE absolute scale? does a data-row
  estimate exceed the measured value?
- **PROVENANCE-BROKEN COPY-PASTE CLASS (2026-09-06, grok-4.6 GPQA-D)**: a
  seed-era benchmarks.jsonl row carried a score BYTE-IDENTICAL to another
  family's measured value (grok-4.6 GPQA-D 94.9/100 == gpt-5.6-sol's) with no
  grok-specific source. Rule: identical cross-family scores with no per-model
  source = provenance-broken — DELETE the row, never keep or re-estimate it;
  re-seed and REPORT the boundary direction (removing an inflated row LOWERS
  min_perf boundaries: reasoning -2 moved 0.65→0.52, +1 0.85→0.8175 — more
  models clear the bar, so re-diff heads). Found via the seed sanity read:
  derived perf values that no appended row explains deserve a provenance grep
  before commit.

- **CRON STATUS LIES — DESTINATION COVERAGE IS THE ONLY TRUTH (2026-09-07,
  PROBE-DRIFT-001)**: the hourly health-probe cron reported `status: ok` for
  SIX DAYS while writing its output to a CWD-relative path — the 09-01
  argparse refactor gave `--output` the relative default `state/health-state.json`,
  which rebinds the module globals and repoints the health.jsonl append
  target too. Canonical `~/.hermes/model-router/health.jsonl` froze at 08-31;
  router_probefix scanned the same stale failures every morning. Rules:
  (a) every pipeline run must STAT the destination file's mtime/size, not
  trust the cron's exit status — same law as CHATGAP-001;
  (b) argparse defaults for paths must be ABSOLUTE (`os.path.join(MR, ...)`);
  (c) `main()` must not rebind module path globals when the passed value
  equals the canonical default (relocation is only for EXPLICIT custom
  targets);
  (d) after fixing the mechanism, BACKFILL the store from the drift file's
  last complete snapshot so consumers resume on real data the same hour.
  Sibling rule: a refactor that touches a script's output wiring must
  diff where the file ACTUALLY lands the next run.

- **PROBE 5xx "EMPTY RESPONSE" ON REASONING LANES = PING-BUDGET ARTIFACT
  (2026-09-07, clinepass)**: a 16-token chat ping burns its completion budget
  on hidden reasoning → HTTP 500 "empty response content" → lane marked DOWN
  → STUCK loop in probe_gaps (six lanes sat there 09-05→09-07 with CORRECT
  ids). Rule: before treating persistent 500-empty as a lane failure, re-probe
  with a generous completion budget (300 tokens flips them to HTTP 200);
  `PROBE_PARAMS[provider]` carries the per-provider budget. A probe result is
  only evidence of the lane when the probe's own request shape can't cause
  the failure.

- **FREE-LANE 400 ≠ PING-BUDGET — REVOKE THE DISCOUNT (2026-09-08,
  clinepass ling-3.0-flash-sante:free)**: the 09-07 ping-budget fix applies to
  500 "empty response"; a persistent **400** across a FULL probe day (11+
  probes) is a hard reject = dead lane. A dead :free lane still shows
  normalized_price 0.0 and passes every price check, so nothing flags it —
  revoke: discount `valid_to` + lane `disabled`/`disabled_reason` + price back
  to NULL. Never leave a $0 row alive on a dead lane.
  **⚠️ SUPERSEDED IN PART (2026-09-09): this revocation rule was itself an
  ID-FORM ARTIFACT for sante:free — see the next pitfall. The revoke action is
  still correct WHEN the probe used the /models-listed vendor-org id; it is
  premise-false when the probe hit the bare or cline-pass/:free form.**
- **CLINEPASS CHAT-ID FORMS — TWO FORMS, ONE PER LANE CLASS (2026-09-09,
  chat probes 18/18 GET /models :free ids = HTTP 200)**: paid/in-plan lanes
  answer ONLY at `cline-pass/<bare>` (vendor-org form = 403 product-surface).
  FREE `:free` lanes answer ONLY at `<vendor-org>/<model>:free` exactly as
  GET /models lists them — bare = 400 "invalid model format", `cline-pass/:free`
  = 404 "model not found". Consequences: (a) the 09-05 `cline-pass/<bare>`
  doctrine applies to PAID lanes only; (b) a :free-lane death verdict MUST
  chat-probe the /models-listed vendor-org id BEFORE revoking — the 09-08
  sante:free revocation (bare-form 400s) and the 08-28 "catalog scrape
  artifact" family disable were the SAME artifact; sante:free + 16 sibling
  lanes were alive all along (restored 09-09); (c) genuinely removed upstream
  09-09: glm-5.2:free, minimax-m2.7:free, minimax-m3:free (absent from GET
  /models + 404 at every form). Fix mechanism: probe_fixes rows
  bare → vendor-org id (18 added 09-09) so the hourly probe retries at the
  callable id; `provider_rules.jsonl` clinepass/chat-id-forms carries the
  contract (DATA > CODE).
- **AUTO PROBE_GAP ROWS CAN BE PREMISE-FALSE — CHECK provider_rules FIRST
  (2026-09-08, opencode-go)**: router_probefix auto-rows said "HTTP 400 …
  likely transient/auth" for all 10 opencode-go lanes while the 09-07
  session-header contract row already explained every 400 (probe deliberately
  omits `x-opencode-session` to report fleet usability, not raw endpoint
  health). Rule: resolve each auto row against provider_rules contracts before
  treating it as open work; an explanation row beats a re-diagnosis.

- Sub-plan providers on models.dev look like junk ids (`zai-coding-plan`) —
  they are the FLAT-RATE LANES the registry wants; don't filter them out.
- models.dev model names ≠ registry names (zai: `glm-5.3` vs registry
  `glm-5.3-flash`; family prefix matching required, exact-id matching wrong).
- `deepseek-v4-flash-vision-exp` exists on models.dev — the registry must not
  carry it as the plain `deepseek-v4-flash` (TR-005 reprice note: "no
  vision-exp/-0813 shadowing" — match on exact OR id).
- **VARIANT FAMILY-FILL GUARD (2026-08-30)**: fill perf_* from family values
  ONLY when the target lane's MODEL NAME already exists in the quantile pool
  (same-name fills like crof/glm-5.3 ← zai glm-5.3 are safe: model_perf dedups
  by max per (model, category)). Serving variants (neuralwatt glm-5.2-fast,
  kimi-k3-flex, vision-exp…) are NEW unique model names — filling them
  duplicates weights into cat_q, moves the tier scale, and breaks golden heads
  + hardcoded adhoc bars. Variant lanes stay BLANK (-1) until independently
  evidenced; the gaps report tracks them.
- **STALE-FLAT REPRICE NEEDS AN INCLUDED LIST (2026-08-30)**: the stale-flat
  reprice only applies to plans WITH included_models. Usage-bucket flat plans
  (ollama-cloud: no per-model list, flat fee buys a bucket) keep their
  researched estimate prices — never re-tag them 'outside flat-plan included
  list'. Pricing engine enforces this; bucket-plan gap message is honest.
- The inline-python guard: write probes as `/tmp/*.py` files, never
  `python3 -c` with JSON-ish content.
- registry sanity invariant: `active_models × categories == model_perf rows`.

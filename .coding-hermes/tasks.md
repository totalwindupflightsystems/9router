
## Dogfood Findings (2026-09-01)
Verdict: PROMISING-BUT-ROUGH
Promise: {"entry_point":"HTTP server: Next.js 16 standalone app booted through custom-server.js (federation-aware wrapper) — serves the OpenAI-compatible /v1 API (chat/completions, /v1/messages, /v1/models) plus the management dashboard at /dashboard on port 20128 (PORT env overrides); a CLI launcher package

- [P0] Silent DATA_DIR fallback touches the real instance DB — Doc-faithful `cp .env.example .env` points DATA_DIR at /var/lib/9router, which is unwritable → app silently falls back to ~/.9router with no warning; first dev boot opened an existing install's DB (shm/wal touched, data.sqlite mtime unchanged) — isolation is undocumented and any real user with an existing install risks cross-instance data bleed.
- [P0] Federation compose crash-loops on doc-faithful .env — `docker compose -f docker-compose.federation.yml up` with the documented `cp .env.example .env` steps FATALs on placeholder secrets, crash-looping all 3 containers; remedy exists only in a compose-file comment + FEDERATION.md §6.1, while the README compose section is silent — the fork's headline deployment path fails for everyone following the docs.
- [P1] npm run cli:pack fails out of the box (MODULE_NOT_FOUND: esbuild) — cli/ deps are never installed and no doc says to run `npm install` inside cli/ (cli/README only covers global npm install); a documented command in the promise's run_commands list dies immediately.
- [P1] Standalone docker compose aborts on hardcoded headroom 8787 — `docker compose up -d` cannot start: headroom container can't bind 0.0.0.0:8787 (occupied on this host); port is hardcoded with no documented override or exclusion, leaving the stack Created — host-specific but unfixable without reading source.
- [P1] FEDERATION_MODE ignores REQUIRE_API_KEY=false (bare 401) — Federation containers return unauthenticated 401 on /v1/models despite REQUIRE_API_KEY=false because roleGuard precedes the API-key check — the only 401 emitter in the /v1 path; bare error, no hint, not covered in README quick-start, so a user following config docs appears locked out.

## Dogfood Findings (2026-09-04)
Verdict: PROMISING-BUT-ROUGH
Promise: {"entry_point":"HTTP server: a Next.js 16 app (plain JS ESM) booted through custom-server.js, exposing an OpenAI-compatible /v1 API (chat/completions, messages, models, responses, audio, embeddings, images) plus an Anthropic-compatible POST /v1/messages and a web dashboard at /dashboard (port 20128,

- [P1] Documented regression gate fails: 12 pass->fail regressions — verify-no-regression.mjs (the project's own judge for 'not all green by design') reports 12 pass->fail regressions (rtk.test.js x8, antigravity-mitm, kiro-model-slots) — the gate is NOT clean, so the 
- [P1] DATA_DIR silently falls back to ~/.9router and touches real instance state — cp .env.example .env yields DATA_DIR=/var/lib/9router, which a non-root user cannot create; the app silently falls back to ~/.9router with no warning, so a new user can unknowingly mutate a pre-existi
- [P1] Production server killed silently mid-run (exit 137, no crash log) — npm run start was SIGKILLed with only 'Killed' in output and no crash log; a real user's long-running gateway can die mid-coding with no diagnostic trail, and the README offers no recovery guidance.
- [P2] Port-collision footguns: silent wrong-server hits and hardcoded 8787 — Port 20128 was already occupied by a pre-existing instance, so the README's default command silently hit the wrong server; docker compose up -d aborts because the headroom image hardcodes 0.0.0.0:8787
- [P2] CLI packaging docs gap and confusing launcher lifecycle — npm run cli:pack succeeds but the README never says how to run the CLI; cli/dist/cli.js does not exist (actual entry is cli/cli.js), and the launcher parent gets SIGKILLed under a timeout wrapper whil

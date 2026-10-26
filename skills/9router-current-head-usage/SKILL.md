---
name: 9router-current-head-usage
description: Use when operating 9Router from source at current HEAD; verify the server identity, auth mode, model catalog, and provider setup before sending a completion.
---

# 9Router current-HEAD usage

## Start an isolated source instance

Use a separate HOME and DATA_DIR for a disposable run:

```bash
HOME=/tmp/9router-home DATA_DIR=/tmp/9router-data PORT=20226 npm run dev
```

Check `/api/health` first, then `/api/version`. A green health response proves only that the process is alive.

## First-user flow

1. POST `/api/auth/login` with the configured initial password and save the session cookie.
2. POST `/api/keys` using that cookie to create a client API key.
3. Query `/v1/models` with `Authorization: Bearer <client-key>`.
4. Select a model actually returned by the current instance; do not assume a catalog id is callable.
5. Send `/v1/chat/completions` with `stream:false` first, then test streaming separately.
6. If no provider connection exists, stop at discovery and report that completion is unproven; do not mint provider credentials during dogfood.

## Auth and state gotchas

`/api/auth/login` and `/api/keys` use dashboard session state, while `/v1/*` may require a separately minted client API key depending on `REQUIRE_API_KEY`. Test both the no-key and invalid-key arms before interpreting a successful `/v1/models` response. Isolate HOME and DATA_DIR before the first login so keys and settings cannot land in the operator's real installation.

`/v1/models/<kind>` can legitimately be empty on a fresh instance. Treat an empty embedding catalog as an unconfigured-provider state, not as a successful embedding workflow.

## Fresh-machine evidence

The fleet `bunker-qa.sh` battery has a generic `fresh-install` detector that looks for a `toolsd` artifact. That detector is not a 9Router executable check. Grade the Node/Next install from the target's own `npm install`/`npm run dev`, `/api/health`, `/api/version`, and `/v1/models` smoke evidence; preserve a battery detector FAIL as harness evidence unless it actually ran the 9Router commands.

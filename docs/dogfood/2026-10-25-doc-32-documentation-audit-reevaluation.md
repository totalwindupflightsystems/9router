# DOC-32 documentation audit re-evaluation — 2026-10-25

Scope: re-evaluate only the two findings from the prior static audit after their
completion rows landed. This is a source-to-documentation check; it does not
start a server or claim a live HTTP probe.

Target at recheck: `/home/kara/worktrees/9router-DOC-32`, branch `wt/DOC-32`,
pre-commit HEAD `1c1e48014a6541e7b536b009c9360effa7a438b2`.

Prior artifact: `/home/kara/.hermes/stand-in/docs/9router/2026-10-24-13-39-29-audit.md`.
That artifact found (1) no `docs/traceability-doctrine.md` and (2) no documented
`GET /api/federation/config-status` route in the two integration references.
This artifact is newer in content because it re-runs those two findings against
the current checkout, including the DOC-30 and DOC-31 landed changes.

## Prerequisite recheck

Command:

```sh
test -f docs/traceability-doctrine.md && grep -n 'config-status' docs/FEDERATION.md docs/api-reference.md
```

Output (exit 0):

```text
docs/FEDERATION.md:25:| **central** | `central` | Single authoritative writer. Serves its own dashboard, `/v1` pipeline and the federation API (`/api/federation/{config-status,local-status,delta,replay,snapshot,status,verify}`). Every write to a replicated table stamps a monotonically increasing `federation_version`. |
docs/FEDERATION.md:168:The federation API has these seven registered handlers. `GET /api/federation/config-status`
docs/FEDERATION.md:172:server). Its CORS preflight, `OPTIONS /api/federation/config-status`, returns
docs/FEDERATION.md:177:| `GET /api/federation/config-status` | Local federation configuration metadata for the dashboard config page | Token-less, read-only; `OPTIONS` returns `204` |
docs/api-reference.md:488:/api/federation/config-status` is a **token-less, read-only** endpoint for an
docs/api-reference.md:492:/api/federation/config-status` returns `204 No Content` for CORS preflight.
docs/api-reference.md:496:| `GET /api/federation/config-status` | Local federation configuration metadata | Token-less, read-only; `OPTIONS` returns `204` |
```

## DOC-30 — resolved

The prior finding was the absence of `docs/traceability-doctrine.md`. The current
tracked document exists, is linked from the root README, and contains the three
terms required by the row acceptance: marker, evidence, and close-out.

Command:

```sh
test -f docs/traceability-doctrine.md
printf 'traceability_file_exit=%s\n' "$?"
git grep -n 'traceability-doctrine.md' -- README.md docs
printf 'entrypoint_link_exit=%s\n' "$?"
grep -qi 'marker' docs/traceability-doctrine.md && grep -qi 'evidence' docs/traceability-doctrine.md && grep -qi 'close-out' docs/traceability-doctrine.md
printf 'doctrine_terms_exit=%s\n' "$?"
```

Output:

```text
traceability_file_exit=0
README.md:2032:For work-item markers, evidence, and close-out expectations, see the [repository traceability doctrine](docs/traceability-doctrine.md).
entrypoint_link_exit=0
doctrine_terms_exit=0
```

Current source evidence: `docs/traceability-doctrine.md:10-16` defines the
single-line `ch:trace` marker and its fields; `:41-51` defines evidence; `:69-85`
defines close-out. The landed implementation commit is
`0d3e073657bb61223237464bca30bec50c42bd61` (`docs: define repository traceability doctrine. Addresses DOC-30.`).

Decision: resolved. This verifies the repository-documentation contract only; it
does not verify a future review verdict or publication state.

## DOC-31 — resolved

The prior finding was missing `config-status` coverage in `docs/FEDERATION.md`
and `docs/api-reference.md`. Current source declares the route module at
`src/app/api/federation/config-status/route.js`: `GET` is at line 17 and returns
the `handleConfigStatus` payload; `OPTIONS` is at lines 30-31 and returns 204.
The route comments at lines 10-16 describe a token-less, read-only local config
surface whose token value never leaves the server. `src/lib/federation/server.js:268-274`
implements the matching `handleConfigStatus` entry point.

Focused source-to-doc route inventory command:

```sh
for route in config-status local-status delta replay snapshot status verify; do
  source_path="src/app/api/federation/$route/route.js"
  test -f "$source_path"
  source_exit=$?
  federation_hits=$(grep -c "$route" docs/FEDERATION.md || true)
  api_hits=$(grep -c "$route" docs/api-reference.md || true)
  printf 'route=%s source_exit=%s federation_hits=%s api_reference_hits=%s\n' "$route" "$source_exit" "$federation_hits" "$api_hits"
  test "$source_exit" -eq 0 && test "$federation_hits" -gt 0 && test "$api_hits" -gt 0
done
printf 'route_inventory_exit=%s\n' "$?"
```

Output:

```text
route=config-status source_exit=0 federation_hits=4 api_reference_hits=3
route=local-status source_exit=0 federation_hits=12 api_reference_hits=1
route=delta source_exit=0 federation_hits=9 api_reference_hits=3
route=replay source_exit=0 federation_hits=10 api_reference_hits=1
route=snapshot source_exit=0 federation_hits=7 api_reference_hits=1
route=status source_exit=0 federation_hits=26 api_reference_hits=9
route=verify source_exit=0 federation_hits=11 api_reference_hits=1
route_inventory_exit=0
```

The complete source route listing used for the count was:

```text
src/app/api/federation/config-status/route.js
src/app/api/federation/delta/route.js
src/app/api/federation/local-status/route.js
src/app/api/federation/replay/route.js
src/app/api/federation/snapshot/route.js
src/app/api/federation/status/route.js
src/app/api/federation/verify/route.js
source_route_count=7
```

The prerequisite output above independently shows that both current references
name `GET /api/federation/config-status` and state token-less/read-only plus
`OPTIONS` 204 behavior. The landed documentation commit is
`b0dec0724b8611f7a2abb35f0eb97e7c1cc156f9` (`docs: document federation config status route. Addresses DOC-31.`).

Decision: resolved. The route inventory proves that all seven current route
names occur in both references; it does not prove every route's request/response
body or authorization behavior beyond the explicitly rechecked config-status
statements.

## Validation and limits

No repository Markdown linter or dedicated documentation-validation script is
declared in `package.json`; the focused validation for this audit is the
source-to-doc inventory above plus the prerequisite command. No full application
test suite was run because this artifact changes documentation only and does not
alter route behavior.

The check did not re-run the prior audit's unrelated `/api/cloud` investigation,
full environment-key parity, Markdown link reachability, or a live deployment.
Those areas remain outside this two-finding re-evaluation.

ch:trace row=DOC-32 spec=none:repo-doctrine-missing wave=9router-foreman-2026-10-25-17-50-48.json#DOC-32 test=none:documentation-audit doc=docs/dogfood/2026-10-25-doc-32-documentation-audit-reevaluation.md prompt=/tmp/9router-foreman-2026-10-25-17-50-48-DOC-32.md evidence=docs/dogfood/2026-10-25-doc-32-documentation-audit-reevaluation.md witness=none:source-to-doc-recheck verdict=none:pending-foreman-judge commit=none:commit-pending memory=none:not-written

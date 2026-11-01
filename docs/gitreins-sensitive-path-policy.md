# GitReins tracked-template policy

## Scope and decision

`.env.example` is a tracked, copyable template rather than operator state. It may
contain only documented placeholder values. A real credential belongs in the
ignored local `.env` file or the deployment secret store, never in this template.

Decision: option (a) was chosen. The exact scoped
`guards.sensitive_paths.allow` entry for `.env.example` is the selected policy
because `.env.example` is a tracked placeholder-only shipping template. Broad
scanner weakening is not acceptable.

GitReins 0.17.1 treats `.env.*` as a credential-store path class before inspecting
content. 9Router therefore uses its supported, narrowly scoped configuration:

```yaml
guards:
  sensitive_paths:
    allow:
      - ".env.example"
```

The exception suppresses only the sensitive-path classification for that exact
path. It does not bypass gitleaks or GitReins' content scanner, and it does not
match `.env`, nested templates, `credentials.json`, key files, or any other
sensitive-path class.

## Operator workflow

1. Keep every `.env.example` value a non-secret placeholder and explain the
   setting in the surrounding comment or its operator documentation.
2. Run `node scripts/verify-gitreins-sensitive-path-policy.mjs`. The disposable
   probe initializes two temporary repositories and invokes the installed
   GitReins guard with `--staged-only --json`. It requires both an auditable
   `sensitive-path override applied: .env.example` witness for the allowed
   template and a `SENSITIVE PATH (credential-store path class)` rejection for
   an unrelated `.env`.
3. Stage the real change and run `gitreins guard`. The pre-commit hook invokes
   that same supported command. Its secrets result must retain the override
   witness; inspect the emitted guard log or evidence JSON when a concise PASS
   summary does not print it.
4. If a value is credential-shaped, remove it instead of expanding this list.
   A new exception needs an explicit security review and a new positive and
   negative gate proof.

## Durable evidence and test boundary

The already-run `node scripts/verify-gitreins-sensitive-path-policy.mjs` probe
passed both `PASS: .env.example accepted with auditable sensitive-path override`
and `PASS: unrelated .env remains blocked by sensitive-path gate`.

A staged `gitreins guard --staged-only --json` run on the real `.env.example`
reported a secrets pass and `sensitive-path override applied: .env.example`.
The staged file was restored afterward. This is the exact positive policy
result; the negative unrelated `.env` result is the disposable probe's explicit
sensitive-path-gate rejection above.

`tests/node_modules` exists. The full repository regression gate is not green,
however, because the existing `INT-9ROUTER-003` regression remains in
`tests/federation/qa-harness-cell-detection.test.js`. That test renders the
external `~/.hermes/scripts/bunker-qa.sh`; this row does not modify that external
script. Do not represent this document's verification as a full-suite-green
result.

Post-commit `gitreins guard --json` is a DEGRADED PASS with tests skipped when
no files are staged. It is not full test evidence.

## Precedent: 53ab4a2e

`53ab4a2e` is not an ancestor of `federation`; it remains only on
`origin/wt/DOC-22-R2`. Its `.env.example` change was repeated in successor
`01dfcbe9`, the commit that reached `federation`. Live GitReins source records
the sensitive-path class
and `guards.sensitive_paths.allow` support as introduced on 2026-10-07, before
that 2026-10-25 worker commit. The historical commit has no retained guard log
or recorded override invocation, so its claim of a full guard pass is not
reproducible evidence for the current policy. Current GitReins 0.17.1 rejects a
staged `.env.example` without this scoped allow entry; this documented exception
and its disposable proof replace reliance on the historical claim.

## Traceability

ch:trace row=HYG-9ROUTER-20 spec=none:tooling-policy wave=none:serial test=node scripts/verify-gitreins-sensitive-path-policy.mjs doc=docs/gitreins-sensitive-path-policy.md evidence=scripts/verify-gitreins-sensitive-path-policy.mjs witness="gitreins guard: PASS; gitleaks: clean; sensitive-path override applied: .env.example" verdict=none:foreman-judges commit=none:worker-sha-written-after-commit memory=none:foreman-writes

ch:trace row=HYG-9ROUTER-20-R2 spec=none:tooling-policy wave=none:serial test=node scripts/verify-gitreins-sensitive-path-policy.mjs doc=docs/gitreins-sensitive-path-policy.md evidence=docs/gitreins-sensitive-path-policy.md witness=verdict:b042810f+live-probe verdict=none:foreman-judges commit=none:worker-sha-written-after-commit memory=none:foreman-writes

STATUS: complete

TIER: state T3; observed `node scripts/verify-gitreins-sensitive-path-policy.mjs` (positive and negative disposable fixtures) and staged `gitreins guard --staged-only --json` evidence for the real `.env.example`. The post-commit unstaged guard is DEGRADED PASS only; the repository regression gate remains blocked by INT-9ROUTER-003.

EVIDENCE: `.gitreins/config.yaml`, `scripts/verify-gitreins-sensitive-path-policy.mjs`, the staged guard evidence's secrets pass / `sensitive-path override applied: .env.example` witness, the probe's explicit unrelated `.env` block, and the committed `.env.example` placeholder-only notice.

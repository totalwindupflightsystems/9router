# PRD (deep): `h3-forge` — Lane-Health & Credential-Custody Boundary

**Project:** get-h3 · agent-ops line · **Item:** B7 · **Author:** Kara-agent · **Date:** 2026-09-17
**Status:** proposed (v2 — security-boundary rewrite) · **Effort:** M (~2 weeks) · **Depends on:** nothing · **Feeds:** digest (lane health), sentinel (rotation-overdue pins)

---

## The concern, taken seriously

> *"That is going to require a lot of rebuilding tools like 1Password. I assume there are open-source ones but of course managing people's creds is critical and also an attack vector."*

Both halves are correct, and together they force the design: **forge must not become a credential store.** Building custody means owning encryption-at-rest, key derivation, recovery, sharing, rotation semantics, audits, and — the part people underestimate — *a new crown jewel to defend*. A half-built secrets manager is worse than 0600 env files, because it concentrates everything and adds a false sense of safety.

So v2 draws a hard line and names both sides of it.

---

## 1. What forge is NOT (the boundary)

| forge does | forge never does |
|---|---|
| store **references**: env-var names, file paths, manager item IDs, provider/lane metadata | store, copy, cache, or transmit credential **material** |
| **probe** lanes and record health receipts | read a key's value into its own process |
| **orchestrate** rotation across registered consumers | generate, derive, or escrow keys |
| track key **age/quota/plan** metadata (declared + measured) | claim custody, backup, or recovery of secrets |
| prove a lane is healthy/unhealthy with evidence | decide a secret is "safe" without a receipt |

**Architectural consequence:** compromising forge yields *no credentials* — only the map of which lanes exist and how healthy they are. That is a materially smaller prize than today's state, where a single readable `.env` (93 keys in one file on this box) is the whole kingdom.

## 2. What exists today (measured, this box, 2026-09-17)

| Layer | Reality |
|---|---|
| secret stores installed | **none** of `op`, `bw`, `sops`, `age`, `vault`, `pass`, `keepassxc-cli`; `gpg` present |
| OS keystore | GNOME Keyring running (`login.keyring`, `user.keystore`) |
| Hermes vault pattern | `~/.hermes/vault/` exists (tokens, wg keys); `browser_vault_*` tool family already implements the **reference-and-fill** pattern incl. 1Password/Bitwarden detection; `agent/credential_pool.py` handles OAuth pools |
| fleet reality | `~/.hermes/.env` = **93 keys**, 0600; `9router/.env` = 0600; services consume via env / systemd `EnvironmentFile` |

**Design implication:** the fleet already has the *reference* pattern (Hermes vault tools) and the *consumption* pattern (env files). What it lacks is the **management plane** — knowing which lane is healthy, which key is old, which consumers depend on it. That plane needs no plaintext, which is exactly why forge is buildable without becoming 1Password.

## 3. Trust tiers — forge works at every tier, and upgrades transparently

| Tier | Storage | forge sees | When appropriate |
|---|---|---|---|
| **T0 (today)** | 0600 `.env` files, systemd `EnvironmentFile`, `~/.hermes/vault/` files | paths + var names only | current fleet; single-operator; already the status quo |
| **T1** | OS keystore (GNOME Keyring) or a self-hosted manager — **Bitwarden** (self-host, open source), **1Password** (CLI), **HashiCorp Vault**, **SOPS+age** | item references (`op://…`, `bw://…`, sops-encrypted file paths) | when ≥2 humans share custody, or compliance demands access logs |
| **T2** | hardware/KMS-backed (YubiKey + age, cloud KMS, systemd-creds w/ TPM) | key handles only | when a real adversary model exists |

**Adoption rule:** forge's registry is the same at every tier — only the *reference type* changes. Moving from T0→T1 is a per-lane edit + a re-probe, not a forge rewrite. **We do not build T1/T2 ourselves**; we adopt existing open-source custody when the sharing/compliance need actually appears.

## 4. Threat model (who attacks what, and what they get)

| Compromise | Attacker gains | Blast radius |
|---|---|---|
| **forge's registry/DB** | lane names, provider + plan metadata, env-var *names*, health receipts | **no credential material**; reveals which lanes exist (low value given rate limits + provider-side revocation) |
| **forge's probe output/logs** | model names, latencies, status codes | none — redaction pass + no-plaintext rule enforced at write time (the argv-leak doctrine, GAP-038) |
| **a 0600 `.env` (today's reality)** | **all 93 keys** | **full fleet compromise** — this is the actual attack vector, and the one that motivates everything else |
| **a T1 manager** | whatever the item's policy exposes; audited | bounded by per-item access policy + audit trail (the reason T1 exists) |
| **a rotated-out key** | nothing | inert by doctrine — **rotation > purge**; no history rewriting, ever |

**Honest conclusion:** forge does not *reduce* the attack surface of messy `.env` files by itself — it makes the *inventory* visible so the human can decide when T1 custody is warranted. Its security win is (a) never holding secrets, (b) making rotation cheap enough that "rotate, don't purge" is practical, and (c) producing the audit trail that shows when a lane's key changed and every consumer that was rewired.

## 5. Rotation choreography (the operation nobody does because it's scary)

Forge makes rotation a **transaction**, and the plaintext never enters forge:

```
1. ISSUE      operator issues a new key at the provider (human + MFA — forge never holds account creds)
2. REGISTER   forge records the new reference (var name / manager item) — a NAME, not a value
3. INJECT     the value moves manager→target via the manager's own tooling:
              op run / bw get --raw / sops exec-env / systemd-creds — injected by the tool, never printed
4. PROBE      forge runs the lane probe with the NEW key  → must pass
5. FLIP       forge marks the lane's active reference = new; old key enters overlap window
6. REWIRE     each registered consumer is updated (env file line, unit EnvironmentFile, container env)
              and the consumer's own health check must pass before the lane is considered migrated
7. VERIFY     forge re-probes end-to-end through the consumers (not just direct) — a receipt per consumer
8. RETIRE     after the overlap window the old key is revoked at the provider; forge records the retirement
ABORT anywhere → the old reference stays active; the transaction is recorded as failed with the exact step
```

**Overlap window is the point:** both keys valid during migration means rotation never causes downtime — the difference between "we should rotate" and "we actually rotate quarterly".

## 6. What forge still needs from humans (not automated, and shouldn't be)

- issuing/revoking keys at providers (account + MFA);
- approving a rotation transaction (default: propose, human confirms — the fleet's proposal-not-write doctrine);
- choosing custody tier per lane when sharing/compliance appears;
- account recovery. Forge never becomes the thing you can't get back into.

## 7. Requirements & anti-patterns

**Requirements:** no plaintext in argv, logs, DB, or crash dumps (write-time redaction + test); probes are declared, budgeted, and tiny; registry is append-only JSONL (auditable); per-lane access policy for who may trigger rotation; kill-switch (remove forge → lanes keep working; nothing depends on it at runtime).

**Anti-patterns (rejected explicitly):** storing values "just for convenience"; becoming the backup/recovery authority; auto-rotating without operator confirmation; inventing our own crypto; a single registry file that concentrates every lane's metadata *and* a value cache — never.

## 8. Success criteria

1. **Invalid-key replay:** a lane whose key is revoked at the provider flips to `degraded` within one probe cycle — before any consumer 401s (inject a dead key on a test lane).
2. **Rotation drill, zero plaintext:** a full 8-step rotation completes across 3 registered consumers with **no key value appearing in forge output, logs, or the registry** — verified by grep of every artifact + a secrets scan.
3. **Abort path:** a rotation with a failing probe aborts cleanly, old reference stays active, and no consumer is left half-migrated (verified test).
4. **Misroute detection:** `forge reconcile --provider X --window 7d` flags ledger rows for models the provider never served (the hand-found quorum signature, mechanized).
5. **Tier portability:** one lane migrated T0→T1 (env var → manager reference) with **no registry schema change** and a passing re-probe.
6. **Blast-radius visibility:** `forge audit` reports every lane, its custody tier, key age, and consumer count — the inventory that today lives in one person's head.

## 9. Recommendation (the decision this PRD actually asks for)

**Build forge as the management plane only (refs + health + rotation orchestration), at T0 today.** Do **not** build custody. When custody needs appear — and the real trigger is **sharing credentials between people**, not technology — adopt a self-hosted open-source manager (Bitwarden self-host is the natural first candidate: open source, self-hostable, CLI + API, audit log) and point forge's references at it. If a *personal* 1Password/Keychain need appears for Bane's own accounts, that's the existing Hermes vault pattern (`browser_vault_*`), already shipped, and **orthogonal** to this tool.

**Net security effect:** fewer secrets in agent-readable files over time (rotation becomes routine), one visible inventory instead of a hand-managed `.env`, and no new crown jewel for an attacker to target — because forge has nothing worth stealing.

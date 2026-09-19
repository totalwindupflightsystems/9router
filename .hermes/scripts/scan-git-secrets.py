#!/usr/bin/env python3
"""
Git Secret Scanner — scan local repos for leaked secrets in recent commits.

v2 rewrite — fixes two problems:
  1. TIMEOUT: Only scans repos with actual recent activity (git log --since pre-check).
     Skips 35+ idle repos instantly instead of 120s timeout each.
  2. FALSE POSITIVES: Moves detection into git itself via -G (pickaxe) for regex-level
     pre-filtering, then Python-side false-positive rejection with richer context.

Runs as a cron script. Output goes to stdout for LLM analysis.
"""

import subprocess
import re
import os
import sys
import argparse
from datetime import datetime, timezone, timedelta

# ── Secret patterns ────────────────────────────────────────────────────────
# (pattern, type, severity_hint)
SECRET_PATTERNS = [
    (re.compile(r'-----BEGIN [A-Z ]*PRIVATE KEY-----'), 'private_key', 'CRITICAL'),
    (re.compile(r'(?i)(?:api[_-]?key|apikey|secret|token|password|passwd)\s*[=:]\s*["\']([A-Za-z0-9_\-!@#$%^&*+/=]{12,})["\']'), 'credential', 'CRITICAL'),
    (re.compile(r'gh[pousr]_[A-Za-z0-9_]{20,}'), 'github_token', 'CRITICAL'),
    (re.compile(r'sk-[A-Za-z0-9]{20,}'), 'openai_key', 'CRITICAL'),
    # OpenRouter keys (sk-or-v1-...) — added scan #50 2026-09-02: the plain sk- rule
    # never matched them (hyphens break the alnum run), letting 3 REAL LIVE keys hide
    # through scans #49/#50 (caught only by the agent literal probe).
    (re.compile(r'sk-or-v1-[A-Za-z0-9-]{20,}'), 'openrouter_key', 'CRITICAL'),
    (re.compile(r'xox[baprs]-[A-Za-z0-9-]{10,}'), 'slack_token', 'CRITICAL'),
    (re.compile(r'AKIA[0-9A-Z]{16}'), 'aws_access_key', 'CRITICAL'),
    (re.compile(r'AIza[0-9A-Za-z\-_]{35}'), 'gcp_api_key', 'CRITICAL'),
    # Telegram bot tokens: 123456789:AAxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx (bot id + secret)
    (re.compile(r'\b\d{5,12}:AA[0-9A-Za-z_\-]{30,40}\b'), 'telegram_bot_token', 'CRITICAL'),
    # Hyphenated provider keys (added scan #97 2026-09-18): the plain sk- rule above
    # stops at the first hyphen, so `sk-xt-<47 hex>` (xKiro) and any `sk-<tag>-<hex>`
    # provider key was INVISIBLE. Two LIVE xKiro keys sat committed in
    # ~/duckbrain/namespaces/chat-archive (pushed to s3://duckbrain/...) and the
    # scanner reported a clean fire. Same failure mode as the sk-or-v1 gap (scan #50).
    # Negative lookahead keeps the known sk-or-v1 (dummy/FP corpus) family on its own rule.
    (re.compile(r'sk-xt-[0-9a-f]{20,}'), 'xkiro_key', 'CRITICAL'),
    (re.compile(r'sk-(?!or-v1-|xt-)[a-z][a-z0-9]{0,7}-[0-9a-f]{32,}\b'), 'hyphenated_provider_key', 'CRITICAL'),
]

# ── False positive indicators ───────────────────────────────────────────────
# If ANY of these match the matched line OR file path, it's a false positive.
# Per-repo `git log -p` timeout. The big DuckBrain namespace stores
# (~/duckbrain/namespaces/scheduler: 735 MB .git / 83,770 objects) need >30s, so they
# were reported as INFO timeouts and never actually scanned (scan #97/#98). The default
# stays 30s to keep the cron runtime bounded; set SCAN_REPO_TIMEOUT=180 (or run `git gc`
# on the repo) to cover those stores in a targeted run. Verified scan #98: with
# SCAN_REPO_TIMEOUT=180 the scheduler namespace scanned clean (13,872 added lines).
REPO_TIMEOUT_S = int(os.environ.get('SCAN_REPO_TIMEOUT', '30'))

FP_PATTERNS = [
    # Placeholder / example values
    re.compile(r'(?i)(?:\.example|\.sample|placeholder|your[-_.]|my[-_.]|insert[-_.]|replace[-_.]|demo[-_])'),
    re.compile(r'(?i)\b(?:YOUR_|MY_|TEST_|EXAMPLE_|DEMO_|REPLACE_ME|CHANGE_ME)\b'),
    re.compile(r'(?i)<(?:your|insert|replace|token|key|api[-_.]?key)>'),
    # Test fixtures (file path or content)
    re.compile(r'(?i)(?:/test[s]?/|/tests/|/__tests__/|_test\.|\.test\.|/spec/|/fixture|/mock)'),
    re.compile(r'(?i)(?:pytest|conftest|spec_fixture|test[-_]fixture)'),
    # Known test/demo/development strings
    re.compile(r'(?i)["\'](?:old|expired|invalid|valid|demo|test|dummy|fake|mock|example|dev|development)[._-]*(?:access|refresh|auth|api)?[._-]*(?:token|key|secret|password)["\']'),
    re.compile(r'(?i)["\']password\d*["\']'),
    re.compile(r'(?i)["\'](?:super|top|ultra)[._-]*secret["\']'),
    re.compile(r'(?i)(?:testpassword|securepassword|originalsecret|webhook[-_]secret)'),
    re.compile(r'(?i)["\'].*change[-_]in[-_]production.*["\']'),
    re.compile(r'(?i)["\']invalid[-_]key[-_]\d+["\']'),
    # Fake token patterns (sequential alphabet, obvious nonsense)
    re.compile(r'ghp_x1234567890abcdefghijklmnopqrstuvwxyz'),
    re.compile(r'(?i)mka_live_original\d+'),
    # OpenAI/Stripe test key prefixes
    re.compile(r'(?i)sk[-_](?:test|demo|example)[-_]'),
    re.compile(r'(?i)sk[-_](?:live|test|demo)[-_](?:abc|123|xxx|placeholder|your|demo|dummy|nope)'),
    # Documentation showing regex/key patterns (backtick-wrapped, indented code blocks)
    re.compile(r'`-{3,}BEGIN [A-Z ]*PRIVATE KEY-{3,}`'),
    re.compile(r'(?i)sk[-_](?:live|test|demo)[-_](?:abc|123|xxx|placeholder|your|demo|dummy)'),
    # Educational/hardening docs
    re.compile(r'(?i)(?:hardening|security[-_]best[-_]practices|anti[-_]pattern|secrets[-_]management)'),
    # Dotenv examples with URLs instead of keys
    re.compile(r'(?i)(?:DATABASE_URL|REDIS_URL|MONGO_URI)\s*=\s*(?:postgres|mysql|redis|mongodb)://'),
    # JWT/base64 placeholders
    re.compile(r'eyJ[A-Za-z0-9_-]{5,}\.(?:your|demo|test|example)'),
    # Session files / build logs / test output
    re.compile(r'(?i)(?:/\.hermes/sessions/|/__pycache__/|/node_modules/|/\.venv/|/dist/)'),
    re.compile(r'(?i)(?:/\.ralph/logs/|/build[-_]log|/test[-_]output)'),
    # Binary/autogenerated files
    re.compile(r'(?i)\.(?:pb\.go|generated\.|auto\.|lock\.json|sum)'),
    # Changelog/release notes documenting past secrets
    re.compile(r'(?i)(?:CHANGELOG|RELEASE[-_]NOTES|HISTORY\.md)'),
    # Generic descriptions like "the API key is..."
    re.compile(r'(?i)the (?:API|secret|token|password|key) (?:is|was|were)'),
    # Spec/test docs that explicitly contain fake examples
    re.compile(r'(?i)(?:specs/testing/|merged-specs/|docs/.*secret|curl[-_]examples)'),
    # GCP API key matches that are actually inside base64 data blobs (long strings > 500 chars)
    re.compile(r'(?i)["\']data["\']\s*:\s*["\'][A-Za-z0-9+/=]{200,}["\']'),
    # Docs that DISCUSS secret-scanning with example keys by design (FP corpus).
    # These files were scrubbed of real keys on 2026-08-22; what remains is
    # documented example material (AKIAIOSFODNN7EXAMPLE, xoxb-1234..., sk-abc...).
    re.compile(r'(?i)(?:known-false-positiv|secret-history-scrubbing|gitleaks-test-token-allowlist|tier2-self-testing|key-prefix-cheat-sheet|gitleaks-secrets-guard-and-lsp-skips|secrets-guard-gitleaks-blindspots)'),
    re.compile(r'(?i)/security/secret-scan/'),
    re.compile(r'(?i)/security-scan/'),
    # Placeholder values: long x-runs (ghp_xxxx…, sk-xxxx…), literal words as values
    re.compile(r'(?i)x{8,}'),
    re.compile(r'(?i)(?:extracted_value|generate-a-strong-secret-here|test-fake-key-not-a-real-secret|comfyui-xx|dexdat-bunker-token-2026)'),
    # Env-var reference as value (KEY="$OTHER_VAR") — the documented FP tell
    re.compile(r'(?i)(?:KEY|TOKEN|SECRET|PASSWORD)\s*=\s*"\$[A-Z0-9_]+"'),
    # Explicitly-fake values in prose/tests
    re.compile(r'(?i)(?:thisisafake|test-key-abc123|fake-refresh|fake-token)'),
    # PEM header as a C #define constant (marker text, not a real key)
    re.compile(r'(?i)#define\s+PEM_BEGIN'),
    # ── Documented-example shapes in skill docs / references (scan #82, 2026-09-16) ──
    # Scan #82 raised 34 CRITICALs, all of them documentation examples that the
    # skills tree deliberately carries (the scanner's own prose about the scanner).
    # Each rule below is narrow — it keys on an EXAMPLE marker (sequential digits,
    # all-caps identifier, env-var reference, alphabet run), so a real key with a
    # mixed-case random body still trips its SECRET_PATTERN.
    # Env-var REFERENCE as an assigned value: apiKey: "$OPENROUTER_API_KEY"
    # (extends the KEY="$OTHER_VAR" rule above to colon / JSON style).
    re.compile(r'(?i)[:=]\s*"\$[A-Z0-9_]{4,}"'),
    # Assigned value is an ALL-CAPS underscore IDENTIFIER, i.e. an env-var NAME:
    # ENV_API_KEY = "COMFY_CLOUD_API_KEY", envAdminPassword = "FORGEJO_ADMIN_PASSWORD"
    re.compile(r'[:=]\s*"[A-Z][A-Z0-9]*_[A-Z0-9_]{6,}"'),
    # HTTP header name used as a Go const: StrXAuthToken = "X-Auth-Token"
    re.compile(r'(?i)["\']X-Auth[a-z-]*["\']'),
    # Sequential / repeated-block placeholder keys: sk-1234567890abcdef…,
    # sk-A1A1A1A…, sk-abcdef0123456789abcdef, sk-a1b2c3…  (all-lowercase bodies
    # are the example tell — real keys carry a mixed-case random body)
    re.compile(r'(?i)sk-(?:or-v1-)?1234567890'),
    re.compile(r'sk-(?:A1){3,}'),
    re.compile(r'sk-(?:abc|a1b2c3)[a-z0-9]*\b'),
    # Alphabet-run GitHub PAT example: ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghij
    re.compile(r'ghp_ABCDEFGHI'),
    # LocalStack documented fixture access-key IDs (aws/accounts.py docstring example)
    re.compile(r'AKIA(?:RZPUZDIKGB2VALC4|IOSFODNN7EXAMPLE)'),
    # Sequential Slack placeholder used in docs: xoxb-1234567890123
    # Documented-example markers (scan #97): the fanout doc line pairs the Stripe docs key
    # `sk_live_4eC39…` with the sequential Slack placeholder `xoxb-123456789012-…`, and the
    # gitreins doc line carries the fixture literal `INITIAL_PASSWORD: "pw-abc-12345"`.
    # Keying on the marker (not on a broad `xoxb-<digits>` shape) keeps REAL Slack tokens
    # detectable — a real xoxb with digits after the prefix still trips slack_token.
    re.compile(r'sk_live_4eC39'),
    re.compile(r'"pw-abc-12345"'),
    # Mock/fake token values with a trailing descriptor: 'mock-access-token-heading'
    re.compile(r'(?i)["\'](?:mock|fake|dummy)[-_][a-z0-9_-]*(?:token|key|secret)'),
    # ── Quoted PEM BEGIN-header literals with NO key body (scan #90, 2026-09-16) ──
    # /home/kara/trouble specs/SPEC-02-scrubbing.md carries the scanner's own BEGIN
    # markers as quoted detection patterns ("-----BEGIN PRIVATE KEY-----" …) and the
    # project's Go test vectors embed the same headers in string literals — neither
    # has a base64 body, so neither is key material. Narrow by construction: the
    # header must be a COMPLETE quoted string (optionally ending in an escaped \n).
    # Real key material keeps flagging — a JSON/YAML one-liner is followed by the
    # base64 body on the same line, and the bare `+-----BEGIN RSA PRIVATE KEY-----`
    # diff line of a committed key file has no quote after the header.
    re.compile(r'"-----BEGIN [A-Z ]*(?:PRIVATE KEY|PRIVATE KEY BLOCK|KEY BLOCK)-----(?:\\(?:r\\n|n))?"'),
    # ── SPEC-02 scrub-spec family, carriers beyond the .md (scan #92, 2026-09-17) ──
    # Scan #90's rule above keys on a STRAIGHT-QUOTED complete header. Four carriers of
    # the same non-key material slipped past it: the generated review copy (HTML-escaped
    # &quot;), the vector table's <code>-wrapped header, the TSV test vector itself, and
    # the Go byte-set alphabet constant. Each rule is narrow: a real PEM must carry a
    # base64 BODY on the line (none of these do), and the alphabet run cannot be key
    # material. Verified canary: 4 new patterns hit 6/6 live flags; 4 real-material
    # controls (bare committed-key header line, header+body one-liner, real-shaped
    # sk-or key, PEM body line) all still flag.
    # (a) HTML-escaped quoted header in a rendered doc: &quot;-----BEGIN RSA PRIVATE KEY-----&quot;
    re.compile(r'&quot;-----BEGIN [A-Z ]*(?:PRIVATE KEY|PRIVATE KEY BLOCK|KEY BLOCK)-----'),
    # (b) header wrapped in an HTML code span (docs table row)
    re.compile(r'<code>-----BEGIN [A-Z ]*(?:PRIVATE KEY|PRIVATE KEY BLOCK|KEY BLOCK)-----(?:</code>)?'),
    # (c) the scrubber's own test vector file (marker text + [REDACTED:...] expected-output column)
    re.compile(r'(?i)/scrub/testdata/.*(?:private_key_block|\[REDACTED:)'),
    # ── Backtick-quoted PEM BEGIN-header in the scanner's own prose (scan #101) ──
    # The scanner's source comment describing the bare-diff-line miss wraps the
    # marker in backticks: `+-----BEGIN RSA PRIVATE KEY-----`. Complete header,
    # no base64 body on the line — documentation, not material. Narrow like the
    # straight-quote rule: header must END the backtick span immediately.
    re.compile(r'`\+?-----BEGIN [A-Z ]*(?:PRIVATE KEY|PRIVATE KEY BLOCK|KEY BLOCK)-----`'),
    # (d) literal alphabet run as an assigned value (Go byte-set const: setToken = "ABC…XYZabc…xyz0-9")
    re.compile(r'"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz'),
    # ── Secret-store KEY-NAME constants (scan #93, 2026-09-17) ──
    # A secret-store lookup key or an ACP auth-method ID is an IDENTIFIER, not
    # credential material: the value is what you PASS to the store at runtime
    # (secrets.get(<CONST>) / new ServerSecretStore(<CONST>)) to fetch the real
    # secret from the OS keychain. Scans #93 flagged 7 of these in /home/kara/t3code
    # (`RELAY_URL_SECRET = "cloud-relay-url"`, `GROK_AUTH_METHOD_CACHED_TOKEN =
    # "cached_token"`). Both rules are deliberately NARROW: the assigned value must
    # be a whole quoted word-chain of LOWERCASE LETTERS joined by -/_/. — no digits
    # and no uppercase. Real key material is base64/hex and carries digits, so a
    # genuine leak assigned to such a constant still fires: e.g.
    # `OPENROUTER_API_SECRET = "sk-or-v1-73504d…"` cannot match ('v1' has a digit,
    # and the value must run to the closing quote).
    # (a) `<…>_SECRET = "<lowercase word chain>"` — keychain key names
    re.compile(r'[A-Z0-9_]{2,}_SECRET\s*[:=]\s*"[a-z]+(?:[-_.][a-z]+)+"'),
    # (b) `<…>AUTH_METHOD<…> = "<lowercase word chain>"` — ACP/auth-method IDs
    re.compile(r'AUTH_METHOD[A-Z0-9_]*\s*[:=]\s*"[a-z]+(?:[._-][a-z]+)+"'),
    # ── Self-describing fixture TOKENs in E2E batteries (scan #94, 2026-09-17) ──
    # (c) `/home/kara/bunker/e2e-full-battery.sh` (carrier f3d8543) sets two documented
    # test tokens: `BUNKER_TOKEN="test-regression-token"` (the battery's documented
    # DEFAULT, README env table) and a precedence self-test value
    # `BUNKER_TOKEN="selftest-token-explicit"` that exists only to prove an exported
    # BUNKER_TOKEN wins over the default. The live daemon token is unrelated (48-hex
    # random in /etc/bunkerd/config.yaml — verified 2026-09-17).
    # Narrow: the whole quoted value must be LOWERCASE letters joined by -/_/. and must
    # itself spell "token". Real key material is base64/hex and carries digits or
    # uppercase, and never spells "token", so a genuine leak on the same name still
    # fires: `BUNKER_TOKEN="sk-or-v1-73504d…"` cannot match (`v1` = digits).
    re.compile(r'[A-Z0-9_]*TOKEN\s*[:=]\s*"[a-z][a-z._-]*token[a-z._-]*"'),
    # ── Status / sentinel string constants whose NAME ends in "Token" (scan #96, 2026-09-18) ──
    # /home/kara/bunker internal/agent/manager_lifecycle.go:41 `stoppedToken = "agent_stopped"`
    # (carrier 948ebf4, the GAP-071 lifecycle-RPC commit): the value is the stable status
    # TOKEN used in the error text and matched by errors.Is (ErrAgentStopped) — a sentinel
    # name, not credential material. Neighbours on the same const block are the same shape
    # (`StatusAlreadyStopped = "already_stopped"`). The live bunkerd token is unrelated: a
    # random 48-hex value in /etc/bunkerd/config.yaml (rotated off the old test token by GAP-014).
    # Narrow by construction: the assigned value must be a whole quoted chain of LOWERCASE
    # letters joined by -/_/. (no digits, no uppercase) AND must not start with a known
    # real-key prefix. Real key material is base64/hex and carries digits or uppercase, so a
    # genuine leak on the same name still fires: `stoppedToken = "sk-or-v1-73504d…"` cannot
    # match, and even an all-lowercase `ghp_abcdef…` value stays detected via the prefix guard.
    re.compile(r'[A-Za-z0-9_]*[Tt]oken\s*[:=]\s*"(?!(?:sk|gh[opsur]|github_pat|tskey|xox|AKIA|AIza|eyJ|glpat)[-_A-Za-z0-9]*")[a-z][a-z._-]*"'),
    # ── SEQUENTIAL-DIGIT placeholder keys in board/task prose (scan #98, 2026-09-18) ──
    # Scan #98 flagged two CRITICALs in gitreins-poc `.coding-hermes/board/tasks.jsonl`:
    # rows GR-GAP-005 and GR-GAP-007 are the repo's OWN security findings, whose text
    # quotes the planted test values used to reproduce the leaks they document
    # (`AWS_ACCESS_KEY_ID=AKIA1234567890ABCDEF`, `GITHUB_TOKEN=ghp_1234567890…` — 36
    # sequential digits). Both rows are permanent board content and get re-added to the
    # 24h diff window by every en-masse board rewrite (carrier 07ef86e), so without a
    # rule this pair re-flags on every rewrite.
    # Narrow by construction — these key on the sequential marker, exactly like the
    # existing `sk-(or-v1-)?1234567890`, `sk-(?:A1){3,}` and `ghp_ABCDEFGHI` examples
    # above. Real material keeps firing: AKIA + random base32 body, or ghp_ + a
    # mixed-case random body, cannot match (verified canary 2026-09-18).
    re.compile(r'AKIA1234567890'),
    re.compile(r'ghp_1234567890'),
    # ── The secret-scrubber's OWN fixture battery (scan #100, 2026-09-19) ──
    # ~/.hermes/scripts/test_secret_scrub.py (SEC-001, carrier 8edba9f) plants ONE
    # credential-shaped dummy per provider so it can assert scrub() redacts each of them;
    # the file's docstring states every value is SYNTHETIC ("same shape as real secrets,
    # never real values"). Four flagged CRITICAL on the first fire that saw the file:
    # sk-or-v1-fake0fa…, ghp_FakeToken…, gho_FakeOAuth…, xoxb-123456789012-….
    # Rule (a) narrow by construction: the body must SPELL 'fake' within a handful of
    # characters of a real-key prefix. Real key material is random base64/hex and never
    # contains the word, so a genuine leak still fires.
    re.compile(r'(?i)(?:sk-[A-Za-z0-9-]{0,7}|gh[pousr]_[A-Za-z0-9]{0,4}|'
               r'github_pat_[A-Za-z0-9]{0,4}|tskey-[a-z-]{0,6})fake'),
    # Rule (b): the canonical sequentially-numbered Slack placeholder (docs dummy
    # `xoxb-1234567890123` and the battery's `xoxb-123456789012-123456789012-FaKe…`).
    # Keys on the sequential marker only — a real xoxb body is random, so real Slack
    # tokens still trip the slack_token pattern.
    re.compile(r'xox[baprs]-1234567890\d*'),
]

# Repos to ALWAYS scan (the active dev + config repos)
PRIORITY_REPOS = [
    "/home/kara/helios-work",
    "/home/kara/conscientiousness",
    "/home/kara/muster",
    "/home/kara/dexdat-memory",
    "/home/kara/Kobayashi-Maru",
    "/home/kara/frontiers-ghost-audit",  # was /home/kara/frontiers-ghost (renamed Jun 2026; stale path caused FileNotFoundError mislabeled as "timeout")
]

# Repos/dirs to NEVER scan
SKIP_PATTERNS = [
    re.compile(r'node_modules'),
    re.compile(r'__pycache__'),
    re.compile(r'\.venv'),
    re.compile(r'\.cache'),
    re.compile(r'\.cargo'),
    re.compile(r'\.local/share'),
    re.compile(r'\.npm'),
    re.compile(r'\.hermes/sessions'),
    re.compile(r'\.hermes/logs'),
    re.compile(r'snap/'),
    re.compile(r'/tmp/'),
]


def find_git_repos(base_dirs, max_depth=3):
    """Find git repos, skipping known noise dirs."""
    repos = list(PRIORITY_REPOS)  # Always include these
    for base in base_dirs:
        if not os.path.isdir(base):
            continue
        for root, dirs, _ in os.walk(base):
            depth = root[len(base):].count(os.sep)
            if depth >= max_depth:
                dirs.clear()
                continue
            dirs[:] = [d for d in dirs if not any(p.search(os.path.join(root, d)) for p in SKIP_PATTERNS)]
            if '.git' in dirs:
                if root not in repos:
                    repos.append(root)
                dirs.remove('.git')
    # DuckBrain namespace stores are one git repo per namespace at depth 3
    # (~/duckbrain/namespaces/<ns>) — ABOVE the depth-3 walk limit, so the whole memory
    # store was invisible to this scanner until scan #97 (2026-09-18), where 2 LIVE
    # xKiro keys sat committed in chat-archive (pushed to s3://duckbrain/...). Add them
    # explicitly rather than deepening the walk (keeps repo discovery bounded).
    ns_root = '/home/kara/duckbrain/namespaces'
    if os.path.isdir(ns_root):
        try:
            names = sorted(os.listdir(ns_root))
        except OSError:
            names = []
        for name in names:
            p = os.path.join(ns_root, name)
            if os.path.isdir(os.path.join(p, '.git')) and p not in repos:
                repos.append(p)
    return repos


def repo_has_recent_commits(repo_dir, since_iso):
    """Quick check: does this repo have ANY commits in the window?"""
    try:
        result = subprocess.run(
            ['git', 'log', '--since=' + since_iso, '--oneline', '-n', '1'],
            capture_output=True, text=True, timeout=5, cwd=repo_dir
        )
        return bool(result.stdout.strip())
    except (subprocess.TimeoutExpired, OSError):
        return False


def is_false_positive(line, file_path):
    """Check if a matched line is a false positive."""
    combined = f"{file_path} | {line}"
    for fp in FP_PATTERNS:
        if fp.search(combined):
            return True
    return False


def fp_window(line, match, span=120):
    """Return a bounded excerpt around a match, for FP-checking and reporting.

    Chat/JSONL rows run to 70 KB+ and can contain FP trigger words ('DEMO-', '_test.',
    'hardening', 'the key was') ANYWHERE in the row. Running is_false_positive on the
    whole line let those words swallow a REAL key (scan #97: two live xKiro keys
    committed in the chat-archive namespace row, invisible to every scan until the
    excerpt was bounded). A ±span window keeps the prose heuristics meaningful while
    giving long-line secrets the same treatment as short lines.
    """
    start = max(0, match.start() - span)
    return line[start:match.end() + span]


def redact_line(line):
    """Redact every secret-looking span before it is printed into a report.

    The scan report is itself archived to ~/.hermes/cron/output/<job-id>/*.md,
    so printing raw matches wrote live key material to disk 4x/day (found scan #80).
    Reports must show prefix + length only — enough to classify, never the value.
    """
    out = line
    for pattern, _ptype, _severity in SECRET_PATTERNS:
        if not pattern.search(out):
            continue

        def _sub(m):
            target = m.group(1) if (m.lastindex and m.group(1) is not None) else m.group(0)
            keep = 16 if len(target) >= 40 else 6  # long keys stay identifiable for rotation
            return m.group(0).replace(
                target, f"{target[:keep]}…<redacted:{len(target)}>", 1
            )

        out = pattern.sub(_sub, out)
    return out


def scan_repo(repo_dir, since_iso):
    """Scan a repo that has recent commits using git pickaxe for speed."""
    findings = []
    try:
        # Get the full diff for the window
        result = subprocess.run(
            ['git', 'log', '--since=' + since_iso,
             '--diff-filter=AM', '-p', '--no-color',
             '--no-renames',  # Skip rename detection → faster
             '-U0'],  # Zero context lines → smaller output
            capture_output=True, timeout=REPO_TIMEOUT_S, cwd=repo_dir
        )
        stdout_text = result.stdout.decode('utf-8', errors='replace')
    except (subprocess.TimeoutExpired, OSError):
        return [{'repo': repo_dir, 'type': 'timeout', 'severity': 'INFO',
                 'file': '', 'line': f'Repo timed out (>{repo_dir})'}]

    current_file = ''
    for line in stdout_text.split('\n'):
        # Track current file
        if line.startswith('diff ') or line.startswith('--- ') or line.startswith('+++ '):
            current_file = line
            continue

        # Only look at added lines (potential new secrets)
        if not line.startswith('+') or line.startswith('+++'):
            continue

        for pattern, ptype, severity in SECRET_PATTERNS:
            m = pattern.search(line)
            if not m:
                continue
            excerpt = fp_window(line, m)
            if is_false_positive(excerpt, current_file):
                continue
            findings.append({
                'repo': repo_dir,
                'type': ptype,
                'severity': severity,
                'file': current_file.strip()[:150],
                'line': redact_line(excerpt.strip()[:200]),
            })

    return findings


def scan_plaintext_dir(base_dir, live_env_files):
    """Scan a non-git directory (skills, backups) line-by-line for secret patterns.

    Catches secrets pasted into skill docs / reference files / backup .envs
    (e.g. the gamemaster-investigations telegram-file-upload.md incident of
    2026-08-22: the real bot token sat in a skill reference for 3 months).
    Live .env files are skipped — they are the legitimate home of tokens.
    """
    findings = []
    for root, dirs, files in os.walk(base_dir):
        dirs[:] = [d for d in dirs if not any(p.search(os.path.join(root, d)) for p in SKIP_PATTERNS)]
        for fname in files:
            fpath = os.path.join(root, fname)
            if fpath in live_env_files:
                continue
            if not fname.endswith(('.md', '.sh', '.py', '.js', '.ts', '.txt', '.json', '.yaml', '.yml', '.toml', '.env')):
                continue
            try:
                with open(fpath, 'r', errors='replace') as f:
                    for i, line in enumerate(f, 1):
                        for pattern, ptype, severity in SECRET_PATTERNS:
                            m = pattern.search(line)
                            if not m:
                                continue
                            excerpt = fp_window(line, m)
                            if is_false_positive(excerpt, fpath):
                                continue
                            findings.append({
                                'repo': f'plaintext:{base_dir}',
                                'type': ptype,
                                'severity': severity,
                                'file': fpath,
                                'line': redact_line(f'L{i}: {excerpt.strip()[:200]}'),
                            })
            except (OSError, UnicodeDecodeError):
                continue
    return findings


def main():
    parser = argparse.ArgumentParser(description='Scan git repos for secrets (v2)')
    parser.add_argument('--hours', type=int, default=24)
    parser.add_argument('--verbose', '-v', action='store_true')
    args = parser.parse_args()

    cutoff = datetime.now(timezone.utc) - timedelta(hours=args.hours)
    # +00:00 makes this a TRUE 24h UTC window. Without the offset git reads the tz-less
    # ISO as LOCAL time (UTC-5 here) => the window silently shrank to ~19h and the most
    # recent ~5h of commits were never scanned (found in scan #97: the chat-archive
    # backfill carrying the live xKiro keys sat in exactly that band).
    since_iso = cutoff.strftime('%Y-%m-%dT%H:%M:%S+00:00')

    # Step 1: Find repos
    repos = find_git_repos(['/home/kara'])
    if args.verbose:
        print(f"Found {len(repos)} repos. Checking for recent activity...", file=sys.stderr)

    # Step 2: Filter to repos with recent activity + priority repos
    active_repos = []
    for repo in repos:
        if repo in PRIORITY_REPOS or repo_has_recent_commits(repo, since_iso):
            active_repos.append(repo)

    if args.verbose:
        print(f"{len(active_repos)} repos have recent activity. Scanning...", file=sys.stderr)

    # Step 3: Scan active repos
    all_findings = []
    for repo in active_repos:
        if args.verbose:
            print(f"  Scanning: {repo}", file=sys.stderr)
        findings = scan_repo(repo, since_iso)
        all_findings.extend(findings)

    # Step 3.5: Plaintext scan of non-git secret hotspots (skill docs, backups)
    live_env_files = {
        os.path.expanduser('~/.hermes/.env'),
        os.path.expanduser('~/.hermes/foreman/.env'),
        os.path.expanduser('~/.hermes/profiles/eduos-e2e-tester/.env'),
        os.path.expanduser('~/.hermes/profiles/uncensored/.env'),
    }
    plaintext_dirs = [
        os.path.expanduser('~/.hermes/skills'),
        os.path.expanduser('~/.hermes/20260524-181118-pre-update'),
        os.path.expanduser('~/.hermes/state-snapshots'),
        # Added 2026-09-13 (scan #81): skills.bak-* = pre-edit skill snapshots that held
        # LIVE key copies (849/8fd/b34) for 8 consecutive fires while staying outside the
        # walk. Deliberately NOT added: ~/.hermes/cron/output (this job's run records) —
        # measured 698 findings/scan there, almost all briefings quoting the FP corpus,
        # which would drown the real signal; scrub + redact_line() cover it instead.
        os.path.expanduser('~/.hermes/skills.bak-2026-08-23'),
    ]
    for pdir in plaintext_dirs:
        if not os.path.isdir(pdir):
            continue
        if args.verbose:
            print(f"  Plaintext: {pdir}", file=sys.stderr)
        all_findings.extend(scan_plaintext_dir(pdir, live_env_files))

    # Step 4: Output
    if not all_findings:
        print(f"SCAN_VERSION: 3")
        print(f"SCAN_TIME: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}")
        print(f"REPOS_TOTAL: {len(repos)}")
        print(f"REPOS_ACTIVE: {len(active_repos)}")
        print(f"PLAINTEXT_DIRS: {len(plaintext_dirs)}")
        print(f"SCAN_WINDOW: {args.hours}h")
        print("")
        print("✅ **No secrets found in recent commits or plaintext hotspots.**")
        print(f"   Scanned {len(active_repos)} active repos, {len(repos)} total, {len(plaintext_dirs)} plaintext dirs.")
        print("")
        print("---")
        print("SCAN_SUMMARY: 0 findings | clean")
        sys.exit(0)

    print(f"SCAN_VERSION: 3")
    print(f"SCAN_TIME: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}")
    print(f"REPOS_TOTAL: {len(repos)}")
    print(f"REPOS_ACTIVE: {len(active_repos)}")
    print(f"PLAINTEXT_DIRS: {len(plaintext_dirs)}")
    print(f"SCAN_WINDOW: {args.hours}h")
    print(f"FINDINGS: {len(all_findings)}")
    print("")

    # Sort by severity
    severity_order = {'CRITICAL': 0, 'HIGH': 1, 'MEDIUM': 2, 'INFO': 3}
    all_findings.sort(key=lambda f: severity_order.get(f.get('severity', 'INFO'), 99))

    for f in all_findings:
        emoji = {'CRITICAL': '🔴', 'HIGH': '🟠', 'MEDIUM': '🟡', 'INFO': 'ℹ'}.get(f.get('severity', 'INFO'), '⚪')
        print(f"{emoji} **{f['severity']}** — `{f['repo']}`")
        print(f"   Type: {f['type']}")
        print(f"   File: {f['file']}")
        print(f"   Line: `{f['line']}`")
        print()

    print("---")
    criticals = [f for f in all_findings if f.get('severity') == 'CRITICAL']
    highs = [f for f in all_findings if f.get('severity') == 'HIGH']
    print(f"SCAN_SUMMARY: {len(all_findings)} findings | {len(criticals)} critical")
    # Exit semantics (fixed 2026-09-19): a bare sys.exit(1) fired on INFO-only days
    # (e.g. two repo timeouts) so the cron wrapper reported "Script Error" and buried
    # the real signal. Now nonzero ONLY when a real-severity finding exists.
    sys.exit(1 if (criticals or highs) else 0)


if __name__ == "__main__":
    main()

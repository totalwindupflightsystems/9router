#!/usr/bin/env python3
"""Test battery for secret_scrub.py (SEC-001).  Plain python3, no pytest.

Run:  python3 test_secret_scrub.py
Exits 0 when every planted secret shape is redacted and every false-positive
guard survives unredacted; exits 1 otherwise.

All planted values are SYNTHETIC (same shape as real secrets, never real
values) — do not paste real keys into this file.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from secret_scrub import scrub

# (case name, planted secret, expected marker).  Each planted value is
# embedded in a realistic 'HH:MM Sender: text' chat row before scrubbing.
POSITIVE_CASES = [
    ("xkiro-api-key",        "sk-xt-fakeTESTKEY9f8e7d6c5b4a3210fedcba98", "sk-xt-[REDACTED]"),
    ("openrouter-api-key",   "sk-or-v1-fake0fa1ce0f00ba11d5e5e5e5e5e5e5e5e5e5e5e", "sk-or-v1-[REDACTED]"),
    ("anthropic-api-key",    "sk-ant-fakeTESTKEY-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "sk-ant-[REDACTED]"),
    ("github-token-ghp",     "ghp_FakeTokenFakeTokenFakeToken",           "[REDACTED-GITHUB-TOKEN]"),
    ("github-token-gho",     "gho_FakeOAuthFakeOAuthFakeOAu",             "[REDACTED-GITHUB-TOKEN]"),
    ("github-token-ghpou",   "ghpou_" + "FakeGhpou" * 5,                  "[REDACTED-GITHUB-TOKEN]"),
    ("github-pat",           "github_pat_11FAKEFAKEFAKEFAKEFAKEFAKE",     "github_pat_[REDACTED]"),
    # AWS's own documentation placeholder access key id — shape-correct, public.
    ("aws-access-key-id",    "AKIAIOSFODNN7EXAMPLE",                      "AKIA[REDACTED]"),
    ("telegram-bot-token",   "123456789:AAF" + "a" * 35,                  "[REDACTED-TELEGRAM-BOT-TOKEN]"),
    ("tailscale-api-key",    "tskey-api-kFAKEctrlFAKE1234567890",         "tskey-api-[REDACTED]"),
    ("slack-token",          "xoxb-123456789012-123456789012-FaKeToKeN000000000000", "xox-[REDACTED]"),
    # sha1/sha256 of the empty string — well-known public constants, shape-correct.
    ("hex40-blob",           "da39a3ee5e6b4b0d3255bfef95601890afd80709",  "[REDACTED-HEX40]"),
    ("hex64-blob",           "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855", "[REDACTED-HEX64]"),
    ("kv-password",          "Sup3rFakePassw0rd",                         "password:[REDACTED]"),
    ("kv-api-key",           "fakeapikeyvalue123456",                     "api_key:[REDACTED]"),
]

PEM_SECRET = (
    "-----BEGIN OPENSSH PRIVATE KEY-----\n"
    "b3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAAEbm9uZQAAAAAAAAABAAAAMwAAAAtzc2gt\n"
    "ZWQyNTUxOQAAACBGAKEFAKEFAKEFAKEFAKEFAKEFAKEFAKEFAKEFAKEFAKE=\n"
    "-----END OPENSSH PRIVATE KEY-----"
)

# False-positive guards: these rows must come through scrub() UNCHANGED.
NEGATIVE_CASES = [
    "09:15 Bane: the token rotation runbook is done; no token expires this week, and password managers help a lot.",
    "10:01 KaraHermes: commit 1a2b3c4 landed the fix; parent is 890abcd.",
]


def main():
    failures = 0

    for name, secret, marker in POSITIVE_CASES:
        if name == "kv-password":
            row = "14:32 Bane: try password: %s on that box" % secret
        elif name == "kv-api-key":
            row = "14:33 Bane: api_key = %s is the test one" % secret
        else:
            row = "14:32 Bane: hey check this config value %s and let me know" % secret
        out = scrub(row)
        ok = (marker in out) and (secret not in out)
        print("%s %-22s -> marker %r present=%s secret-gone=%s"
              % ("PASS" if ok else "FAIL", name, marker, marker in out, secret not in out))
        if not ok:
            failures += 1

    # PEM block (multi-line) inside a chat row.
    row = "15:40 Bane: here is the key:\n" + PEM_SECRET + "\nend of key"
    out = scrub(row)
    ok = ("[REDACTED-PRIVATE-KEY]" in out
          and "b3BlbnNzaC1rZXktdjE" not in out
          and "PRIVATE KEY" not in out)
    print("%s %-22s -> PEM block redacted=%s" % ("PASS" if ok else "FAIL", "pem-private-key", ok))
    if not ok:
        failures += 1

    # PEM block flattened to one line (chat rows are newline-flattened upstream).
    flat = "15:41 Bane: key: " + PEM_SECRET.replace("\n", " ") + " end"
    out = scrub(flat)
    ok = ("[REDACTED-PRIVATE-KEY]" in out and "b3BlbnNzaC1rZXktdjE" not in out)
    print("%s %-22s -> flattened PEM redacted=%s" % ("PASS" if ok else "FAIL", "pem-flattened", ok))
    if not ok:
        failures += 1

    # False-positive guards must survive byte-identical.
    for row in NEGATIVE_CASES:
        out = scrub(row)
        ok = out == row
        print("%s %-22s -> unchanged=%s" % ("PASS" if ok else "FAIL", "fp-guard", ok))
        if not ok:
            failures += 1
            print("   in : %r" % row)
            print("   out: %r" % out)

    # Idempotency: scrubbing an already-redacted row changes nothing.
    redacted = scrub("x: sk-xt-fakeTESTKEY9f8e7d6c5b4a3210fedcba98 y: password: Sup3rFakePassw0rd")
    ok = scrub(redacted) == redacted
    print("%s %-22s -> stable=%s" % ("PASS" if ok else "FAIL", "idempotent", ok))
    if not ok:
        failures += 1

    if failures:
        print("\n%d FAILURE(S)" % failures)
        return 1
    print("\nALL TESTS PASSED (%d positive + 2 PEM + %d fp-guards + idempotency)"
          % (len(POSITIVE_CASES), len(NEGATIVE_CASES)))
    return 0


if __name__ == "__main__":
    sys.exit(main())

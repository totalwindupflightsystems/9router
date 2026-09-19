#!/usr/bin/env python3
"""Write-time secret scrubbing for DuckBrain chat-archive ingestion (SEC-001).

Root cause of SEC-001: the chat-archive ingestion scripts wrote raw message
text into the git-versioned namespace store with either no scrub
(daily_chat_extract.py, state_db_backfill.py) or a partial one
(tg_backfill_duckbrain.py — it missed sk-xt- xKiro keys).  This module is the
single shared scrub every ingester routes EVERY row through BEFORE write.

Usage:
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from secret_scrub import scrub

    row = scrub(row)

Each redaction replaces the secret with a short stable marker (e.g.
``sk-xt-[REDACTED]``) so redaction is visible downstream.  Markers are
idempotent: re-scrubbing an already-redacted row changes nothing (the
character classes never match the ``[``/``]`` of a marker).
"""
import re

__all__ = ["SCRUB_PATTERNS", "scrub"]


def _kv_repl(m):
    # Preserve the key name (original case), redact only the value.
    return m.group(1) + ":[REDACTED]"


# (name, compiled regex, replacement).  ORDER MATTERS: multi-line PEM blocks
# and specific token prefixes first, generic hex blobs and key=value shapes
# last, so a specific shape is never mangled by a generic one first.
SCRUB_PATTERNS = [
    ("pem-private-key",
     re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?"
                r"-----END [A-Z0-9 ]*PRIVATE KEY-----", re.DOTALL),
     "[REDACTED-PRIVATE-KEY]"),
    ("telegram-bot-token",
     re.compile(r"\b\d{8,12}:AA[A-Za-z0-9_\-]{30,}"),
     "[REDACTED-TELEGRAM-BOT-TOKEN]"),
    ("xkiro-api-key",
     re.compile(r"sk-xt-[A-Za-z0-9_\-]+"),
     "sk-xt-[REDACTED]"),
    ("openrouter-api-key",
     re.compile(r"sk-or-v1-[A-Za-z0-9_\-]+"),
     "sk-or-v1-[REDACTED]"),
    ("anthropic-api-key",
     re.compile(r"sk-ant-[A-Za-z0-9_\-]+"),
     "sk-ant-[REDACTED]"),
    ("github-pat",
     re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
     "github_pat_[REDACTED]"),
    ("github-token",
     re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
     "[REDACTED-GITHUB-TOKEN]"),
    ("aws-access-key-id",
     re.compile(r"\bAKIA[A-Z0-9]{16}\b"),
     "AKIA[REDACTED]"),
    ("tailscale-api-key",
     re.compile(r"\btskey-api-[A-Za-z0-9_\-]+"),
     "tskey-api-[REDACTED]"),
    ("slack-token",
     re.compile(r"\bxox[baprs]-[A-Za-z0-9\-]+"),
     "xox-[REDACTED]"),
    ("hex64-blob",
     re.compile(r"\b[0-9a-f]{64}\b"),
     "[REDACTED-HEX64]"),
    ("hex40-blob",
     re.compile(r"\b[0-9a-f]{40}\b"),
     "[REDACTED-HEX40]"),
    ("kv-secret",
     re.compile(r"(?i)(password|passwd|api[_-]?key|secret|token)"
                r"\s*[:=]\s*['\"]?[A-Za-z0-9_\-\.]{6,}"),
     _kv_repl),
]


def scrub(text):
    """Redact every known secret shape from text.  Idempotent."""
    if not text:
        return text
    for _name, rx, rep in SCRUB_PATTERNS:
        text = rx.sub(rep, text)
    return text

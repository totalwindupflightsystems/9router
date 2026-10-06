#!/usr/bin/env python3
"""Expose daily Hermes usage aggregates from the read-only state.db."""
import os
import re
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote

DB_PATH = Path(os.environ.get("HERMES_STATE_DB", "/state/state.db"))
TICK_TITLE = re.compile(r"\b([A-Za-z0-9_.-]+)\s+tick\s*#", re.I)


def lane_for(cwd, title):
    match = TICK_TITLE.search(title or "")
    if match:
        return match.group(1)
    name = Path((cwd or "").rstrip("/")).name
    match = re.search(r"(?:^|-)((?:MON|[A-Z]{2,})-GAP-[A-Z0-9-]+)$", name)
    return (match.group(1) if match else name) or "unattributed"


def _label(value):
    return str(value).replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def scrape_text(db_path=DB_PATH):
    if not db_path.is_file():
        raise FileNotFoundError(f"state database not found: {db_path}")
    uri = f"file:{quote(str(db_path.resolve()), safe='/')}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=5)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA query_only=ON")
        rows = conn.execute("""SELECT u.billing_base_url,u.input_tokens,u.output_tokens,
          u.cache_read_tokens,u.cache_write_tokens,u.estimated_cost_usd,u.api_call_count,
          s.started_at,s.cwd,s.title FROM session_model_usage u JOIN sessions s
          ON s.id=u.session_id WHERE s.started_at IS NOT NULL""").fetchall()
    finally:
        conn.close()
    data = defaultdict(lambda: [0, 0, 0, 0.0, 0, 0])
    for r in rows:
        day = datetime.fromtimestamp(float(r["started_at"]), timezone.utc).date().isoformat()
        key = (day, lane_for(r["cwd"], r["title"]), r["billing_base_url"] or "unknown")
        v = data[key]
        for i, col in enumerate(("input_tokens", "output_tokens", "cache_read_tokens")):
            v[i] += int(r[col] or 0)
        v[3] += float(r["estimated_cost_usd"] or 0)
        v[4] += int(r["api_call_count"] or 0)
        v[5] += int(r["cache_write_tokens"] or 0)
    defs = {
        "hermes_session_tokens_in": "Daily input tokens from session_model_usage.",
        "hermes_session_tokens_out": "Daily output tokens from session_model_usage.",
        "hermes_session_cache_read_tokens": "Daily prompt-cache read tokens.",
        "hermes_session_est_cost_usd": "Daily estimated session cost in USD.",
        "hermes_session_api_calls": "Daily API calls; the work-unit denominator.",
        "hermes_session_cache_write_tokens": "Daily prompt-cache write tokens.",
        "hermes_session_cache_hit_ratio": "Cache-read / (input + cache-read) token ratio.",
        "hermes_session_cost_per_api_call_usd": "Estimated USD per API call work unit.",
    }
    out = [line for name, help_ in defs.items() for line in (f"# HELP {name} {help_}", f"# TYPE {name} gauge")]
    for (day, lane, provider), (tin, tout, cache, cost, calls, writes) in sorted(data.items()):
        labels = f'day="{day}",lane="{_label(lane)}",provider="{_label(provider)}"'
        vals = (tin, tout, cache, cost, calls, writes,
                cache / (tin + cache) if tin + cache else 0, cost / calls if calls else 0)
        for name, value in zip(defs, vals):
            out.append(f"{name}{{{labels}}} {value:.12g}")
    return "\n".join(out) + "\n"


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            body, status = b"ok\n", 200
        elif self.path == "/metrics":
            try:
                body, status = scrape_text().encode(), 200
            except (OSError, sqlite3.Error, ValueError):
                body, status = b"exporter_error 1\n", 503
        else:
            self.send_error(404)
            return
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        return


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", int(os.environ.get("PORT", "9108"))), Handler).serve_forever()

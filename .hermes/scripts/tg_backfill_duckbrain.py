#!/usr/bin/env python3
"""Backfill a Telegram export into the DuckBrain chat-archive tables.

Idempotent: skips keys that already have live entries. Run again after new
exports (or the 24h full backup) — only new days get written.

Usage:
  python3 tg_backfill_duckbrain.py <export.json> [--dry-run]

Layout (one namespace, one table per thread):
  /chats/karahermes-set/YYYY-MM-DD[/part-N]   KaraHermes - Set group rows
  /chats/karahermes-dm/YYYY-MM-DD[/part-N]    KaraHermes bot DM rows
  /index                                      table of contents (auto-updated if missing)

Rows: 'HH:MM sender: text' (UTC). Secrets scrubbed on write; the unscrubbed
master export stays local (see /index in the namespace).
"""
import json, sys, os, glob, re, urllib.request, datetime

# SEC-001: scrub() now comes from the shared secret_scrub module — the local
# partial list (sk-or-v1, gh[pousr]_, hex40/64, key=value) missed sk-xt- keys.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from secret_scrub import scrub

NS = "chat-archive"
API = "http://127.0.0.1:3000"
# DB-GAP-031: send X-API-Key when the daemon runs --auth=apikey (key file > env)
def _duckbrain_key(name):
    f = os.path.expanduser(f"~/.hermes/state/duckbrain-tokens/{name}.key")
    try:
        with open(f) as fh:
            return fh.read().strip()
    except OSError:
        return os.environ.get("DUCKBRAIN_API_KEY", "")
DB_KEY = _duckbrain_key("tg_backfill_duckbrain")
NS_DIR = os.path.expanduser("~/duckbrain/namespaces/chat-archive")
CHUNK = 80000
KEEP_CHATS = {
    3310984808: "karahermes-set",
    8925815583: "karahermes-dm",
}

def flatten_text(t):
    if t is None:
        return ""
    if isinstance(t, str):
        return t
    parts = []
    for p in t:
        if isinstance(p, str):
            parts.append(p)
        elif isinstance(p, dict):
            parts.append(p.get("text", ""))
    return "".join(parts)

def live_keys():
    """Authoritative live-key set from JSONL (by-id, tombstones shadowed)."""
    live = {}
    for f in glob.glob(os.path.join(NS_DIR, "*/*/*.jsonl")):
        for l in open(f, encoding="utf-8"):
            try:
                d = json.loads(l)
            except Exception:
                continue
            if d.get("action") == "tombstone":
                live.pop(d.get("id"), None)
            else:
                live[d["id"]] = d
    return {d["key"] for d in live.values()}

def post(key, domain, content, attrs, dry):
    body = json.dumps({"key": key, "domain": domain, "content": content,
                       "attributes": attrs}).encode()
    req = urllib.request.Request(f"{API}/api/memories?namespace={NS}",
                                 data=body, headers={"Content-Type": "application/json",
                                                     **({"X-API-Key": DB_KEY} if DB_KEY else {})})
    with urllib.request.urlopen(req, timeout=120) as r:
        d = json.loads(r.read())
        return d.get("id", "?")

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    if sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        sys.exit(0)
    src = sys.argv[1]
    dry = "--dry-run" in sys.argv[2:]
    with open(src, encoding="utf-8") as f:
        data = json.load(f)

    kept = [c for c in data.get("chats", {}).get("list", []) if c.get("id") in KEEP_CHATS]
    if not kept:
        print("ERROR: no matching chats in export")
        sys.exit(1)

    # flatten + group: slug -> day -> [rows]
    groups = {}
    for c in kept:
        slug = KEEP_CHATS[c["id"]]
        for m in c.get("messages", []):
            if m.get("type") == "service":
                continue
            text = flatten_text(m.get("text") or m.get("caption") or "").strip()
            if not text:
                continue
            date = (m.get("date") or "")[:10]
            if len(date) != 10:
                continue
            sender = (m.get("from") or "?").replace("\t", " ")
            row = f"{(m.get('date') or '')[11:16]} {sender}: {scrub(text.replace(chr(9), ' ').replace(chr(10), ' '))}"
            groups.setdefault(slug, {}).setdefault(date, []).append(row)

    existing = live_keys()
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    n_new = n_skip = 0
    ids = []
    for slug in sorted(groups):
        for day in sorted(groups[slug]):
            text = "\n".join(groups[slug][day])
            if len(text) <= CHUNK:
                parts = [(f"/chats/{slug}/{day}", text)]
            else:
                chunks, cur = [], ""
                for ln in groups[slug][day]:
                    if len(cur) + len(ln) + 1 > CHUNK and cur:
                        chunks.append(cur); cur = ""
                    cur += ln + "\n"
                if cur:
                    chunks.append(cur)
                parts = [(f"/chats/{slug}/{day}/part-{i+1}", t.rstrip("\n"))
                         for i, t in enumerate(chunks)]
            for key, content in parts:
                if key in existing:
                    n_skip += 1
                    continue
                attrs = {"date": day, "thread": slug, "source": "tg_backfill_duckbrain.py"}
                if "/part-" in key:
                    attrs["part"] = int(key.rsplit("-", 1)[1])
                if dry:
                    print(f"[dry-run] would write {key} ({len(content)}B)")
                    n_new += 1
                    continue
                try:
                    uid = post(key, "message", content, attrs, dry)
                    ids.append((uid, key, slug, day))
                    print(f"201 {uid[:12]} {key} ({len(content)}B)")
                    n_new += 1
                except Exception as e:
                    print(f"ERR {key}: {e}")

    # /index if missing
    if "/index" not in existing and not dry:
        content = ("Telegram archive tables (chat-archive ns). ONE NAMESPACE, ONE TABLE PER THREAD: "
                   "/chats/karahermes-set/YYYY-MM-DD[/part-N] (group rows), "
                   "/chats/karahermes-dm/YYYY-MM-DD[/part-N] (DM rows). Row format 'HH:MM sender: text' UTC. "
                   "Entries >80KB split into part-N (daemon body cap ~100KB). Secrets scrubbed; unscrubbed "
                   "master export stays in ~/telegram-archive/ (local only). Maintained by daily cron "
                   "869aec0b1c15 (03:00 local) reading state.db via daily_chat_extract.py.")
        try:
            uid = post("/index", "config", content, {"v": 3, "source": "tg_backfill_duckbrain.py"}, dry)
            print(f"201 {uid[:12]} /index")
        except Exception as e:
            print(f"ERR /index: {e}")

    # verify on disk
    if not dry and ids:
        found = 0
        for uid, key, slug, day in ids:
            hits = 0
            for f in glob.glob(os.path.join(NS_DIR, "message", "2026-*", "*.jsonl")):
                hits += sum(1 for l in open(f, encoding="utf-8") if uid in l)
            if hits >= 1:
                found += 1
            else:
                print(f"  ! NOT FOUND on disk: {key} ({uid})")
        print(f"verified {found}/{len(ids)} on disk")
    print(f"summary: {n_new} written, {n_skip} skipped (already present)")

if __name__ == "__main__":
    main()

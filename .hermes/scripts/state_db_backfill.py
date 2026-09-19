#!/usr/bin/env python3
"""Load the ACTUAL Hermes session database (state.db) into DuckBrain chat-archive.

Native transcripts — both sides, real gateway records — land under:
  /hermes/karahermes-set/YYYY-MM-DD[/part-N]   group transcripts
  /hermes/karahermes-dm/YYYY-MM-DD[/part-N]    DM transcripts
  (the /chats/ prefix stays the Telegram-export + daily-cron rows)

Idempotent: skips keys with live entries. Usage:
  python3 state_db_backfill.py [--db /path/to/state.db] [--since YYYY-MM-DD] [--dry-run]
"""
import sqlite3, os, sys, json, glob, re, urllib.request, datetime

# SEC-001: every row is secret-scrubbed before it is written to DuckBrain.
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
DB_KEY = _duckbrain_key("state_db_backfill")
NS_DIR = os.path.expanduser("~/duckbrain/namespaces/chat-archive")
CHUNK = 80000
THREADS = {
    "-1003310984808": "karahermes-set",
    "8925815583": "karahermes-dm",
}

def resolve_thread(chat_id, origin_json):
    if chat_id in THREADS:
        return THREADS[chat_id]
    try:
        o = json.loads(origin_json) if origin_json else {}
        cid = str(o.get("chat_id", ""))
        if cid in THREADS:
            return THREADS[cid]
    except Exception:
        pass
    return "unknown"

def live_keys():
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

def post(key, content, attrs):
    body = json.dumps({"key": key, "domain": "message", "content": content,
                       "attributes": attrs}).encode()
    req = urllib.request.Request(f"{API}/api/memories?namespace={NS}",
                                 data=body, headers={"Content-Type": "application/json",
                                                     **({"X-API-Key": DB_KEY} if DB_KEY else {})})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read()).get("id", "?")

def main():
    db = os.path.expanduser("~/.hermes/state.db")
    since = None
    dry = False
    args = sys.argv[1:]
    while args:
        a = args.pop(0)
        if a in ("-h", "--help"):
            print(__doc__)
            sys.exit(0)
        elif a == "--db":
            db = os.path.expanduser(args.pop(0))
        elif a == "--since":
            since = args.pop(0)
        elif a == "--dry-run":
            dry = True

    con = sqlite3.connect(db)
    params = []
    q = """SELECT m.timestamp, m.role, m.content, s.chat_id, s.origin_json
           FROM messages m JOIN sessions s ON m.session_id = s.id
           WHERE s.source='telegram' AND m.role IN ('user','assistant')
             AND m.timestamp IS NOT NULL"""
    if since:
        start = datetime.datetime.fromisoformat(since).replace(tzinfo=datetime.timezone.utc).timestamp()
        q += " AND m.timestamp>=?"
        params.append(start)
    q += " ORDER BY m.timestamp"
    rows = con.execute(q, params).fetchall()
    con.close()
    print(f"read {len(rows)} telegram user/assistant messages from {db}")

    days = {}
    for ts, role, content, chat_id, origin in rows:
        if not content:
            continue
        text = content if isinstance(content, str) else json.dumps(content)
        text = text.replace("\t", " ").replace("\n", " ").strip()
        text = scrub(text)  # SEC-001: scrub BEFORE truncation so a capped PEM cannot leak
        if role == "assistant" and text.startswith("{"):
            continue  # tool-call payload
        if len(text) > 600:
            text = text[:600] + "…"
        slug = resolve_thread(chat_id, origin)
        dt = datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc)
        sender = "Bane" if role == "user" else "KaraHermes"
        days.setdefault(slug, {}).setdefault(dt.strftime("%Y-%m-%d"), []).append(
            f"{dt.strftime('%H:%M')} {sender}: {text}")

    existing = live_keys()
    n_new = n_skip = 0
    ids = []
    for slug in sorted(days):
        for day in sorted(days[slug]):
            text = "\n".join(days[slug][day])
            if len(text) <= CHUNK:
                parts = [(f"/hermes/{slug}/{day}", text)]
            else:
                chunks, cur = [], ""
                for ln in days[slug][day]:
                    if len(cur) + len(ln) + 1 > CHUNK and cur:
                        chunks.append(cur); cur = ""
                    cur += ln + "\n"
                if cur:
                    chunks.append(cur)
                parts = [(f"/hermes/{slug}/{day}/part-{i+1}", t.rstrip("\n"))
                         for i, t in enumerate(chunks)]
            for key, content in parts:
                if key in existing:
                    n_skip += 1
                    continue
                attrs = {"date": day, "thread": slug, "source": "state.db",
                         "db": os.path.basename(db)}
                if "/part-" in key:
                    attrs["part"] = int(key.rsplit("-", 1)[1])
                if dry:
                    print(f"[dry-run] would write {key} ({len(content)}B)")
                    n_new += 1
                    continue
                try:
                    uid = post(key, content, attrs)
                    ids.append((uid, key))
                    print(f"201 {uid[:12]} {key} ({len(content)}B)")
                    n_new += 1
                except Exception as e:
                    print(f"ERR {key}: {e}")

    if not dry and ids:
        found = 0
        for uid, key in ids:
            hits = sum(1 for f in glob.glob(os.path.join(NS_DIR, "message", "2026-*", "*.jsonl"))
                       for l in open(f, encoding="utf-8") if uid in l)
            if hits >= 1:
                found += 1
            else:
                print(f"  ! NOT FOUND on disk: {key} ({uid})")
        print(f"verified {found}/{len(ids)} on disk")
    print(f"summary: {n_new} written, {n_skip} skipped (already present)")

if __name__ == "__main__":
    main()

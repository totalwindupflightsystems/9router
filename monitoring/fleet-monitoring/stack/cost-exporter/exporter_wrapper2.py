import os, sys, re
sys.path.insert(0, "/home/kara/worktrees/mon-gap012-merge/monitoring/fleet-monitoring/stack/cost-exporter")
import exporter

_orig_scrape = exporter.scrape_text
days = int(os.environ.get("HERMES_EXPORT_DAYS", "14"))
DAY_RE = re.compile(r'day="([0-9]{4}-[0-9]{2}-[0-9]{2})"')


def scrape_text_bounded(db_path=None):
    path = db_path if db_path is not None else exporter.DB_PATH
    if os.environ.get("HERMES_EXPORT_ALL_DAYS") == "1":
        return _orig_scrape(path)
    from datetime import date, timedelta
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    text = _orig_scrape(path)
    kept = []
    for line in text.splitlines():
        if line.startswith("#"):
            kept.append(line)
            continue
        m = DAY_RE.search(line)
        if m and m.group(1) >= cutoff:
            kept.append(line)
    return "\n".join(kept) + "\n"


exporter.scrape_text = scrape_text_bounded
exporter.Handler.log_message = lambda *a, **k: None
from http.server import ThreadingHTTPServer
ThreadingHTTPServer(("0.0.0.0", int(os.environ.get("PORT", "9108"))), exporter.Handler).serve_forever()

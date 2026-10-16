import os, sys, re
# MON-DOGFOOD-039: standalone path (the mon-gap012 worktree was reaped); fall back
# to the deployed repo copy when the service runs from the tree.
_CANDIDATES = [
    os.environ.get("HERMES_EXPORTER_DIR", ""),
    "/home/kara/monitoring/fleet-monitoring/stack/cost-exporter",
]
for _d in _CANDIDATES:
    if _d and os.path.isdir(_d):
        sys.path.insert(0, _d)
        break
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
if __name__ == "__main__":
    from http.server import ThreadingHTTPServer
    # Fleet convention (see fleet-monitoring prometheus.yml): exporters bind ONLY the
    # tailscale IP, never 0.0.0.0, so nothing lands on a public interface.
    bind = os.environ.get("HERMES_EXPORTER_BIND", "0.0.0.0")
    ThreadingHTTPServer((bind, int(os.environ.get("PORT", "9108"))), exporter.Handler).serve_forever()

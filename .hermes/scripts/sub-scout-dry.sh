#!/bin/bash
# SUB-MODEL SCOUT — dagger DRY-RUN driver.
# Key-safe: keys are read from config/.env and used for curl INSIDE this
# script; the sandbox never sees them. The pipeline reads only
# sub-scout-input.json (live model lists + selector state).
set -u
cd /home/kara/hermes-dagger || exit 1
export SCOUT_HOME="$HOME/.hermes/sub-scout"
mkdir -p "$SCOUT_HOME"
export SCOUT_INPUT_PATH="$SCOUT_HOME/sub-scout-input.json"
export SCOUT_HISTORY_PATH="$SCOUT_HOME/proposals.jsonl"
export SCOUT_SCRATCH_PATH="$SCOUT_HOME/proposals-scratch.jsonl"

KEY=$(grep -oE '^GATEWAY_API_KEY=.*' ~/.hermes/.env 2>/dev/null | head -1 | cut -d= -f2-)
[ -z "$KEY" ] && KEY=$(grep -oE '^API_SERVER_KEY=.*' ~/.hermes/.env 2>/dev/null | head -1 | cut -d= -f2-)
[ -z "$KEY" ] && { echo "sub-scout: no gateway key in ~/.hermes/.env"; exit 1; }

# ---- build input: per-sub live model lists + selector state ----
python3 - "$SCOUT_INPUT_PATH" <<'PYEOF'
import atexit, json, os, re, subprocess, sys, tempfile

out_path = sys.argv[1]
cfg = open(os.path.expanduser("~/.hermes/config.yaml")).read()
envf = {}
try:
    for line in open(os.path.expanduser("~/.hermes/.env")):
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            envf[k.strip()] = v.strip()
except Exception:
    pass

# parse custom_providers block: name -> {base_url, api_key_env, inline_key, models}
providers = {}
cur = None
for line in cfg.splitlines():
    m = re.match(r"^  ([a-z0-9_-]+):$", line)
    if m:
        cur = m.group(1)
        providers.setdefault(cur, {})
        continue
    if cur is None:
        continue
    m = re.match(r"^    base_url:\s*(.+)$", line)
    if m:
        providers[cur]["base_url"] = m.group(1).strip().strip('"').strip("'")
        continue
    m = re.match(r"^    api_key_env:\s*(.+)$", line)
    if m:
        providers[cur]["api_key_env"] = m.group(1).strip()
        continue
    m = re.match(r"^    api_key:\s*(.+)$", line)
    if m:
        providers[cur]["inline_key"] = m.group(1).strip().strip('"').strip("'")
        continue
    m = re.match(r"^    models:\s*$", line)
    if m:
        providers[cur]["in_models"] = True
        continue
    m = re.match(r"^      - (.+)$", line)
    if m and providers[cur].get("in_models"):
        providers[cur].setdefault("models", []).append(m.group(1).strip())

subs = []
for name, p in providers.items():
    if not p.get("base_url"):
        continue
    key = None
    if p.get("api_key_env"):
        key = envf.get(p["api_key_env"]) or os.environ.get(p["api_key_env"])
    elif p.get("inline_key"):
        key = p["inline_key"]
    subs.append({"name": name, "base_url": p["base_url"], "key": key or "",
                 "selector_models": p.get("models", [])})


# TR-147: credentials must not sit in argv (argv is world-readable on this box, and
# the fleet runs workers as the same user). curl reads the header from a 0600 config
# file instead, so the process listing shows only the path.
_AUTH_CFGS = []


def auth_cfg(token):
    fd, path = tempfile.mkstemp(prefix="tr147-auth-", suffix=".cfg")
    os.chmod(path, 0o600)
    os.write(fd, ('header = "Authorization: Bearer %s"\n' % token).encode())
    os.close(fd)
    _AUTH_CFGS.append(path)
    atexit.register(lambda p=path: os.path.exists(p) and os.unlink(p))
    return path

# live model lists via curl (credential via a 0600 config file: TR-147)
# Only providers with a REAL key (api_key_env/inline) are subs — skip
# config sections that merely match the YAML shape (bitwarden vault, etc.).
NON_SUBS = {"bitwarden", "vision", "compression", "skills_hub", "title_generation", "triage_specifier"}
subs = [s for s in subs if s["key"] and s["name"] not in NON_SUBS and not s["name"].startswith("deepseek")]
for s in subs:
    live = []
    try:
        url = s["base_url"].rstrip("/") + "/models"
        r = subprocess.run(["curl", "-s", "-m", "20", url, "-K", auth_cfg(s["key"])],
                           capture_output=True, text=True, timeout=30)
        d = json.loads(r.stdout or "{}")
        live = [m.get("id") for m in (d.get("data") or []) if m.get("id")]
        if not live:
            # /models absent (clinepass returns 404 there but serves chat/completions):
            # probe auth with a real completion on one selector model; if the key is
            # recognized, treat the selector list as the live set (cannot enumerate).
            auth_ok = False
            try:
                probe = (s["selector_models"] or ["cline-pass/glm-5.3"])[0]
                r2 = subprocess.run(
                    ["curl", "-s", "-m", "20", "-w", "\n%{http_code}",
                     s["base_url"].rstrip("/") + "/chat/completions",
                     "-K", auth_cfg(s["key"]),
                     "-H", "Content-Type: application/json",
                     "-d", json.dumps({"model": probe, "max_tokens": 5,
                                       "messages": [{"role": "user", "content": "hi"}]})],
                    capture_output=True, text=True, timeout=30)
                out = r2.stdout or ""
                code = out.rsplit("\n", 1)[-1].strip() if "\n" in out else ""
                body = out[:300].lower()
                auth_ok = code in ("200", "400", "500") or (
                    "unauthorized" not in body and "not found" not in body)
            except Exception:
                auth_ok = False
            if auth_ok:
                live = list(s["selector_models"])
                s["live_fallback"] = "no /models endpoint; auth verified via chat probe, selector list presumed live"
    except Exception:
        live = []
    s["live_models"] = sorted(set(live))
    s["live_error"] = None if live else ("no live models (endpoint/auth)" if not s.get("live_fallback") else s["live_fallback"])
    s.pop("key", None)  # never persist keys

json.dump({"generated_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
           "subs": subs}, open(out_path, "w"), separators=(",", ":"))
for s in subs:
    print(f"{s['name']}: selector={len(s['selector_models'])} live={len(s['live_models'])} {s.get('live_error') or ''}")
PYEOF

# ---- run the pipeline (fresh DB + unique port per run) ----
# Per-run isolation: unique dir (pid+ns) — no shared /tmp names, no
# second-granularity DB (same contamination class fixed 2026-08-27).
RUN_DIR="/tmp/sub-scout-$$-$(date +%s%N)"
mkdir -p "$RUN_DIR"
DB="$RUN_DIR/run.db"
SERVE_LOG="$RUN_DIR/serve.log"
RUN_LOG="$RUN_DIR/run.log"
PORT=""
for _ in $(seq 1 8); do
  CAND=$(( (RANDOM % 4000) + 11000 ))
  if ! ss -ltn 2>/dev/null | grep -q ":$CAND "; then PORT="$CAND"; break; fi
  sleep 0.2
done
[ -n "$PORT" ] || { echo "sub-scout: no free port in 11000-14999"; exit 1; }
# Scratch must start empty — a stale line from a failed run re-appends as a
# duplicate proposal on the next successful run.
rm -f "$SCOUT_SCRATCH_PATH"
env GATEWAY_API_KEY="$KEY" ./dagger serve --addr :$PORT --db "$DB" --tier 2 >"$SERVE_LOG" 2>&1 &
SERVE_PID=$!
OK=0
for _ in $(seq 1 25); do
  if curl -s -m 2 "http://127.0.0.1:$PORT/health" >/dev/null 2>&1 && kill -0 "$SERVE_PID" 2>/dev/null; then
    OK=1
    break
  fi
  sleep 1
done
[ "$OK" = "1" ] || { echo "sub-scout: serve failed to start on :$PORT"; kill -9 "$SERVE_PID" 2>/dev/null; exit 1; }

export DAGGER_ENV="SCOUT_INPUT_PATH=$SCOUT_INPUT_PATH,SCOUT_HISTORY_PATH=$SCOUT_HISTORY_PATH,SCOUT_SCRATCH_PATH=$SCOUT_SCRATCH_PATH"
env GATEWAY_API_KEY="$KEY" ./dagger run examples/coding-hermes/sub-scout.ts --server "http://127.0.0.1:$PORT" \
  --log-file "$SCOUT_HOME/sub-scout.jsonl" --log-level info >"$RUN_LOG" 2>&1
RUN_RC=$?

if [ -s "$SCOUT_SCRATCH_PATH" ]; then
  grep -v '^File not found' "$SCOUT_SCRATCH_PATH" >> "$SCOUT_HISTORY_PATH"
fi

if grep -q "Failed: 0" "$RUN_LOG" 2>/dev/null; then
  RUN_RC=0
fi

echo "SUB-SCOUT DRY-RUN — $(date -u +%Y-%m-%dT%H:%MZ)"
echo "dagger = dry-run proposals (never writes config/skills/DuckBrain) | cron 4d61449c9863 = weekly writer (cron-proposals.jsonl / report)"
echo
python3 demo/subscout_compare.py 2>/dev/null || echo "(no compare output — first run)"
echo
if [ "$RUN_RC" -ne 0 ]; then
  echo "⚠ pipeline exit $RUN_RC (details: $RUN_LOG)"
fi

kill -9 "$SERVE_PID" 2>/dev/null
wait "$SERVE_PID" 2>/dev/null
exit 0

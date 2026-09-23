#!/usr/bin/env python3
"""
fleet-topology-audit.py — Hermes fleet alignment: planets (projects) and their moons
(satellite lanes). One of each moon per planet is the invariant.

  SUN      = Hermes
  PLANET   = an enabled base project row      (e.g. auger)
  MOON     = that planet's satellite lane     (e.g. auger-qa, auger-dogfood, auger-sync)
  DEBRIS   = cron jobs / one-off rows

Checks:
  A. MOON COMPLETENESS — every enabled planet must carry one moon of each type.
  B. ORPHAN MOONS      — a lane whose planet is not enabled.
  C. SKILL WIRING      — each moon family's skill must exist and be named in the live prompt.

Usage:
  fleet-topology-audit.py                 # audit, human report
  fleet-topology-audit.py --json          # machine-readable gaps
  fleet-topology-audit.py --apply         # CREATE the missing moons (clones a sibling)
  fleet-topology-audit.py --apply --dry   # show exactly what would be POSTed
"""
from __future__ import annotations
import json, os, sqlite3, subprocess, sys, urllib.error, urllib.request

DB      = os.path.expanduser("~/.hermes/coding-hermes/scheduler.db")
API     = "http://127.0.0.1:9090/api/v1"
SKILLS  = os.path.expanduser("~/.hermes/skills")

# Row names that are fleet SERVICES, not planets: they own no moons by design.
SERVICE_ROWS = {"qa-audit", "release-engineer", "dogfooding", "stand-in"}

# Satellite LANES that are themselves per-project rows: a -review or -perf row is a MOON of its
# planet (per fleet.toml), never a planet needing moons of its own. classify() excludes rows
# whose namespace_id is one of these, so enabled review/perf lanes stop spawning fake gaps.
LANE_NAMESPACES = {"review", "perf"}

# moon -> (skill it must load, workdir template, weight, priority, cooldown_s)
MOONS = {
    "qa":      ("qa-foreman-ops",                "/home/kara/.hermes/stand-in/pm/{p}",          4, 4, 21600),
    "dogfood": ("coding-hermes-dogfood",         "/home/kara/.hermes/stand-in/dogfood/{p}",    3, 5, 21600),
    "pm":      ("coding-hermes-project-manager", "/home/kara/.hermes/stand-in/pm-lane/{p}",    4, 4, 21600),
    "releng":  ("coding-hermes-releng",          "/home/kara/.hermes/stand-in/releng-lane/{p}", 4, 4, 21600),
    "sync":    ("context-sync-duckbrain",        "/home/kara/.hermes/sync-workdirs/{p}-sync",  3, 5, 21600),
}
# The scheduler enforces ONE enabled project per workdir (409, case-insensitive).
# If the canonical dir is taken by an enabled sibling, fall back to a lane-scoped one.
WD_FALLBACK = {
    "qa":     "/home/kara/.hermes/stand-in/qa/{p}",
    "pm":     "/home/kara/.hermes/stand-in/pm-2/{p}",
    "dogfood": "/home/kara/.hermes/stand-in/dogfood-2/{p}",
    "releng": "/home/kara/.hermes/stand-in/releng-2/{p}",
    "sync":   "/home/kara/.hermes/sync-workdirs/{p}-sync-2",
}
LANES = list(MOONS)

# The shared contract every DuckBrain-touching moon should load.
DUCKBRAIN_CONTRACT = "coding-hermes-foreman-duckbrain-usage"


def rows():
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    out = [dict(r) for r in con.execute("SELECT * FROM projects")]
    con.close()
    return out


def ns_defaults():
    """namespace_id -> default_prompt. A project prompt resolves at spawn time as
    namespace default_prompt (base) + project prompt (append) — spawn.go buildForemanPrompt.
    Wiring checks must count the base, or empty-prompt moons read as silent."""
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    out = {r["id"]: r["default_prompt"] or "" for r in
           con.execute("SELECT id, default_prompt FROM namespaces")}
    con.close()
    return out


def classify(all_rows):
    planets, moons, debris = {}, {}, {}
    for r in all_rows:
        n = r["name"]
        if n in SERVICE_ROWS:
            debris[n] = r; continue
        for lane in LANES:
            if n.endswith("-" + lane):
                moons.setdefault(n[: -(len(lane) + 1)], {})[lane] = r
                break
        else:
            # a -review / -perf row is itself a satellite lane of its planet — not a planet
            if (r.get("namespace_id") or "") in LANE_NAMESPACES:
                debris[n] = r
                continue
            planets[n] = r
    return planets, moons, debris


def audit():
    allr = rows()
    planets, moons, debris = classify(allr)
    enabled_planets = sorted(p for p, r in planets.items() if r["enabled"])
    gaps, orphans = [], []
    for p in enabled_planets:
        have = moons.get(p, {})
        missing = [l for l in LANES if not (have.get(l) and have[l]["enabled"])]
        if missing:
            gaps.append({"planet": p, "missing": missing})
    for p, m in sorted(moons.items()):
        if not (planets.get(p) and planets[p]["enabled"]):
            live = [l for l, r in m.items() if r["enabled"]]
            if live:
                orphans.append({"base": p, "moons": live})
    # skill wiring: does each moon family's EFFECTIVE prompt name its skill?
    # effective = namespace default_prompt (base) + project prompt (append),
    # per spawn.go buildForemanPrompt — an empty project prompt is wired if the
    # namespace default names the skill.
    nsd = ns_defaults()
    wiring = {}
    for lane, (skill, *_rest) in MOONS.items():
        rows_l = [r for r in allr if r["enabled"] and lane in _lanes_of(r["name"])]
        ref = sum(1 for r in rows_l
                  if skill in (nsd.get(r.get("namespace_id") or "", "") + "\n" + (r["prompt"] or "")))
        wiring[lane] = {"skill": skill, "wired": ref, "lanes": len(rows_l)}
    db_ref = sum(1 for r in allr if r["enabled"] and DUCKBRAIN_CONTRACT in
                 (nsd.get(r.get("namespace_id") or "", "") + "\n" + (r["prompt"] or "")))
    return {"planets": enabled_planets, "gaps": gaps, "orphans": orphans,
            "wiring": wiring, "duckbrain_contract_wired": db_ref,
            "all_rows": allr, "planets_rows": planets, "moons_rows": moons}


def _lanes_of(name):
    return [l for l in LANES if name.endswith("-" + l)]


def build_payload(planet, lane, all_rows):
    """Clone a same-lane sibling row and retarget it at `planet`."""
    skill, wd_t, w, pr, cd = MOONS[lane]
    tmpl = next((r for r in all_rows
                 if r["enabled"] and r["name"].endswith("-" + lane)
                 and r["name"][: -(len(lane) + 1)] != planet
                 and (r["prompt"] or "")), None)
    if not tmpl:
        return None, f"no enabled sibling template for lane '{lane}'"
    src_p = tmpl["name"][: -(len(lane) + 1)]
    out = dict(tmpl)
    out["name"] = f"{planet}-{lane}"
    out["repo_url"] = f"local:/home/kara/{planet}"
    out["workdir"] = wd_t.format(p=planet)
    out["weight"], out["priority"], out["cooldown_s"] = w, pr, cd
    out["cooldown_floor_s"], out["cooldown_ceiling_s"] = cd, cd * 16
    # retarget the prompt: replace the template planet token with this planet
    pr_text = tmpl["prompt"] or ""
    pr_text = pr_text.replace(f"/home/kara/{src_p}", f"/home/kara/{planet}")
    pr_text = pr_text.replace(src_p, planet)
    out["prompt"] = pr_text
    out["prompt_mode"] = "append"
    # SQLite stores these as 0/1 ints; the API's Go structs want real bools.
    for k in ("enabled", "adaptive_cooldown", "no_global_fallback"):
        if k in out:
            out[k] = bool(out[k])
    for k in ("created_at", "updated_at", "last_tick_started", "last_tick_completed",
              "consecutive_failures", "bump_active", "bump_remaining_ticks", "bump_reason",
              "bump_started_at", "disabled_at", "disabled_by", "disabled_reason"):
        out.pop(k, None)
    return out, None


def post_project(payload):
    body = json.dumps(payload).encode()
    req = urllib.request.Request(f"{API}/projects", data=body, method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.status, resp.read().decode()[:300]
    except urllib.error.HTTPError as e:
        # surface the API's validation message — a bare "400" hides the real cause
        raise RuntimeError(f"HTTP {e.code}: {e.read().decode()[:300]}") from None


def resume_project(name):
    """Resume a disabled lane row (the scheduler's own verb — keeps its workdir/reason)."""
    req = urllib.request.Request(f"{API}/projects/{name}/resume", data=b"", method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.status, resp.read().decode()[:200]
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}: {e.read().decode()[:200]}") from None


def moon_workdir_state(row, planet_wd):
    """A satellite can only run if its stand-in workdir exists AND its board is linked
    to the PLANET's live board (resolved from the planet's own workdir — names != paths).
    Returns 'ok' | 'no-board-link' | 'no-planet-board'."""
    src = os.path.join(planet_wd, ".coding-hermes", "board")
    if not os.path.isdir(os.path.realpath(src)):
        return "no-planet-board"
    wd = row["workdir"]
    link = os.path.join(wd, ".coding-hermes", "board")
    if os.path.islink(link) or os.path.isdir(link):
        return "ok"
    return "no-board-link"


def provision_moon(row, planet_wd):
    """Create the moon's workdir and symlink its board to the planet's board."""
    wd = row["workdir"]
    src = os.path.realpath(os.path.join(planet_wd, ".coding-hermes", "board"))
    if not os.path.isdir(src):
        return f"planet board missing: {src}"
    os.makedirs(os.path.join(wd, ".coding-hermes"), exist_ok=True)
    link = os.path.join(wd, ".coding-hermes", "board")
    if not os.path.exists(link):
        os.symlink(src, link)
        return f"linked {link} -> {src}"
    return None


def main():
    a = audit()
    if "--json" in sys.argv:
        print(json.dumps({"planets": a["planets"], "gaps": a["gaps"],
                          "orphans": a["orphans"], "wiring": a["wiring"],
                          "duckbrain_contract_wired": a["duckbrain_contract_wired"]}, indent=1))
        return 0
    print(f"SUN=Hermes   PLANETS(enabled)={len(a['planets'])}   "
          f"MOONS={sum(len(v) for v in a['moons_rows'].values())}\n")
    print(f"COMPLETE planets: {len(a['planets']) - len(a['gaps'])}/{len(a['planets'])}")
    if a["gaps"]:
        print(f"\nMISSING MOONS ({sum(len(g['missing']) for g in a['gaps'])} gaps):")
        for g in a["gaps"]:
            print(f"  {g['planet']:32s} missing: {', '.join(g['missing'])}")
    else:
        print("  none — every planet is complete")
    if a["orphans"]:
        print(f"\nORPHAN MOONS (planet not enabled) — {len(a['orphans'])}, namespace syncs etc.:")
        for o in a["orphans"]:
            print(f"  {o['base']:32s} {', '.join(o['moons'])}")
    print("\nSKILL WIRING (is each moon family's skill named in the live prompt?):")
    for lane, v in a["wiring"].items():
        flag = "OK " if v["wired"] == v["lanes"] else "!! "
        print(f"  {flag}{lane:8s} {v['skill']:32s} {v['wired']}/{v['lanes']} lanes")
    print(f"  {'OK ' if a['duckbrain_contract_wired'] else '!! '}"
          f"{DUCKBRAIN_CONTRACT:32s} {a['duckbrain_contract_wired']} lanes")

    # moon runnability: workdir present + board linked to the planet's live board
    unrunnable = []
    for p in a["planets"]:
        pwd = a["planets_rows"][p]["workdir"]
        for lane, row in (a["moons_rows"].get(p) or {}).items():
            if not row["enabled"]:
                continue
            st = moon_workdir_state(row, pwd)
            if st != "ok":
                unrunnable.append((f"{p}-{lane}", st))
    if unrunnable:
        print(f"\nUNRUNNABLE MOONS ({len(unrunnable)}) — no workdir / board link:")
        for n, st in unrunnable:
            print(f"  {n:34s} {st}")
    else:
        print("\nMoon runnability: all enabled moons have a workdir + linked board")

    if "--apply" in sys.argv:
        dry = "--dry" in sys.argv
        print("\n=== APPLY ===")
        for g in a["gaps"]:
            for lane in g["missing"]:
                ex = (a["moons_rows"].get(g["planet"]) or {}).get(lane)
                if ex:
                    # Row exists but is disabled — RESUME it, never recreate (avoids the
                    # workdir-409 and preserves the row's own workdir/reason).
                    if dry:
                        print(f"  WOULD RESUME {ex['name']:30s} "
                              f"(was: {ex.get('disabled_reason') or 'n/a'})")
                    else:
                        try:
                            st, _ = resume_project(ex["name"])
                            print(f"  RESUMED {ex['name']:30s} HTTP {st}")
                        except Exception as e:
                            print(f"  FAILED RESUME {ex['name']}: {e}")
                    continue
                payload, err = build_payload(g["planet"], lane, a["all_rows"])
                if err:
                    print(f"  SKIP {g['planet']}-{lane}: {err}"); continue
                if dry:
                    print(f"  WOULD CREATE {payload['name']:32s} ns={payload.get('namespace_id')} "
                          f"wd={payload['workdir']}")
                else:
                    try:
                        st, _ = post_project(payload)
                        print(f"  CREATED {payload['name']:32s} HTTP {st}")
                    except Exception as e:
                        if "already registered by enabled project" in str(e):
                            payload["workdir"] = WD_FALLBACK[lane].format(p=g["planet"])
                            try:
                                st, _ = post_project(payload)
                                print(f"  CREATED {payload['name']:32s} HTTP {st} (lane-scoped wd)")
                            except Exception as e2:
                                print(f"  FAILED {payload['name']}: {e2}")
                        else:
                            print(f"  FAILED {payload['name']}: {e}")
        # provision workdirs + board links for any enabled moon that cannot run yet
        print("  --- provisioning ---")
        for p in a["planets"]:
            pwd = a["planets_rows"][p]["workdir"]
            for lane, row in (a["moons_rows"].get(p) or {}).items():
                if not row["enabled"]:
                    continue
                if moon_workdir_state(row, pwd) != "ok":
                    msg = provision_moon(row, pwd)
                    print(f"  {p}-{lane:9s} {msg or 'already provisioned'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""
validate.py — the §7.6 self-gate for a spec-decomposition-matrix-tradeoff artifact.

Reads a design/ tree directly (whatever mix of YAML blocks, markdown tables, and headed
sections the run produced) and exits non-zero on the failure classes §7.6 names. This is the
executable check the skill requires; a reading exercise is not a gate.

Usage:
    python3 validate.py <design-dir>

Exit: 0 = PASS, 1 = FAIL. Output is JSON: status, per-register counts, and the error list.
Stdlib only — no PyYAML, no jsonschema.
"""
import json
import os
import re
import sys

ID_PATTERNS = {
    "decisions": r"D-\d{3}",
    "tradeoffs": r"T-\d{3}",
    "escalations": r"ESC-\d{2}",
    "unknowns": r"U-\d{3}",
    "assumptions": r"A-\d{3}",
    "contradictions": r"C-\d{3}",
    "core_checks": r"core-check-\d{3}",
}

REGISTER_FILES = {
    "decisions": ["03-decisions.md"],
    "tradeoffs": ["06-tradeoff-ledger.md"],
    "escalations": ["07-escalations.md"],
    "unknowns": ["08-open-questions.md"],
    "assumptions": ["09-assumptions.md"],
    "contradictions": ["05-contradictions.md"],
    "core_checks": ["14-core-checks.md", "03-decisions.md", "02-domains"],
}

NULLISH = {"", "null", "none", "~", "n/a", "-"}


def read(path):
    try:
        with open(path, "r", errors="replace") as fh:
            return fh.read()
    except OSError:
        return ""


def scrub(v):
    """Normalize a scalar; 'null'/'none'/'-' and empty containers all mean absent."""
    if v is None:
        return None
    if isinstance(v, (list, tuple, dict)) and len(v) == 0:
        return None
    s = str(v).strip().strip('"').strip("'")
    if s in ("[]", "{}", "()"):
        return None
    return None if s.lower() in NULLISH else s


def norm_key(k):
    return str(k).strip().strip("*`").lower().replace(" ", "_").replace("-", "_")


def as_list(v):
    if v is None:
        return []
    if isinstance(v, list):
        return [x for x in (scrub(i) for i in v) if x]
    s = str(v)
    parts = re.split(r"[,;]", s)
    return [x for x in (scrub(p) for p in parts) if x]


def parse_yaml_blocks(text):
    """Pull flat `key: value` rows from ```yaml blocks. Shallow by design."""
    rows = []
    for block in re.findall(r"```(?:yaml|yml)\s*\n(.*?)```", text, re.S):
        row, cur = {}, None
        for raw in block.splitlines():
            line = raw.rstrip()
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*):\s*(.*)$", line)
            if m:
                key, val = m.group(1), val_clean(m.group(2))
                if key not in row:
                    row[key] = [] if val is None else val
                cur = key if val is None else None
                continue
            m2 = re.match(r"^\s*-\s*(.+)$", line)
            if m2 and cur:
                if not isinstance(row.get(cur), list):
                    row[cur] = []
                item = scrub(m2.group(1))
                if item:
                    row[cur].append(item)
        if row:
            rows.append(row)
    return rows


def val_clean(v):
    v = v.strip()
    if v == "":
        return None
    if v.startswith("[") and v.endswith("]"):
        inner = v[1:-1].strip()
        return [x for x in (scrub(i) for i in inner.split(",")) if x]
    return scrub(v)


def parse_md_tables(text):
    """Every markdown table in the text, as dicts with normalized lowercase keys."""
    rows, header = [], None
    for line in text.splitlines():
        s = line.strip()
        if not s.startswith("|"):
            header = None
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if header is None:
            header = [norm_key(c) for c in cells]
            continue
        if all(set(c) <= set("-: ") for c in cells):
            continue
        if len(cells) == len(header):
            rows.append({k: scrub(v) for k, v in zip(header, cells)})
        elif header and len(cells) > len(header):
            # a cell contained a literal '|' — keep the first N-1 columns aligned
            rows.append({k: scrub(v) for k, v in zip(header, cells[:len(header)])})
    return rows


def parse_escalation_headings(text):
    """Escalations in this skill are prose envelopes under `## ESC-nn` headings."""
    rows = []
    for block in re.split(r"\n(?=##\s)", text):
        m = re.search(r"^##\s+(ESC-\d{2})\b", block)
        if not m:
            continue
        eid = m.group(1)
        opts = re.findall(r"^\s*(?:-\s*)?Option ([A-Z])\s*[—-]", block, re.M)
        has_default = bool(re.search(r"if unanswered by|no-answer default|proceed with", block, re.I))
        opt_lines = re.findall(r"^\s*(?:-\s*)?Option [A-Z]\s*[—-].*$", block, re.M)
        rows.append({
            "id": eid,
            "options": sorted(set(opts)),
            "option_lines": opt_lines,
            "default_if_unanswered": "yes" if has_default else None,
        })
    return rows


def main():
    if len(sys.argv) != 2:
        print("usage: validate.py <design-dir>", file=sys.stderr)
        return 2
    base = sys.argv[1]
    if not os.path.isdir(base):
        print(json.dumps({"status": "FAIL", "errors": [f"not a directory: {base}"]}, indent=2))
        return 1
    errors = []

    for f in ("00-seed.md", "01-scope.md", "03-decisions.md", "04-break-report.md",
              "06-tradeoff-ledger.md", "07-escalations.md", "08-open-questions.md",
              "_index.md"):
        if not os.path.exists(os.path.join(base, f)):
            errors.append(f"missing required register file: {f}")

    index_text = read(os.path.join(base, "_index.md"))

    def gather(reg):
        out = []
        for f in REGISTER_FILES[reg]:
            p = os.path.join(base, f)
            if os.path.isdir(p):
                for fn in sorted(os.listdir(p)):
                    if fn.endswith(".md"):
                        out.append((fn, read(os.path.join(p, fn))))
                continue
            out.append((f, read(p)))
        return out

    # ---- build each register from all of its possible carriers ------------
    def rows_from(reg, key="id", extra_parsers=()):
        pat = re.compile("^" + ID_PATTERNS[reg] + "$")
        found = []
        for fname, txt in gather(reg):
            cands = parse_yaml_blocks(txt) + parse_md_tables(txt)
            for p in extra_parsers:
                cands += p(txt)
            for r in cands:
                rid = scrub(r.get(key)) or scrub(r.get("id"))
                if rid and pat.match(rid):
                    r = dict(r)
                    r["__src"] = fname
                    r["id"] = rid
                    found.append(r)
        # de-duplicate by id, preferring the row carrying the most fields
        best = {}
        for r in found:
            prev = best.get(r["id"])
            if prev is None or len(r) > len(prev):
                best[r["id"]] = r
        return list(best.values())

    reg_rows = {}
    for reg in ID_PATTERNS:
        extra = (lambda t: parse_escalation_headings(t),) if reg == "escalations" else ()
        reg_rows[reg] = rows_from(reg, extra_parsers=extra)

    decisions = {r["id"]: r for r in reg_rows["decisions"]}
    a_ids = {r["id"] for r in reg_rows["assumptions"]}
    c_ids = {r["id"] for r in reg_rows["contradictions"]}
    e_ids = {r["id"] for r in reg_rows["escalations"]}
    core_ids = {r["id"] for r in reg_rows["core_checks"]}
    core_ids |= {scrub(d.get("core_check")) for d in decisions.values()} - {None}

    # ---- id collisions across registers ----------------------------------
    seen = {}
    for reg, rows in reg_rows.items():
        for r in rows:
            if r["id"] in seen and seen[r["id"]] != reg:
                errors.append(f"duplicate id {r['id']} in {seen[r['id']]} and {reg}")
            seen[r["id"]] = reg

    # ---- decision quality -------------------------------------------------
    for did, d in sorted(decisions.items()):
        if len(as_list(d.get("alternatives_considered"))) < 2:
            errors.append(f"{did} fewer than 2 alternatives_considered")
        brk = d.get("breaks")
        items = brk if isinstance(brk, (list, str)) else []
        items = [items] if isinstance(items, str) else items
        items = [i for i in (scrub(i) for i in items) if i]
        if not items:
            errors.append(f"{did} missing breaks")
        for b in items:
            if re.match(r"^\s*none\b", str(b), re.I) and "checked against" not in str(b).lower():
                errors.append(f"{did} breaks 'none' without a checked-against list")
        if "depends_on" not in d:
            errors.append(f"{did} missing depends_on field")
        for x in as_list(d.get("depends_on")):
            if x not in decisions:
                errors.append(f"{did} dangling depends_on {x}")
        for x in as_list(d.get("assumptions")):
            if x not in a_ids:
                errors.append(f"{did} dangling assumption {x}")
        for x in as_list(d.get("contradicts")):
            if x not in c_ids:
                errors.append(f"{did} dangling contradiction {x}")
        cc = scrub(d.get("core_check"))
        if not cc:
            errors.append(f"{did} missing core_check")
        elif cc not in core_ids:
            errors.append(f"{did} dangling core_check {cc}")
        if not scrub(d.get("reversal_cost")):
            errors.append(f"{did} missing reversal_cost")
        # §7.6 names supersedes/superseded_by among the dangling references the gate checks
        for fld in ("supersedes", "superseded_by"):
            for x in as_list(d.get(fld)):
                if x not in decisions:
                    errors.append(f"{did} dangling {fld} {x}")

    # ---- tradeoffs --------------------------------------------------------
    for r in sorted(reg_rows["tradeoffs"], key=lambda x: x["id"]):
        esc = scrub(r.get("escalation_id"))
        if esc and esc not in e_ids:
            errors.append(f"{r['id']} dangling escalation_id {esc}")

    # ---- escalations ------------------------------------------------------
    for r in sorted(reg_rows["escalations"], key=lambda x: x["id"]):
        opts = r.get("options")
        if isinstance(opts, list) and len(opts) < 2:
            errors.append(f"{r['id']} fewer than 2 options")
        if not scrub(r.get("default_if_unanswered")):
            errors.append(f"{r['id']} missing a no-answer default")
        # §6.5: options are "attached with costs" — an option with no cost is a bare
        # opinion, and §7.6 names costs explicitly. Count cost-bearing option lines.
        opt_lines = r.get("option_lines")
        if opt_lines and len(opt_lines) != len(r.get("options") or []):
            pass  # parser could not pair them; do not guess
        if opt_lines is not None and opt_lines and opts:
            priced = sum(1 for ln in opt_lines if re.search(r"\bcosts?\b", ln, re.I))
            if priced < len(opt_lines):
                errors.append(f"{r['id']} has {len(opt_lines)-priced} option(s) with no stated costs")

    # ---- unknowns ---------------------------------------------------------
    for r in sorted(reg_rows["unknowns"], key=lambda x: x["id"]):
        for k in ("owner", "deadline_or_trigger", "containment_default"):
            if not scrub(r.get(k)):
                errors.append(f"{r['id']} missing {k}")
        for x in as_list(r.get("decisions_affected")):
            if x not in decisions:
                errors.append(f"{r['id']} dangling decisions_affected {x}")

    # ---- contradictions ---------------------------------------------------
    for r in sorted(reg_rows["contradictions"], key=lambda x: x["id"]):
        # §5.6: parties are whatever is in conflict — decision, escalation, or assumption ids
        for x in as_list(r.get("parties")):
            if x not in decisions and x not in e_ids and x not in a_ids:
                errors.append(f"{r['id']} dangling party {x}")
        status = (scrub(r.get("status")) or "OPEN").upper()
        if status != "OPEN":
            if not scrub(r.get("resolution")) or not scrub(r.get("resolved_date_or_trigger")):
                errors.append(f"{r['id']} status={status} without resolution + resolved_date_or_trigger")
        else:
            if r["id"] not in index_text:
                errors.append(f"{r['id']} is OPEN but absent from _index.md")

    # ---- invariant -> test map -------------------------------------------
    map_text = read(os.path.join(base, "15-invariant-test-map.md")) + "\n" + \
        read(os.path.join(base, "03-decisions.md"))
    mapped = set()
    for row in parse_md_tables(map_text):
        for v in row.values():
            if v and re.match(r"^D-\d{3}$", str(v)):
                mapped.add(str(v))
    for did, d in sorted(decisions.items()):
        if (scrub(d.get("classification")) or "").upper() == "BEFORE-BUILD" and did not in mapped:
            errors.append(f"{did} is BEFORE-BUILD but absent from the invariant->test map")

    # ---- domain coverage --------------------------------------------------
    ddir = os.path.join(base, "02-domains")
    files = sorted(f for f in os.listdir(ddir) if f.endswith(".md")) if os.path.isdir(ddir) else []
    # Domain files are `4.NN-<slug>.md`. Normalise an unpadded `4.N` spelling to the same
    # key rather than failing it: the skill's own section headings read `4.5` while filenames
    # are padded, so a run that copies the heading form has still produced that domain, and
    # failing it on padding would be a false positive. The gate fails on substance — a domain
    # with no file at all — not on a format variant the skill itself models.
    nums = set()
    for f in files:
        m = re.match(r"^4\.(\d{1,2})[-.]", f)
        if m:
            nums.add(f"4.{int(m.group(1)):02d}")
    expected = {f"4.{i:02d}" for i in range(1, 45)}
    missing = sorted(expected - nums)
    if missing:
        errors.append(f"domain coverage missing: {missing}")
    for f in files:
        txt = read(os.path.join(ddir, f))
        # §7.6: a branch terminating below its floor must carry a fixed-point-below-floor
        # record. Only enforced when both numbers are machine-readably present — the skill
        # allows a prose header, so an unparseable file is skipped rather than failed.
        fl = re.search(r"ring_floor\s*[:=]\s*(\d+)", txt) or re.search(r"floor\s+(\d+)", txt)
        tr = re.search(r"terminating_ring\s*[:=]\s*(\d+)", txt) or \
             re.search(r"terminating ring\s+(\d+)", txt)
        if fl and tr and int(tr.group(1)) < int(fl.group(1)):
            if "fixed-point-below-floor" not in txt:
                errors.append(f"{f}: terminated at ring {tr.group(1)} below floor "
                              f"{fl.group(1)} without a fixed-point-below-floor record")
        # a domain is NOT-REACHED only when it says so in its own status line — a mention
        # of some OTHER domain being not-reached is not a status (that bug flagged every
        # cascaded file that referenced a skipped neighbour)
        status_not_reached = re.search(
            r"^\s*(?:status\s*[:=]\s*)?\**NOT-REACHED\**\s*$|^\s*status\s*[:=]\s*\**NOT-REACHED",
            txt, re.M | re.I)
        if status_not_reached:
            low = txt.lower()
            for k in ("reason", "owner", "trigger", "containment_default"):
                if k not in low:
                    errors.append(f"{f}: NOT-REACHED without {k}")

    # ---- single-writer rule (§7.0) ---------------------------------------
    run_p = os.path.join(base, "run.json")
    if os.path.exists(run_p):
        try:
            run = json.loads(read(run_p))
            writers = run.get("writers") or []
            if len(writers) > 1:
                errors.append(f"run.json lists {len(writers)} writers — §7.0 requires exactly one")
        except ValueError:
            errors.append("run.json is not valid JSON")

    counts = {reg: len(rows) for reg, rows in reg_rows.items()}
    counts["domain_files"] = len(files)
    print(json.dumps({"status": "PASS" if not errors else "FAIL",
                      "counts": counts, "errors": errors}, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())

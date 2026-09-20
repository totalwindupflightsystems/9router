# Dogfood run — executing the skill for real (2026-09-20)

The skill was executed by two independent seats (GPT-5.6-sol, Kimi-K3) on one bounded
scratch seed, each writing a genuine artifact. Both completed. Between them they found 13
real gaps, one of which was a defect: the §7.6 gate was unsatisfiable when §7.1 was followed
to the letter. All 13 were verified against the raw skill and fixed.

## The seed they were given

> "I keep ending up with half-built internal tools where the pieces don't fit. I want one
> small command-line tool that watches a set of directories for new files, keeps a record of
> what it has seen, and once an hour posts a short digest of what changed. It should run on
> one small Linux box, survive a reboot, and tell me when it has stopped working. I don't
> want to lose anything if it crashes mid-run. Keep it simple — I'd rather have one box and
> no extra services than a distributed system."

## What the run proved (the three claims the run existed to test)

- **The cascade grammar generates.** Both seats reached a fixed point with the closing ring's
  candidate questions re-derived and shown to be duplicate signatures. One seat: 9 domains
  cascaded, all closing at ring 5; the other: 7 domains terminated by fixed point.
- **The break-check modifies.** 8 decisions modified on one seat. Four of the other seat's
  modifications trace to a measurement, not an opinion: 3 paths on 1 inode forced the key to
  a 3-tuple; 99.7% partial reads killed the size-stability poll; an absent MTA forced the
  delivery seam; 99.8% inode reuse forced whole-pass retirement.
- **The owner stayed out of the questionnaire seat.** 18 unknowns / 18 owners / 0 research
  requests, 3 escalations all carrying a default and a named risk. The agent answered its own
  questions, which is the whole design.

## Findings (all 13, all fixed)

1. **DEFECT — the gate was unsatisfiable.** §7.6 fails an artifact with no core-check rows and
   no invariant→test map, but §7.1 allocated a file to neither. Fixed: `14-core-checks.md`,
   `15-invariant-test-map.md`, with the absent-vs-empty distinction stated.
2. Thin-domain ring-2 closes satisfied none of the floor rule's three branches. Fixed with an
   explicit score≤6 exemption.
3. The pair walk (n(n−1)/2 — 190 pairs at n=20) competed with the domains for one clock, with
   no precedence. Fixed: enumerate fully, run in blast-radius order, record
   `pair-walk-partial` on exhaustion.
4. **Cost real work** — no single-writer rule. Five register files plus two domain files were
   clobbered mid-run by the peer writer. Fixed: §7.0.
5. `breaks` was one prose string, so §7.6's check was a regex over English. Fixed: structured
   fields.
6. The modification rule was ambiguous between pair-level and pass-level. Fixed: pass-level,
   stated.
7. `core-check-\d+` admitted both `core-check-1` and `core-check-001` — two registers merged
   with no collision detected (it happened). Fixed: fixed-width padding.
8. No id namespace for §4's required outputs, so cross-reference integrity could not see
   tables, runbooks, or invariants at all. Fixed: DD/SC/IX/IF/PT/LB/IN/FM/RB/AL/IV.
9. §3.4's signature test needed §4.5's data dictionary, which the §4.5 cascade produces — a
   circular dependency inside one stage. Fixed: ordering rule (sign off the seed's nouns,
   re-sign on rename).
10. §3.1 was labelled "the generator" but is the classifier; the generators are §3.2/§3.3/§4.
11. §10.2's supersession machinery is untestable on a greenfield run and nothing said so.
12. §7.6 required `matrix.schema.json` with no template shipping. Fixed: a starter schema.
13. No budget-thin marker for a clear seed on a short clock. Fixed beside `seed-thin`.

## Honesty note worth keeping

One seat's crash-safety prototype printed `LOST=25` on its first run because of a bug in its
own probe (a 3-column select coerced into a 2-tuple); the corrected version measured 0 lost
events across 8 SIGKILLs. Both runs were logged and the bug stated in the artifact rather
than quietly dropped. That is the anti-gaming rule holding under real conditions — which is
the behavior this skill is supposed to produce in its executor.

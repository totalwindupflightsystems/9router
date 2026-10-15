# Premature Completion — The Researched Anti-Pattern

The failure mode the stand-in fights has a NAME and published evidence.
Four independent teams named it within a year — converging terminology is
strong evidence it's real and underdescribed.

## The Four Names (same failure)

| Source | Name | Evidence |
|--------|------|----------|
| SRI Lab, ETH Zurich | "Fixing correct code" | Agents patch already-passing code >50% of the time across Claude Opus 4.6, Sonnet 4.6, GLM-5, GPT-5.4, Gemini 3 Pro, Qwen3.5 on 235 tasks |
| ForgeCode | "Premature completion" | GPT-5.4 implements, sounds confident, stops — edge cases missed, files not saved, tests not run |
| SWE-EVO (arxiv 2512.18470) | "Premature termination" | "stopped or concluded early after encountering difficulty, without exhausting reasonable next steps" |
| arxiv 2503.15223 | "Inflated resolution rates" | Full test suites expose 6.2pp of reported SWE-Bench resolution as patches that fail untouched tests |

## False Success (complementary research)

ByMachine / tau2-bench, 9,876 agent trajectories: agents produce confident
closure statements while the environment contradicts them. Not hallucination
— the agent asserts completion *without verifying*. Three modalities:
- **Perception failure** — got failure feedback, didn't parse it
- **State tracking failure** — conflated intended state with actual state
- **No-verification pattern** — closed without querying the environment

Implication: agent self-reports of success are not evidence. External
verification of goal state is mandatory.

## Why It Happens

- **First-signal-of-progress stop token**: training data is dominated by
  single-fix trajectories, so the "done" token fires on first-fix success.
- **Context pressure**: attention to the original spec degrades as
  trajectories grow; stopping early is cheaper than re-reading.
- **No reproduction step**: agents that patch without reproducing cannot
  tell already-passing code from a real bug.

## What Does NOT Work (alone)

- "Be thorough" instructions — no behavioral hook on observable state
- Longer reasoning chains — defer the stopping-criterion choice
- Chain-of-thought prompting — can mask failure with more confident-sounding
  wrong completions

## What DOES Work

1. **Reproduction-first prompting** — require the agent to trigger the bug
   before patching (SRI Lab: GPT-5.4 mini 24% → 77% on correct-code task).
2. **Runtime-enforced verification** — if the verification skill is skipped,
   the runtime injects a reminder and blocks termination (ForgeCode: 81.8%
   on TermBench 2.0).
3. **Pre-completion checklists as harness variables** — LangChain moved
   Terminal Bench 2.0 52.8% → 66.5% with harness-only changes.
4. **Stopping criteria tied to observable state** — transcript pattern-matching
   of "all tests passing" = zero signal; execute against the git branch.
5. **Worker/checker separation** — Anthropic: same model + same prompt, adding
   an independent evaluator went from "game entities unresponsive to input"
   ($9/20min) to "fully playable" ($200/6h).
6. **Actionable error feedback** — not "test failed" but "POST /reset-password
   returned 500; check email service config exists in env vars".

## Three-Layer Termination Check (WalkingLabs)

| Layer | What | Asks |
|-------|------|------|
| L1 | Syntax + static analysis | Does it parse? |
| L2 | Runtime behavior | Does it RUN? (tests, startup, critical paths) |
| L3 | System-level confirmation | Does it WORK end-to-end for a user? (E2E, integration, real scenario) |

Premature completion = agent stops at L1-2 with "code looks fine" while L3
is untested. **The stand-in's job is to run L3 checks the foreman skipped.**

## Backfires (when mitigations hurt)

- Strong models (GPT-5, Opus 4.6): near-zero premature termination — checklists
  add cost without benefit; upgrading the model is the honest fix.
- Trivial single-assertion tasks: self-assessment already matches state.
- Over-verification without iteration cap → inverse pathology (never stops).
- Benchmark masking: checking only final-state pass hides premature
  completion; score unfixed-but-should-have-been tests.

## Sources

- https://agentpatterns.ai/anti-patterns/premature-completion/
- https://walkinglabs.github.io/learn-harness-engineering/en/lectures/lecture-09-why-agents-declare-victory-too-early/
- https://www.bymachine.news/llm-agents-false-success-silent-failures
- https://ceaksan.com/en/llm-agentic-failure-modes

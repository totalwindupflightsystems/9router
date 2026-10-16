# GITREINS-JUDGE-001 — Monitoring judge target verdict

Status: Keep the monitoring lane eligible for Tier 2 judging. Do not exclude it as a non-code lane. Do not treat the 2026-10-03 verdict under `/home/kara/fleet-monitoring` as evidence for the monitoring scheduler workdir.

## Findings

1. `/home/kara/monitoring` is not an independent Git repository. `git -C /home/kara/monitoring rev-parse --show-toplevel` returns `/home/kara`, and `--show-prefix` returns `monitoring/`. The scheduler's workdir is a subdirectory of the HOME repository. The appropriate canonical GitReins workdir for a CLI invocation there is therefore `/home/kara`, not `/home/kara/monitoring` and not `/home/kara/fleet-monitoring`.

2. No `.gitreins/config.yaml` exists at `/home/kara/monitoring`, `/home/kara`, or `/home/kara/fleet-monitoring`. GitReins 0.16.0's installed `get_workdir()` uses `git rev-parse --show-toplevel`; `load_config(workdir)` reads only `<workdir>/.gitreins/config.yaml` and returns an empty config if absent. The installed `engine/llm.py` resolves the judge model as an explicit model, then `GITREINS_LLM_MODEL`, then the built-in default. Thus an ambient model is sufficient for selecting the Tier 2 model; it does not require a per-directory `.gitreins/config.yaml`. In this worker's environment, `GITREINS_LLM_MODEL=deepseek-v4-flash` and `GITREINS_LLM_BASE_URL=https://api.deepseek.com/v1` are present (no API-key value recorded).

   This does not make the missing config irrelevant to every GitReins surface: `gitreins guard` explicitly requires `.gitreins/config.yaml` and refuses to run without it. The environment-only finding applies to the judge's LLM selection, not to guard policy/configuration. Do not add a repo-root config solely to silence a path-specific audit without deciding whether HOME-wide guard behavior is intended.

3. The monitoring subtree is not docs/config-only. Its tracked inventory includes Python scripts, shell scripts, YAML, JSON, Alloy configuration, and documentation (including `scripts/disk-guard.py`, `scripts/disk-metrics-textfile.py`, `fleet-monitoring/stack/alert-router/router.py`, and corresponding tests). The scheduler prompt also assigns operational triage, health/watchdog/CVE checks and board handling. Therefore a blanket non-code exclusion is unsupported.

## Verdict and follow-up

The previous resolution is not target-valid: its recorded verdicts are in `/home/kara/fleet-monitoring/.gitreins/history/2026-10-03/...`, while the monitoring lane resolves to the distinct Git root `/home/kara`. It must not satisfy a recency check for this lane.

Keep the lane in the judge population. Have the supervisor audit resolve the configured workdir with Git's repository root before checking config or verdict history, and evaluate recent Tier 2 activity only in that canonical root. An ambient `GITREINS_LLM_MODEL` can support judging without a config file, but a recent verdict in the correct root still needs to be observed before marking the audit resolved. If the audit requires a repo config for guard setup, that is a separate HOME-repository configuration decision; it is not a reason to classify monitoring as non-code.

## Evidence boundary

Read-only checks in the GITREINS-JUDGE-001 worktree confirmed the Git roots, absence of the three candidate config files, the installed GitReins resolution paths, and the tracked monitoring file types. No config, supervisor script, or board/state file was changed, and no judge run was launched; this note is a target/configuration verdict, not a claim that a new Tier 2 verdict has been produced.

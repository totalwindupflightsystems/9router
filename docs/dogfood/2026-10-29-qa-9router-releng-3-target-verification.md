# QA-9ROUTER-RELENG-3 — dispatch target verification

Status: blocked on external dispatch configuration. The battery was not run.

## Acceptance probes

Command:

```sh
git -C /home/kara/9router rev-parse --show-toplevel
```

Observed output: `/home/kara/9router` (exit 0). The product checkout satisfies the first acceptance condition.

Command:

```sh
git -C /home/kara/.hermes/stand-in/releng-lane/9router rev-parse --show-toplevel 2>/dev/null || echo ABSENT
```

Observed output: `/home/kara` (exit 0). This fails the second acceptance condition and reproduces the parent-repository launch refusal. No battery tests were executed by these probes.

## Repository-local scope check

The repository's tracked-file inventory and tracked-content search found no `BUNKER_QA_SUBDIR` setting or releng-lane dispatch target/script to repair. The task record itself is present in `.coding-hermes/board/tasks.jsonl` and `.gitreins/tasks.yaml`; neither defines the external launch path. The checked-out product root is `/home/kara/9router`, distinct from the external stand-in path whose Git root is `/home/kara`.

Therefore, changing application code or product documentation cannot make the external path satisfy this acceptance. The external owner/configuration must re-point the releng dispatch target to `/home/kara/9router`, or provision a separate 9router checkout/worktree whose `git rev-parse --show-toplevel` is not `/home/kara`. If that external launcher intentionally dispatches a subdirectory of a parent checkout, its owner must set the supported `BUNKER_QA_SUBDIR` in that launch configuration to the correct product subdirectory. This worker did not change that configuration, create/remove the stand-in target, or run the battery.

## Close-out

Leave QA-9ROUTER-RELENG-3 pending. Do not treat the launch refusal as a product pass or failure: the fresh-system battery remains unverified. After the external target/configuration is corrected, rerun both exact acceptance probes before launching the battery.

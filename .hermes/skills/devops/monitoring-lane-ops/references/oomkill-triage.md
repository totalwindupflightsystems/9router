# OOMKills alert triage (scope attribution + memory-pressure split)

**Triage OOMKills alerts by kill SCOPE before hunting a host problem.** The kernel log line gives
  it: `constraint=CONSTRAINT_MEMCG,oom_memcg=/some-cgroup` scoped to a test/CI cgroup is the
  project's own regression suite intentionally killing test processes — benign. Corroborate fast:
  `cat /sys/fs/cgroup/<memcg>/memory.events` (oom_kill counter vs the global `grep oom_kill /proc/vmstat`)
  plus `free -g`. The memcg dir may ALREADY BE DELETED when you check — ephemeral test cgroups are torn down after each CI run — then attribute by run activity instead: empty crontab/systemd timers plus a CI-runner process (actions-runner / Runner.Worker) live between the kill timestamps is the benign signature; say the cgroup was ephemeral in the close note. If no runner matches either, attribute from the DOCKERD journal at the kill timestamp: `sbJoin ... net=<name>` lines name the ephemeral containers' compose network, and grepping the host's project source trees for the exact victim command from the kernel line (`task=dd ... dd if=/dev/zero bs=32M`) finds the OOM self-test primitive that spawned it — a hit in a `selftest`/`live_test` file proves the kill was intentional by design and closes the alert as a benign self-test. Only constraint=GLOBAL kills (or a memcg serving a real service) are host problems.
  A benign alert keeps firing (and spools a DUPLICATE row per evaluation) until the RULE learns the
  scope — the fix is in the rule, not the row. When re-triaging a fresh fingerprint of the same
  host, identify the kill CLASS first from one grep of the kernel log (constraint + memcg) and
  attribute it to the existing triage instead of re-deriving from scratch: a memcg cgroup-test
  kill class already verified once makes every new fingerprint of the same class a fast
  re-verification (kernel-log grep as witness), not a new investigation. The proven fix is a MEMORY-PRESSURE SPLIT: a real
  host OOM only happens when the host is actually out of memory, so gate the critical on kills AND
  `node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes < 0.15`, and add a warning twin
  (`OOMKillsLowPressure`) for kills with >=15% MemAvailable whose annotation self-describes the
  scope-check (`dmesg -T | grep oom-kill` — if constraint=CONSTRAINT_MEMCG under an expected test
  cgroup, benign). Never silence the GLOBAL-kill path. Gate the split LIVE: after reload, the
  previously-firing critical must go inactive while the CI suite is still killing — "0 active
  alerts with kills in progress" is the benign-case proof; a real host-OOM firing was validated by
  rule logic + promtool only, say so as UNVERIFIED in the report.

# Probe attribution — is the failure the product's, the host's, or your probe's?

Rules for attributing a failure observed during a dogfood real-use pass. The
SKILL.md pitfall list carries the always-on version; this file collects the
store/host attribution traps.

## Attribute the DB port before filing schema drift from a boot failure

A product configured for `localhost:5432` is NOT necessarily talking to the store
you think. A dev host runs a SYSTEM postgres on the default port alongside the
project's own compose DB on a per-project port — a boot test with default settings
hits the system instance, whose schema can be months stale or belong to a different
product entirely, and a missing-column error then reads as migration drift that does
not exist.

Before filing schema-drift findings:

    docker ps --format '{{.Names}} {{.Ports}}'   # find the project's own DB container
    ss -tlnp | grep 5432                          # who owns the default port

Then re-run the boot against the product's compose DB with credentials from its
compose file. A schema that is current there is a probe error, not a finding — and
the corrected probe (and the wrong first target) belongs in the report, because the
next agent will make the same mistake.

## Same attribution discipline, other stores

The same trap generalizes: any default-port dependency (redis 6379, rabbit 5672,
object stores on :9000) can resolve to a host-global service instead of the
project's. `ss -tlnp` first, then the product's compose/config, THEN interpret the
error. An error that changes (or vanishes) when pointed at the right store is
attribution evidence, never a product defect.

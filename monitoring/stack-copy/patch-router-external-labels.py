#!/usr/bin/env python3
"""Drop Alertmanager-injected external labels from the router's PROM state-check selector.

prom_label_matchers() builds ALERTS{...} from the webhook labels. Alertmanager adds
its external_labels (monitor="fleet-monitoring") to every alert it forwards, but those
labels exist ONLY on the Alertmanager side - Prometheus's own ALERTS series never carry
them. The monitor matcher therefore makes every state-check query match nothing,
prom_alert_firing() returns False, and every firing alert is 'pre-resolved' into a
spool fan-out row instead of landing on its board as pending. 47 pre-resolutions/48h,
0 spooled rows. Fix: drop label keys that Alertmanager injects (monitor, and a
defensive external-label blocklist) from the selector.
"""
import re
import sys

OLD = '''def prom_label_matchers(labels):
    """PromQL selector for an alert's labels, minus `alertstate`.

    `alertstate` is what the caller is asking about, so it must not be part of the
    selector the caller builds. Values are escaped the way PromQL string literals want
    (backslash, double quote, newline), so a label carrying a quote can never break the
    query into something else. A label NAME that is not a bare PromQL identifier is
    dropped rather than smuggled into the selector.
    """
    parts = []
    for key in sorted(labels or {}):
        value = labels[key]
        if key == "alertstate" or value is None or value == "":
            continue'''

NEW = '''# Labels Alertmanager injects from its own config (external_labels / identity),
# which NEVER exist on Prometheus's local ALERTS series. Matching on any of them
# makes the state-check query match nothing -> every firing alert reads as
# "not firing" and gets pre-resolved instead of landing on its board (seen live
# 2026-10-07: 47 pre-resolutions in 48h, 0 spooled rows, while TargetUnreachable
# on standby-cx53-01-2147 was firing the whole time).
AM_EXTERNAL_LABELS = frozenset({
    "monitor",
})


def prom_label_matchers(labels):
    """PromQL selector for an alert's labels, minus `alertstate`.

    `alertstate` is what the caller is asking about, so it must not be part of the
    selector the caller builds. Values are escaped the way PromQL string literals want
    (backslash, double quote, newline), so a label carrying a quote can never break the
    query into something else. A label NAME that is not a bare PromQL identifier is
    dropped rather than smuggled into the selector.
    """
    parts = []
    for key in sorted(labels or {}):
        value = labels[key]
        if key == "alertstate" or key in AM_EXTERNAL_LABELS or value is None or value == "":
            continue'''

path = sys.argv[1]
src = open(path).read()
if src.count(OLD) != 1:
    print("FAIL: expected exactly 1 match of OLD block in %s, got %d" % (path, src.count(OLD)))
    sys.exit(1)
open(path, "w").write(src.replace(OLD, NEW))
check = open(path).read()
assert "AM_EXTERNAL_LABELS" in check and "key in AM_EXTERNAL_LABELS" in check
print("OK: patched %s" % path)

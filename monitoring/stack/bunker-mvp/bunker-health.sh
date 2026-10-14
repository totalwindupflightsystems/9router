#!/bin/bash
# bunker health textfile exporter: logind liveness + spawn-failure window (MON-MONITORING-LOGIND-20261014)
OUT=/var/lib/node_exporter/textfile/bunker_health.prom
TMP=$OUT.tmp
HOST=$(hostname -s)
LOGIND_UP=1
if ! timeout 10 busctl introspect org.freedesktop.login1 /org/freedesktop/login1 org.freedesktop.login1.Manager >/dev/null 2>&1; then
  LOGIND_UP=0
fi
FAILS=$(journalctl -u bunkerd --since "30 min ago" 2>/dev/null | grep -cE "enable linger|spawn agent failed|spawn failed")
LFRSS=$(systemctl show systemd-logind -p ActiveEnterTimestampMonotonic --value 2>/dev/null)
{
  echo "# HELP bunker_logind_up 1 if systemd-logind D-Bus Manager introspection succeeded"
  echo "# TYPE bunker_logind_up gauge"
  echo "bunker_logind_up{host=\"$HOST\"} $LOGIND_UP"
  echo "# HELP bunker_spawn_failures_30m spawn/linger failure lines in bunkerd journal last 30m"
  echo "# TYPE bunker_spawn_failures_30m gauge"
  echo "bunker_spawn_failures_30m{host=\"$HOST\"} $FAILS"
} > "$TMP"
mv "$TMP" "$OUT"

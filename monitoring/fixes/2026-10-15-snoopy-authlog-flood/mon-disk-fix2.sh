#!/bin/bash
# finish: HUP rsyslogd, empty oversized auth.log, verify
sudo pkill -HUP rsyslogd
sleep 1
sudo truncate -s 0 /var/log/auth.log
df -h /
ls -lh /var/log/snoopy.log 2>/dev/null || echo "snoopy.log not yet created"
tail -1 /var/log/auth.log
sudo tail -1 /var/log/snoopy.log 2>/dev/null

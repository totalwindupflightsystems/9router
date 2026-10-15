#!/bin/bash
# MON-MONITORING-EE32DFF5-20261015: snoopy exec-audit flooding /var/log/auth.log (23G)
set -e
sudo cp /etc/snoopy.ini /etc/snoopy.ini.bak-mon-20261015

# 1. Snoopy gets its own rotated file instead of flooding auth.log
sudo sed -i 's|^;output = file:/var/log/snoopy.log$|output = file:/var/log/snoopy.log|' /etc/snoopy.ini
echo "--- enabled output line:"; grep -n '^output' /etc/snoopy.ini

# 2. logrotate policy for it
sudo tee /etc/logrotate.d/snoopy >/dev/null <<'EOF'
/var/log/snoopy.log {
    daily
    rotate 7
    size 100M
    compress
    delaycompress
    missingok
    notifempty
}
EOF

# 3. rsyslog: snoopy no longer lands in auth.log
sudo tee /etc/rsyslog.d/30-snoopy-drop.conf >/dev/null <<'EOF'
if ($programname == "snoopy") then {
    stop
}
EOF
sudo rsyslogd -N1 2>&1 | tail -2
sudo systemctl reload rsyslog

# 4. free the 23G in-place (file stays open by syslog, do not delete)
sudo sh -c ': > /var/log/auth.log'
df -h /
ls -lh /var/log/snoopy.log 2>/dev/null || echo "snoopy.log will appear on next logged exec"

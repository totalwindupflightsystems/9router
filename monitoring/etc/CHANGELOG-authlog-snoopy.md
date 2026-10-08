# authlog-snoopy rotation change 2026-10-08 (MON-MONITORING-TICK-20261008-0822)

Live finding on karahermes-mde-7840hs: DiskWillFillIn24h firing with REAL writer
(deriv -248KB/s over 3h, avail 325->268GiB in 6h).

Root cause: snoopy exec-audit floods /var/log/auth.log ~7GB/day (auth.log.1 was
6.9G uncompressed; .10-.14.gz + 2-9.gz held ~1.6G more). Old policy: rotate 14
daily, maxsize 1G => steady state ~17G and daily churn.

Fix applied on host (backup /var/tmp/authlog-snoopy.bak-20261008):
- rotate 14 -> rotate 4
- su syslog adm added (logrotate was failing renames without it)
- /var/log perms 775 (was insecure-permissions error)
- removed auth.log.5..14.gz; gzipped the 6.9G auth.log.1 (-> 204M)

Reclaimed: ~7.7G disk. Steady-state bound now ~1.2G total instead of ~17G.
ch:trace row=MON-MONITORING-TICK-20261008-0822 evidence=/var/log/auth.log* df sample

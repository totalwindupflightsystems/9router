#!/bin/bash
# MON-GAP-013 -- final deploy of pg + redis exporters on master001 (tailnet-bound, restart=unless-stopped)
# Run as root on master001. No secrets printed; credentials are read from the containers at runtime.
set -e
TS=100.99.183.108
# temp probe container from earlier runs must go
docker rm -f mon-gap013-pg-exporter >/dev/null 2>&1 || true

PGUSER=$(docker exec coolify-db printenv POSTGRES_USER)
PGDB=$(docker exec coolify-db printenv POSTGRES_DB)
PGPW=$(docker exec coolify-db printenv POSTGRES_PASSWORD)
RPW=$(docker exec coolify-redis printenv REDIS_PASSWORD)

# postgres exporter: attached to the coolify network (DNS alias coolify-db), published ONLY on the tailnet IP
docker run -d --name mon-gap013-pg-exporter --restart unless-stopped \
  --network coolify -p $TS:9187:9187 \
  -e DATA_SOURCE_NAME="postgresql://$PGUSER:$PGPW@coolify-db:5432/$PGDB?sslmode=disable" \
  prometheuscommunity/postgres-exporter:latest >/dev/null

# redis exporter: REDIS_ADDR via the coolify network alias "redis"
docker run -d --name mon-gap013-redis-exporter --restart unless-stopped \
  --network coolify -p $TS:9121:9121 \
  -e REDIS_ADDR=redis:6379 -e REDIS_PASSWORD="$RPW" \
  oliver006/redis_exporter:latest >/dev/null

unset PGPW RPW
sleep 4
docker ps --format '{{.Names}} {{.Status}} {{.Ports}}' | grep mon-gap013
echo "--- health from inside coolify net:"
docker run --rm --network coolify curlimages/curl:latest sh -c \
  "curl -s -m 8 http://mon-gap013-pg-exporter:9187/metrics | grep -E '^pg_up '; curl -s -m 8 http://mon-gap013-redis-exporter:9121/metrics | grep -E '^redis_up |^redis_running_scripts'"
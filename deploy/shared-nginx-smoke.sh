#!/bin/sh
set -eu

if [ "$#" -ne 1 ]; then
    printf '%s\n' 'usage: shared-nginx-smoke.sh AURORA_WEB_CONTAINER_ID' >&2
    exit 2
fi

if [ -z "${AURORA_WEB_SMOKE_MARKER:-}" ]; then
    printf '%s\n' 'AURORA_WEB_SMOKE_MARKER is required' >&2
    exit 2
fi

test "$(docker inspect --format '{{.Id}}' aurora-web)" = "$1"
docker inspect --format '{{json .NetworkSettings.Networks}}' aurora-web | grep -q 'beyondcandidate_edge'
docker inspect --format '{{json .NetworkSettings.Networks}}' beyondcandidate-proxy-1 | grep -q 'beyondcandidate_edge'
curl --fail --silent --show-error --connect-timeout 5 --max-time 15 \
    https://hr.aurora-tek.cn/health/ready >/dev/null
curl --fail --silent --show-error --connect-timeout 5 --max-time 15 \
    https://hr.aurora-tek.cn/ >/dev/null
curl --fail --silent --show-error --connect-timeout 5 --max-time 15 \
    https://aurora-tek.cn/ | grep -Fq "$AURORA_WEB_SMOKE_MARKER"
curl --fail --silent --show-error --connect-timeout 5 --max-time 15 \
    https://www.aurora-tek.cn/ | grep -Fq "$AURORA_WEB_SMOKE_MARKER"

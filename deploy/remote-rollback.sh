#!/bin/sh
set -eu

if [ "$#" -ne 3 ]; then
    printf '%s\n' 'usage: remote-rollback.sh APP_ROOT DOMAIN EXPECTED_RELEASE' >&2
    exit 2
fi

app_root=$1
domain=$2
expected_release=$3
current_release=$(readlink -f "$app_root/current")
expected_path="$app_root/releases/$expected_release"
info_file="$current_release/deploy/release-info.txt"
smoke_tool="$current_release/deploy/shared-nginx-smoke.sh"

if [ "$current_release" != "$expected_path" ]; then
    printf 'refusing rollback: current release is not %s\n' "$expected_release" >&2
    exit 1
fi
test -f "$info_file"
test -f "$smoke_tool"
scope=$(sed -n 's/^scope=//p' "$info_file")
previous_release=$(sed -n 's/^previous_release=//p' "$info_file")
case "$scope" in
    frontend|all) ;;
    *) printf '%s\n' 'release info contains an invalid scope' >&2; exit 1 ;;
esac
case "$previous_release" in
    "$app_root"/releases/*) ;;
    *) printf '%s\n' 'release info contains an invalid rollback path' >&2; exit 1 ;;
esac
test -d "$previous_release"
test -f "$previous_release/deploy/nginx/production.conf.template"

compose_previous() {
    docker compose -p beyondcandidate \
        --env-file "$previous_release/deploy/.env" \
        -f "$previous_release/deploy/compose.yaml" \
        -f "$previous_release/deploy/compose.server-https.yaml" \
        "$@"
}

shared_nginx_smoke_marker() {
    python3 - "$previous_release/deploy/.env" <<'PY'
import sys
from pathlib import Path

for raw_line in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines():
    line = raw_line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    key, value = line.split("=", 1)
    if key.strip() != "AURORA_WEB_SMOKE_MARKER":
        continue
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1]
    print(value)
    break
PY
}

wait_for_health() {
    container=$1
    count=0
    while [ "$count" -lt 45 ]; do
        health=$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container" 2>/dev/null || true)
        [ "$health" = healthy ] && return 0
        count=$((count + 1))
        sleep 2
    done
    return 1
}

verify_shared_networks() {
    docker inspect --format '{{json .NetworkSettings.Networks}}' aurora-web | grep -q 'beyondcandidate_edge'
    docker inspect --format '{{json .NetworkSettings.Networks}}' beyondcandidate-proxy-1 | grep -q 'beyondcandidate_edge'
}

python3 "$current_release/deploy/shared_nginx_release_validator.py" \
    --nginx-template "$previous_release/deploy/nginx/production.conf.template"
compose_previous config --quiet
aurora_web_before=$(docker inspect --format '{{.Id}}' aurora-web)
test -n "$aurora_web_before"

if [ "$scope" = all ]; then
    compose_previous up -d --no-build api worker proxy
    wait_for_health beyondcandidate-api-1
    wait_for_health beyondcandidate-worker-1
else
    compose_previous up -d --no-deps --force-recreate proxy
fi
wait_for_health beyondcandidate-proxy-1
aurora_web_smoke_marker=$(shared_nginx_smoke_marker)
compose_previous exec -T proxy nginx -t
verify_shared_networks
AURORA_WEB_SMOKE_MARKER="$aurora_web_smoke_marker" \
    sh "$smoke_tool" "$aurora_web_before"
ln -sfn "$previous_release" "$app_root/current.new"
mv -Tf "$app_root/current.new" "$app_root/current"
printf 'rolled_back_from=%s\n' "$expected_release"
printf 'active_release=%s\n' "$previous_release"

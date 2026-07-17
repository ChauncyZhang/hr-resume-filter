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

if [ "$current_release" != "$expected_path" ]; then
    printf 'refusing rollback: current release is not %s\n' "$expected_release" >&2
    exit 1
fi
test -f "$info_file"
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

compose_previous() {
    docker compose -p beyondcandidate \
        --env-file "$previous_release/deploy/.env" \
        -f "$previous_release/deploy/compose.yaml" \
        -f "$previous_release/deploy/compose.server-https.yaml" \
        "$@"
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

if [ "$scope" = all ]; then
    compose_previous up -d --no-build api worker proxy
    wait_for_health beyondcandidate-api-1
    wait_for_health beyondcandidate-worker-1
else
    compose_previous up -d --no-deps --force-recreate proxy
fi
wait_for_health beyondcandidate-proxy-1
curl --fail --silent --show-error --max-time 15 "https://$domain/health/ready" >/dev/null
ln -sfn "$previous_release" "$app_root/current.new"
mv -Tf "$app_root/current.new" "$app_root/current"
printf 'rolled_back_from=%s\n' "$expected_release"
printf 'active_release=%s\n' "$previous_release"

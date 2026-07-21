#!/bin/sh
set -eu

if [ "$#" -ne 7 ]; then
    printf '%s\n' 'usage: remote-release.sh RELEASE SCOPE DOMAIN APP_ROOT STAGING COMMIT SOURCE_SHA256' >&2
    exit 2
fi

release=$1
scope=$2
domain=$3
app_root=$4
staging=$5
commit=$6
source_sha=$7
release_dir="$app_root/releases/$release"
previous_release=$(readlink -f "$app_root/current")
previous_env_file="$previous_release/deploy/.env"
overlay="$release_dir/deploy/compose.server-https.yaml"
env_file="$release_dir/deploy/.env"
nginx_template="$release_dir/deploy/nginx/production.conf.template"
frontend_image="beyondcandidate-frontend:$release"
app_image="beyondcandidate-server:$release"

case "$scope" in
    frontend|all) ;;
    *) printf 'unsupported release scope: %s\n' "$scope" >&2; exit 2 ;;
esac
case "$release" in
    *[!A-Za-z0-9._-]*|'') printf '%s\n' 'invalid release id' >&2; exit 2 ;;
esac

read_aurora_web_smoke_marker() {
    marker_file=$1
    python3 - "$marker_file" <<'PY'
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

test -d "$release_dir"
test -d "$previous_release"
test -f "$previous_env_file"
test -f "$previous_release/deploy/compose.server-https.yaml"
test -f "$previous_release/deploy/nginx/production.conf.template"
test -f "$staging/frontend-image.tar"
aurora_web_smoke_marker=$(read_aurora_web_smoke_marker "$previous_env_file")
if [ -z "$aurora_web_smoke_marker" ]; then
    printf '%s\n' 'AURORA_WEB_SMOKE_MARKER is required' >&2
    exit 1
fi
cp "$previous_env_file" "$env_file"
chmod 600 "$env_file"
cp "$previous_release/deploy/compose.server-https.yaml" "$overlay"
cp "$previous_release/deploy/nginx/production.conf.template" "$nginx_template"
python3 "$release_dir/deploy/shared_nginx_release_validator.py" \
    --nginx-template "$nginx_template"

compose_at() {
    compose_root=$1
    shift
    docker compose -p beyondcandidate \
        --env-file "$compose_root/deploy/.env" \
        -f "$compose_root/deploy/compose.yaml" \
        -f "$compose_root/deploy/compose.server-https.yaml" \
        "$@"
}

rollback_services() {
    if [ "$scope" = all ]; then
        compose_at "$previous_release" up -d --no-build api worker proxy
    else
        compose_at "$previous_release" up -d --no-deps --force-recreate proxy
    fi
}

wait_for_health() {
    container=$1
    attempts=${2:-45}
    count=0
    while [ "$count" -lt "$attempts" ]; do
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

verify_release_runtime() {
    runtime_release=$1
    wait_for_health beyondcandidate-proxy-1 \
        && compose_at "$runtime_release" exec -T proxy nginx -t \
        && verify_shared_networks \
        && AURORA_WEB_SMOKE_MARKER="$aurora_web_smoke_marker" \
            sh "$smoke_tool" "$aurora_web_before"
}

restore_previous_and_verify() {
    if ! rollback_services; then
        printf '%s\n' 'rollback service restoration failed' >&2
        return 1
    fi
    if ! verify_release_runtime "$previous_release"; then
        printf '%s\n' 'rollback verification failed; previous release is not healthy' >&2
        return 1
    fi
}

docker load -i "$staging/frontend-image.tar"
docker image inspect "$frontend_image" >/dev/null
sed -i -E "0,/image: beyondcandidate-frontend:[^[:space:]]+/s//image: beyondcandidate-frontend:$release/" "$overlay"
grep -qF "image: $frontend_image" "$overlay"
docker run --rm --entrypoint sh "$frontend_image" -c 'test -s /usr/share/nginx/html/index.html'

if [ "$scope" = all ]; then
    test -f "$staging/app-image.tar"
    docker load -i "$staging/app-image.tar"
    docker image inspect "$app_image" >/dev/null
    sed -i -E "s|image: beyondcandidate-server:[^[:space:]]+|image: beyondcandidate-server:$release|g" "$overlay"
    [ "$(grep -cF "image: $app_image" "$overlay")" -eq 2 ]
fi

compose_at "$release_dir" config --quiet
aurora_web_before=$(docker inspect --format '{{.Id}}' aurora-web)
test -n "$aurora_web_before"
smoke_tool="$release_dir/deploy/shared-nginx-smoke.sh"
test -f "$smoke_tool"

if [ "$scope" = all ]; then
    compose_at "$release_dir" up -d postgres minio clamav
    compose_at "$release_dir" up --no-deps minio-provision
    owner_url=$(python3 - "$env_file" <<'PY'
import sys
from pathlib import Path
from urllib.parse import quote

values = {}
for raw_line in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines():
    line = raw_line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    key, value = line.split("=", 1)
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1]
    values[key.strip()] = value
required = ("POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB")
if any(not values.get(key) for key in required):
    raise SystemExit("release environment is missing PostgreSQL owner settings")
print(
    "postgresql+asyncpg://"
    + quote(values["POSTGRES_USER"], safe="")
    + ":"
    + quote(values["POSTGRES_PASSWORD"], safe="")
    + "@postgres:5432/"
    + quote(values["POSTGRES_DB"], safe="")
)
PY
    )
    compose_at "$release_dir" run --rm --no-deps -e "DATABASE_URL=$owner_url" api \
        python -m alembic -c server/alembic.ini upgrade head
    unset owner_url
    compose_at "$release_dir" exec -T postgres \
        sh /docker-entrypoint-initdb.d/10-provision-app-role.sh
    if ! compose_at "$release_dir" up -d --no-build api worker proxy; then
        restore_previous_and_verify || exit 1
        exit 1
    fi
    if ! wait_for_health beyondcandidate-api-1 || ! wait_for_health beyondcandidate-worker-1; then
        printf '%s\n' 'application health verification failed; rolling back services' >&2
        restore_previous_and_verify || exit 1
        exit 1
    fi
else
    if ! compose_at "$release_dir" up -d --no-deps --force-recreate proxy; then
        restore_previous_and_verify || exit 1
        exit 1
    fi
fi

if ! verify_release_runtime "$release_dir"; then
    printf '%s\n' 'shared routing verification failed; rolling back services' >&2
    restore_previous_and_verify || exit 1
    exit 1
fi

frontend_image_id=$(docker image inspect --format '{{.Id}}' "$frontend_image")
{
    printf 'release=%s\n' "$release"
    printf 'scope=%s\n' "$scope"
    printf 'git_commit=%s\n' "$commit"
    printf 'source_sha256=%s\n' "$source_sha"
    printf 'frontend_image=%s\n' "$frontend_image"
    printf 'frontend_image_id=%s\n' "$frontend_image_id"
    if [ "$scope" = all ]; then
        printf 'app_image=%s\n' "$app_image"
        printf 'app_image_id=%s\n' "$(docker image inspect --format '{{.Id}}' "$app_image")"
    fi
    printf 'previous_release=%s\n' "$previous_release"
    printf 'deployed_at=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
} > "$release_dir/deploy/release-info.txt"
ln -sfn "$release_dir" "$app_root/current.new"
mv -Tf "$app_root/current.new" "$app_root/current"

rm -f "$staging/source.tar.gz" "$staging/frontend-image.tar" "$staging/app-image.tar"
rmdir "$staging" 2>/dev/null || true
printf 'deployed_release=%s\n' "$release"
printf 'previous_release=%s\n' "$previous_release"
printf 'proxy_health=%s\n' "$(docker inspect --format '{{.State.Health.Status}}' beyondcandidate-proxy-1)"

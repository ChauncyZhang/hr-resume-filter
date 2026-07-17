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
overlay="$release_dir/deploy/compose.server-https.yaml"
env_file="$release_dir/deploy/.env"
frontend_image="beyondcandidate-frontend:$release"
app_image="beyondcandidate-server:$release"

case "$scope" in
    frontend|all) ;;
    *) printf 'unsupported release scope: %s\n' "$scope" >&2; exit 2 ;;
esac
case "$release" in
    *[!A-Za-z0-9._-]*|'') printf '%s\n' 'invalid release id' >&2; exit 2 ;;
esac

test -d "$release_dir"
test -d "$previous_release"
test -f "$previous_release/deploy/.env"
test -f "$previous_release/deploy/compose.server-https.yaml"
test -f "$staging/frontend-image.tar"
cp "$previous_release/deploy/.env" "$env_file"
chmod 600 "$env_file"
cp "$previous_release/deploy/compose.server-https.yaml" "$overlay"

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
        compose_at "$previous_release" up -d --no-build api worker proxy || true
    else
        compose_at "$previous_release" up -d --no-deps --force-recreate proxy || true
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
        rollback_services
        exit 1
    fi
    if ! wait_for_health beyondcandidate-api-1 || ! wait_for_health beyondcandidate-worker-1; then
        printf '%s\n' 'application health verification failed; rolling back services' >&2
        rollback_services
        exit 1
    fi
else
    if ! compose_at "$release_dir" up -d --no-deps --force-recreate proxy; then
        rollback_services
        exit 1
    fi
fi

if ! wait_for_health beyondcandidate-proxy-1 \
    || ! curl --fail --silent --show-error --max-time 15 "https://$domain/health/ready" >/dev/null; then
    printf '%s\n' 'HTTPS health verification failed; rolling back services' >&2
    rollback_services
    exit 1
fi

ln -sfn "$release_dir" "$app_root/current.new"
mv -Tf "$app_root/current.new" "$app_root/current"
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

rm -f "$staging/source.tar.gz" "$staging/frontend-image.tar" "$staging/app-image.tar"
rmdir "$staging" 2>/dev/null || true
printf 'deployed_release=%s\n' "$release"
printf 'previous_release=%s\n' "$previous_release"
printf 'proxy_health=%s\n' "$(docker inspect --format '{{.State.Health.Status}}' beyondcandidate-proxy-1)"

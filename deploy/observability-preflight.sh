#!/bin/sh
set -eu

script_directory=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repository_root=$(CDPATH= cd -- "$script_directory/.." && pwd)
production_preflight="$script_directory/production-preflight.sh"
base_compose="$script_directory/compose.yaml"
production_overlay="$script_directory/compose.production.yaml"
observability_overlay="$script_directory/compose.observability.yaml"
compose_env_file=${COMPOSE_ENV_FILE:-"$script_directory/.env"}

# This must remain the first validation layer. It enforces the supported
# Compose version and proves the base + production model independently.
sh "$production_preflight"

docker compose \
    --env-file "$compose_env_file" \
    -f "$base_compose" \
    -f "$production_overlay" \
    -f "$observability_overlay" \
    config --quiet

printf '%s\n' 'observability preflight: merged three-file Compose model is valid'

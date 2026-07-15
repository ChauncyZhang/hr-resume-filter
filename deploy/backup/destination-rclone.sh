#!/bin/sh
set -eu
# rclone reads credentials only from the supplied CONFIG_FILE; values never enter argv.

operation=${1:?operation is required}
shift
config_file=
destination=
run_id=
source_path=
output_path=
while [ "$#" -gt 0 ]; do
  case "$1" in
    --config-file) config_file=${2:?}; shift 2 ;;
    --destination) destination=${2:?}; shift 2 ;;
    --run-id) run_id=${2:?}; shift 2 ;;
    --source) source_path=${2:?}; shift 2 ;;
    --output) output_path=${2:?}; shift 2 ;;
    *) printf '%s\n' "unknown destination-client argument" >&2; exit 2 ;;
  esac
done
: "${config_file:?CONFIG_FILE is required}"
: "${destination:?destination is required}"
export RCLONE_CONFIG=$config_file
pending=${destination%/}/.incomplete/${run_id}
complete=${destination%/}/${run_id}

case "$operation" in
  stage-group)
    : "${run_id:?run id is required}" "${source_path:?source is required}"
    if rclone lsf "$complete/COMPLETE" --files-only --quiet 2>/dev/null | grep -q '^COMPLETE$'; then
      printf '%s\n' "refusing to overwrite an existing complete backup run id" >&2
      exit 1
    fi
    rclone copy "$source_path" "$pending" --quiet
    ;;
  publish-group)
    : "${run_id:?run id is required}"
    rclone copy "$pending" "$complete" --exclude manifest.json --exclude COMPLETE --quiet
    rclone copyto "$pending/manifest.json" "$complete/manifest.json" --quiet
    rclone copyto "$pending/COMPLETE" "$complete/COMPLETE" --quiet
    rclone purge "$pending" --quiet
    ;;
  abort-group)
    : "${run_id:?run id is required}"
    rclone purge "$pending" --quiet || true
    ;;
  fetch-complete-group)
    : "${run_id:?run id is required}" "${output_path:?output is required}"
    rclone lsf "$complete/COMPLETE" --files-only --quiet | grep -q '^COMPLETE$'
    rclone copy "$complete" "$output_path" --quiet
    ;;
  delete-complete-group)
    : "${run_id:?run id is required}"
    rclone lsf "$complete/COMPLETE" --files-only --quiet | grep -q '^COMPLETE$'
    rclone purge "$complete" --quiet
    ;;
  catalog)
    : "${output_path:?output is required}"
    temporary=$(mktemp -d)
    trap 'rm -rf "$temporary"' EXIT HUP INT TERM
    # Prune catalog validity is based on downloaded payload hashes, inventory,
    # and pg_restore listing, not only on the presence of a marker.
    rclone copy "$destination" "$temporary" --exclude '.incomplete/**' --quiet
    python3 /opt/ux09-backup/backupctl.py catalog-local "$temporary" "$output_path"
    ;;
  *) printf '%s\n' "unsupported destination-client operation" >&2; exit 2 ;;
esac

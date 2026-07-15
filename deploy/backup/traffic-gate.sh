#!/bin/sh
set -eu
# Phase 6C foundation has no traffic-open transition. Caller evidence is ignored.
: "${TRAFFIC_OPEN_MARKER_FILE:?Set TRAFFIC_OPEN_MARKER_FILE}"
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec python3 "$SCRIPT_DIR/backupctl.py" traffic-gate \
  /dev/null /dev/null "$TRAFFIC_OPEN_MARKER_FILE"

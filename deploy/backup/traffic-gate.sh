#!/bin/sh
set -eu
# Evidence paths are files; no credential or secret value is accepted here.
: "${RESTORE_EVIDENCE_FILE:?Set RESTORE_EVIDENCE_FILE}"
: "${B2B3_EVIDENCE_FILE:?Set B2B3_EVIDENCE_FILE from the real B2B3 CLI and Worker}"
: "${TRAFFIC_OPEN_MARKER_FILE:?Set TRAFFIC_OPEN_MARKER_FILE}"
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec python3 "$SCRIPT_DIR/backupctl.py" traffic-gate \
  "$RESTORE_EVIDENCE_FILE" "$B2B3_EVIDENCE_FILE" "$TRAFFIC_OPEN_MARKER_FILE"

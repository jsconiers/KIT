#!/bin/bash
# The shared to-do sync (shared/kit_sync_core.py): regression against the pre-refactor sync, routing,
# and both entry points (the Windows one over a fake COM layer).
#   bash tests/test_sync_core.sh
exec python3 "$(dirname "$0")/test_sync_core.py" "$@"

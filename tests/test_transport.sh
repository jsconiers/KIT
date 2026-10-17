#!/bin/bash
# Runs the transport tests (shared/kit_transport.py, kit-publish, kit-team, team dashboard).
exec python3 "$(dirname "$0")/test_transport.py" "$@"

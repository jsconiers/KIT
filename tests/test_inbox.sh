#!/bin/bash
# Phone and remote access phase 1: Kit Inbox requests, coded approvals, OneDrive publishing.
#   bash tests/test_inbox.sh
exec python3 "$(dirname "$0")/test_inbox.py" "$@"

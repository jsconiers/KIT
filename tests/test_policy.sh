#!/bin/bash
# Runs the organization-profile (sharing policy) tests.
exec python3 "$(dirname "$0")/test_policy.py" "$@"

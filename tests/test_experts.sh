#!/bin/bash
# Expertise finder tests (kit-team experts, expertise records).
cd "$(dirname "$0")/.." || exit 1
exec python3 tests/test_teamviews.py experts

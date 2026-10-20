#!/bin/bash
# Team load view tests (shared/kit_teamviews.py, kit-team load, team dashboard panel, kit-publish kinds).
cd "$(dirname "$0")/.." || exit 1
exec python3 tests/test_teamviews.py load

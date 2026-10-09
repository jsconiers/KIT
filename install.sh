#!/bin/bash
# install.sh: top-level installer dispatcher for Kit.
# Detects the OS and hands off to the matching platform installer.
#   macOS   -> platform/mac/install.sh
#   other   -> not yet supported (see platform/windows/PORTING.md for the Windows plan)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

case "$(uname -s)" in
  Darwin)
    exec bash "$ROOT/platform/mac/install.sh" "$@" ;;
  *)
    printf 'Kit currently installs on macOS only.\n'
    printf 'Windows support is planned — see %s.\n' "$ROOT/platform/windows/PORTING.md"
    printf 'On Windows, run:  powershell -ExecutionPolicy Bypass -File install.ps1\n'
    exit 1 ;;
esac

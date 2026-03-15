#!/usr/bin/env bash
set -eu
set -o pipefail 2>/dev/null || true

if ! . "$HOME/.eonix/venv/bin/activate" 2>/dev/null; then
  export PATH="$HOME/.eonix/venv/bin:$PATH"
fi

EONIX_HOME="${EONIX_HOME:-$HOME/.eonix/os}"
exec python3 "$EONIX_HOME/eonix-shell/shell.py" "$@"

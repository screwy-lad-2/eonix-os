#!/bin/bash
export EONIX_HOME="${EONIX_HOME:-$HOME/.eonix/os}"
source ~/.eonix/venv/bin/activate 2>/dev/null
bash "$EONIX_HOME/start_eonix.sh" &
sleep 3
exec python3 "$EONIX_HOME/eonix-desktop/desktop.py"

#!/bin/bash
# Inside ISO, EONIX_HOME is /home/eonix. Outside, it remains ~/.eonix/os
if [[ -d "/home/eonix/eonix-desktop" ]]; then
    export EONIX_HOME="/home/eonix"
else
    export EONIX_HOME="${EONIX_HOME:-$HOME/.eonix/os}"
fi

# Activate venv only if it exists (local dev), otherwise use system python (ISO)
if [[ -f "$HOME/.eonix/venv/bin/activate" ]]; then
    source "$HOME/.eonix/venv/bin/activate"
fi

bash "$EONIX_HOME/start_eonix.sh" &
sleep 3
exec python3 "$EONIX_HOME/eonix-desktop/desktop.py"

#!/bin/bash
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-python3}"

echo "⚡ Starting EONIX OS..."

$PYTHON_BIN eonix-cortex/goal-engine/engine.py --start &
$PYTHON_BIN eonix-cortex/context-agent/agent.py --start &
$PYTHON_BIN eonix-cortex/resource-agent/agent.py --start &
$PYTHON_BIN eonix-sync/sync_daemon.py --start &

sleep 3

$PYTHON_BIN eonix-hub/hub_server.py &

sleep 2

echo "✅ All agents online"
echo "🌐 Hub: http://localhost:7750"
echo "Starting MIND..."

$PYTHON_BIN eonix-mind/mind_v2.py

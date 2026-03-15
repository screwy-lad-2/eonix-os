#!/bin/bash
set -eu
set -o pipefail 2>/dev/null || true

DEFAULT_PY="python3"
if [[ -x "$HOME/.eonix/venv/bin/python3" ]]; then
	DEFAULT_PY="$HOME/.eonix/venv/bin/python3"
fi
PYTHON_BIN="${PYTHON_BIN:-$DEFAULT_PY}"
NO_MIND="${EONIX_START_NO_MIND:-0}"
NO_MIND="${NO_MIND//$'\r'/}"

cleanup() {
	if [[ "${NO_MIND}" == "1" ]]; then
		return
	fi
	for pid in "${PIDS[@]:-}"; do
		if [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null; then
			kill "${pid}" 2>/dev/null || true
		fi
	done
}

trap cleanup EXIT INT TERM

declare -a PIDS=()

start_bg() {
	local label="$1"
	shift
	"$@" >/dev/null 2>&1 &
	local pid=$!
	PIDS+=("${pid}")
	echo "  started ${label} (pid ${pid})"
}

echo "⚡ Starting EONIX OS..."

start_bg "GoalEngine" "$PYTHON_BIN" eonix-cortex/goal-engine/engine.py --start
start_bg "ContextAgent" "$PYTHON_BIN" eonix-cortex/context-agent/agent.py --start
start_bg "ResourceAgent" "$PYTHON_BIN" eonix-cortex/resource-agent/agent.py --start
start_bg "SyncDaemon" "$PYTHON_BIN" eonix-sync/sync_daemon.py --start

sleep 3

start_bg "Hub" "$PYTHON_BIN" eonix-hub/hub_server.py

sleep 2

echo "✅ All agents online"
echo "🌐 Hub: http://localhost:7750"

if [[ "${NO_MIND}" == "1" ]]; then
	echo "ℹ️ EONIX_START_NO_MIND=1 -> skipping MIND startup"
	exit 0
fi

echo "Starting MIND..."
"$PYTHON_BIN" eonix-mind/mind_v2.py

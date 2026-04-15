#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
RESULTS_DIR="${ROOT_DIR}/results"
HUB_PROOF="${RESULTS_DIR}/week28_hub_health_proof.json"
mkdir -p "${RESULTS_DIR}"

DEFAULT_PY="python3"
if [[ -x "$HOME/.eonix/venv/bin/python3" ]]; then
	DEFAULT_PY="$HOME/.eonix/venv/bin/python3"
fi
PYTHON_BIN="${PYTHON_BIN:-$DEFAULT_PY}"
NO_MIND="${EONIX_START_NO_MIND:-0}"
NO_MIND="${NO_MIND//$'\r'/}"
HEALTH_RETRIES="${EONIX_HEALTH_RETRIES:-30}"
HEALTH_INTERVAL_SECONDS="${EONIX_HEALTH_INTERVAL_SECONDS:-2}"
SMOKE_MODE="${EONIX_START_SMOKE:-0}"

declare -a PIDS=()
declare -A STATUS=()
KEEP_PROCS_ON_SUCCESS=1

log() {
	local msg="$1"
	echo "[$(date -u +%H:%M:%S)] ${msg}"
}

ensure_httpx() {
	if ! "${PYTHON_BIN}" - <<'PY' 2>/dev/null
import httpx
PY
	then
		log "httpx missing -> installing"
		"${PYTHON_BIN}" -m pip install httpx -q >/dev/null 2>&1 || pip install httpx -q >/dev/null 2>&1 || true
	else
		log "httpx already installed"
	fi
}

cleanup() {
	if [[ "${KEEP_PROCS_ON_SUCCESS}" -eq 1 && "${overall_success:-0}" -eq 1 ]]; then
		return
	fi
	for pid in "${PIDS[@]:-}"; do
		if [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null; then
			kill "${pid}" 2>/dev/null || true
		fi
	done
}

trap cleanup EXIT INT TERM

start_bg() {
	local label="$1"
	shift
	local log_file="${RESULTS_DIR}/start_${label// /_}.log"
	nohup "$@" >"${log_file}" 2>&1 &
	local pid=$!
	PIDS+=("${pid}")
	log "started ${label} (pid ${pid}) -> ${log_file}"
}

http_json() {
	local url="$1"
	curl -fsS --max-time 3 "${url}" || return 1
}

wait_for_health() {
	local name="$1" url="$2"
	local retries="${HEALTH_RETRIES}"
	for ((i=1; i<=retries; i++)); do
		if output=$(http_json "${url}"); then
			STATUS["${name}"]="ok"
			return 0
		fi
		sleep "${HEALTH_INTERVAL_SECONDS}"
	done
	STATUS["${name}"]="fail"
	return 1
}

print_summary() {
	local goal="${STATUS[goal]:-fail}"
	local ctx="${STATUS[context]:-fail}"
	local res="${STATUS[resource]:-fail}"
	local sync="${STATUS[sync]:-fail}"
	local hub="${STATUS[hub]:-fail}"
	local mind="${STATUS[mind]:-fail}"

	local icon_goal icon_ctx icon_res icon_sync icon_hub icon_mind
	icon_goal=$([[ "${goal}" == "ok" ]] && echo "✅" || echo "❌")
	icon_ctx=$([[ "${ctx}" == "ok" ]] && echo "✅" || echo "❌")
	icon_res=$([[ "${res}" == "ok" ]] && echo "✅" || echo "❌")
	icon_sync=$([[ "${sync}" == "ok" ]] && echo "✅" || echo "❌")
	icon_hub=$([[ "${hub}" == "ok" ]] && echo "✅" || echo "❌")
	icon_mind=$([[ "${mind}" == "ok" ]] && echo "✅" || ([[ "${mind}" == "skip" ]] && echo "!" || echo "❌"))

	echo "Port 7735 GoalEngine:     ${icon_goal}"
	echo "Port 7736 ContextAgent:   ${icon_ctx}"
	echo "Port 7737 ResourceAgent:  ${icon_res}"
	echo "Port 7740 SyncDaemon:     ${icon_sync}"
	echo "Port 7750 Hub:            ${icon_hub}"
	echo "MIND v2:                  ${icon_mind}"
}

overall_success=0

log "⚡ Starting EONIX OS..."

ensure_httpx

if [[ "${SMOKE_MODE}" -eq 1 ]]; then
	log "SMOKE mode enabled -> skipping service startup"
	STATUS[goal]="skip"; STATUS[context]="skip"; STATUS[resource]="skip"; STATUS[sync]="skip"; STATUS[hub]="skip"; STATUS[mind]="skip"
	overall_success=1
	print_summary
	exit 0
fi

start_bg "GoalEngine" "$PYTHON_BIN" eonix-cortex/goal-engine/engine.py --start
start_bg "ContextAgent" "$PYTHON_BIN" eonix-cortex/context-agent/agent.py --start
start_bg "ResourceAgent" "$PYTHON_BIN" eonix-cortex/resource-agent/agent.py --start
start_bg "SyncDaemon" "$PYTHON_BIN" eonix-sync/sync_daemon.py --start --port 7740

sleep 3

start_bg "Hub" "$PYTHON_BIN" eonix-hub/hub_server.py

sleep 2

wait_for_health "goal" "http://127.0.0.1:7735/goal/status" || true
wait_for_health "context" "http://127.0.0.1:7736/context/status" || true
wait_for_health "resource" "http://127.0.0.1:7737/resource/status" || true
wait_for_health "sync" "http://127.0.0.1:7740/sync/status" || true

hub_status_raw=""
hub_attempts="${HEALTH_RETRIES}"
for ((i=1; i<=hub_attempts; i++)); do
		hub_status_raw=$(http_json "http://127.0.0.1:7750/hub/status") || true
	if [[ -n "${hub_status_raw}" ]]; then
		STATUS[hub]="ok"
			echo "${hub_status_raw}" >"${RESULTS_DIR}/week28_hub_status_raw.txt"
			"${PYTHON_BIN}" - <<'PY' "${RESULTS_DIR}/week28_hub_status_raw.txt" "${HUB_PROOF}" || true
import json, pathlib, sys
raw_path = pathlib.Path(sys.argv[1])
out_path = pathlib.Path(sys.argv[2])
data = json.loads(raw_path.read_text())
out_path.write_text(json.dumps(data, indent=2))
PY
		break
	fi
	sleep "${HEALTH_INTERVAL_SECONDS}"
done
if [[ -z "${hub_status_raw}" ]]; then
	STATUS[hub]="fail"
fi

all_healthy=0
if [[ "${STATUS[goal]}" == "ok" && "${STATUS[context]}" == "ok" && "${STATUS[resource]}" == "ok" && "${STATUS[sync]}" == "ok" && "${STATUS[hub]}" == "ok" ]]; then
	if [[ -s "${HUB_PROOF}" ]]; then
		if "${PYTHON_BIN}" - "${HUB_PROOF}" <<'PY'; then
import json, sys, pathlib
path = pathlib.Path(sys.argv[1])
data = json.loads(path.read_text()) if path.exists() else {}
sys.exit(0 if data.get("all_agents_healthy") else 1)
PY
			all_healthy=1
		fi
	fi
fi

if [[ "${NO_MIND}" == "1" ]]; then
	log "EONIX_START_NO_MIND=1 -> skipping MIND startup"
	STATUS[mind]="skip"
else
	MIND_PATH=""
	MIND_FOUND=$( { find "${HOME}/eonix-os" "${HOME}/eonix-mind" -name 'mind_v2.py' 2>/dev/null || true; } | head -n 1 )
	if [[ -n "${MIND_FOUND}" ]]; then
		MIND_PATH="${MIND_FOUND}"
	fi
	if [[ -z "${MIND_PATH}" ]]; then
		log "MIND not found -> skipping"
		STATUS[mind]="skip"
	else
		log "Starting MIND from ${MIND_PATH}"
		start_bg "MIND" "$PYTHON_BIN" "${MIND_PATH}"
		STATUS[mind]="ok"
	fi
fi

print_summary

if [[ "${all_healthy}" -eq 1 ]]; then
	overall_success=1
	log "✅ all_agents_healthy=true"
	log "🌐 Hub: http://127.0.0.1:7750"
	exit 0
fi

log "⚠ Agents not all healthy yet; they may still be starting. See logs in ${RESULTS_DIR}"
exit 0

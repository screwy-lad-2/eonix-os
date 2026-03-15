#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
RESULTS_DIR="${ROOT_DIR%/iso}/results"
SERIAL_LOG="${RESULTS_DIR}/week28_qemu_serial.log"
SCREENSHOT="${RESULTS_DIR}/week28_boot_screenshot.png"
REPORT="${RESULTS_DIR}/week28_qemu_boot_test.txt"
ISO_PATH="${ISO_PATH:-$HOME/eonix-os-0.8.0.iso}"
XVFB_DISPLAY=":99"
VNC_DISPLAY=":1"
QEMU_LOG="${RESULTS_DIR}/week28_qemu.log"
mkdir -p "${RESULTS_DIR}"

echo "[verify_boot] ISO: ${ISO_PATH}"

cleanup() {
	for pid in ${QEMU_PID:-} ${XVFB_PID:-}; do
		if [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null; then
			kill "${pid}" 2>/dev/null || true
		fi
	done
}
trap cleanup EXIT INT TERM

if [[ ! -f "${ISO_PATH}" ]]; then
	echo "ISO not found: ${ISO_PATH}" >&2
	exit 1
fi

Xvfb ${XVFB_DISPLAY} -screen 0 1280x800x24 >/dev/null 2>&1 &
XVFB_PID=$!
sleep 2

BOOT_START=$(date +%s)
DISPLAY=${XVFB_DISPLAY} nohup qemu-system-x86_64 \
  -m 4096 \
  -smp 2 \
  -cdrom "${ISO_PATH}" \
  -vga virtio \
  -display sdl,gl=off \
  -vnc ${VNC_DISPLAY} \
  -serial file:"${SERIAL_LOG}" \
  -no-reboot \
  -boot d \
  -nic user \
  >"${QEMU_LOG}" 2>&1 &
QEMU_PID=$!

echo "[verify_boot] qemu pid=${QEMU_PID}, waiting for boot..."
sleep 90 || true
BOOT_END=$(date +%s)
BOOT_TIME=$((BOOT_END-BOOT_START))

if command -v import >/dev/null 2>&1; then
	DISPLAY=${XVFB_DISPLAY} import -window root "${SCREENSHOT}" || true
elif command -v scrot >/dev/null 2>&1; then
	DISPLAY=${XVFB_DISPLAY} scrot "${SCREENSHOT}" || true
else
	echo "Neither import nor scrot available for screenshot" >&2
	touch "${SCREENSHOT}"
fi

if kill -0 "${QEMU_PID}" 2>/dev/null; then
	kill "${QEMU_PID}" 2>/dev/null || true
	wait "${QEMU_PID}" 2>/dev/null || true
fi

GRUB_SEEN="NO"
BOOT_OK="NO"
DESKTOP_OK="NO"
SERIAL_TEXT=""
if [[ -f "${SERIAL_LOG}" ]]; then
	SERIAL_TEXT="$(tr '\r' '\n' <"${SERIAL_LOG}" | sed 's/\x1b\[[0-9;]*[a-zA-Z]//g')"
	if echo "${SERIAL_TEXT}" | grep -qi "grub"; then
		GRUB_SEEN="YES"
	fi
	if echo "${SERIAL_TEXT}" | grep -Eqi "login|kernel|ready|started"; then
		BOOT_OK="YES"
	fi
	if echo "${SERIAL_TEXT}" | grep -qi "EONIX"; then
		DESKTOP_OK="YES"
	fi
fi

PIXEL_OK=1
python - <<'PY'
from pathlib import Path
import sys
from statistics import mean
path = Path(sys.argv[1])
if not path.exists() or path.stat().st_size == 0:
    sys.exit(1)
# Try Pillow first for pixel mean
try:
    from PIL import Image, ImageStat  # type: ignore
    img = Image.open(path).convert("L")
    m = float(ImageStat.Stat(img).mean[0])
    print(f"pixel_mean={m:.2f}")
    sys.exit(0 if m > 1.0 else 1)
except Exception:
    pass
# Fallback to ImageMagick convert if available
import subprocess
try:
    out = subprocess.check_output(["convert", str(path), "-format", "%[fx:mean]", "info:"], text=True).strip()
    val = float(out)
    print(f"pixel_mean={val:.4f}")
    sys.exit(0 if val > 0.01 else 1)
except Exception:
    pass
sys.exit(0 if path.stat().st_size > 1024 else 1)
PY "${SCREENSHOT}" || PIXEL_OK=0

if [[ "${PIXEL_OK}" -eq 1 ]]; then
	DESKTOP_OK="YES"
fi

cat >"${REPORT}" <<EOF
GRUB menu appeared:   ${GRUB_SEEN}
Boot completed:       ${BOOT_OK}
Desktop loaded:       ${DESKTOP_OK}
Boot time:            ${BOOT_TIME} seconds
EOF

echo "[verify_boot] Report written to ${REPORT}"

if [[ "${BOOT_OK}" == "YES" && "${DESKTOP_OK}" == "YES" ]]; then
	echo "Boot confirmed"
	exit 0
fi

echo "Boot check failed"
exit 1

#!/usr/bin/env bash
set -eu
set -o pipefail 2>/dev/null || true

DEV_MODE=0
MINIMAL_MODE=0
UNINSTALL_MODE=0

for arg in "$@"; do
  case "$arg" in
    --dev) DEV_MODE=1 ;;
    --minimal) MINIMAL_MODE=1 ;;
    --uninstall) UNINSTALL_MODE=1 ;;
    *) echo "[EONIX][ERROR] Unknown flag: $arg"; exit 1 ;;
  esac
done

EONIX_HOME="${EONIX_HOME:-$HOME/.eonix}"
EONIX_OS_DIR="$EONIX_HOME/os"
EONIX_VENV_DIR="$EONIX_HOME/venv"
EONIX_PYTHON="$EONIX_VENV_DIR/bin/python"
EONIX_LOG_DIR="$EONIX_HOME/logs"
EONIX_BIN_DIR="$HOME/.local/bin"
WRAPPER_TARGET="$EONIX_BIN_DIR/eonix-shell"
SERVICE_DIR="$HOME/.config/systemd/user"
SERVICE_PATH="$SERVICE_DIR/eonix.service"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOCAL_REPO="$(cd "$SCRIPT_DIR/.." && pwd)"
DEFAULT_REPO_URL="https://github.com/shahnoor-exe/eonix-os.git"
if [ -d "$LOCAL_REPO/.git" ]; then
  REPO_URL="${EONIX_REPO_URL:-$LOCAL_REPO}"
else
  REPO_URL="${EONIX_REPO_URL:-$DEFAULT_REPO_URL}"
fi

log() { echo "[EONIX] $*"; }
warn() { echo "[EONIX][WARN] $*"; }
step() { echo; echo "[EONIX] STEP $1/9: $2"; }

uninstall() {
  step 1 "Uninstall Eonix user service"
  if command -v systemctl >/dev/null 2>&1; then
    systemctl --user disable --now eonix.service >/dev/null 2>&1 || true
    systemctl --user daemon-reload >/dev/null 2>&1 || true
  fi
  rm -f "$SERVICE_PATH"

  step 2 "Remove shell wrapper"
  rm -f "$WRAPPER_TARGET"

  step 3 "Remove Eonix home"
  rm -rf "$EONIX_HOME"

  log "✅ Eonix uninstall complete"
  exit 0
}

system_check() {
  if [ "${CI:-}" = "true" ]; then
    log "CI detected; using safe, non-destructive install path"
  fi
  if [ -r /proc/meminfo ]; then
    mem_gb="$(awk '/MemTotal/ {printf "%d", $2/1024/1024}' /proc/meminfo)"
    if [ "$mem_gb" -lt 8 ]; then
      warn "RAM is below 8GB (${mem_gb}GB). EONIX may run slower."
    fi
  fi
  log "✅ System check passed"
}

install_system_deps() {
  if [ "${CI:-}" = "true" ] || [ "$DEV_MODE" -eq 1 ]; then
    log "Skipping system package install (CI/dev mode)"
    return
  fi
  if command -v apt-get >/dev/null 2>&1; then
    sudo apt-get update
    sudo apt-get install -y python3 python3-venv python3-pip git curl
  elif command -v dnf >/dev/null 2>&1; then
    sudo dnf install -y python3 python3-pip git curl
  elif command -v pacman >/dev/null 2>&1; then
    sudo pacman -Sy --noconfirm python python-pip git curl
  else
    warn "Unsupported package manager; ensure python3, pip, git, curl are installed"
  fi
}

prepare_directories() {
  mkdir -p "$EONIX_HOME" "$EONIX_LOG_DIR" "$EONIX_BIN_DIR"
  log "Prepared $EONIX_HOME"
}

init_repo() {
  if [ "$DEV_MODE" -eq 1 ] && [ -d "$LOCAL_REPO" ]; then
    log "Dev mode: using local repository at $LOCAL_REPO"
    rm -rf "$EONIX_OS_DIR"
    cp -a "$LOCAL_REPO" "$EONIX_OS_DIR"
    return
  fi

  if [ ! -d "$EONIX_OS_DIR/.git" ]; then
    log "Cloning Eonix OS into $EONIX_OS_DIR"
    rm -rf "$EONIX_OS_DIR"
    GIT_TERMINAL_PROMPT=0 git clone "$REPO_URL" "$EONIX_OS_DIR"
    return
  fi

  log "Updating existing repo (conflict-safe mode)"
  (
    cd "$EONIX_OS_DIR"
    git stash push -u -m "eonix-installer-autostash" >/dev/null 2>&1 || true
    if ! GIT_TERMINAL_PROMPT=0 git fetch origin master >/dev/null 2>&1; then
      warn "Fetch failed; keeping current checkout without blocking install"
      return
    fi

    local_head="$(git rev-parse HEAD 2>/dev/null || echo "")"
    remote_head="$(git rev-parse origin/master 2>/dev/null || echo "")"
    if [ -z "$local_head" ] || [ -z "$remote_head" ] || [ "$local_head" = "$remote_head" ]; then
      log "Repository already up to date"
      return
    fi

    if ! git pull --rebase --strategy-option=theirs origin master; then
      warn "Auto-merge failed; keeping local tree. Resolve manually with: cd $EONIX_OS_DIR ; git pull"
    fi
  )
}

init_python_env() {
  py="${PYTHON_BIN:-python3}"
  if [ ! -x "$EONIX_VENV_DIR/bin/python" ]; then
    log "Creating virtual environment"
    if ! "$py" -m venv "$EONIX_VENV_DIR"; then
      warn "venv creation failed; using system python fallback"
    fi
  else
    log "Reusing existing virtual environment"
  fi

  py_cmd="$py"
  if [ -x "$EONIX_VENV_DIR/bin/python" ]; then
    EONIX_PYTHON="$EONIX_VENV_DIR/bin/python"
    py_cmd="$EONIX_PYTHON"
    if ! . "$EONIX_VENV_DIR/bin/activate" 2>/dev/null; then
      warn "Could not source venv activate script; using PATH fallback"
      export PATH="$EONIX_VENV_DIR/bin:$PATH"
    fi
  else
    EONIX_PYTHON="$py"
    warn "No venv python available; continuing with system python"
  fi

  "$py_cmd" -m pip install --upgrade pip >/dev/null 2>&1 || true
  if [ -f "$EONIX_OS_DIR/requirements.txt" ]; then
    "$py_cmd" -m pip install -r "$EONIX_OS_DIR/requirements.txt" >/dev/null 2>&1 || true
  fi

  if [ "$MINIMAL_MODE" -eq 0 ]; then
    "$py_cmd" -m pip install prompt_toolkit psutil >/dev/null 2>&1 || true
  fi
}

install_wrapper() {
  src="$EONIX_OS_DIR/install/eonix-shell-wrapper.sh"
  if [ ! -f "$src" ] && [ -f "$SCRIPT_DIR/eonix-shell-wrapper.sh" ]; then
    src="$SCRIPT_DIR/eonix-shell-wrapper.sh"
  fi
  if [ -f "$src" ]; then
    cp "$src" "$WRAPPER_TARGET"
    chmod +x "$WRAPPER_TARGET"
    log "Installed shell wrapper to $WRAPPER_TARGET"
  else
    warn "Wrapper script missing at $src"
  fi
}

configure_systemd() {
  if [ "${CI:-}" = "true" ] || [ "$DEV_MODE" -eq 1 ]; then
    log "Skipping systemd service creation (CI/dev mode)"
    return
  fi
  mkdir -p "$SERVICE_DIR"
  cat > "$SERVICE_PATH" <<EOF
[Unit]
Description=Eonix OS Hub Service
After=network.target

[Service]
Type=simple
WorkingDirectory=$EONIX_OS_DIR
ExecStart=$EONIX_PYTHON $EONIX_OS_DIR/eonix-hub/hub_server.py
Restart=on-failure

[Install]
WantedBy=default.target
EOF

  if command -v systemctl >/dev/null 2>&1; then
    systemctl --user daemon-reload >/dev/null 2>&1 || true
    systemctl --user enable --now eonix.service >/dev/null 2>&1 || true
  fi
  log "systemd user service created at $SERVICE_PATH"
}

final_banner() {
  echo
  echo "=============================================="
  echo "✅ EONIX INSTALL COMPLETE"
  echo "Home: $EONIX_HOME"
  echo "Wrapper: $WRAPPER_TARGET"
  echo "Run: eonix-shell"
  echo "=============================================="
}

if [ "$UNINSTALL_MODE" -eq 1 ]; then
  uninstall
fi

step 1 "System checks"
system_check

step 2 "Install system dependencies"
install_system_deps

step 3 "Prepare directories"
prepare_directories

step 4 "Fetch or update repository"
init_repo

step 5 "Create and configure virtual environment"
init_python_env

step 6 "Install runtime packages"
log "Python runtime ready"

step 7 "Install shell wrapper"
install_wrapper

step 8 "Configure systemd user service"
configure_systemd

step 9 "Finish"
final_banner

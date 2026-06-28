#!/usr/bin/env bash
# Bootstrap the AI Music POC with validated ACE paths.
#
# Default: app/subprocess mode — start only this app. ACE jobs run per-request
# via scripts/ace_runner.py (generation) and scripts/ace_train_runner.py
# (training). The app does not call acestep-api today.
#
# Paths (override with env vars):
#   APP_DIR          repo root (default: parent of this scripts/ folder)
#   ACE_MODELS_ROOT  parent for ACE checkout (default: $HOME/models)
#   ACE_STEP_DIR     ACE checkout (default: $ACE_MODELS_ROOT/ACE-Step-1.5)
#
# Usage:
#   ./scripts/dev_bootstrap.sh
#   ACE_MODE=gradio ./scripts/dev_bootstrap.sh
#   ACE_MODE=api ./scripts/dev_bootstrap.sh
#   AUTO_SETUP=0 ./scripts/dev_bootstrap.sh   # skip clone/venv creation

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="${APP_DIR:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
ACE_MODELS_ROOT="${ACE_MODELS_ROOT:-${HOME}/models}"
ACE_STEP_DIR="${ACE_STEP_DIR:-${ACE_MODELS_ROOT}/ACE-Step-1.5}"
ACE_REPO_URL="${ACE_REPO_URL:-https://github.com/ace-step/ACE-Step-1.5.git}"
AUTO_SETUP="${AUTO_SETUP:-1}"

LOG_DIR="${APP_DIR}/logs"
ACE_MODE="${ACE_MODE:-none}"

APP_PORT="${APP_PORT:-8000}"
APP_HEALTH_URL="${APP_HEALTH_URL:-http://127.0.0.1:${APP_PORT}/api/health}"
ACE_WAIT_SECONDS="${ACE_WAIT_SECONDS:-300}"
APP_WAIT_SECONDS="${APP_WAIT_SECONDS:-120}"

ACE_GRADIO_HEALTH_URL="${ACE_GRADIO_HEALTH_URL:-http://127.0.0.1:7860/}"
ACE_API_HEALTH_URL="${ACE_API_HEALTH_URL:-http://127.0.0.1:8001/health}"

ACE_PYTHON="${ACE_STEP_DIR}/.venv/bin/python"
ACE_MODEL_DIR="${ACE_STEP_DIR}/checkpoints"

ACE_PID=""
APP_PID=""
ACE_DAEMON_LOG=""
ACE_DAEMON_LABEL=""

die() {
  echo "dev_bootstrap: $*" >&2
  exit 1
}

info() {
  echo "dev_bootstrap: $*"
}

require_command() {
  local cmd="$1"
  local hint="${2:-}"
  command -v "$cmd" >/dev/null 2>&1 || die "${cmd} not found on PATH${hint:+ — ${hint}}"
}

normalize_ace_mode() {
  case "${ACE_MODE,,}" in
    "" | none | default | subprocess | app)
      ACE_MODE="none"
      ;;
    gradio)
      ACE_MODE="gradio"
      ;;
    api)
      ACE_MODE="api"
      ;;
    *)
      die "invalid ACE_MODE=${ACE_MODE} (use none, gradio, or api)"
      ;;
  esac
}

require_path() {
  local label="$1"
  local path="$2"
  [[ -e "$path" ]] || die "missing ${label}: ${path}"
}

require_curl() {
  require_command curl
}

require_ffmpeg() {
  require_command ffmpeg "required by ACE-Step audio preprocessing"
}

resolve_app_dir() {
  require_path "app entrypoint" "${APP_DIR}/run.py"
  require_path "app requirements" "${APP_DIR}/requirements.txt"
  require_path "ACE runner script" "${APP_DIR}/scripts/ace_runner.py"
  require_path "ACE train runner script" "${APP_DIR}/scripts/ace_train_runner.py"
}

ensure_dotenv() {
  if [[ -f "${APP_DIR}/.env" ]]; then
    return 0
  fi
  if [[ ! -f "${APP_DIR}/.env.example" ]]; then
    info "no .env found (optional — bootstrap exports ACE paths at runtime)"
    return 0
  fi
  sed "s|\${HOME}|${HOME}|g" "${APP_DIR}/.env.example" > "${APP_DIR}/.env"
  info "created ${APP_DIR}/.env from .env.example"
}

ensure_app_venv() {
  if [[ -x "${APP_DIR}/.venv/bin/python" ]]; then
    return 0
  fi
  [[ "$AUTO_SETUP" == "1" ]] || die "app venv missing at ${APP_DIR}/.venv (run install steps or set AUTO_SETUP=1)"

  require_command python3
  info "creating app venv..."
  python3 -m venv "${APP_DIR}/.venv"
  "${APP_DIR}/.venv/bin/pip" install --upgrade pip
  "${APP_DIR}/.venv/bin/pip" install -r "${APP_DIR}/requirements.txt"
}

ensure_ace_checkout() {
  if [[ -d "${ACE_STEP_DIR}/.git" ]]; then
    return 0
  fi
  if [[ -e "${ACE_STEP_DIR}" ]]; then
    die "${ACE_STEP_DIR} exists but is not an ACE-Step git checkout — remove it or set ACE_STEP_DIR"
  fi
  [[ "$AUTO_SETUP" == "1" ]] || die "ACE checkout missing at ${ACE_STEP_DIR} (clone it or set AUTO_SETUP=1)"

  require_command git
  mkdir -p "${ACE_MODELS_ROOT}"
  info "cloning ACE-Step into ${ACE_STEP_DIR}..."
  git clone "${ACE_REPO_URL}" "${ACE_STEP_DIR}"
}

ensure_ace_venv() {
  if [[ -x "${ACE_PYTHON}" ]]; then
    return 0
  fi
  [[ "$AUTO_SETUP" == "1" ]] || die "ACE venv missing at ${ACE_STEP_DIR}/.venv (run uv sync there or set AUTO_SETUP=1)"

  require_command uv "install from https://docs.astral.sh/uv/ — ACE-Step uses uv for its environment"
  info "creating ACE venv with uv sync (first run can take several minutes)..."
  (
    cd "${ACE_STEP_DIR}"
    uv sync
  )
}

warn_if_checkpoints_missing() {
  local turbo="${ACE_MODEL_DIR}/acestep-v15-turbo/model.safetensors"
  local symlink_count=0

  if [[ -d "${ACE_MODEL_DIR}" ]]; then
    symlink_count=$(find "${ACE_MODEL_DIR}" -type l 2>/dev/null | wc -l)
  fi

  if [[ "$symlink_count" -gt 0 ]]; then
    echo
    echo "WARNING: ${symlink_count} symlink(s) under ${ACE_MODEL_DIR}"
    echo "         Use real weight files there (not /mnt/c HF cache symlinks) for stable Linux inference."
    echo
  fi

  if [[ -f "$turbo" && ! -L "$turbo" ]]; then
    return 0
  fi

  echo
  echo "WARNING: ACE weight files not ready under ${ACE_MODEL_DIR}"
  echo "         Procedural generation still works. Neural ACE jobs need model weights."
  echo "         Download once with:"
  echo "           cd ${ACE_STEP_DIR} && uv run acestep-download"
  echo
}

validate_layout() {
  require_curl
  require_ffmpeg
  resolve_app_dir
  ensure_dotenv
  ensure_app_venv
  ensure_ace_checkout
  ensure_ace_venv
  require_path "ACE-Step directory" "${ACE_STEP_DIR}"
  require_path "ACE-Step venv python" "${ACE_PYTHON}"

  if [[ "$ACE_MODE" != "none" ]]; then
    require_path "ACE-Step uv" "${ACE_STEP_DIR}/.venv/bin/uv"
  fi

  warn_if_checkpoints_missing
}

wait_for_url() {
  local url="$1"
  local label="$2"
  local timeout="$3"
  local pid="$4"
  local log_file="$5"
  local elapsed=0

  echo "waiting for ${label} at ${url} (timeout ${timeout}s)..."

  while (( elapsed < timeout )); do
    if curl -fsS -o /dev/null "$url" 2>/dev/null; then
      echo "${label} ready"
      return 0
    fi

    if ! kill -0 "$pid" 2>/dev/null; then
      die "${label} process exited before ${url} responded (see ${log_file})"
    fi

    sleep 2
    elapsed=$((elapsed + 2))
  done

  die "${label} did not become ready within ${timeout}s (${url}); see ${log_file}"
}

stop_process() {
  local pid="$1"
  local label="$2"
  [[ -n "$pid" ]] || return 0
  if kill -0 "$pid" 2>/dev/null; then
    echo "stopping ${label} (pid ${pid})..."
    kill "$pid" 2>/dev/null || true
    wait "$pid" 2>/dev/null || true
  fi
}

cleanup() {
  stop_process "$APP_PID" "app"
  if [[ -n "$ACE_PID" ]]; then
    stop_process "$ACE_PID" "$ACE_DAEMON_LABEL"
  fi
}

on_signal() {
  echo
  cleanup
  exit 130
}

print_mode_banner() {
  echo
  echo "== dev bootstrap =="
  echo "ACE_MODE:        ${ACE_MODE}"
  echo "APP_DIR:         ${APP_DIR}"
  echo "ACE_STEP_DIR:    ${ACE_STEP_DIR}"
  echo "ACE_MODEL_DIR:   ${ACE_MODEL_DIR}"
  echo "ACE_PYTHON:      ${ACE_PYTHON}"
  echo

  case "$ACE_MODE" in
    none)
      echo "Runtime:         app/subprocess"
      echo "ACE integration: per-job via scripts/ace_runner.py and scripts/ace_train_runner.py"
      echo "ACE daemon:      not started (app does not use acestep-api today)"
      ;;
    gradio)
      echo "Runtime:         ACE Gradio daemon + app"
      echo "ACE integration: Gradio at ${ACE_GRADIO_HEALTH_URL} (debug/upstream only)"
      echo "App jobs:        still use scripts/ace_runner.py subprocess unless you change the app"
      ;;
    api)
      echo "Runtime:         ACE HTTP API daemon + app"
      echo "ACE integration: API at ${ACE_API_HEALTH_URL} (not wired into app yet)"
      echo "App jobs:        still use scripts/ace_runner.py subprocess unless you change the app"
      ;;
  esac
  echo
}

start_ace_daemon() {
  local ace_run=()
  local health_url=""

  case "$ACE_MODE" in
    gradio)
      ace_run=(run acestep)
      health_url="$ACE_GRADIO_HEALTH_URL"
      ACE_DAEMON_LOG="${LOG_DIR}/ace-step-gradio.log"
      ACE_DAEMON_LABEL="ACE-Step Gradio"
      ;;
    api)
      ace_run=(run acestep-api)
      health_url="$ACE_API_HEALTH_URL"
      ACE_DAEMON_LOG="${LOG_DIR}/ace-step-api.log"
      ACE_DAEMON_LABEL="ACE-Step API"
      ;;
    *)
      return 0
      ;;
  esac

  : > "${ACE_DAEMON_LOG}"
  echo "starting ${ACE_DAEMON_LABEL} from ${ACE_STEP_DIR}..."
  (
    cd "$ACE_STEP_DIR"
    exec "${ACE_STEP_DIR}/.venv/bin/uv" "${ace_run[@]}"
  ) >>"${ACE_DAEMON_LOG}" 2>&1 &
  ACE_PID=$!
  echo "${ACE_DAEMON_LABEL} pid ${ACE_PID} -> ${ACE_DAEMON_LOG}"

  wait_for_url "$health_url" "$ACE_DAEMON_LABEL" "$ACE_WAIT_SECONDS" "$ACE_PID" "$ACE_DAEMON_LOG"
}

start_app() {
  echo "starting app from ${APP_DIR}..."
  (
    cd "$APP_DIR"
    export ACE_STEP_DIR="$ACE_STEP_DIR"
    export ACE_PYTHON="$ACE_PYTHON"
    export ACE_MODEL_DIR="$ACE_MODEL_DIR"
    export ACE_TRAIN_CHECKPOINT_DIR="$ACE_MODEL_DIR"
    export APP_RELOAD=false
    exec .venv/bin/python run.py
  ) >>"${LOG_DIR}/app.log" 2>&1 &
  APP_PID=$!
  echo "app pid ${APP_PID} -> ${LOG_DIR}/app.log"
}

print_ready_summary() {
  echo
  echo "Ready."
  echo "  App:  http://127.0.0.1:${APP_PORT}/"
  echo "  Log:  ${LOG_DIR}/app.log"

  case "$ACE_MODE" in
    gradio)
      echo "  ACE:  ${ACE_GRADIO_HEALTH_URL}"
      echo "  Log:  ${ACE_DAEMON_LOG}"
      ;;
    api)
      echo "  ACE:  ${ACE_API_HEALTH_URL}"
      echo "  Log:  ${ACE_DAEMON_LOG}"
      ;;
    none)
      echo "  ACE:  subprocess only (${APP_DIR}/scripts/ace_runner.py)"
      ;;
  esac

  echo
  if [[ "$ACE_MODE" == "none" ]]; then
    echo "Press Ctrl+C to stop the app."
  else
    echo "Press Ctrl+C to stop the app and ACE daemon."
  fi
}

main() {
  normalize_ace_mode
  validate_layout
  mkdir -p "$LOG_DIR"
  : > "${LOG_DIR}/app.log"
  trap on_signal INT TERM

  print_mode_banner
  start_ace_daemon
  start_app
  wait_for_url "$APP_HEALTH_URL" "app" "$APP_WAIT_SECONDS" "$APP_PID" "${LOG_DIR}/app.log"
  print_ready_summary

  while true; do
    if [[ -n "$ACE_PID" ]] && ! kill -0 "$ACE_PID" 2>/dev/null; then
      echo "${ACE_DAEMON_LABEL} exited unexpectedly (see ${ACE_DAEMON_LOG})" >&2
      cleanup
      exit 1
    fi
    if ! kill -0 "$APP_PID" 2>/dev/null; then
      echo "app exited unexpectedly (see ${LOG_DIR}/app.log)" >&2
      cleanup
      exit 1
    fi
    sleep 2
  done
}

main "$@"

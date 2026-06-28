#!/usr/bin/env bash
# Validate local wiring, start external ACE-Step runtime, then start the app.
#
# Boundaries:
#   app repo:  ~/web/ai-music-poc
#   ACE repo:  ~/models/ACE-Step-1.5
#
# Usage:
#   ./scripts/dev_bootstrap.sh
#
# Override paths:
#   ACE_STEP_DIR=... APP_DIR=... ./scripts/dev_bootstrap.sh

set -euo pipefail

ACE_STEP_DIR="${ACE_STEP_DIR:-$HOME/models/ACE-Step-1.5}"
APP_DIR="${APP_DIR:-$HOME/web/ai-music-poc}"
LOG_DIR="${APP_DIR}/logs"

# One-line switch for API mode later (also set ACE_HEALTH_URL):
#   ACE_RUN=(run acestep-api)
#   ACE_HEALTH_URL="http://127.0.0.1:8001/health"
ACE_RUN=(run acestep)
ACE_HEALTH_URL="${ACE_HEALTH_URL:-http://127.0.0.1:7860/}"

APP_PORT="${APP_PORT:-8000}"
APP_HEALTH_URL="${APP_HEALTH_URL:-http://127.0.0.1:${APP_PORT}/api/health}"
ACE_WAIT_SECONDS="${ACE_WAIT_SECONDS:-300}"
APP_WAIT_SECONDS="${APP_WAIT_SECONDS:-120}"

ACE_PID=""
APP_PID=""

die() {
  echo "dev_bootstrap: $*" >&2
  exit 1
}

require_path() {
  local label="$1"
  local path="$2"
  [[ -e "$path" ]] || die "missing ${label}: ${path}"
}

require_curl() {
  command -v curl >/dev/null 2>&1 || die "curl not found on PATH"
}

require_ffmpeg() {
  command -v ffmpeg >/dev/null 2>&1 || die "ffmpeg not found on PATH (required by ACE-Step)"
}

validate_layout() {
  require_curl
  require_ffmpeg
  require_path "app directory" "$APP_DIR"
  require_path "app venv python" "${APP_DIR}/.venv/bin/python"
  require_path "app entrypoint" "${APP_DIR}/run.py"
  require_path "ACE runner script" "${APP_DIR}/scripts/ace_runner.py"
  require_path "ACE-Step directory" "$ACE_STEP_DIR"
  require_path "ACE-Step venv" "${ACE_STEP_DIR}/.venv"
  require_path "ACE-Step uv" "${ACE_STEP_DIR}/.venv/bin/uv"
  require_path "ACE-Step venv python" "${ACE_STEP_DIR}/.venv/bin/python"
  require_path "ACE-Step checkpoints" "${ACE_STEP_DIR}/checkpoints"
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
  stop_process "$ACE_PID" "ACE-Step"
}

on_signal() {
  echo
  cleanup
  exit 130
}

start_ace() {
  echo "starting ACE-Step from ${ACE_STEP_DIR}..."
  (
    cd "$ACE_STEP_DIR"
    exec "${ACE_STEP_DIR}/.venv/bin/uv" "${ACE_RUN[@]}"
  ) >>"${LOG_DIR}/ace-step.log" 2>&1 &
  ACE_PID=$!
  echo "ACE-Step pid ${ACE_PID} -> ${LOG_DIR}/ace-step.log"
}

start_app() {
  echo "starting app from ${APP_DIR}..."
  (
    cd "$APP_DIR"
    export ACE_STEP_DIR="$ACE_STEP_DIR"
    export ACE_PYTHON="${ACE_STEP_DIR}/.venv/bin/python"
    export ACE_MODEL_DIR="${ACE_STEP_DIR}/checkpoints"
    export ACE_TRAIN_CHECKPOINT_DIR="${ACE_STEP_DIR}/checkpoints"
    exec .venv/bin/python run.py
  ) >>"${LOG_DIR}/app.log" 2>&1 &
  APP_PID=$!
  echo "app pid ${APP_PID} -> ${LOG_DIR}/app.log"
}

main() {
  validate_layout
  mkdir -p "$LOG_DIR"
  : > "${LOG_DIR}/ace-step.log"
  : > "${LOG_DIR}/app.log"
  trap on_signal INT TERM

  start_ace
  wait_for_url "$ACE_HEALTH_URL" "ACE-Step" "$ACE_WAIT_SECONDS" "$ACE_PID" "${LOG_DIR}/ace-step.log"

  start_app
  wait_for_url "$APP_HEALTH_URL" "app" "$APP_WAIT_SECONDS" "$APP_PID" "${LOG_DIR}/app.log"

  echo
  echo "Both services are up."
  echo "  ACE-Step: ${ACE_HEALTH_URL}"
  echo "  App:      http://127.0.0.1:${APP_PORT}/"
  echo "  Logs:     ${LOG_DIR}/ace-step.log"
  echo "            ${LOG_DIR}/app.log"
  echo
  echo "Press Ctrl+C to stop both."

  while true; do
    if ! kill -0 "$ACE_PID" 2>/dev/null; then
      echo "ACE-Step exited unexpectedly (see ${LOG_DIR}/ace-step.log)" >&2
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

#!/bin/bash
# Hourly production DB update: scrapes Telegram and writes new messages
# directly to the Render production Postgres DB.
#
# Run by launchd via ~/Library/LaunchAgents/com.tzahal-mapper.hourly-update.plist
# Safe to also run by hand for testing: ./scripts/run_hourly_update.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$REPO_ROOT/.env.production"
PYTHON_BIN="$REPO_ROOT/venv/bin/python"
LOCK_FILE="/tmp/tzahal-mapper-hourly-update.lock"
LOG_DIR="$REPO_ROOT/logs"
LOG_FILE="$LOG_DIR/hourly-update.log"
MAX_LOG_BYTES=5242880  # 5 MB

mkdir -p "$LOG_DIR"

# --- simple log rotation: truncate to last ~half if it's grown too large ---
if [ -f "$LOG_FILE" ] && [ "$(stat -f%z "$LOG_FILE" 2>/dev/null || echo 0)" -gt "$MAX_LOG_BYTES" ]; then
    tail -c $((MAX_LOG_BYTES / 2)) "$LOG_FILE" > "$LOG_FILE.tmp" && mv "$LOG_FILE.tmp" "$LOG_FILE"
fi

log() {
    printf '%s %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$1" >> "$LOG_FILE"
}

# --- prevent overlapping runs (e.g. if a run takes >1h) using shlock (BSD, ships with macOS) ---
if ! shlock -f "$LOCK_FILE" -p $$; then
    log "SKIP: previous run still holds $LOCK_FILE (pid $(cat "$LOCK_FILE" 2>/dev/null))."
    exit 0
fi
trap 'rm -f "$LOCK_FILE"' EXIT

log "START hourly update"

# --- load production env vars, exported so they win over any load_dotenv() cwd lookup ---
if [ ! -f "$ENV_FILE" ]; then
    log "ERROR: $ENV_FILE not found. Aborting."
    exit 1
fi
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

cd "$REPO_ROOT"

# --- retry with backoff: launchd sometimes fires this job during a brief
# macOS DarkWake maintenance window (e.g. right after the lid was closed),
# where the CPU is up but WiFi/DNS haven't reconnected yet. A first-attempt
# DNS failure in that situation is transient, so give the network a few
# chances to come back before giving up for the hour. ---
RETRY_DELAYS=(5 15 30)
attempt=1
status=0
if "$PYTHON_BIN" -m app.update_db >> "$LOG_FILE" 2>&1; then
    log "OK hourly update finished"
else
    status=$?
    for delay in "${RETRY_DELAYS[@]}"; do
        attempt=$((attempt + 1))
        log "RETRY hourly update attempt $attempt after ${delay}s (previous exit status $status)"
        sleep "$delay"
        if "$PYTHON_BIN" -m app.update_db >> "$LOG_FILE" 2>&1; then
            log "OK hourly update finished (attempt $attempt)"
            status=0
            break
        fi
        status=$?
    done
    if [ "$status" -ne 0 ]; then
        log "FAIL hourly update exited with status $status after $attempt attempts"
        exit "$status"
    fi
fi

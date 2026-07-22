#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STATE_DIR="$ROOT/data/run_state"
LOG_DIR="$ROOT/logs"
PID_FILE="$STATE_DIR/linkedin_local_crawl.pid"
mkdir -p "$STATE_DIR" "$LOG_DIR"

if [ -f "$PID_FILE" ]; then
  existing_pid="$(cat "$PID_FILE" || true)"
  if [ -n "$existing_pid" ] && kill -0 "$existing_pid" 2>/dev/null; then
    echo "LinkedIn local crawl is already running with pid $existing_pid"
    echo "Log: $(ls -t "$LOG_DIR"/linkedin-local-crawl-*.log 2>/dev/null | head -1)"
    exit 0
  fi
fi

timestamp="$(date +%Y%m%d-%H%M%S)"
log_file="$LOG_DIR/linkedin-local-crawl-$timestamp.log"

nohup python3 "$ROOT/scripts/run_linkedin_local_crawl.py" \
  --until-complete \
  --target-jobs "${LINKEDIN_TARGET_JOBS:-371000}" \
  --max-runtime-hours "${LINKEDIN_MAX_RUNTIME_HOURS:-12}" \
  --max-partitions "${LINKEDIN_MAX_PARTITIONS:-720}" \
  --backfill-details "${LINKEDIN_BACKFILL_DETAILS:-0}" \
  --build-report \
  "$@" >"$log_file" 2>&1 &

pid="$!"
echo "Started LinkedIn local crawl pid=$pid"
echo "Log: $log_file"
echo "Follow with: tail -f \"$log_file\""

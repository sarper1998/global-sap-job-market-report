#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PID_FILE="$ROOT/data/run_state/company_career_crawl.pid"
LOG_DIR="$ROOT/logs"
mkdir -p "$LOG_DIR" "$ROOT/data/run_state"

if [ -f "$PID_FILE" ]; then
  existing_pid="$(cat "$PID_FILE")"
  if kill -0 "$existing_pid" 2>/dev/null; then
    echo "Company career crawl is already running with pid $existing_pid"
    exit 0
  fi
fi

timestamp="$(date +"%Y%m%d-%H%M%S")"
log_file="$LOG_DIR/company-career-crawl-$timestamp.log"
python3 "$ROOT/scripts/fetch_company_career_jobs.py" "$@" > "$log_file" 2>&1 &
pid=$!
echo "Started company career crawl pid=$pid"
echo "Log: $log_file"

#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$ROOT/logs"
STATE_DIR="$ROOT/data/run_state"
mkdir -p "$LOG_DIR" "$STATE_DIR"

background=0
if [ "${1:-}" = "--background" ]; then
  background=1
  shift
fi

worker_id="${1:-${LINKEDIN_WORKER_ID:-}}"
offset="${2:-${LINKEDIN_PARTITION_OFFSET:-}}"
limit="${3:-${LINKEDIN_MAX_PARTITIONS:-}}"

if [ -z "$worker_id" ] || [ -z "$offset" ] || [ -z "$limit" ]; then
  echo "Usage: $0 [--background] <worker_id> <partition_offset> <partition_limit>"
  exit 2
fi

if ! [[ "$worker_id" =~ ^[A-Za-z0-9._-]+$ ]]; then
  echo "worker_id can only contain letters, numbers, dot, underscore, and hyphen"
  exit 2
fi

pid_file="$STATE_DIR/linkedin_worker_${worker_id}.pid"
if [ -f "$pid_file" ]; then
  existing_pid="$(cat "$pid_file" || true)"
  if [ -n "$existing_pid" ] && kill -0 "$existing_pid" 2>/dev/null; then
    echo "LinkedIn worker $worker_id is already running with pid $existing_pid"
    exit 0
  fi
fi

timestamp="$(date +%Y%m%d-%H%M%S)"
log_file="$LOG_DIR/linkedin-worker-${worker_id}-${timestamp}.log"
output_dir="${LINKEDIN_WORKER_OUTPUT_DIR:-$ROOT/data/worker_outputs/$worker_id}"
python_bin="${PYTHON:-python3}"

export SNAPSHOT_DATE="${SNAPSHOT_DATE:-$(date +%F)}"
export LINKEDIN_WORKER_ID="$worker_id"
export LINKEDIN_WORKER_OUTPUT_DIR="$output_dir"
export LINKEDIN_QUERY_FILE="${LINKEDIN_QUERY_FILE:-$ROOT/data/config/linkedin_queries_expanded.txt}"
export LINKEDIN_LOCATION_FILE="${LINKEDIN_LOCATION_FILE:-$ROOT/data/config/linkedin_locations_expanded.txt}"
export LINKEDIN_FILTERS="${LINKEDIN_FILTERS:-all,past_24h,past_week,past_month,onsite,remote,hybrid,past_week_remote,past_week_hybrid}"
export LINKEDIN_PARTITION_OFFSET="$offset"
export LINKEDIN_MAX_PARTITIONS="$limit"
export LINKEDIN_MAX_PAGES_PER_SEARCH="${LINKEDIN_MAX_PAGES_PER_SEARCH:-8}"
export LINKEDIN_MAX_DETAILS="${LINKEDIN_MAX_DETAILS:-0}"
export LINKEDIN_REQUEST_DELAY_SECONDS="${LINKEDIN_REQUEST_DELAY_SECONDS:-0.6}"
export LINKEDIN_REQUEST_TIMEOUT_SECONDS="${LINKEDIN_REQUEST_TIMEOUT_SECONDS:-15}"
export LINKEDIN_RATE_LIMIT_SLEEP_SECONDS="${LINKEDIN_RATE_LIMIT_SLEEP_SECONDS:-120}"
export LINKEDIN_RATE_LIMIT_RETRIES="${LINKEDIN_RATE_LIMIT_RETRIES:-0}"
export LINKEDIN_SAVE_EVERY_PARTITIONS="${LINKEDIN_SAVE_EVERY_PARTITIONS:-25}"
export LINKEDIN_PRINT_FULL_SUMMARY="${LINKEDIN_PRINT_FULL_SUMMARY:-0}"

run_worker() {
  echo "${BASHPID:-$$}" > "$pid_file"
  trap 'rm -f "$pid_file"' EXIT
  echo "Worker: $worker_id"
  echo "Output: $output_dir"
  echo "Offset/limit: $offset/$limit"
  echo "Log: $log_file"
  "$python_bin" "$ROOT/scripts/fetch_linkedin_guest_jobs.py"
}

if [ "$background" = "1" ]; then
  run_worker >"$log_file" 2>&1 </dev/null &
  pid="$!"
  disown "$pid" 2>/dev/null || true
  echo "Started LinkedIn worker $worker_id pid=$pid"
  echo "Output: $output_dir"
  echo "Log: $log_file"
  echo "Follow with: tail -f \"$log_file\""
else
  run_worker 2>&1 | tee "$log_file"
fi

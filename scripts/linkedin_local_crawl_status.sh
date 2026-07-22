#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STATE_FILE="$ROOT/data/run_state/linkedin_local_crawl_state.json"
PID_FILE="$ROOT/data/run_state/linkedin_local_crawl.pid"
LOG_DIR="$ROOT/logs"
SUMMARY_FILE="$ROOT/data/processed/linkedin_jobs_summary.json"

if [ "${1:-}" = "stop" ]; then
  if [ ! -f "$PID_FILE" ]; then
    echo "No local crawl pid file found."
    exit 0
  fi
  pid="$(cat "$PID_FILE")"
  if kill -0 "$pid" 2>/dev/null; then
    kill "$pid"
    echo "Sent stop signal to pid $pid"
  else
    echo "Pid $pid is not running."
  fi
  exit 0
fi

if [ -f "$PID_FILE" ]; then
  pid="$(cat "$PID_FILE")"
  if kill -0 "$pid" 2>/dev/null; then
    echo "Running: pid $pid"
  else
    echo "Not running. Stale pid file: $pid"
  fi
else
  echo "Not running."
fi

if [ -f "$STATE_FILE" ]; then
  python3 - <<PY
import json
state = json.load(open("$STATE_FILE"))
print("State:")
for key in ["snapshot_date", "next_offset", "total_partitions", "cycles_completed", "last_completed_at"]:
    if key in state:
        print(f"  {key}: {state[key]}")
history = state.get("history") or []
if history:
    print("Last batch:")
    for key, value in history[-1].items():
        print(f"  {key}: {value}")
PY
fi

if [ -f "$SUMMARY_FILE" ]; then
  python3 - <<PY
import json
summary = json.load(open("$SUMMARY_FILE"))
print("Saved summary:")
for key in ["jobs_collected", "jobs_seen_in_snapshot", "new_jobs_in_snapshot", "description_enriched_jobs", "latest_run_partition_offset", "latest_run_searches_attempted", "generated_at"]:
    print(f"  {key}: {summary.get(key)}")
PY
fi

latest_log="$(ls -t "$LOG_DIR"/linkedin-local-crawl-*.log 2>/dev/null | head -1 || true)"
monthly_log="$LOG_DIR/linkedin-monthly-launchd.out.log"
if [ -f "$monthly_log" ]; then
  monthly_total="$(grep -Eo 'total [0-9]+' "$monthly_log" 2>/dev/null | tail -1 | awk '{print $2}' || true)"
  if [ -n "$monthly_total" ]; then
    echo "Latest live log total: $monthly_total"
  fi
fi
if [ -n "$latest_log" ]; then
  echo "Latest log: $latest_log"
  echo "Tail with: tail -f \"$latest_log\""
fi

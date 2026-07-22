#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PID_FILE="$ROOT/data/run_state/company_career_crawl.pid"
SUMMARY_FILE="$ROOT/data/processed/company_career_jobs_summary.json"
LOG_DIR="$ROOT/logs"

if [ "${1:-}" = "stop" ]; then
  if [ ! -f "$PID_FILE" ]; then
    echo "No company career crawl pid file found."
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

if [ -f "$SUMMARY_FILE" ]; then
  python3 - <<PY
import json
summary = json.load(open("$SUMMARY_FILE"))
print("Saved summary:")
for key in ["generated_at", "jobs_collected", "sap_jobs_after_filter"]:
    print(f"  {key}: {summary.get(key)}")
print("Providers:")
for key, value in (summary.get("providers") or {}).items():
    print(f"  {key}: {value}")
print("Top companies:")
for key, value in list((summary.get("companies") or {}).items())[:8]:
    print(f"  {key}: {value}")
PY
fi

monthly_log="$LOG_DIR/company-careers-launchd.out.log"
latest_log="$(ls -t "$LOG_DIR"/company-career-crawl-*.log 2>/dev/null | head -1 || true)"
if [ -f "$monthly_log" ]; then
  echo "LaunchAgent log: $monthly_log"
  tail -n 12 "$monthly_log"
elif [ -n "$latest_log" ]; then
  echo "Latest log: $latest_log"
  tail -n 12 "$latest_log"
fi

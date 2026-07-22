#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PID_FILE="$ROOT/data/run_state/daily_delta.pid"
SUMMARY_FILE="$ROOT/data/processed/daily_delta_summary.json"
LOG_FILE="$ROOT/logs/daily-delta-launchd.out.log"
ERR_FILE="$ROOT/logs/daily-delta-launchd.err.log"

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
print("Saved daily delta:")
for key in ["generated_at", "snapshot_date", "mode"]:
    print(f"  {key}: {summary.get(key)}")
for section in ["linkedin", "company_careers"]:
    data = summary.get(section) or {}
    print(f"{section}:")
    for key in ["status", "jobs_before", "jobs_after", "net_new_jobs", "jobs_seen_in_snapshot", "new_jobs_in_snapshot"]:
        print(f"  {key}: {data.get(key)}")
PY
fi

if [ -f "$LOG_FILE" ]; then
  echo "Latest daily log:"
  tail -n 18 "$LOG_FILE"
fi
if [ -s "$ERR_FILE" ]; then
  echo "Latest daily errors:"
  tail -n 18 "$ERR_FILE"
fi

#!/usr/bin/env bash
set -eo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON:-python3}"

echo "Worker processes:"
shopt -s nullglob
declare -a pid_files
declare -a win_pid_files
pid_files=("$ROOT"/data/run_state/linkedin_worker_*.pid)
win_pid_files=("$ROOT"/data/run_state/linkedin_worker_*.winpid)
if [ "${#pid_files[@]}" -eq 0 ] && [ "${#win_pid_files[@]}" -eq 0 ]; then
  echo "  none"
else
  for pid_file in "${pid_files[@]}"; do
    worker="$(basename "$pid_file" | sed 's/^linkedin_worker_//; s/\.pid$//')"
    pid="$(cat "$pid_file" || true)"
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
      echo "  $worker: running pid $pid"
    else
      echo "  $worker: stale pid $pid"
    fi
  done
  for pid_file in "${win_pid_files[@]}"; do
    worker="$(basename "$pid_file" | sed 's/^linkedin_worker_//; s/\.winpid$//')"
    pid="$(cat "$pid_file" || true)"
    if powershell.exe -NoProfile -Command "if (Get-Process -Id $pid -ErrorAction SilentlyContinue) { exit 0 } else { exit 1 }" >/dev/null 2>&1; then
      echo "  $worker: running Windows pid $pid"
    else
      echo "  $worker: stale Windows pid $pid"
    fi
  done
fi

active_commands="$(ps -ef | grep '[f]etch_linkedin_guest_jobs.py' || true)"
if [ -n "$active_commands" ]; then
  echo "Active crawler commands:"
  echo "$active_commands" | sed 's/^/  /'
fi

echo "Worker outputs:"
summary_files=("$ROOT"/data/worker_outputs/*/linkedin_jobs_summary.json)
if [ "${#summary_files[@]}" -eq 0 ]; then
  echo "  none"
else
  "$PYTHON_BIN" - "$ROOT" "${summary_files[@]}" <<'PY'
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
for raw_path in sys.argv[2:]:
    path = Path(raw_path)
    summary = json.loads(path.read_text(encoding="utf-8"))
    rel = path.relative_to(root)
    print(
        "  "
        + str(rel.parent)
        + ": jobs="
        + str(summary.get("jobs_collected", 0))
        + " offset="
        + str(summary.get("latest_run_partition_offset"))
        + " limit="
        + str(summary.get("latest_run_partition_limit"))
        + " attempted="
        + str(summary.get("latest_run_searches_attempted", 0))
        + " generated_at="
        + str(summary.get("generated_at", ""))
    )
PY
fi

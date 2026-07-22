#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$ROOT/logs"
STATE_DIR="$ROOT/data/run_state"
DAILY_PID_FILE="$STATE_DIR/daily_delta.pid"
LINKEDIN_FULL_PID_FILE="$STATE_DIR/linkedin_local_crawl.pid"
COMPANY_PID_FILE="$STATE_DIR/company_career_crawl.pid"
MONTHLY_LINKEDIN_LABEL="com.sap-market-report.linkedin-monthly"
MONTHLY_LINKEDIN_PLIST="$HOME/Library/LaunchAgents/$MONTHLY_LINKEDIN_LABEL.plist"
SNAPSHOT_DATE="${SNAPSHOT_DATE:-$(date +%F)}"

mkdir -p "$LOG_DIR" "$STATE_DIR" "$ROOT/data/processed" "$ROOT/data/snapshots/$SNAPSHOT_DATE"

if [ -f "$DAILY_PID_FILE" ]; then
  existing_pid="$(cat "$DAILY_PID_FILE")"
  if kill -0 "$existing_pid" 2>/dev/null; then
    echo "Daily delta is already running with pid $existing_pid"
    exit 0
  fi
fi

echo "$$" > "$DAILY_PID_FILE"
cleanup() {
  if [ -f "$DAILY_PID_FILE" ] && [ "$(cat "$DAILY_PID_FILE")" = "$$" ]; then
    rm -f "$DAILY_PID_FILE"
  fi
}
trap cleanup EXIT

json_value() {
  local file="$1"
  local key="$2"
  python3 - "$file" "$key" <<'PY'
import json, pathlib, sys
path = pathlib.Path(sys.argv[1])
key = sys.argv[2]
if not path.exists():
    print(0)
    raise SystemExit
try:
    data = json.loads(path.read_text(encoding="utf-8"))
except Exception:
    print(0)
    raise SystemExit
print(data.get(key) or 0)
PY
}

is_running_pid_file() {
  local file="$1"
  if [ ! -f "$file" ]; then
    return 1
  fi
  local pid
  pid="$(cat "$file")"
  [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null
}

maybe_disable_idle_monthly_full() {
  if [ ! -f "$MONTHLY_LINKEDIN_PLIST" ]; then
    return
  fi
  local launch_pid
  launch_pid="$(launchctl list 2>/dev/null | awk -v label="$MONTHLY_LINKEDIN_LABEL" '$3 == label {print $1}')"
  if [ "$launch_pid" = "-" ] || [ -z "$launch_pid" ]; then
    launchctl unload "$MONTHLY_LINKEDIN_PLIST" 2>/dev/null || true
    echo "Disabled idle monthly full LinkedIn crawler; daily delta now owns routine updates."
  fi
}

write_delta_summary() {
  local linkedin_before="$1"
  local linkedin_after="$2"
  local linkedin_status="$3"
  local company_before="$4"
  local company_after="$5"
  local company_status="$6"
  python3 - "$SNAPSHOT_DATE" "$linkedin_before" "$linkedin_after" "$linkedin_status" "$company_before" "$company_after" "$company_status" <<'PY'
import datetime as dt
import json
import pathlib
import sys

root = pathlib.Path.cwd()
snapshot_date, linkedin_before, linkedin_after, linkedin_status, company_before, company_after, company_status = sys.argv[1:]
processed = root / "data" / "processed"
snapshot = root / "data" / "snapshots" / snapshot_date

def load(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}

linkedin = load(processed / "linkedin_jobs_summary.json")
company = load(processed / "company_career_jobs_summary.json")
linkedin_net_new = int(linkedin_after) - int(linkedin_before) if linkedin_status == "completed" else 0
company_net_new = int(company_after) - int(company_before) if company_status == "completed" else 0
payload = {
    "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
    "snapshot_date": snapshot_date,
    "mode": "daily_delta",
    "linkedin": {
        "status": linkedin_status,
        "jobs_before": int(linkedin_before),
        "jobs_after": int(linkedin_after),
        "net_new_jobs": linkedin_net_new,
        "jobs_seen_in_snapshot": linkedin.get("jobs_seen_in_snapshot", 0),
        "new_jobs_in_snapshot": linkedin.get("new_jobs_in_snapshot", 0),
        "summary_generated_at": linkedin.get("generated_at"),
    },
    "company_careers": {
        "status": company_status,
        "jobs_before": int(company_before),
        "jobs_after": int(company_after),
        "net_new_jobs": company_net_new,
        "jobs_seen_in_snapshot": company.get("jobs_seen_in_snapshot", 0),
        "new_jobs_in_snapshot": company.get("new_jobs_in_snapshot", 0),
        "summary_generated_at": company.get("generated_at"),
    },
}
processed.mkdir(parents=True, exist_ok=True)
snapshot.mkdir(parents=True, exist_ok=True)
(processed / "daily_delta_summary.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
(snapshot / "daily_delta_summary.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(payload, ensure_ascii=False, indent=2))
PY
}

cd "$ROOT"
echo "Daily delta started at $(date +"%Y-%m-%dT%H:%M:%S%z"), snapshot=$SNAPSHOT_DATE"

linkedin_before="$(json_value "$ROOT/data/processed/linkedin_jobs_summary.json" jobs_collected)"
company_before="$(json_value "$ROOT/data/processed/company_career_jobs_summary.json" jobs_collected)"
linkedin_status="skipped"
company_status="skipped"

if [ "${DAILY_DELTA_SKIP_LINKEDIN:-0}" = "1" ]; then
  echo "Skipping LinkedIn daily delta because DAILY_DELTA_SKIP_LINKEDIN=1."
  linkedin_status="skipped_by_env"
elif is_running_pid_file "$LINKEDIN_FULL_PID_FILE"; then
  echo "LinkedIn full crawler is running; skipping LinkedIn daily delta to avoid concurrent writes."
  linkedin_status="skipped_full_running"
else
  echo "Running LinkedIn daily delta: past_24h, daily location set, 2 pages/search."
  SNAPSHOT_DATE="$SNAPSHOT_DATE" \
  LINKEDIN_QUERY_FILE="$ROOT/data/config/linkedin_queries_expanded.txt" \
  LINKEDIN_LOCATION_FILE="$ROOT/data/config/linkedin_locations_daily_delta.txt" \
  LINKEDIN_FILTERS="past_24h" \
  LINKEDIN_MAX_PAGES_PER_SEARCH="${LINKEDIN_DAILY_MAX_PAGES_PER_SEARCH:-2}" \
  LINKEDIN_MAX_DETAILS="${LINKEDIN_DAILY_MAX_DETAILS:-0}" \
  LINKEDIN_REQUEST_DELAY_SECONDS="${LINKEDIN_DAILY_REQUEST_DELAY_SECONDS:-0.5}" \
  LINKEDIN_REQUEST_TIMEOUT_SECONDS="${LINKEDIN_DAILY_REQUEST_TIMEOUT_SECONDS:-12}" \
  LINKEDIN_RATE_LIMIT_RETRIES="${LINKEDIN_DAILY_RATE_LIMIT_RETRIES:-0}" \
  LINKEDIN_RATE_LIMIT_SLEEP_SECONDS="${LINKEDIN_DAILY_RATE_LIMIT_SLEEP_SECONDS:-20}" \
  LINKEDIN_SAVE_EVERY_PARTITIONS="${LINKEDIN_DAILY_SAVE_EVERY_PARTITIONS:-50}" \
  LINKEDIN_PRINT_FULL_SUMMARY="0" \
  LINKEDIN_WRITE_SNAPSHOT="0" \
  python3 scripts/fetch_linkedin_guest_jobs.py
  linkedin_status="completed"
fi

if [ "${DAILY_DELTA_SKIP_COMPANY:-0}" = "1" ]; then
  echo "Skipping company career daily delta because DAILY_DELTA_SKIP_COMPANY=1."
  company_status="skipped_by_env"
elif is_running_pid_file "$COMPANY_PID_FILE"; then
  echo "Company career crawler is running; skipping company daily delta to avoid concurrent writes."
  company_status="skipped_company_running"
else
  echo "Running company career / ATS daily delta."
  SNAPSHOT_DATE="$SNAPSHOT_DATE" \
  COMPANY_CAREER_MAX_WORKERS="${COMPANY_CAREER_DAILY_MAX_WORKERS:-6}" \
  COMPANY_CAREER_JOBS2WEB_FETCH_DETAILS="${COMPANY_CAREER_DAILY_JOBS2WEB_FETCH_DETAILS:-0}" \
  python3 scripts/fetch_company_career_jobs.py --max-workers "${COMPANY_CAREER_DAILY_MAX_WORKERS:-6}"
  company_status="completed"
fi

linkedin_after="$(json_value "$ROOT/data/processed/linkedin_jobs_summary.json" jobs_collected)"
company_after="$(json_value "$ROOT/data/processed/company_career_jobs_summary.json" jobs_collected)"

if [ "${DAILY_DELTA_SKIP_BUILD:-0}" = "1" ]; then
  echo "Skipping report build because DAILY_DELTA_SKIP_BUILD=1."
else
  echo "Building report after daily delta."
  python3 scripts/build_report.py
  if [ -f package.json ]; then
    npm run build
  fi
fi

write_delta_summary "$linkedin_before" "$linkedin_after" "$linkedin_status" "$company_before" "$company_after" "$company_status"
maybe_disable_idle_monthly_full
echo "Daily delta finished at $(date +"%Y-%m-%dT%H:%M:%S%z")"

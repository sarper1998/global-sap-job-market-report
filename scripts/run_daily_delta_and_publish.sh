#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$ROOT/logs"
mkdir -p "$LOG_DIR" "$ROOT/data/processed"

cd "$ROOT"

echo "Daily publish started at $(date +"%Y-%m-%dT%H:%M:%S%z")"

git pull --ff-only origin main

seed_processed_from_public_data() {
  local name
  for name in linkedin_jobs.csv.gz linkedin_jobs.json.gz; do
    if [ -f "$ROOT/data/$name" ] && [ ! -f "$ROOT/data/processed/$name" ]; then
      cp "$ROOT/data/$name" "$ROOT/data/processed/$name"
      echo "Seeded data/processed/$name from data/$name"
    fi
  done
}

sync_public_data() {
  local name
  for name in \
    sap_jobs.csv sap_jobs.json summary.json linkedin_signal.json \
    linkedin_jobs.csv.gz linkedin_jobs.json.gz linkedin_jobs_summary.json \
    company_career_jobs.csv company_career_jobs.json company_career_jobs_summary.json \
    daily_delta_summary.json
  do
    if [ -f "$ROOT/data/processed/$name" ]; then
      cp "$ROOT/data/processed/$name" "$ROOT/data/$name"
    fi
  done
}

seed_processed_from_public_data

echo "Refreshing open job feeds."
python3 scripts/fetch_sap_jobs.py

bash "$ROOT/scripts/run_daily_delta.sh"

# run_daily_delta writes daily_delta_summary after its build step, so rebuild once more
# to include the latest delta note in the public report.
python3 scripts/build_report.py
if [ -f package.json ]; then
  npm run build
fi

sync_public_data

git add index.html report/index.html data
if git diff --cached --quiet; then
  echo "No public report changes to publish."
else
  git config user.name "sap-market-report-bot"
  git config user.email "sap-market-report-bot@users.noreply.github.com"
  git commit -m "Refresh SAP job market data $(date +%F)"
  git push origin HEAD:main
fi

echo "Daily publish finished at $(date +"%Y-%m-%dT%H:%M:%S%z")"

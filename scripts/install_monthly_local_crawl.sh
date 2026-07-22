#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LABEL="com.sap-market-report.linkedin-monthly"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG_DIR="$ROOT/logs"
PYTHON_BIN="$(command -v python3)"
mkdir -p "$HOME/Library/LaunchAgents" "$LOG_DIR" "$ROOT/data/run_state"

if [[ "$ROOT" == "$HOME/Documents/"* || "$ROOT" == "$HOME/Desktop/"* || "$ROOT" == "$HOME/Downloads/"* ]]; then
  cat <<WARN
Warning: this project is under a macOS privacy-protected folder:
$ROOT

LaunchAgents may fail with "Operation not permitted" unless Python/Terminal has Full Disk Access.
For unattended monthly crawling, either:
  1. move the repo to a folder such as ~/Projects/global-sap-job-market-report, or
  2. grant Full Disk Access to Terminal and the Python binary used by this plist.

Manual Terminal runs still work from the current folder.
WARN
fi

cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$LABEL</string>
  <key>WorkingDirectory</key>
  <string>$ROOT</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
  </dict>
  <key>ProgramArguments</key>
  <array>
    <string>$PYTHON_BIN</string>
    <string>$ROOT/scripts/run_linkedin_local_crawl.py</string>
    <string>--until-complete</string>
    <string>--cycle-when-complete</string>
    <string>--target-jobs</string>
    <string>371000</string>
    <string>--max-runtime-hours</string>
    <string>72</string>
    <string>--max-partitions</string>
    <string>720</string>
    <string>--backfill-details</string>
    <string>0</string>
    <string>--rate-limit-retries</string>
    <string>0</string>
    <string>--rate-limit-sleep</string>
    <string>20</string>
    <string>--request-delay</string>
    <string>0.6</string>
    <string>--save-every</string>
    <string>10</string>
    <string>--build-report</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Day</key>
    <integer>1</integer>
    <key>Hour</key>
    <integer>2</integer>
    <key>Minute</key>
    <integer>30</integer>
  </dict>
  <key>StandardOutPath</key>
  <string>$LOG_DIR/linkedin-monthly-launchd.out.log</string>
  <key>StandardErrorPath</key>
  <string>$LOG_DIR/linkedin-monthly-launchd.err.log</string>
</dict>
</plist>
PLIST

launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"
echo "Installed monthly LaunchAgent: $PLIST"
echo "Schedule: every month on day 1 at 02:30 local time"
echo "Manual start: scripts/start_linkedin_local_crawl.sh"
echo "Status: scripts/linkedin_local_crawl_status.sh"
echo "Launch now: launchctl start $LABEL"

#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LABEL="com.sap-market-report.company-careers-monthly"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG_DIR="$ROOT/logs"
PYTHON_BIN="$(command -v python3)"
mkdir -p "$HOME/Library/LaunchAgents" "$LOG_DIR" "$ROOT/data/run_state"

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
    <string>$ROOT/scripts/fetch_company_career_jobs.py</string>
    <string>--max-workers</string>
    <string>6</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Day</key>
    <integer>1</integer>
    <key>Hour</key>
    <integer>3</integer>
    <key>Minute</key>
    <integer>30</integer>
  </dict>
  <key>StandardOutPath</key>
  <string>$LOG_DIR/company-careers-launchd.out.log</string>
  <key>StandardErrorPath</key>
  <string>$LOG_DIR/company-careers-launchd.err.log</string>
</dict>
</plist>
PLIST

launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"
echo "Installed monthly LaunchAgent: $PLIST"
echo "Schedule: every month on day 1 at 03:30 local time"
echo "Launch now: launchctl start $LABEL"
echo "Status: scripts/company_career_crawl_status.sh"

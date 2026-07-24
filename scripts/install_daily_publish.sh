#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LABEL="com.sap-market-report.daily-publish"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
OLD_PLIST="$HOME/Library/LaunchAgents/com.sap-market-report.daily-delta.plist"
LOG_DIR="$ROOT/logs"
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
    <string>/bin/bash</string>
    <string>$ROOT/scripts/run_daily_delta_and_publish.sh</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key>
    <integer>6</integer>
    <key>Minute</key>
    <integer>15</integer>
  </dict>
  <key>StandardOutPath</key>
  <string>$LOG_DIR/daily-publish-launchd.out.log</string>
  <key>StandardErrorPath</key>
  <string>$LOG_DIR/daily-publish-launchd.err.log</string>
</dict>
</plist>
PLIST

if [ -f "$OLD_PLIST" ]; then
  launchctl unload "$OLD_PLIST" 2>/dev/null || true
fi

launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"

echo "Installed daily publish LaunchAgent: $PLIST"
echo "Schedule: every day at 06:15 local time"
echo "Launch now: launchctl start $LABEL"

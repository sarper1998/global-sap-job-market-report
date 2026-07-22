param(
  [Parameter(Mandatory = $true)][string]$WorkerId,
  [Parameter(Mandatory = $true)][int]$PartitionOffset,
  [Parameter(Mandatory = $true)][int]$PartitionLimit
)

$ErrorActionPreference = "Stop"

function ConvertTo-GitBashPath([string]$Path) {
  if (Test-Path $Path) {
    $resolved = (Resolve-Path $Path).Path
  } else {
    $resolved = [System.IO.Path]::GetFullPath($Path)
  }
  if ($resolved -match "^([A-Za-z]):\\(.*)$") {
    $drive = $matches[1].ToLowerInvariant()
    $rest = $matches[2] -replace "\\", "/"
    return "/$drive/$rest"
  }
  return $resolved -replace "\\", "/"
}

$Root = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
$LogDir = Join-Path $Root "logs"
$StateDir = Join-Path $Root "data/run_state"
$OutputDir = Join-Path $Root "data/worker_outputs/$WorkerId"
New-Item -ItemType Directory -Force -Path $LogDir, $StateDir, $OutputDir | Out-Null

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$LogFile = Join-Path $LogDir "linkedin-worker-$WorkerId-$timestamp.log"
$WinPidFile = Join-Path $StateDir "linkedin_worker_$WorkerId.winpid"
$RunnerFile = Join-Path $StateDir "run_linkedin_worker_$WorkerId.sh"

$bash = "C:\Program Files\Git\bin\bash.exe"
if (!(Test-Path $bash)) {
  throw "Git Bash was not found at $bash"
}

$rootBash = ConvertTo-GitBashPath $Root
$outputBash = ConvertTo-GitBashPath $OutputDir
$logBash = ConvertTo-GitBashPath $LogFile
$runnerBash = ConvertTo-GitBashPath $RunnerFile

$runner = @"
#!/usr/bin/env bash
set -euo pipefail
cd '$rootBash'
exec >> '$logBash' 2>&1
echo "Worker $WorkerId started at `$(date -Is 2>/dev/null || date)"
SNAPSHOT_DATE='$(Get-Date -Format yyyy-MM-dd)' \
LINKEDIN_WORKER_ID='$WorkerId' \
LINKEDIN_WORKER_OUTPUT_DIR='$outputBash' \
LINKEDIN_QUERY_FILE='$rootBash/data/config/linkedin_queries_expanded.txt' \
LINKEDIN_LOCATION_FILE='$rootBash/data/config/linkedin_locations_expanded.txt' \
LINKEDIN_FILTERS='all,past_24h,past_week,past_month,onsite,remote,hybrid,past_week_remote,past_week_hybrid' \
LINKEDIN_PARTITION_OFFSET='$PartitionOffset' \
LINKEDIN_MAX_PARTITIONS='$PartitionLimit' \
LINKEDIN_MAX_PAGES_PER_SEARCH='8' \
LINKEDIN_MAX_DETAILS='0' \
LINKEDIN_REQUEST_DELAY_SECONDS='0.6' \
LINKEDIN_REQUEST_TIMEOUT_SECONDS='15' \
LINKEDIN_RATE_LIMIT_SLEEP_SECONDS='120' \
LINKEDIN_RATE_LIMIT_RETRIES='0' \
LINKEDIN_SAVE_EVERY_PARTITIONS='25' \
LINKEDIN_PRINT_FULL_SUMMARY='0' \
python scripts/fetch_linkedin_guest_jobs.py
"@

[System.IO.File]::WriteAllText($RunnerFile, $runner.Replace("`r`n", "`n"), [System.Text.UTF8Encoding]::new($false))

$process = Start-Process -FilePath $bash -ArgumentList @($RunnerFile) -WindowStyle Hidden -PassThru
$process.Id | Set-Content -Encoding ascii $WinPidFile

Write-Output "Started LinkedIn Windows worker $WorkerId pid=$($process.Id)"
Write-Output "Output: $OutputDir"
Write-Output "Log: $LogFile"
Write-Output "Runner: $RunnerFile"

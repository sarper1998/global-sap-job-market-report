#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List


ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = ROOT / "data" / "run_state"
DEFAULT_STATE_FILE = STATE_DIR / "linkedin_local_crawl_state.json"
DEFAULT_PID_FILE = STATE_DIR / "linkedin_local_crawl.pid"
DEFAULT_QUERY_FILE = ROOT / "data" / "config" / "linkedin_queries_expanded.txt"
DEFAULT_LOCATION_FILE = ROOT / "data" / "config" / "linkedin_locations_expanded.txt"
SUMMARY_FILE = ROOT / "data" / "processed" / "linkedin_jobs_summary.json"
DEFAULT_FILTERS = [
    "all",
    "past_24h",
    "past_week",
    "past_month",
    "onsite",
    "remote",
    "hybrid",
    "past_week_remote",
    "past_week_hybrid",
]


def read_list(path: Path) -> List[str]:
    values = []
    for line in path.read_text(encoding="utf-8").splitlines():
        item = line.strip()
        if item and not item.startswith("#"):
            values.append(item)
    return values


def load_json(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def pid_is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def acquire_lock(pid_file: Path) -> None:
    pid_file.parent.mkdir(parents=True, exist_ok=True)
    if pid_file.exists():
        try:
            existing = int(pid_file.read_text(encoding="utf-8").strip())
        except ValueError:
            existing = 0
        if existing and pid_is_running(existing):
            raise SystemExit(f"LinkedIn local crawl is already running with pid {existing}")
    pid_file.write_text(str(os.getpid()), encoding="utf-8")


def release_lock(pid_file: Path) -> None:
    try:
        if pid_file.exists() and pid_file.read_text(encoding="utf-8").strip() == str(os.getpid()):
            pid_file.unlink()
    except OSError:
        pass


def current_job_count() -> int:
    summary = current_summary()
    return int(summary.get("jobs_collected") or 0)


def current_summary() -> Dict[str, Any]:
    return load_json(SUMMARY_FILE, {})


def run_command(label: str, command: List[str], env: Dict[str, str]) -> None:
    print(f"\n[{dt.datetime.now().isoformat(timespec='seconds')}] {label}", flush=True)
    print(" ".join(command), flush=True)
    subprocess.run(command, cwd=ROOT, env=env, check=True)


def build_env(args: argparse.Namespace, offset: int, batch_size: int, snapshot_date: str, filters: List[str]) -> Dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "SNAPSHOT_DATE": snapshot_date,
            "LINKEDIN_QUERY_FILE": str(args.query_file),
            "LINKEDIN_LOCATION_FILE": str(args.location_file),
            "LINKEDIN_FILTERS": ",".join(filters),
            "LINKEDIN_MAX_PAGES_PER_SEARCH": str(args.pages_per_search),
            "LINKEDIN_MAX_DETAILS": str(args.max_details_per_batch),
            "LINKEDIN_REQUEST_DELAY_SECONDS": str(args.request_delay),
            "LINKEDIN_REQUEST_TIMEOUT_SECONDS": str(args.request_timeout),
            "LINKEDIN_RATE_LIMIT_SLEEP_SECONDS": str(args.rate_limit_sleep),
            "LINKEDIN_RATE_LIMIT_RETRIES": str(args.rate_limit_retries),
            "LINKEDIN_PARTITION_OFFSET": str(offset),
            "LINKEDIN_MAX_PARTITIONS": str(batch_size),
            "LINKEDIN_SAVE_EVERY_PARTITIONS": str(args.save_every),
            "LINKEDIN_PRINT_FULL_SUMMARY": "0",
            "LINKEDIN_WRITE_SNAPSHOT": "0",
        }
    )
    return env


def run_backfill(args: argparse.Namespace, snapshot_date: str) -> None:
    if args.backfill_details <= 0:
        return
    env = os.environ.copy()
    env.update(
        {
            "SNAPSHOT_DATE": snapshot_date,
            "LINKEDIN_BACKFILL_ONLY": "1",
            "LINKEDIN_MAX_DETAILS": str(args.backfill_details),
            "LINKEDIN_REQUEST_DELAY_SECONDS": str(args.request_delay),
            "LINKEDIN_REQUEST_TIMEOUT_SECONDS": str(args.request_timeout),
            "LINKEDIN_RATE_LIMIT_SLEEP_SECONDS": str(args.rate_limit_sleep),
            "LINKEDIN_RATE_LIMIT_RETRIES": str(args.rate_limit_retries),
            "LINKEDIN_PRINT_FULL_SUMMARY": "0",
            "LINKEDIN_WRITE_SNAPSHOT": "0",
        }
    )
    run_command("Backfill missing LinkedIn descriptions", [sys.executable, "scripts/fetch_linkedin_guest_jobs.py"], env)


def build_report(args: argparse.Namespace) -> None:
    if not args.build_report:
        return
    run_command("Build HTML report", [sys.executable, "scripts/build_report.py"], os.environ.copy())
    package_json = ROOT / "package.json"
    if package_json.exists():
        run_command("Build static site server bundle", ["npm", "run", "build"], os.environ.copy())


def reset_state_if_needed(state: Dict[str, Any], args: argparse.Namespace, snapshot_date: str, total_partitions: int, filters: List[str]) -> Dict[str, Any]:
    config_fingerprint = {
        "snapshot_date": snapshot_date,
        "query_file": str(args.query_file),
        "location_file": str(args.location_file),
        "filters": filters,
        "total_partitions": total_partitions,
    }
    if args.reset_offset:
        return {**config_fingerprint, "next_offset": 0, "cycles_completed": 0, "history": []}
    for key, value in config_fingerprint.items():
        if state.get(key) != value:
            return {**config_fingerprint, "next_offset": 0, "cycles_completed": 0, "history": []}
    state.setdefault("next_offset", 0)
    state.setdefault("cycles_completed", 0)
    state.setdefault("history", [])
    return state


def recover_offset_from_summary(state: Dict[str, Any], total_partitions: int) -> Dict[str, Any]:
    summary = current_summary()
    offset = int(summary.get("latest_run_partition_offset") or 0)
    attempted = int(summary.get("latest_run_searches_attempted") or 0)
    recovered = min(total_partitions, offset + attempted)
    if recovered > int(state.get("next_offset") or 0):
        state["next_offset"] = recovered
        state["recovered_from_summary_at"] = dt.datetime.now().isoformat(timespec="seconds")
    return state


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the LinkedIn SAP crawler locally in resumable batches.")
    parser.add_argument("--snapshot-date", default=dt.date.today().isoformat())
    parser.add_argument("--query-file", type=Path, default=DEFAULT_QUERY_FILE)
    parser.add_argument("--location-file", type=Path, default=DEFAULT_LOCATION_FILE)
    parser.add_argument("--filters", default=",".join(DEFAULT_FILTERS))
    parser.add_argument("--state-file", type=Path, default=DEFAULT_STATE_FILE)
    parser.add_argument("--pid-file", type=Path, default=DEFAULT_PID_FILE)
    parser.add_argument("--target-jobs", type=int, default=371000)
    parser.add_argument("--max-partitions", type=int, default=720)
    parser.add_argument("--max-batches", type=int, default=1)
    parser.add_argument("--until-complete", action="store_true")
    parser.add_argument("--cycle-when-complete", action="store_true")
    parser.add_argument("--max-runtime-hours", type=float, default=0)
    parser.add_argument("--pages-per-search", type=int, default=8)
    parser.add_argument("--max-details-per-batch", type=int, default=0)
    parser.add_argument("--backfill-details", type=int, default=0)
    parser.add_argument("--request-delay", type=float, default=0.8)
    parser.add_argument("--request-timeout", type=float, default=15)
    parser.add_argument("--rate-limit-sleep", type=float, default=120)
    parser.add_argument("--rate-limit-retries", type=int, default=3)
    parser.add_argument("--save-every", type=int, default=25)
    parser.add_argument("--build-report", action="store_true")
    parser.add_argument("--reset-offset", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    args.query_file = args.query_file if args.query_file.is_absolute() else ROOT / args.query_file
    args.location_file = args.location_file if args.location_file.is_absolute() else ROOT / args.location_file
    args.state_file = args.state_file if args.state_file.is_absolute() else ROOT / args.state_file
    args.pid_file = args.pid_file if args.pid_file.is_absolute() else ROOT / args.pid_file

    filters = [item.strip() for item in args.filters.split(",") if item.strip()]
    queries = read_list(args.query_file)
    locations = read_list(args.location_file)
    total_partitions = len(queries) * len(locations) * len(filters)
    theoretical_cards = total_partitions * args.pages_per_search * 25
    state = reset_state_if_needed(load_json(args.state_file, {}), args, args.snapshot_date, total_partitions, filters)
    state = recover_offset_from_summary(state, total_partitions)

    print(
        json.dumps(
            {
                "snapshot_date": args.snapshot_date,
                "queries": len(queries),
                "locations": len(locations),
                "filters": len(filters),
                "total_partitions": total_partitions,
                "theoretical_card_requests_before_dedupe": theoretical_cards,
                "next_offset": state["next_offset"],
                "current_jobs_collected": current_job_count(),
                "target_jobs": args.target_jobs,
                "max_partitions_per_batch": args.max_partitions,
                "until_complete": args.until_complete,
                "max_runtime_hours": args.max_runtime_hours,
            },
            ensure_ascii=False,
            indent=2,
        ),
        flush=True,
    )

    if args.dry_run:
        return

    acquire_lock(args.pid_file)
    started = time.monotonic()
    batches_run = 0
    try:
        while True:
            jobs_before = current_job_count()
            if jobs_before >= args.target_jobs:
                print(f"Target reached: {jobs_before} jobs >= {args.target_jobs}", flush=True)
                break

            if state["next_offset"] >= total_partitions:
                state["cycles_completed"] = int(state.get("cycles_completed", 0)) + 1
                state["last_completed_at"] = dt.datetime.now().isoformat(timespec="seconds")
                if not args.cycle_when_complete:
                    write_json(args.state_file, state)
                    print("Partition grid completed. Re-run with --cycle-when-complete to start again.", flush=True)
                    break
                state["next_offset"] = 0

            if args.max_runtime_hours and (time.monotonic() - started) >= args.max_runtime_hours * 3600:
                print("Runtime limit reached before next batch.", flush=True)
                break

            if not args.until_complete and batches_run >= args.max_batches:
                print("Batch limit reached.", flush=True)
                break

            offset = int(state["next_offset"])
            batch_size = min(args.max_partitions, total_partitions - offset)
            env = build_env(args, offset, batch_size, args.snapshot_date, filters)
            try:
                run_command(
                    f"Collect LinkedIn links offset={offset} size={batch_size}",
                    [sys.executable, "scripts/fetch_linkedin_guest_jobs.py"],
                    env,
                )
            except subprocess.CalledProcessError as exc:
                state = recover_offset_from_summary(state, total_partitions)
                state.setdefault("history", []).append(
                    {
                        "completed_at": dt.datetime.now().isoformat(timespec="seconds"),
                        "offset": offset,
                        "batch_size": batch_size,
                        "jobs_before": jobs_before,
                        "jobs_after": current_job_count(),
                        "error": f"crawler exited with {exc.returncode}; recovered next_offset={state['next_offset']}",
                    }
                )
                write_json(args.state_file, state)
                print(f"Crawler failed with {exc.returncode}; recovered next_offset={state['next_offset']}", flush=True)
                if state["next_offset"] <= offset:
                    raise
                continue
            batches_run += 1
            jobs_after = current_job_count()
            state["next_offset"] = offset + batch_size
            history = state.setdefault("history", [])
            history.append(
                {
                    "completed_at": dt.datetime.now().isoformat(timespec="seconds"),
                    "offset": offset,
                    "batch_size": batch_size,
                    "jobs_before": jobs_before,
                    "jobs_after": jobs_after,
                    "new_jobs": jobs_after - jobs_before,
                }
            )
            del history[:-50]
            write_json(args.state_file, state)
            print(f"Batch complete: {jobs_before} -> {jobs_after} jobs; next_offset={state['next_offset']}", flush=True)

            run_backfill(args, args.snapshot_date)
            build_report(args)
    finally:
        write_json(args.state_file, state)
        release_lock(args.pid_file)


if __name__ == "__main__":
    main()

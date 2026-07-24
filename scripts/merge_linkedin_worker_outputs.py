#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT_GLOB = ROOT / "data" / "worker_outputs" / "*" / "linkedin_jobs.json"
DEFAULT_STATE_FILE = ROOT / "data" / "run_state" / "linkedin_local_crawl_state.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Merge LinkedIn worker shard outputs into the main processed pool.")
    parser.add_argument("--input", dest="inputs", action="append", type=Path, help="Worker linkedin_jobs.json file. Can be repeated.")
    parser.add_argument("--snapshot-date", default=dt.date.today().isoformat())
    parser.add_argument("--write-snapshot", action="store_true", help="Also write the full merged LinkedIn pool under data/snapshots/YYYY-MM-DD.")
    parser.add_argument("--state-file", type=Path, default=DEFAULT_STATE_FILE)
    parser.add_argument("--update-state", action="store_true", help="Advance the supplied state file to the merged worker high watermark.")
    return parser.parse_args()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_json_or_empty(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = load_json(path)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def int_or_zero(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def merge_unique_list(left: Any, right: Any) -> List[str]:
    out: List[str] = []
    for values in (left, right):
        if isinstance(values, str):
            values = [part.strip() for part in values.split(";") if part.strip()]
        if not isinstance(values, list):
            continue
        for value in values:
            text = str(value).strip()
            if text and text not in out:
                out.append(text)
    return out


def earliest(left: Any, right: Any) -> Any:
    values = [value for value in [left, right] if present(value)]
    return min(values) if values else ""


def latest(left: Any, right: Any) -> Any:
    values = [value for value in [left, right] if present(value)]
    return max(values) if values else ""


def row_key(row: Dict[str, Any], li: Any) -> str:
    return str(
        row.get("linkedin_job_id")
        or row.get("id")
        or li.stable_id([row.get("title"), row.get("company"), row.get("location"), row.get("url")])
    )


def merge_row(existing: Dict[str, Any], incoming: Dict[str, Any], li: Any) -> Dict[str, Any]:
    merged = dict(existing)

    for key, value in incoming.items():
        if present(value) and not present(merged.get(key)):
            merged[key] = value

    for key in ["description", "description_excerpt"]:
        left = str(merged.get(key) or "")
        right = str(incoming.get(key) or "")
        if len(right) > len(left):
            merged[key] = right

    for key in ["modules", "skills", "soft_skills", "degree_levels", "degree_fields"]:
        merged[key] = merge_unique_list(merged.get(key), incoming.get(key))

    for key, observed_key in [
        ("query", "observed_queries"),
        ("query_location", "observed_query_locations"),
        ("query_filter", "observed_query_filters"),
    ]:
        merged[observed_key] = merge_unique_list(merged.get(observed_key), [merged.get(key), incoming.get(key)])

    merged["first_seen_at"] = earliest(merged.get("first_seen_at"), incoming.get("first_seen_at"))
    merged["last_seen_at"] = latest(merged.get("last_seen_at"), incoming.get("last_seen_at"))
    merged["first_seen_snapshot"] = earliest(merged.get("first_seen_snapshot"), incoming.get("first_seen_snapshot"))
    merged["last_seen_snapshot"] = latest(merged.get("last_seen_snapshot"), incoming.get("last_seen_snapshot"))
    merged["detail_fetched_at"] = latest(merged.get("detail_fetched_at"), incoming.get("detail_fetched_at"))

    return li.enrich(merged)


def iter_input_paths(paths: Iterable[Path] | None) -> List[Path]:
    if paths:
        return [path if path.is_absolute() else ROOT / path for path in paths]
    return sorted(DEFAULT_INPUT_GLOB.parent.parent.glob("*/linkedin_jobs.json"))


def worker_coverage(summary: Dict[str, Any]) -> Dict[str, Any]:
    start = int_or_zero(summary.get("latest_run_partition_offset"))
    limit = int_or_zero(summary.get("latest_run_partition_limit"))
    attempted = int_or_zero(summary.get("latest_run_searches_attempted"))
    covered = attempted
    return {
        "partition_offset": start,
        "partition_limit": limit or None,
        "searches_attempted": attempted,
        "covered_until": start + covered,
        "complete": bool(limit and attempted >= limit),
    }


def update_state_high_watermark(state: Dict[str, Any], high_watermark: int, merged_at: str) -> Dict[str, Any]:
    if not state:
        return {}
    current_next = int_or_zero(state.get("next_offset"))
    total = int_or_zero(state.get("total_partitions"))
    next_offset = max(current_next, high_watermark)
    if total:
        next_offset = min(next_offset, total)
    state["next_offset"] = next_offset
    state["merged_worker_outputs_at"] = merged_at
    return state


def main() -> None:
    args = parse_args()
    args.state_file = args.state_file if args.state_file.is_absolute() else ROOT / args.state_file
    os.environ["SNAPSHOT_DATE"] = args.snapshot_date
    os.environ["LINKEDIN_WRITE_SNAPSHOT"] = "1" if args.write_snapshot else "0"
    os.environ.pop("LINKEDIN_WORKER_ID", None)
    os.environ.pop("LINKEDIN_WORKER_OUTPUT_DIR", None)

    sys.path.insert(0, str(ROOT / "scripts"))
    import fetch_linkedin_guest_jobs as li  # noqa: E402

    input_paths = [path for path in iter_input_paths(args.inputs) if path.exists()]
    previous_summary = load_json_or_empty(li.PROCESSED_DIR / "linkedin_jobs_summary.json")
    previous_merge = previous_summary.get("merge") if isinstance(previous_summary.get("merge"), dict) else {}
    previous_inputs = {
        item.get("path"): item
        for item in previous_merge.get("worker_inputs", [])
        if isinstance(item, dict) and item.get("path")
    }
    local_state = load_json_or_empty(args.state_file) if args.update_state else {}
    rows_by_key: Dict[str, Dict[str, Any]] = {}
    main_rows = li.load_existing()
    main_before = len(main_rows)
    for row in main_rows:
        rows_by_key[row_key(row, li)] = row

    input_rows = 0
    input_stats = []
    for path in input_paths:
        worker_rows = load_json(path)
        worker_summary = load_json_or_empty(path.with_name("linkedin_jobs_summary.json"))
        input_rows += len(worker_rows)
        new_before = len(rows_by_key)
        for row in worker_rows:
            key = row_key(row, li)
            if key in rows_by_key:
                rows_by_key[key] = merge_row(rows_by_key[key], row, li)
            else:
                rows_by_key[key] = li.enrich(row)
        relative_path = str(path.relative_to(ROOT) if path.is_relative_to(ROOT) else path)
        net_new_jobs = len(rows_by_key) - new_before
        previous_input = previous_inputs.get(relative_path, {})
        if net_new_jobs == 0 and previous_input.get("rows") == len(worker_rows):
            net_new_jobs = int_or_zero(previous_input.get("net_new_jobs"))
        input_stats.append(
            {
                "path": relative_path,
                "rows": len(worker_rows),
                "net_new_jobs": net_new_jobs,
                "summary": worker_coverage(worker_summary),
            }
        )

    merged_rows = list(rows_by_key.values())
    summary = li.save_outputs(merged_rows, 0, {})
    merged_at = dt.datetime.now().isoformat(timespec="seconds")
    worker_high_watermark = max(
        [int_or_zero(item.get("summary", {}).get("covered_until")) for item in input_stats] or [0]
    )
    local_high_watermark = int_or_zero(local_state.get("next_offset"))
    combined_high_watermark = max(local_high_watermark, worker_high_watermark)
    if args.update_state and combined_high_watermark:
        summary["latest_run_partition_offset"] = combined_high_watermark
        summary["latest_run_searches_attempted"] = 0
        summary["latest_run_partition_limit"] = None
    else:
        for key in ["latest_run_searches_attempted", "latest_run_partition_offset", "latest_run_partition_limit"]:
            if key in previous_summary:
                summary[key] = previous_summary[key]
    summary["merge"] = {
        "merged_at": merged_at,
        "snapshot_date": args.snapshot_date,
        "main_jobs_before": int_or_zero(previous_merge.get("main_jobs_before")) or main_before,
        "worker_inputs": input_stats,
        "worker_input_rows": input_rows,
        "jobs_after": len(merged_rows),
        "net_new_jobs": sum(item["net_new_jobs"] for item in input_stats),
        "local_state_next_offset_before": int_or_zero(previous_merge.get("local_state_next_offset_before")) or local_high_watermark,
        "combined_partition_high_watermark": combined_high_watermark,
        "total_partitions": int_or_zero(local_state.get("total_partitions")),
    }
    li.write_json(li.PROCESSED_DIR / "linkedin_jobs_summary.json", summary)
    li.write_json(li.SNAPSHOT_DIR / "linkedin_jobs_summary.json", summary)
    updated_state = update_state_high_watermark(local_state, combined_high_watermark, merged_at) if args.update_state else {}
    if updated_state:
        li.write_json(args.state_file, updated_state)

    print(json.dumps(summary["merge"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

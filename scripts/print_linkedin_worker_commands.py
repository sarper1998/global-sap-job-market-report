#!/usr/bin/env python3
from __future__ import annotations

import argparse
import math
from pathlib import Path
from typing import List


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_QUERY_FILE = ROOT / "data" / "config" / "linkedin_queries_expanded.txt"
DEFAULT_LOCATION_FILE = ROOT / "data" / "config" / "linkedin_locations_expanded.txt"
DEFAULT_FILTERS = "all,past_24h,past_week,past_month,onsite,remote,hybrid,past_week_remote,past_week_hybrid"


def read_list(path: Path) -> List[str]:
    values = []
    for line in path.read_text(encoding="utf-8").splitlines():
        item = line.strip()
        if item and not item.startswith("#"):
            values.append(item)
    return values


def main() -> None:
    parser = argparse.ArgumentParser(description="Print non-overlapping LinkedIn worker shard commands.")
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--start-offset", type=int, default=0)
    parser.add_argument("--query-file", type=Path, default=DEFAULT_QUERY_FILE)
    parser.add_argument("--location-file", type=Path, default=DEFAULT_LOCATION_FILE)
    parser.add_argument("--filters", default=DEFAULT_FILTERS)
    parser.add_argument("--worker-prefix", default="pc")
    parser.add_argument("--background", action="store_true")
    args = parser.parse_args()

    query_file = args.query_file if args.query_file.is_absolute() else ROOT / args.query_file
    location_file = args.location_file if args.location_file.is_absolute() else ROOT / args.location_file
    filters = [item.strip() for item in args.filters.split(",") if item.strip()]
    total_partitions = len(read_list(query_file)) * len(read_list(location_file)) * len(filters)
    if args.start_offset >= total_partitions:
        raise SystemExit(f"start-offset {args.start_offset} is already beyond total partitions {total_partitions}")

    remaining = total_partitions - args.start_offset
    shard_size = math.ceil(remaining / args.workers)
    flag = "--background " if args.background else ""

    print(f"# total_partitions={total_partitions} start_offset={args.start_offset} remaining={remaining}")
    print("# Run one command on each PC from the repository root.")
    for index in range(args.workers):
        offset = args.start_offset + index * shard_size
        if offset >= total_partitions:
            break
        limit = min(shard_size, total_partitions - offset)
        worker_id = f"{args.worker_prefix}-{index + 1}"
        print(f"./scripts/start_linkedin_worker_shard.sh {flag}{worker_id} {offset} {limit}")
    print("# After worker output folders are copied back to this PC:")
    print("./scripts/merge_linkedin_worker_outputs.py")


if __name__ == "__main__":
    main()

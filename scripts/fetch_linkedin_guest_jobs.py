#!/usr/bin/env python3
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


ROOT = Path(__file__).resolve().parents[1]
PROCESSED_DIR = ROOT / "data" / "processed"
SNAPSHOT_DATE = os.environ.get("SNAPSHOT_DATE", dt.date.today().isoformat())
SNAPSHOT_DIR = ROOT / "data" / "snapshots" / SNAPSHOT_DATE

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_sap_jobs as sap_core  # noqa: E402


USER_AGENT = "Mozilla/5.0 (compatible; sap-market-report/1.0; +research)"
SEARCH_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
DETAIL_URL = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"

DEFAULT_QUERIES = [
    "SAP",
    "SAP SD",
    "SAP SuccessFactors",
    "SAP ABAP",
    "SAP HANA",
    "SAP S/4HANA",
    "SAP FICO",
    "SAP MM",
    "SAP Consultant",
    "SAP Fiori",
    "SAP Basis",
    "SAP BTP",
]
DEFAULT_LOCATIONS = [
    "Worldwide",
    "United States",
    "Brazil",
    "Germany",
    "India",
    "France",
    "Netherlands",
    "United Kingdom",
    "Canada",
    "Poland",
    "Spain",
    "Mexico",
    "Australia",
    "Turkey",
    "Singapore",
]

MAX_PAGES_PER_SEARCH = int(os.environ.get("LINKEDIN_MAX_PAGES_PER_SEARCH", "8"))
PAGE_STEP = int(os.environ.get("LINKEDIN_PAGE_STEP", "25"))
MAX_DETAILS = int(os.environ.get("LINKEDIN_MAX_DETAILS", "250"))
REQUEST_DELAY_SECONDS = float(os.environ.get("LINKEDIN_REQUEST_DELAY_SECONDS", "0.8"))
REQUEST_TIMEOUT_SECONDS = float(os.environ.get("LINKEDIN_REQUEST_TIMEOUT_SECONDS", "12"))
RATE_LIMIT_SLEEP_SECONDS = float(os.environ.get("LINKEDIN_RATE_LIMIT_SLEEP_SECONDS", "90"))
RATE_LIMIT_RETRIES = int(os.environ.get("LINKEDIN_RATE_LIMIT_RETRIES", "2"))
PARTITION_OFFSET = int(os.environ.get("LINKEDIN_PARTITION_OFFSET", "0"))
MAX_PARTITIONS = int(os.environ.get("LINKEDIN_MAX_PARTITIONS", "0"))
BACKFILL_ONLY = os.environ.get("LINKEDIN_BACKFILL_ONLY", "0") == "1"

FILTER_DEFINITIONS: Dict[str, Dict[str, str]] = {
    "all": {},
    "past_24h": {"f_TPR": "r86400"},
    "past_week": {"f_TPR": "r604800"},
    "past_month": {"f_TPR": "r2592000"},
    "onsite": {"f_WT": "1"},
    "remote": {"f_WT": "2"},
    "hybrid": {"f_WT": "3"},
    "past_week_remote": {"f_TPR": "r604800", "f_WT": "2"},
    "past_week_hybrid": {"f_TPR": "r604800", "f_WT": "3"},
}


def split_env(name: str, fallback: List[str]) -> List[str]:
    value = os.environ.get(name)
    if not value:
        return fallback
    return [part.strip() for part in value.split(",") if part.strip()]


def split_file_or_env(file_env: str, value_env: str, fallback: List[str]) -> List[str]:
    file_value = os.environ.get(file_env)
    if file_value:
        path = Path(file_value)
        if not path.is_absolute():
            path = ROOT / path
        values = []
        for line in path.read_text(encoding="utf-8").splitlines():
            item = line.strip()
            if item and not item.startswith("#"):
                values.append(item)
        return values
    return split_env(value_env, fallback)


def normalize_space(value: Any) -> str:
    return re.sub(r"\s+", " ", html.unescape(str(value or ""))).strip()


def stable_id(parts: Iterable[Any]) -> str:
    text = "|".join(normalize_space(p).lower() for p in parts if p is not None)
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


def clean_location(value: Any) -> str:
    location = normalize_space(value)
    if re.search(r"\b(applicants?|views?|reposted|promoted)\b", location, flags=re.IGNORECASE):
        return ""
    return location


def fetch_text(url: str, params: Optional[Dict[str, Any]] = None) -> str:
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_SECONDS) as resp:
        return resp.read().decode("utf-8", errors="replace")


def fetch_text_with_backoff(url: str, params: Optional[Dict[str, Any]] = None, context: str = "") -> str:
    for attempt in range(RATE_LIMIT_RETRIES + 1):
        try:
            return fetch_text(url, params)
        except urllib.error.HTTPError as exc:
            if exc.code != 429 or attempt >= RATE_LIMIT_RETRIES:
                raise
            sleep_for = RATE_LIMIT_SLEEP_SECONDS * (attempt + 1)
            print(f"Rate limited at {context or url}; sleeping {sleep_for:.0f}s before retry", flush=True)
            time.sleep(sleep_for)
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            if attempt >= RATE_LIMIT_RETRIES:
                raise
            sleep_for = min(RATE_LIMIT_SLEEP_SECONDS, 30 * (attempt + 1))
            print(f"Network error at {context or url}: {exc}; sleeping {sleep_for:.0f}s before retry", flush=True)
            time.sleep(sleep_for)
    return fetch_text(url, params)


class CardParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.cards: List[Dict[str, Any]] = []
        self.current: Optional[Dict[str, Any]] = None
        self.depth = 0
        self.field: Optional[str] = None
        self.parts: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[tuple[str, Optional[str]]]) -> None:
        attr = {key: value or "" for key, value in attrs}
        classes = attr.get("class", "")
        entity = attr.get("data-entity-urn", "")
        if self.current is None and "urn:li:jobPosting:" in entity:
            job_id = entity.rsplit(":", 1)[-1]
            self.current = {"linkedin_job_id": job_id}
            self.depth = 1
            return

        if self.current is None:
            return
        self.depth += 1

        if tag == "a" and "base-card__full-link" in classes and not self.current.get("url"):
            self.current["url"] = html.unescape(attr.get("href", "")).split("?")[0]
        elif tag == "h3" and "base-search-card__title" in classes:
            self.field = "title"
            self.parts = []
        elif tag == "h4" and "base-search-card__subtitle" in classes:
            self.field = "company"
            self.parts = []
        elif tag == "span" and "job-search-card__location" in classes:
            self.field = "location"
            self.parts = []
        elif tag == "time" and "job-search-card__listdate" in classes:
            self.current["posted_at"] = attr.get("datetime", "")

    def handle_data(self, data: str) -> None:
        if self.current is not None and self.field:
            self.parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self.current is None:
            return
        if self.field and tag in {"h3", "h4", "span"}:
            self.current[self.field] = normalize_space(" ".join(self.parts))
            self.field = None
            self.parts = []
        self.depth -= 1
        if self.depth <= 0:
            if self.current.get("linkedin_job_id") and self.current.get("url"):
                self.cards.append(self.current)
            self.current = None
            self.depth = 0


class DetailParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.description_parts: List[str] = []
        self.in_description = False
        self.description_depth = 0
        self.field: Optional[str] = None
        self.parts: List[str] = []
        self.values: Dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: List[tuple[str, Optional[str]]]) -> None:
        attr = {key: value or "" for key, value in attrs}
        classes = attr.get("class", "")
        if "show-more-less-html__markup" in classes:
            self.in_description = True
            self.description_depth = 1
        elif self.in_description:
            self.description_depth += 1

        if tag == "h2" and "top-card-layout__title" in classes:
            self.field = "title"
            self.parts = []
        elif tag == "a" and "topcard__org-name-link" in classes:
            self.field = "company"
            self.parts = []
        elif tag == "span" and "topcard__flavor--bullet" in classes:
            self.field = "location"
            self.parts = []

    def handle_data(self, data: str) -> None:
        if self.in_description:
            self.description_parts.append(data)
        if self.field:
            self.parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self.field and tag in {"h2", "a", "span"}:
            self.values[self.field] = normalize_space(" ".join(self.parts))
            self.field = None
            self.parts = []
        if self.in_description:
            self.description_depth -= 1
            if self.description_depth <= 0:
                self.in_description = False

    def result(self) -> Dict[str, str]:
        out = dict(self.values)
        out["description"] = normalize_space(" ".join(self.description_parts))
        return out


def parse_cards(body: str) -> List[Dict[str, Any]]:
    parser = CardParser()
    parser.feed(body)
    return parser.cards


def parse_detail(body: str) -> Dict[str, str]:
    parser = DetailParser()
    parser.feed(body)
    return parser.result()


def load_existing() -> List[Dict[str, Any]]:
    path = PROCESSED_DIR / "linkedin_jobs.json"
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def dedupe(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    out = []
    for row in rows:
        key = row.get("linkedin_job_id") or stable_id([row.get("title"), row.get("company"), row.get("location"), row.get("url")])
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def enrich(row: Dict[str, Any]) -> Dict[str, Any]:
    row["location"] = clean_location(row.get("location")) or "Not specified"
    text = normalize_space(f"{row.get('title', '')} {row.get('company', '')} {row.get('description', '')}")
    modules = sap_core.regex_hits(sap_core.MODULE_PATTERNS, text) or ["Unspecified SAP"]
    skills = sap_core.regex_hits(sap_core.SKILL_PATTERNS, text)
    soft_skills = sap_core.regex_hits(sap_core.SOFT_SKILL_PATTERNS, text)
    degree_levels = sap_core.regex_hits(sap_core.DEGREE_LEVEL_PATTERNS, text)
    degree_fields = sap_core.regex_hits(sap_core.DEGREE_FIELD_PATTERNS, text)
    row.update(
        {
            "id": stable_id(["linkedin_guest", row.get("linkedin_job_id"), row.get("url")]),
            "source": "linkedin_guest",
            "sap_focus": sap_core.classify_focus(row.get("title", ""), text, modules),
            "role_family": sap_core.classify_role(row.get("title", ""), text),
            "seniority": sap_core.classify_seniority(row.get("title", ""), text),
            "modules": modules,
            "skills": skills,
            "soft_skills": soft_skills,
            "degree_levels": degree_levels,
            "degree_fields": degree_fields,
            "description_excerpt": row.get("description", "")[:420],
        }
    )
    return row


def apply_detail(row: Dict[str, Any], errors: Dict[str, str]) -> bool:
    job_id = row.get("linkedin_job_id")
    if not job_id:
        return False
    try:
        detail_body = fetch_text_with_backoff(DETAIL_URL.format(job_id=job_id), context=f"detail|{job_id}")
        detail = parse_detail(detail_body)
        for key, value in detail.items():
            if not value:
                continue
            if key == "location" and row.get("location"):
                continue
            if key == "location":
                value = clean_location(value)
            if value:
                row[key] = value
        row["detail_fetched_at"] = dt.datetime.now().isoformat(timespec="seconds")
        enrich(row)
        return True
    except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
        errors[f"detail|{job_id}"] = str(exc)
        return False


def needs_detail(row: Dict[str, Any]) -> bool:
    return bool(row.get("linkedin_job_id")) and len(normalize_space(row.get("description", ""))) < 80


def count_values(rows: List[Dict[str, Any]], field: str, multi: bool = False) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for row in rows:
        values = row.get(field, [])
        if not multi:
            values = [values]
        for value in values:
            if not value:
                continue
            counts[str(value)] = counts.get(str(value), 0) + 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "id",
        "linkedin_job_id",
        "title",
        "company",
        "location",
        "posted_at",
        "url",
        "query",
        "query_location",
        "query_filter",
        "sap_focus",
        "role_family",
        "seniority",
        "modules",
        "skills",
        "soft_skills",
        "degree_levels",
        "degree_fields",
        "description_excerpt",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            copy = row.copy()
            for key in ["modules", "skills", "soft_skills", "degree_levels", "degree_fields"]:
                copy[key] = "; ".join(row.get(key, []))
            clean = {}
            for field in fields:
                value = copy.get(field, "")
                clean[field] = value.strip() if isinstance(value, str) else value
            writer.writerow(clean)


def build_summary(rows: List[Dict[str, Any]], search_count: int, errors: Dict[str, str]) -> Dict[str, Any]:
    partitions = {
        (row.get("query", ""), row.get("query_location", ""), row.get("query_filter", ""))
        for row in rows
        if row.get("query") and row.get("query_location")
    }
    description_enriched = sum(1 for row in rows if len(normalize_space(row.get("description", ""))) >= 80)
    return {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "methodology": "LinkedIn public guest job search endpoints, without logged-in cookies, proxies, or anti-bot bypass. Result depth is limited by LinkedIn's public pagination behavior and should be treated as a collected link pool, not the full 371,000+ market.",
        "search_partitions_collected": len(partitions),
        "latest_run_searches_attempted": search_count,
        "latest_run_partition_offset": PARTITION_OFFSET,
        "latest_run_partition_limit": MAX_PARTITIONS or None,
        "searches_attempted": len(partitions),
        "jobs_collected": len(rows),
        "description_enriched_jobs": description_enriched,
        "description_enriched_share": round(description_enriched / len(rows), 4) if rows else 0,
        "locations": count_values(rows, "location"),
        "queries": count_values(rows, "query"),
        "query_locations": count_values(rows, "query_location"),
        "query_filters": count_values(rows, "query_filter"),
        "role_families": count_values(rows, "role_family"),
        "seniority": count_values(rows, "seniority"),
        "modules": count_values(rows, "modules", multi=True),
        "skills": count_values(rows, "skills", multi=True),
        "soft_skills": count_values(rows, "soft_skills", multi=True),
        "degree_levels": count_values(rows, "degree_levels", multi=True),
        "degree_fields": count_values(rows, "degree_fields", multi=True),
        "errors": errors,
    }


def save_outputs(rows: List[Dict[str, Any]], searches_attempted: int, errors: Dict[str, str]) -> Dict[str, Any]:
    rows = sorted(dedupe(rows), key=lambda row: (row.get("query", ""), row.get("location", ""), row.get("company", ""), row.get("title", "")))
    summary = build_summary(rows, searches_attempted, errors)

    write_json(PROCESSED_DIR / "linkedin_jobs.json", rows)
    write_csv(PROCESSED_DIR / "linkedin_jobs.csv", rows)
    write_json(PROCESSED_DIR / "linkedin_jobs_summary.json", summary)
    write_json(SNAPSHOT_DIR / "linkedin_jobs.json", rows)
    write_csv(SNAPSHOT_DIR / "linkedin_jobs.csv", rows)
    write_json(SNAPSHOT_DIR / "linkedin_jobs_summary.json", summary)
    refresh_snapshot_index()
    return summary


def backfill_missing_details(rows: List[Dict[str, Any]], errors: Dict[str, str]) -> int:
    filled = 0
    for row in rows:
        if filled >= MAX_DETAILS:
            break
        if not needs_detail(row):
            continue
        if apply_detail(row, errors):
            filled += 1
            if filled % 25 == 0:
                save_outputs(rows, 0, errors)
            time.sleep(REQUEST_DELAY_SECONDS)
    return filled


def refresh_snapshot_index() -> None:
    root = SNAPSHOT_DIR.parent
    entries = []
    for path in sorted(root.iterdir()):
        if not path.is_dir():
            continue
        summary_path = path / "summary.json"
        if not summary_path.exists():
            continue
        item = sap_core.load_snapshot_summary(summary_path)
        if item:
            entries.append(item)
    write_json(root / "index.json", entries)


def main() -> None:
    queries = split_file_or_env("LINKEDIN_QUERY_FILE", "LINKEDIN_QUERIES", DEFAULT_QUERIES)
    locations = split_file_or_env("LINKEDIN_LOCATION_FILE", "LINKEDIN_LOCATIONS", DEFAULT_LOCATIONS)
    filter_names = split_env("LINKEDIN_FILTERS", ["all", "past_week", "remote"])
    unknown_filters = [name for name in filter_names if name not in FILTER_DEFINITIONS]
    if unknown_filters:
        raise SystemExit(f"Unknown LINKEDIN_FILTERS values: {', '.join(unknown_filters)}")
    filters = [(name, FILTER_DEFINITIONS[name]) for name in filter_names]
    partitions = [(query, location, filter_name, extra) for query in queries for location in locations for filter_name, extra in filters]
    total_partitions = len(partitions)
    if PARTITION_OFFSET:
        partitions = partitions[PARTITION_OFFSET:]
    if MAX_PARTITIONS:
        partitions = partitions[:MAX_PARTITIONS]

    rows = load_existing()
    seen_ids = {row.get("linkedin_job_id") for row in rows if row.get("linkedin_job_id")}
    errors: Dict[str, str] = {}
    searches_attempted = 0
    detail_fetches = 0

    if BACKFILL_ONLY:
        filled = backfill_missing_details(rows, errors)
        summary = save_outputs(rows, searches_attempted, errors)
        print(f"Backfilled details for {filled} LinkedIn rows, total {summary['jobs_collected']}", flush=True)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return

    print(
        f"Partition plan: running {len(partitions)} of {total_partitions} partitions "
        f"(offset={PARTITION_OFFSET}, limit={MAX_PARTITIONS or 'all'})",
        flush=True,
    )

    try:
        for query, location, filter_name, extra in partitions:
            searches_attempted += 1
            before = len(rows)
            for page in range(MAX_PAGES_PER_SEARCH):
                start = page * PAGE_STEP
                params = {"keywords": query, "location": location, "start": start}
                params.update(extra)
                try:
                    body = fetch_text_with_backoff(SEARCH_URL, params, f"{query}|{location}|{filter_name}|{start}")
                except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
                    errors[f"{query}|{location}|{filter_name}|{start}"] = str(exc)
                    break
                cards = parse_cards(body)
                if not cards:
                    break
                for card in cards:
                    job_id = card.get("linkedin_job_id")
                    if job_id in seen_ids:
                        continue
                    seen_ids.add(job_id)
                    card.update(
                        {
                            "query": query,
                            "query_location": location,
                            "query_filter": filter_name,
                            "fetched_at": dt.datetime.now().isoformat(timespec="seconds"),
                        }
                    )
                    if detail_fetches < MAX_DETAILS and job_id:
                        if apply_detail(card, errors):
                            detail_fetches += 1
                            time.sleep(REQUEST_DELAY_SECONDS)
                    rows.append(enrich(card))
                time.sleep(REQUEST_DELAY_SECONDS)
            summary = save_outputs(rows, searches_attempted, errors)
            print(
                f"{query} | {location} | {filter_name}: +{len(rows) - before} new, total {summary['jobs_collected']}",
                flush=True,
            )
    except KeyboardInterrupt:
        summary = save_outputs(rows, searches_attempted, errors)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        raise

    summary = save_outputs(rows, searches_attempted, errors)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

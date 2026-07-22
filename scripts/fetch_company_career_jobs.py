#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import datetime as dt
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import fetch_sap_jobs as base


ROOT = Path(__file__).resolve().parents[1]
CONFIG_FILE = ROOT / "data" / "config" / "company_career_sources.json"
SNAPSHOT_DATE = os.environ.get("SNAPSHOT_DATE", dt.date.today().isoformat())
RAW_DIR = ROOT / "data" / "raw" / SNAPSHOT_DATE / "company_careers"
PROCESSED_DIR = ROOT / "data" / "processed"
SNAPSHOT_DIR = ROOT / "data" / "snapshots" / SNAPSHOT_DATE
PID_FILE = ROOT / "data" / "run_state" / "company_career_crawl.pid"

USER_AGENT = "sap-market-report/1.0 (+public-company-career-research)"
REQUEST_TIMEOUT_SECONDS = float(os.environ.get("COMPANY_CAREER_TIMEOUT_SECONDS", "25"))
REQUEST_DELAY_SECONDS = float(os.environ.get("COMPANY_CAREER_DELAY_SECONDS", "0.15"))
DEFAULT_MAX_WORKERS = int(os.environ.get("COMPANY_CAREER_MAX_WORKERS", "6"))
SMARTRECRUITERS_PAGE_SIZE = int(os.environ.get("COMPANY_CAREER_SMARTRECRUITERS_PAGE_SIZE", "100"))
WORKDAY_PAGE_SIZE = int(os.environ.get("COMPANY_CAREER_WORKDAY_PAGE_SIZE", "20"))


class Jobs2WebSearchParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__()
        self.base_url = base_url
        self.rows: List[Dict[str, str]] = []
        self.current: Optional[Dict[str, Any]] = None
        self.capture_title = False
        self.capture_location = False
        self.row_depth = 0

    def handle_starttag(self, tag: str, attrs_list: List[tuple[str, Optional[str]]]) -> None:
        attrs = {key: value or "" for key, value in attrs_list}
        class_name = attrs.get("class", "")
        if tag == "tr" and "data-row" in class_name:
            self.current = {"title_parts": [], "location_parts": []}
            self.row_depth = 1
            return
        if not self.current:
            return
        self.row_depth += 1
        if tag == "a" and "jobTitle-link" in class_name and not self.current.get("url"):
            href = html.unescape(attrs.get("href", ""))
            self.current["url"] = urllib.parse.urljoin(self.base_url, href)
            self.capture_title = True
        elif tag == "td" and "colLocation" in class_name:
            self.capture_location = True

    def handle_data(self, data: str) -> None:
        if not self.current:
            return
        if self.capture_title:
            self.current["title_parts"].append(data)
        if self.capture_location:
            self.current["location_parts"].append(data)

    def handle_endtag(self, tag: str) -> None:
        if not self.current:
            return
        if tag == "a":
            self.capture_title = False
        elif tag == "td":
            self.capture_location = False
        elif tag == "tr":
            title = base.normalize_space(" ".join(self.current.get("title_parts", [])))
            location = base.normalize_space(" ".join(self.current.get("location_parts", [])))
            url = self.current.get("url", "")
            if title and url:
                self.rows.append({"title": title, "location": location, "url": url})
            self.current = None
            self.row_depth = 0
            self.capture_title = False
            self.capture_location = False
            return
        self.row_depth = max(0, self.row_depth - 1)


class Jobs2WebDescriptionParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.capture_depth = 0
        self.parts: List[str] = []

    def handle_starttag(self, tag: str, attrs_list: List[tuple[str, Optional[str]]]) -> None:
        attrs = {key: value or "" for key, value in attrs_list}
        if self.capture_depth:
            self.capture_depth += 1
            return
        if tag == "span" and "jobdescription" in attrs.get("class", ""):
            self.capture_depth = 1

    def handle_data(self, data: str) -> None:
        if self.capture_depth:
            self.parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self.capture_depth:
            self.capture_depth -= 1

    def text(self) -> str:
        return base.normalize_space(" ".join(self.parts))


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
            raise SystemExit(f"Company career crawl is already running with pid {existing}")
    pid_file.write_text(str(os.getpid()), encoding="utf-8")


def release_lock(pid_file: Path) -> None:
    try:
        if pid_file.exists() and pid_file.read_text(encoding="utf-8").strip() == str(os.getpid()):
            pid_file.unlink()
    except OSError:
        pass


def fetch_text(url: str, headers: Optional[Dict[str, str]] = None, data: Optional[bytes] = None) -> str:
    request_headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json,text/html,application/rss+xml,text/xml,*/*",
    }
    if headers:
        request_headers.update(headers)
    req = urllib.request.Request(url, data=data, headers=request_headers)
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_SECONDS) as resp:
        return resp.read().decode("utf-8", errors="replace")


def fetch_json(url: str, headers: Optional[Dict[str, str]] = None, data: Optional[bytes] = None) -> Any:
    return json.loads(fetch_text(url, headers=headers, data=data))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def flatten_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return base.html_to_text(value)
    if isinstance(value, dict):
        return base.normalize_space(" ".join(flatten_text(item) for item in value.values()))
    if isinstance(value, list):
        return base.normalize_space(" ".join(flatten_text(item) for item in value))
    return base.normalize_space(value)


def infer_salary(description: str) -> tuple[None, None, None, None]:
    return None, None, None, None


def normalize_company_job(raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    title = base.normalize_space(raw.get("title"))
    company = base.normalize_space(raw.get("company"))
    description = base.normalize_space(raw.get("description"))
    url = raw.get("url")
    source = raw.get("source") or raw.get("provider") or "Company Career"
    if not title or not company or not url:
        return None

    text = base.normalize_space(f"{title} {company} {description}")
    if not base.is_sap_job(text):
        return None

    locations = base.split_locations(raw.get("location"))
    if not locations:
        locations = ["Remote / Not specified"] if raw.get("remote") else ["Not specified"]
    modules = base.regex_hits(base.MODULE_PATTERNS, text)
    skills = base.regex_hits(base.SKILL_PATTERNS, text)
    salary_min, salary_max, currency, salary_period = infer_salary(description)

    row = {
        "id": base.stable_id([source, url, title, company]),
        "source": source,
        "title": title,
        "company": company,
        "url": url,
        "posted_at": raw.get("posted_at"),
        "locations": locations,
        "primary_location": locations[0],
        "remote": bool(raw.get("remote")),
        "salary_status": base.salary_state(salary_min, salary_max, text=description),
        "salary_min": salary_min,
        "salary_max": salary_max,
        "salary_currency": currency,
        "salary_period": salary_period,
        "sap_focus": base.classify_focus(title, text, modules or ["Unspecified SAP"]),
        "role_family": base.classify_role(title, text),
        "seniority": base.classify_seniority(title, description),
        "modules": modules or ["Unspecified SAP"],
        "skills": skills,
        "description_excerpt": description[:420],
        "match_terms": base.regex_hits(base.STRONG_SAP_PATTERNS, text),
        "provider": raw.get("provider"),
        "source_key": raw.get("source_key"),
    }
    return row


def collect_jobs2web(source: Dict[str, Any]) -> Dict[str, Any]:
    base_url = source["base_url"].rstrip("/")
    queries = source.get("queries") or ["SAP"]
    max_pages = int(source.get("max_pages") or 10)
    fetch_details = bool(source.get("fetch_details", True))
    fetch_details_override = os.environ.get("COMPANY_CAREER_JOBS2WEB_FETCH_DETAILS")
    if fetch_details_override is not None:
        fetch_details = fetch_details_override == "1"
    raw_jobs: List[Dict[str, Any]] = []
    seen_urls = set()

    for query in queries:
        for page in range(max_pages):
            params = {
                "q": query,
                "sortColumn": "referencedate",
                "sortDirection": "desc",
                "startrow": page * 25,
            }
            url = f"{base_url}/search/?{urllib.parse.urlencode(params)}"
            body = fetch_text(url)
            parser = Jobs2WebSearchParser(base_url)
            parser.feed(body)
            if not parser.rows:
                break
            new_rows = 0
            for item in parser.rows:
                if item["url"] in seen_urls:
                    continue
                seen_urls.add(item["url"])
                new_rows += 1
                description = ""
                if fetch_details:
                    try:
                        detail_body = fetch_text(item["url"])
                        detail_parser = Jobs2WebDescriptionParser()
                        detail_parser.feed(detail_body)
                        description = detail_parser.text()
                    except (urllib.error.URLError, TimeoutError, OSError):
                        description = ""
                    time.sleep(REQUEST_DELAY_SECONDS)
                raw_jobs.append(
                    {
                        "provider": "jobs2web",
                        "source_key": source["key"],
                        "source": source.get("source") or source.get("company") or source["key"],
                        "company": source.get("company") or source.get("source") or source["key"],
                        "title": item["title"],
                        "location": item.get("location"),
                        "url": item["url"],
                        "description": description,
                        "remote": bool(re.search(r"\bremote\b", item.get("location", ""), flags=re.IGNORECASE)),
                        "query": query,
                    }
                )
            if new_rows == 0:
                break
            time.sleep(REQUEST_DELAY_SECONDS)

    return {"source": source, "raw_jobs": raw_jobs}


def collect_smartrecruiters(source: Dict[str, Any]) -> Dict[str, Any]:
    identifier = source["company_identifier"]
    queries = source.get("queries") or ["sap"]
    max_pages = int(source.get("max_pages") or 3)
    raw_jobs: List[Dict[str, Any]] = []
    seen_ids = set()

    for query in queries:
        for page in range(max_pages):
            params = {
                "limit": SMARTRECRUITERS_PAGE_SIZE,
                "offset": page * SMARTRECRUITERS_PAGE_SIZE,
                "q": query,
            }
            url = f"https://api.smartrecruiters.com/v1/companies/{identifier}/postings?{urllib.parse.urlencode(params)}"
            payload = fetch_json(url, headers={"Accept": "application/json"})
            content = payload.get("content") or []
            if not content:
                break
            for item in content:
                job_id = str(item.get("id") or item.get("uuid") or item.get("ref") or "")
                if not job_id or job_id in seen_ids:
                    continue
                seen_ids.add(job_id)
                detail = item
                try:
                    detail = fetch_json(
                        f"https://api.smartrecruiters.com/v1/companies/{identifier}/postings/{job_id}",
                        headers={"Accept": "application/json"},
                    )
                except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
                    detail = item
                location = detail.get("location") or item.get("location") or {}
                company_payload = detail.get("company") or item.get("company") or {}
                description = flatten_text(detail.get("jobAd") or item.get("jobAd"))
                raw_jobs.append(
                    {
                        "provider": "smartrecruiters",
                        "source_key": source["key"],
                        "source": source.get("source") or f"{source.get('company', identifier)} SmartRecruiters",
                        "company": source.get("company") or company_payload.get("name") or identifier,
                        "title": detail.get("name") or item.get("name"),
                        "location": location.get("fullLocation") or location.get("city") or location.get("country"),
                        "url": detail.get("postingUrl") or item.get("ref"),
                        "description": description,
                        "remote": bool(location.get("remote")),
                        "posted_at": detail.get("releasedDate") or item.get("releasedDate"),
                        "query": query,
                    }
                )
                time.sleep(REQUEST_DELAY_SECONDS)
            if len(content) < SMARTRECRUITERS_PAGE_SIZE:
                break
            time.sleep(REQUEST_DELAY_SECONDS)

    return {"source": source, "raw_jobs": raw_jobs}


def collect_greenhouse(source: Dict[str, Any]) -> Dict[str, Any]:
    board = source["board"]
    url = f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true"
    payload = fetch_json(url, headers={"Accept": "application/json"})
    raw_jobs = []
    for item in payload.get("jobs", []):
        location = item.get("location") or {}
        raw_jobs.append(
            {
                "provider": "greenhouse",
                "source_key": source["key"],
                "source": source.get("source") or f"{source.get('company', board)} Greenhouse",
                "company": source.get("company") or item.get("company_name") or board,
                "title": item.get("title"),
                "location": location.get("name"),
                "url": item.get("absolute_url"),
                "description": base.html_to_text(item.get("content")),
                "remote": bool(re.search(r"\bremote\b", location.get("name", ""), flags=re.IGNORECASE)),
                "posted_at": item.get("first_published") or item.get("updated_at"),
            }
        )
    return {"source": source, "raw_jobs": raw_jobs}


def collect_workday(source: Dict[str, Any]) -> Dict[str, Any]:
    host = source["host"].rstrip("/")
    tenant = source["tenant"]
    site = source["site"]
    queries = source.get("queries") or ["SAP"]
    max_pages = int(source.get("max_pages") or 3)
    seen_paths = set()
    raw_jobs: List[Dict[str, Any]] = []

    endpoint = f"{host}/wday/cxs/{tenant}/{site}/jobs"
    for query in queries:
        for page in range(max_pages):
            body = json.dumps(
                {
                    "appliedFacets": {},
                    "limit": WORKDAY_PAGE_SIZE,
                    "offset": page * WORKDAY_PAGE_SIZE,
                    "searchText": query,
                }
            ).encode("utf-8")
            payload = fetch_json(
                endpoint,
                headers={"Accept": "application/json", "Content-Type": "application/json"},
                data=body,
            )
            postings = payload.get("jobPostings") or []
            if not postings:
                break
            for item in postings:
                external_path = item.get("externalPath")
                if not external_path or external_path in seen_paths:
                    continue
                seen_paths.add(external_path)
                detail_url = f"{host}/wday/cxs/{tenant}/{site}{external_path}"
                detail = {}
                try:
                    detail = fetch_json(detail_url, headers={"Accept": "application/json"})
                except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
                    detail = {}
                posting_info = detail.get("jobPostingInfo") or {}
                description = base.html_to_text(posting_info.get("jobDescription"))
                raw_jobs.append(
                    {
                        "provider": "workday",
                        "source_key": source["key"],
                        "source": source.get("source") or f"{source.get('company')} Workday",
                        "company": source.get("company") or (detail.get("hiringOrganization") or {}).get("name"),
                        "title": posting_info.get("title") or item.get("title"),
                        "location": posting_info.get("location") or item.get("locationsText"),
                        "url": f"{host}/{site}{external_path}",
                        "description": description,
                        "remote": bool(re.search(r"\bremote\b", item.get("locationsText", ""), flags=re.IGNORECASE)),
                        "posted_at": posting_info.get("startDate") or item.get("postedOn"),
                        "query": query,
                    }
                )
                time.sleep(REQUEST_DELAY_SECONDS)
            if len(postings) < WORKDAY_PAGE_SIZE:
                break
            time.sleep(REQUEST_DELAY_SECONDS)

    return {"source": source, "raw_jobs": raw_jobs}


COLLECTORS = {
    "jobs2web": collect_jobs2web,
    "smartrecruiters": collect_smartrecruiters,
    "greenhouse": collect_greenhouse,
    "workday": collect_workday,
}


def dedupe(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    deduped = []
    for row in rows:
        key = base.normalize_space(f"{row['title']}|{row['company']}|{row.get('url') or ''}").lower()
        fallback = base.normalize_space(f"{row['title']}|{row['company']}|{row.get('primary_location') or ''}").lower()
        hashed = base.stable_id([key or fallback])
        if hashed in seen:
            continue
        seen.add(hashed)
        deduped.append(row)
    return deduped


def load_existing() -> List[Dict[str, Any]]:
    path = PROCESSED_DIR / "company_career_jobs.json"
    if not path.exists():
        return []
    rows = json.loads(path.read_text(encoding="utf-8"))
    for row in rows:
        seen_at = row.get("last_seen_at") or row.get("first_seen_at") or ""
        row.setdefault("first_seen_at", row.get("first_seen_at") or seen_at)
        row.setdefault("last_seen_at", seen_at)
        row.setdefault("first_seen_snapshot", row.get("first_seen_snapshot") or row.get("last_seen_snapshot") or SNAPSHOT_DATE)
        row.setdefault("last_seen_snapshot", row.get("last_seen_snapshot") or SNAPSHOT_DATE)
    return rows


def mark_seen(row: Dict[str, Any], seen_at: str) -> None:
    row.setdefault("first_seen_at", seen_at)
    row.setdefault("first_seen_snapshot", SNAPSHOT_DATE)
    row["last_seen_at"] = seen_at
    row["last_seen_snapshot"] = SNAPSHOT_DATE


def merge_existing(existing_rows: List[Dict[str, Any]], current_rows: List[Dict[str, Any]], seen_at: str) -> List[Dict[str, Any]]:
    merged_by_id = {row.get("id"): row for row in existing_rows if row.get("id")}
    for row in current_rows:
        row_id = row.get("id")
        if row_id in merged_by_id:
            previous = merged_by_id[row_id]
            first_seen_at = previous.get("first_seen_at")
            first_seen_snapshot = previous.get("first_seen_snapshot")
            if not row.get("description_excerpt") and previous.get("description_excerpt"):
                for key in [
                    "description_excerpt",
                    "salary_status",
                    "salary_min",
                    "salary_max",
                    "salary_currency",
                    "salary_period",
                    "sap_focus",
                    "role_family",
                    "seniority",
                    "modules",
                    "skills",
                    "match_terms",
                ]:
                    row[key] = previous.get(key)
            previous.update(row)
            if first_seen_at:
                previous["first_seen_at"] = first_seen_at
            if first_seen_snapshot:
                previous["first_seen_snapshot"] = first_seen_snapshot
            mark_seen(previous, seen_at)
        else:
            mark_seen(row, seen_at)
            merged_by_id[row_id] = row
    return list(merged_by_id.values())


def write_company_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "id",
        "source",
        "provider",
        "source_key",
        "title",
        "company",
        "primary_location",
        "locations",
        "remote",
        "salary_status",
        "salary_min",
        "salary_max",
        "salary_currency",
        "salary_period",
        "sap_focus",
        "role_family",
        "seniority",
        "modules",
        "skills",
        "posted_at",
        "first_seen_at",
        "last_seen_at",
        "first_seen_snapshot",
        "last_seen_snapshot",
        "url",
        "description_excerpt",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            copy = row.copy()
            copy["locations"] = "; ".join(row.get("locations", []))
            copy["modules"] = "; ".join(row.get("modules", []))
            copy["skills"] = "; ".join(row.get("skills", []))
            writer.writerow({field: copy.get(field, "") for field in fields})


def run_source(provider: str, source: Dict[str, Any]) -> Dict[str, Any]:
    started = time.monotonic()
    collector = COLLECTORS[provider]
    result = collector(source)
    normalized = [item for item in (normalize_company_job(raw) for raw in result["raw_jobs"]) if item]
    return {
        "provider": provider,
        "source_key": source["key"],
        "source_label": source.get("source") or source.get("company") or source["key"],
        "raw_count": len(result["raw_jobs"]),
        "sap_count": len(normalized),
        "duration_seconds": round(time.monotonic() - started, 2),
        "raw_jobs": result["raw_jobs"],
        "normalized": normalized,
    }


def iter_sources(config: Dict[str, Any], include_providers: Optional[set[str]] = None) -> Iterable[tuple[str, Dict[str, Any]]]:
    for provider, sources in config.items():
        if include_providers and provider not in include_providers:
            continue
        if provider not in COLLECTORS:
            continue
        for source in sources:
            yield provider, source


def build_company_summary(rows: List[Dict[str, Any]], raw_source_counts: Dict[str, int], run_results: List[Dict[str, Any]], errors: Dict[str, str]) -> Dict[str, Any]:
    summary = base.build_summary(rows, raw_source_counts)
    provider_counts = Counter(row.get("provider") or "unknown" for row in rows)
    company_counts = Counter(row.get("company") or "unknown" for row in rows)
    active_seen = sum(1 for row in rows if row.get("last_seen_snapshot") == SNAPSHOT_DATE)
    new_seen = sum(1 for row in rows if row.get("first_seen_snapshot") == SNAPSHOT_DATE)
    summary.update(
        {
            "methodology": "Public company career pages and ATS endpoints only. No logged-in sessions, proxy rotation, CAPTCHA bypass, or private candidate data are used.",
            "jobs_collected": len(rows),
            "jobs_seen_in_snapshot": active_seen,
            "new_jobs_in_snapshot": new_seen,
            "providers": dict(sorted(provider_counts.items(), key=lambda item: (-item[1], item[0]))),
            "companies": dict(sorted(company_counts.items(), key=lambda item: (-item[1], item[0]))),
            "source_runs": [
                {
                    "provider": item["provider"],
                    "source_key": item["source_key"],
                    "source_label": item["source_label"],
                    "raw_count": item["raw_count"],
                    "sap_count": item["sap_count"],
                    "duration_seconds": item["duration_seconds"],
                }
                for item in sorted(run_results, key=lambda item: item["source_label"])
            ],
            "errors": errors,
        }
    )
    return summary


def write_snapshot(rows: List[Dict[str, Any]], summary: Dict[str, Any]) -> None:
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    write_json(SNAPSHOT_DIR / "company_career_jobs.json", rows)
    write_company_csv(SNAPSHOT_DIR / "company_career_jobs.csv", rows)
    write_json(SNAPSHOT_DIR / "company_career_jobs_summary.json", summary)


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect SAP jobs from public company career pages and ATS feeds.")
    parser.add_argument("--config", type=Path, default=CONFIG_FILE)
    parser.add_argument("--providers", default="", help="Comma-separated provider allow-list, e.g. jobs2web,smartrecruiters")
    parser.add_argument("--max-workers", type=int, default=DEFAULT_MAX_WORKERS)
    parser.add_argument("--replace", action="store_true", help="Replace the company career pool instead of merging into existing history.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    config_path = args.config if args.config.is_absolute() else ROOT / args.config
    config = json.loads(config_path.read_text(encoding="utf-8"))
    include_providers = {item.strip() for item in args.providers.split(",") if item.strip()} or None
    sources = list(iter_sources(config, include_providers))
    print(
        json.dumps(
            {
                "started_at": dt.datetime.now().isoformat(timespec="seconds"),
                "sources": len(sources),
                "providers": sorted({provider for provider, _source in sources}),
                "max_workers": args.max_workers,
            },
            ensure_ascii=False,
            indent=2,
        ),
        flush=True,
    )
    if args.dry_run:
        return

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    acquire_lock(PID_FILE)
    run_results: List[Dict[str, Any]] = []
    errors: Dict[str, str] = {}
    normalized: List[Dict[str, Any]] = []
    raw_source_counts: Dict[str, int] = {}
    try:
        with ThreadPoolExecutor(max_workers=max(1, args.max_workers)) as executor:
            futures = {executor.submit(run_source, provider, source): (provider, source) for provider, source in sources}
            for future in as_completed(futures):
                provider, source = futures[future]
                label = source.get("source") or source.get("company") or source.get("key") or provider
                try:
                    result = future.result()
                    run_results.append(result)
                    normalized.extend(result["normalized"])
                    raw_source_counts[result["source_label"]] = result["raw_count"]
                    write_json(RAW_DIR / f"{result['source_key']}.json", result["raw_jobs"])
                    print(
                        f"{label}: raw={result['raw_count']} sap={result['sap_count']} duration={result['duration_seconds']}s",
                        flush=True,
                    )
                except Exception as exc:
                    errors[f"{provider}:{source.get('key', label)}"] = repr(exc)
                    raw_source_counts[label] = 0
                    print(f"{label}: ERROR {exc!r}", flush=True)

        current_rows = dedupe(normalized)
        if args.replace:
            seen_at = dt.datetime.now().isoformat(timespec="seconds")
            for row in current_rows:
                mark_seen(row, seen_at)
            rows = current_rows
        else:
            rows = merge_existing(load_existing(), current_rows, dt.datetime.now().isoformat(timespec="seconds"))
        rows = sorted(rows, key=lambda row: (row["source"], row["company"], row["title"]))
        summary = build_company_summary(rows, raw_source_counts, run_results, errors)
        write_json(PROCESSED_DIR / "company_career_jobs.json", rows)
        write_company_csv(PROCESSED_DIR / "company_career_jobs.csv", rows)
        write_json(PROCESSED_DIR / "company_career_jobs_summary.json", summary)
        write_snapshot(rows, summary)
        print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    finally:
        release_lock(PID_FILE)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import gzip
import html
import json
import os
from pathlib import Path
from typing import Dict, List, Tuple
from urllib.parse import urlencode


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "processed"
REPORT_DIR = ROOT / "report"
SNAPSHOT_INDEX = ROOT / "data" / "snapshots" / "index.json"
DATA_URL_BASE = os.environ.get(
    "REPORT_DATA_URL_BASE",
    "https://sarper1998.github.io/global-sap-job-market-report/data",
).rstrip("/")
SAP_JOBS_CSV_URL = f"{DATA_URL_BASE}/sap_jobs.csv"
SAP_JOBS_JSON_URL = f"{DATA_URL_BASE}/sap_jobs.json"
LINKEDIN_SIGNAL_URL = f"{DATA_URL_BASE}/linkedin_signal.json"
LINKEDIN_JOBS_CSV_URL = f"{DATA_URL_BASE}/linkedin_jobs.csv.gz"
LINKEDIN_JOBS_JSON_URL = f"{DATA_URL_BASE}/linkedin_jobs.json.gz"
LINKEDIN_JOBS_SUMMARY_URL = f"{DATA_URL_BASE}/linkedin_jobs_summary.json"
COMPANY_CAREER_CSV_URL = f"{DATA_URL_BASE}/company_career_jobs.csv"
COMPANY_CAREER_JSON_URL = f"{DATA_URL_BASE}/company_career_jobs.json"
COMPANY_CAREER_SUMMARY_URL = f"{DATA_URL_BASE}/company_career_jobs_summary.json"


def load_json(path: Path):
    if not path.exists() and path.with_name(f"{path.name}.gz").exists():
        with gzip.open(path.with_name(f"{path.name}.gz"), "rt", encoding="utf-8") as handle:
            return json.load(handle)
    return json.loads(path.read_text(encoding="utf-8"))


def pct(part: int, total: int) -> str:
    if not total:
        return "0%"
    return f"{(part / total) * 100:.1f}%"


def fmt_int(value: int) -> str:
    return f"{value:,}"


def top_items(counts: Dict[str, int], n: int = 8) -> List[Tuple[str, int]]:
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:n]


def list_counts(items: List[Dict], label_key: str) -> Dict[str, int]:
    return {str(item[label_key]): int(item["count"]) for item in items if item.get(label_key) and item.get("count") is not None}


def linkedin_specialist_keyword_counts(linkedin: Dict) -> Dict[str, int]:
    counts = list_counts(linkedin.get("keyword_counts", []), "keyword") if linkedin else {}
    cleaned = {}
    for keyword, count in counts.items():
        if keyword == "SAP":
            continue
        label = keyword.removeprefix("SAP ").strip() or keyword
        cleaned[label] = count
    return cleaned


def optional_json(path: Path, fallback):
    if not path.exists() and not path.with_name(f"{path.name}.gz").exists():
        return fallback
    return load_json(path)


def load_snapshots() -> List[Dict]:
    by_date: Dict[str, Dict] = {}

    if SNAPSHOT_INDEX.exists():
        snapshots = load_json(SNAPSHOT_INDEX)
        if isinstance(snapshots, list):
            for item in snapshots:
                if isinstance(item, dict) and item.get("date"):
                    by_date[str(item["date"])] = dict(item)

    snapshot_root = SNAPSHOT_INDEX.parent
    if snapshot_root.exists():
        for date_dir in sorted(path for path in snapshot_root.iterdir() if path.is_dir()):
            date = date_dir.name
            item = by_date.setdefault(date, {"date": date})

            summary = optional_json(date_dir / "summary.json", {})
            if summary:
                item["generated_at"] = max(str(item.get("generated_at") or ""), str(summary.get("generated_at") or ""))
                item["sap_jobs_after_filter"] = int(summary.get("sap_jobs_after_filter") or item.get("sap_jobs_after_filter") or 0)
                if summary.get("salary_disclosure"):
                    item["salary_disclosure"] = summary.get("salary_disclosure")
                if summary.get("modules"):
                    item["top_modules"] = dict(top_items(summary.get("modules", {}), 5))
                if summary.get("primary_locations"):
                    item["top_locations"] = dict(top_items(summary.get("primary_locations", {}), 5))

            linkedin_summary = optional_json(date_dir / "linkedin_jobs_summary.json", {})
            if linkedin_summary:
                item["generated_at"] = max(str(item.get("generated_at") or ""), str(linkedin_summary.get("generated_at") or ""))
                item["linkedin_jobs_collected"] = int(linkedin_summary.get("jobs_collected") or item.get("linkedin_jobs_collected") or 0)

            linkedin_signal = optional_json(date_dir / "linkedin_signal.json", {})
            if linkedin_signal:
                global_count = linkedin_signal.get("global_count") or {}
                item["linkedin_global_count"] = int(global_count.get("count") or item.get("linkedin_global_count") or 0)
                item["linkedin_global_count_text"] = global_count.get("count_text") or item.get("linkedin_global_count_text")

            company_summary = optional_json(date_dir / "company_career_jobs_summary.json", {})
            if company_summary:
                item["company_career_jobs_collected"] = int(company_summary.get("jobs_collected") or company_summary.get("sap_jobs_after_filter") or 0)

    current_parts = [
        optional_json(DATA_DIR / "summary.json", {}),
        optional_json(DATA_DIR / "linkedin_jobs_summary.json", {}),
        optional_json(DATA_DIR / "company_career_jobs_summary.json", {}),
    ]
    current_generated = max((str(part.get("generated_at")) for part in current_parts if part.get("generated_at")), default="")
    if current_generated:
        current_date = current_generated[:10]
        item = by_date.setdefault(current_date, {"date": current_date})
        item["generated_at"] = max(str(item.get("generated_at") or ""), current_generated)

        current_summary = current_parts[0]
        if current_summary:
            item["sap_jobs_after_filter"] = int(current_summary.get("sap_jobs_after_filter") or item.get("sap_jobs_after_filter") or 0)
            if current_summary.get("salary_disclosure"):
                item["salary_disclosure"] = current_summary.get("salary_disclosure")
            if current_summary.get("modules"):
                item["top_modules"] = dict(top_items(current_summary.get("modules", {}), 5))
            if current_summary.get("primary_locations"):
                item["top_locations"] = dict(top_items(current_summary.get("primary_locations", {}), 5))

        current_linkedin = current_parts[1]
        if current_linkedin:
            item["linkedin_jobs_collected"] = int(current_linkedin.get("jobs_collected") or item.get("linkedin_jobs_collected") or 0)

        current_company = current_parts[2]
        if current_company:
            item["company_career_jobs_collected"] = int(current_company.get("jobs_collected") or current_company.get("sap_jobs_after_filter") or 0)

        current_signal = optional_json(DATA_DIR / "linkedin_signal.json", {})
        if current_signal:
            global_count = current_signal.get("global_count") or {}
            item["linkedin_global_count"] = int(global_count.get("count") or item.get("linkedin_global_count") or 0)
            item["linkedin_global_count_text"] = global_count.get("count_text") or item.get("linkedin_global_count_text")

    return [by_date[key] for key in sorted(by_date)]


def history_counts(snapshots: List[Dict], key: str) -> Dict[str, int]:
    values: Dict[str, int] = {}
    for item in snapshots:
        date = str(item.get("date") or "")
        value = int(item.get(key) or 0)
        if date and value > 0:
            values[date] = value
    return values


def linkedin_jobs_url(keyword: str = "SAP", location: str = "Worldwide", extra: Dict[str, str] | None = None) -> str:
    params = {"keywords": keyword, "location": location}
    if extra:
        params.update(extra)
    return "https://www.linkedin.com/jobs/search/?" + urlencode(params)


def build_linkedin_search_links(linkedin: Dict) -> str:
    if not linkedin:
        return ""

    week_item = next((item for item in linkedin.get("recency_counts", []) if item.get("label") == "Past week"), {})
    remote_item = next((item for item in linkedin.get("work_model_counts", []) if item.get("label") == "Remote"), {})
    links = [
        ("SAP worldwide", linkedin.get("global_count", {}).get("count_text", ""), linkedin_jobs_url()),
        ("SAP posted past week", week_item.get("count_text", ""), linkedin_jobs_url(extra={"f_TPR": "r604800"})),
        ("SAP remote", remote_item.get("count_text", ""), linkedin_jobs_url(extra={"f_WT": "2"})),
    ]
    for item in linkedin.get("location_counts", [])[:4]:
        links.append((f"SAP in {item.get('location', '')}", item.get("count_text", ""), linkedin_jobs_url(location=item.get("location", "Worldwide"))))
    for item in linkedin.get("keyword_counts", [])[1:5]:
        links.append((item.get("keyword", ""), item.get("count_text", ""), linkedin_jobs_url(keyword=item.get("keyword", "SAP"))))

    cards = []
    for label, count_text, url in links:
        cards.append(
            f"""<a href="{html.escape(url)}" target="_blank" rel="noopener"><span>{html.escape(label)}</span><strong>{html.escape(count_text)}</strong></a>"""
        )
    return "\n".join(cards)


def chip_list(values: List[str], limit: int = 4) -> str:
    visible = values[:limit]
    chips = "".join(f"<span>{html.escape(value)}</span>" for value in visible)
    if len(values) > limit:
        chips += f"<span>+{len(values) - limit}</span>"
    return chips


def top_count(summary: Dict, key: str) -> Tuple[str, int]:
    items = top_items(summary.get(key, {}), 1)
    return items[0] if items else ("N/A", 0)


def format_salary(job: Dict) -> str:
    status = job.get("salary_status", "Not disclosed")
    salary_min = job.get("salary_min")
    salary_max = job.get("salary_max")
    currency = job.get("salary_currency") or ""
    period = job.get("salary_period") or ""
    if status == "Not disclosed":
        return "Not disclosed"
    values = [value for value in [salary_min, salary_max] if value not in (None, "", 0, "0")]
    if not values:
        return html.escape(status)
    if len(values) == 1 or values[0] == values[-1]:
        amount = f"{currency} {values[0]}".strip()
    else:
        amount = f"{currency} {values[0]}-{values[-1]}".strip()
    return html.escape(f"{amount} {period}".strip())


def source_label(source: str) -> str:
    return {
        "himalayas": "Himalayas",
        "remotefirst": "Remote First Jobs",
        "jobicy": "Jobicy",
        "remotive": "Remotive",
        "remoteok": "Remote OK",
        "arbeitnow": "Arbeitnow",
    }.get(source, source)


def bars_markup(counts: Dict[str, int], limit: int = 8) -> str:
    items = top_items(counts, limit)
    max_value = max((value for _label, value in items), default=1)
    rows = []
    for index, (label, value) in enumerate(items):
        width = max(4, (value / max_value) * 100)
        rows.append(
            f"""
            <div class="bar-row">
              <div class="bar-label" title="{html.escape(label)}">{html.escape(label)}</div>
              <div class="bar-track"><div class="bar-fill" style="width:{width:.1f}%"></div></div>
              <div>{fmt_int(value)}</div>
            </div>
            """
        )
    return "\n".join(rows)


def build_table_rows(jobs: List[Dict]) -> str:
    rows = []
    for job in jobs:
        modules = chip_list(job.get("modules", []), 3)
        title = html.escape(job.get("title", ""))
        company = html.escape(job.get("company", ""))
        location = html.escape(job.get("primary_location", ""))
        role = html.escape(job.get("role_family", ""))
        seniority = html.escape(job.get("seniority", ""))
        focus = html.escape(job.get("sap_focus", ""))
        salary = format_salary(job)
        source = html.escape(source_label(job.get("source", "")))
        url = html.escape(job.get("url") or "#")
        rows.append(
            f"""
            <tr data-role="{role}" data-source="{source}" data-search="{title.lower()} {company.lower()} {location.lower()} {role.lower()}">
              <td><a href="{url}" target="_blank" rel="noopener">{title}</a><small>{company}</small></td>
              <td>{location}</td>
              <td>{role}<small>{seniority} · {focus}</small></td>
              <td><div class="chips">{modules}</div></td>
              <td>{salary}</td>
              <td>{source}</td>
            </tr>
            """
        )
    return "\n".join(rows)


def build_linkedin_guest_rows(jobs: List[Dict], limit: int = 120) -> str:
    rows = []
    for job in jobs[:limit]:
        modules = chip_list(job.get("modules", []), 3)
        skills = chip_list(job.get("skills", []), 3)
        title = html.escape(job.get("title", ""))
        company = html.escape(job.get("company", ""))
        location = html.escape(job.get("location", ""))
        role = html.escape(job.get("role_family", ""))
        seniority = html.escape(job.get("seniority", ""))
        query = html.escape(job.get("query", ""))
        query_location = html.escape(job.get("query_location", ""))
        query_filter = html.escape(job.get("query_filter", ""))
        url = html.escape(job.get("url") or "#")
        rows.append(
            f"""
            <tr>
              <td><a href="{url}" target="_blank" rel="noopener">{title}</a><small>{company}</small></td>
              <td>{location}<small>{query} · {query_location} · {query_filter}</small></td>
              <td>{role}<small>{seniority}</small></td>
              <td><div class="chips">{modules}</div></td>
              <td><div class="chips">{skills}</div></td>
            </tr>
            """
        )
    return "\n".join(rows)


def main() -> None:
    jobs = load_json(DATA_DIR / "sap_jobs.json")
    summary = load_json(DATA_DIR / "summary.json")
    linkedin_path = DATA_DIR / "linkedin_signal.json"
    linkedin = load_json(linkedin_path) if linkedin_path.exists() else None
    linkedin_guest_summary = optional_json(DATA_DIR / "linkedin_jobs_summary.json", {})
    linkedin_guest_jobs = optional_json(DATA_DIR / "linkedin_jobs.json", [])
    company_career_summary = optional_json(DATA_DIR / "company_career_jobs_summary.json", {})
    company_career_jobs = optional_json(DATA_DIR / "company_career_jobs.json", [])
    daily_delta_summary = optional_json(DATA_DIR / "daily_delta_summary.json", {})
    snapshots = load_snapshots()
    total = len(jobs)
    total_text = fmt_int(total)
    linkedin_guest_total = int(linkedin_guest_summary.get("jobs_collected") or len(linkedin_guest_jobs) or 0)
    linkedin_guest_text = fmt_int(linkedin_guest_total)
    company_career_total = int(company_career_summary.get("jobs_collected") or len(company_career_jobs) or 0)
    company_career_text = fmt_int(company_career_total)
    salary_disclosed = sum(1 for job in jobs if job.get("salary_status") != "Not disclosed")
    unique_locations = len(summary.get("primary_locations", {}))
    top_module = top_items(summary.get("modules", {}), 1)[0][0] if total else "N/A"
    top_role = top_items(summary.get("role_families", {}), 1)[0][0] if total else "N/A"
    linkedin_guest_top_role, linkedin_guest_top_role_count = top_count(linkedin_guest_summary, "role_families")
    linkedin_guest_top_skill, linkedin_guest_top_skill_count = top_count(linkedin_guest_summary, "skills")
    linkedin_guest_top_soft_skill, linkedin_guest_top_soft_skill_count = top_count(linkedin_guest_summary, "soft_skills")
    linkedin_guest_top_location, linkedin_guest_top_location_count = top_count(linkedin_guest_summary, "query_locations")
    linkedin_guest_described = int(linkedin_guest_summary.get("description_enriched_jobs") or 0)
    company_career_top_company, company_career_top_company_count = top_count(company_career_summary, "companies")
    company_career_top_provider, company_career_top_provider_count = top_count(company_career_summary, "providers")
    company_career_top_role, company_career_top_role_count = top_count(company_career_summary, "role_families")
    generated_candidates = [
        value
        for value in [
            summary.get("generated_at"),
            linkedin_guest_summary.get("generated_at"),
            company_career_summary.get("generated_at"),
        ]
        if value
    ]
    generated = max(generated_candidates) if generated_candidates else dt.datetime.now().isoformat(timespec="seconds")
    linkedin_global_text = linkedin.get("global_count", {}).get("count_text", "N/A") if linkedin else "N/A"
    linkedin_week_item = next((item for item in linkedin.get("recency_counts", []) if item.get("label") == "Past week"), {}) if linkedin else {}
    linkedin_week_text = linkedin_week_item.get("count_text", "N/A")
    linkedin_search_links = build_linkedin_search_links(linkedin) if linkedin else ""
    daily_linkedin = daily_delta_summary.get("linkedin") or {}
    daily_company = daily_delta_summary.get("company_careers") or {}
    daily_delta_note = ""
    if daily_delta_summary:
        daily_delta_note = f"""<li>Latest daily delta run: <code>{html.escape(daily_delta_summary.get("generated_at", ""))}</code>. LinkedIn status: <code>{html.escape(str(daily_linkedin.get("status", "")))}</code>, net new links: <code>{fmt_int(int(daily_linkedin.get("net_new_jobs") or 0))}</code>. Company career status: <code>{html.escape(str(daily_company.get("status", "")))}</code>, net new jobs: <code>{fmt_int(int(daily_company.get("net_new_jobs") or 0))}</code>.</li>"""

    chart_payload = {
        "sources": summary.get("sources", {}),
        "focus": summary.get("sap_focus", {}),
        "locations": dict(top_items(summary.get("primary_locations", {}), 14)),
        "roles": summary.get("role_families", {}),
        "seniority": summary.get("seniority", {}),
        "modules": dict(top_items(summary.get("modules", {}), 16)),
        "skills": dict(top_items(summary.get("skills", {}), 18)),
        "softSkills": dict(top_items(summary.get("soft_skills", {}), 14)),
        "degreeLevels": summary.get("degree_levels", {}),
        "degreeFields": dict(top_items(summary.get("degree_fields", {}), 10)),
        "descriptionTerms": dict(top_items(summary.get("description_terms", {}), 20)),
        "salary": summary.get("salary_disclosure", {}),
        "historyJobs": history_counts(snapshots, "sap_jobs_after_filter"),
        "historyLinkedIn": history_counts(snapshots, "linkedin_global_count"),
        "historyLinkedInGuest": history_counts(snapshots, "linkedin_jobs_collected"),
        "linkedinKeywords": linkedin_specialist_keyword_counts(linkedin) if linkedin else {},
        "linkedinLocations": list_counts(linkedin.get("location_counts", []), "location") if linkedin else {},
        "linkedinWorkModel": list_counts(linkedin.get("work_model_counts", []), "label") if linkedin else {},
        "linkedinRecency": list_counts(linkedin.get("recency_counts", []), "label") if linkedin else {},
        "linkedinGuestQueries": dict(top_items(linkedin_guest_summary.get("queries", {}), 12)),
        "linkedinGuestLocations": dict(top_items(linkedin_guest_summary.get("query_locations", {}), 12)),
        "linkedinGuestRoles": dict(top_items(linkedin_guest_summary.get("role_families", {}), 10)),
        "linkedinGuestModules": dict(top_items(linkedin_guest_summary.get("modules", {}), 16)),
        "linkedinGuestSkills": dict(top_items(linkedin_guest_summary.get("skills", {}), 18)),
        "linkedinGuestSoftSkills": dict(top_items(linkedin_guest_summary.get("soft_skills", {}), 14)),
        "linkedinGuestDegreeFields": dict(top_items(linkedin_guest_summary.get("degree_fields", {}), 10)),
    }

    linkedin_section = ""
    if linkedin:
        keyword_leader = next((item for item in linkedin.get("keyword_counts", []) if item.get("keyword") != "SAP"), None)
        location_leader = linkedin.get("location_counts", [{}])[0]
        remote_item = next((item for item in linkedin.get("work_model_counts", []) if item.get("label") == "Remote"), {})
        linkedin_section = f"""
  <section>
    <div class="wrap">
      <div class="note signal-note">
        <div class="eyebrow">LinkedIn Market Signal</div>
        <h2>LinkedIn Shows The Market Scale; The Collected Pool Shows The Links</h2>
        <p>The LinkedIn layer separates two different metrics. <strong>{html.escape(linkedin_global_text)}</strong> is LinkedIn's rounded live search-count estimate for <strong>SAP</strong> + <strong>Worldwide</strong>; it is not a downloadable list of unique jobs. <strong>{linkedin_guest_text}</strong> is the deduplicated set of LinkedIn posting links we actually collected, can cite, and can download. The gap is expected because LinkedIn counts are rounded, search results overlap across filters, and not every result is retrievable as a stable guest link.</p>
      </div>
      <div class="kpis signal-kpis">
        <div class="kpi"><strong>{html.escape(linkedin_global_text)}</strong><span>LinkedIn Jobs rounded result count for SAP worldwide</span></div>
        <div class="kpi"><strong>{html.escape(linkedin_week_text)}</strong><span>LinkedIn SAP rounded result count posted in the past week</span></div>
        <div class="kpi"><strong>{html.escape(remote_item.get("count_text", ""))}</strong><span>LinkedIn SAP results marked remote</span></div>
        <div class="kpi"><strong>{html.escape(location_leader.get("location", ""))}</strong><span>Largest sampled LinkedIn country: {html.escape(location_leader.get("count_text", ""))}</span></div>
        <div class="kpi"><strong>{html.escape(keyword_leader.get("keyword", "") if keyword_leader else "")}</strong><span>Largest sampled specialist query: {html.escape(keyword_leader.get("count_text", "") if keyword_leader else "")}</span></div>
      </div>
      <div class="note linkedin-links">
        <h2>Live LinkedIn Validation Links</h2>
        <p>These links reopen the same live LinkedIn Jobs searches used for the market-size signal. The collected pool below is the evidence layer: individual LinkedIn posting links gathered so far.</p>
        <div class="link-grid">
          {linkedin_search_links}
        </div>
      </div>
      <div class="note">
        <h2>Why LinkedIn Has Overlap</h2>
        <p>LinkedIn search results are not a clean one-row-per-job database. The same posting can appear under several searches before deduplication, and some near-duplicate postings are genuinely separate location or employer variants.</p>
        <ul>
          <li>The same posting can appear across multiple keywords such as SAP, SAP SD, S/4HANA, FICO, ABAP, and BTP.</li>
          <li>The same posting can appear across location searches when a role is advertised for multiple cities, countries, or regions.</li>
          <li>The same posting can appear across filters such as all jobs, remote, hybrid, past week, and past month.</li>
          <li>Some companies publish one role as many location-specific postings; some staffing and aggregator listings describe the same underlying opening more than once.</li>
          <li>For analysis, the report deduplicates mainly by LinkedIn job id and treats the remaining {linkedin_guest_text} records as the evidence pool, while {html.escape(linkedin_global_text)} remains only the market-size signal.</li>
        </ul>
      </div>
    </div>
  </section>

  <section>
    <div class="wrap grid-2">
      <div class="chart tall">
        <h2>LinkedIn Specialist Keyword Signal</h2>
        <p class="chart-note">Rounded LinkedIn UI estimate. Treat these values directionally, not as exact job counts.</p>
        <canvas id="linkedinKeywordsChart"></canvas>
      </div>
      <div class="chart x-tall">
        <h2>LinkedIn Country Signal</h2>
        <p class="chart-note">Rounded LinkedIn UI estimate. The exact evidence layer is the collected posting-link pool below.</p>
        <canvas id="linkedinLocationsChart"></canvas>
      </div>
    </div>
  </section>

  <section>
    <div class="wrap grid-2">
      <div class="chart compact">
        <h2>LinkedIn Work Model</h2>
        <p class="chart-note">Rounded LinkedIn UI estimate.</p>
        <canvas id="linkedinWorkModelChart"></canvas>
      </div>
      <div class="chart compact">
        <h2>LinkedIn Recency</h2>
        <p class="chart-note">Rounded LinkedIn UI estimate.</p>
        <canvas id="linkedinRecencyChart"></canvas>
      </div>
    </div>
  </section>
"""

    linkedin_guest_section = ""
    if linkedin_guest_total:
        linkedin_guest_section = f"""
  <section>
    <div class="wrap">
      <div class="note signal-note">
        <div class="eyebrow">LinkedIn Collected Pool · Experimental</div>
        <h2>{linkedin_guest_text} Deduplicated LinkedIn Links Collected So Far</h2>
        <p>This is not the same number as LinkedIn's {html.escape(linkedin_global_text)} market-size estimate. It is the actual LinkedIn-linked evidence pool collected for analysis: public guest records queried by keyword, country, recency, and work model, deduplicated mainly by LinkedIn job id, enriched with SAP module and description signals, and stored as dated snapshots. It does not use logged-in cookies, proxy rotation, CAPTCHA bypass, or the user's private LinkedIn session.</p>
      </div>
      <div class="kpis signal-kpis">
        <div class="kpi"><strong>{linkedin_guest_text}</strong><span>Collected, deduplicated LinkedIn posting links</span></div>
        <div class="kpi"><strong>{fmt_int(linkedin_guest_described)}</strong><span>LinkedIn rows with fetched job-description detail</span></div>
        <div class="kpi"><strong>{fmt_int(int(linkedin_guest_summary.get("search_partitions_collected") or linkedin_guest_summary.get("searches_attempted", 0)))}</strong><span>Keyword/location/filter partitions represented in the collected pool</span></div>
        <div class="kpi"><strong>{html.escape(linkedin_guest_top_location)}</strong><span>Largest collected query location: {fmt_int(linkedin_guest_top_location_count)} links</span></div>
        <div class="kpi"><strong>{html.escape(linkedin_guest_top_role)}</strong><span>Top collected role family: {fmt_int(linkedin_guest_top_role_count)} links</span></div>
        <div class="kpi"><strong>{html.escape(linkedin_guest_top_skill)}</strong><span>Top extracted technical skill: {fmt_int(linkedin_guest_top_skill_count)} mentions</span></div>
        <div class="kpi"><strong>{html.escape(linkedin_guest_top_soft_skill)}</strong><span>Top extracted soft skill: {fmt_int(linkedin_guest_top_soft_skill_count)} mentions</span></div>
      </div>
      <div class="actions">
        <a class="button primary" href="{html.escape(LINKEDIN_JOBS_CSV_URL)}">Download LinkedIn CSV.gz</a>
        <a class="button" href="{html.escape(LINKEDIN_JOBS_JSON_URL)}">LinkedIn JSON.gz</a>
        <a class="button" href="{html.escape(LINKEDIN_JOBS_SUMMARY_URL)}">LinkedIn summary</a>
      </div>
    </div>
  </section>

  <section>
    <div class="wrap grid-2">
      <div class="chart compact">
        <h2>Collected LinkedIn Queries</h2>
        <canvas id="linkedinGuestQueriesChart"></canvas>
      </div>
      <div class="chart tall">
        <h2>Collected LinkedIn Locations</h2>
        <canvas id="linkedinGuestLocationsChart"></canvas>
      </div>
    </div>
  </section>

  <section>
    <div class="wrap grid-3">
      <div class="chart tall">
        <h2>Collected LinkedIn Roles</h2>
        <canvas id="linkedinGuestRolesChart"></canvas>
      </div>
      <div class="chart x-tall">
        <h2>Collected LinkedIn Soft Skills</h2>
        <canvas id="linkedinGuestSoftSkillsChart"></canvas>
      </div>
      <div class="chart tall">
        <h2>Collected LinkedIn Education Fields</h2>
        <canvas id="linkedinGuestDegreeFieldsChart"></canvas>
      </div>
    </div>
  </section>

  <section>
    <div class="wrap grid-2">
      <div class="note">
        <h2>Collected LinkedIn SAP Areas</h2>
        <div class="bars" id="linkedinGuestModuleBars"></div>
      </div>
      <div class="note">
        <h2>Collected LinkedIn Technical Terms</h2>
        <div class="bars" id="linkedinGuestSkillBars"></div>
      </div>
    </div>
  </section>

  <section>
    <div class="wrap table-panel">
      <div class="table-intro">
        <div>
          <h2>LinkedIn Guest Job Link Sample</h2>
          <p>The table shows the first {fmt_int(min(len(linkedin_guest_jobs), 120))} collected LinkedIn guest records. The full {linkedin_guest_text}-row link pool is available as compressed CSV and JSON downloads.</p>
        </div>
        <div class="actions">
          <a class="button primary" href="{html.escape(LINKEDIN_JOBS_CSV_URL)}">Full CSV.gz</a>
          <a class="button" href="{html.escape(LINKEDIN_JOBS_JSON_URL)}">Full JSON.gz</a>
        </div>
      </div>
      <div class="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Job / Company</th>
              <th>Collected Via</th>
              <th>Role</th>
              <th>SAP Areas</th>
              <th>Technical Terms</th>
            </tr>
          </thead>
          <tbody>
            {build_linkedin_guest_rows(linkedin_guest_jobs)}
          </tbody>
        </table>
      </div>
    </div>
  </section>
"""

    company_career_section = ""
    if company_career_total:
        company_career_section = f"""
  <section>
    <div class="wrap">
      <div class="note signal-note">
        <div class="eyebrow">Direct Company Career / ATS Pool</div>
        <h2>{company_career_text} SAP Jobs From Company Career Sources</h2>
        <p>This layer runs in parallel with the LinkedIn crawler and reads public company career pages or ATS endpoints such as jobs2web / SuccessFactors, SmartRecruiters, Greenhouse, and Workday CXS. It does not use logged-in sessions, proxy rotation, CAPTCHA bypass, or private candidate data.</p>
      </div>
      <div class="kpis signal-kpis">
        <div class="kpi"><strong>{company_career_text}</strong><span>Deduplicated SAP postings from direct company career sources</span></div>
        <div class="kpi"><strong>{html.escape(company_career_top_provider)}</strong><span>Largest ATS provider layer: {fmt_int(company_career_top_provider_count)} jobs</span></div>
        <div class="kpi"><strong>{html.escape(company_career_top_company)}</strong><span>Largest direct company source: {fmt_int(company_career_top_company_count)} jobs</span></div>
        <div class="kpi"><strong>{html.escape(company_career_top_role)}</strong><span>Top role family: {fmt_int(company_career_top_role_count)} jobs</span></div>
      </div>
      <div class="actions">
        <a class="button primary" href="{html.escape(COMPANY_CAREER_CSV_URL)}">Download Company Career CSV</a>
        <a class="button" href="{html.escape(COMPANY_CAREER_JSON_URL)}">Company career JSON</a>
        <a class="button" href="{html.escape(COMPANY_CAREER_SUMMARY_URL)}">Company career summary</a>
      </div>
    </div>
  </section>

  <section>
    <div class="wrap grid-2">
      <div class="note">
        <h2>Company Career Sources</h2>
        <div class="bars">{bars_markup(company_career_summary.get("sources", {}), 10)}</div>
      </div>
      <div class="note">
        <h2>Company Career SAP Areas</h2>
        <div class="bars">{bars_markup(company_career_summary.get("modules", {}), 10)}</div>
      </div>
    </div>
  </section>

  <section>
    <div class="wrap table-panel">
      <div class="table-intro">
        <div>
          <h2>Company Career Job Sample</h2>
          <p>The table shows the first {fmt_int(min(len(company_career_jobs), 120))} direct company career records. The full {company_career_text}-row pool is available in CSV and JSON.</p>
        </div>
        <div class="actions">
          <a class="button primary" href="{html.escape(COMPANY_CAREER_CSV_URL)}">Full CSV</a>
          <a class="button" href="{html.escape(COMPANY_CAREER_JSON_URL)}">Full JSON</a>
        </div>
      </div>
      <div class="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Job / Company</th>
              <th>Location</th>
              <th>Role</th>
              <th>SAP Areas</th>
              <th>Salary</th>
              <th>Source</th>
            </tr>
          </thead>
          <tbody>
            {build_table_rows(company_career_jobs[:120])}
          </tbody>
        </table>
      </div>
    </div>
  </section>
"""

    report_html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Global SAP Job Market Report</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.9/dist/chart.umd.min.js"></script>
  <style>
    :root {{
      --ink: #172026;
      --muted: #66717d;
      --line: #d7dee6;
      --panel: #ffffff;
      --soft: #f5f7fa;
      --paper: #fbfcfd;
      --hero: #102426;
      --hero-2: #193236;
      --teal: #257a75;
      --teal-soft: #dff3ef;
      --blue: #3f6db5;
      --amber: #b97822;
      --red: #c84e3a;
      --green: #4f8a5b;
      --violet: #725ca8;
      --shadow: 0 16px 40px rgba(23, 32, 38, .09);
      color-scheme: light;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: var(--ink);
      background: var(--soft);
    }}
    * {{ box-sizing: border-box; }}
    img, svg, canvas {{ max-width: 100%; }}
    html {{ scroll-behavior: smooth; }}
    body {{
      margin: 0;
      background:
        linear-gradient(180deg, #eef5f4 0, #f7f9fb 460px, #f7f9fb 100%);
      overflow-x: hidden;
      -webkit-font-smoothing: antialiased;
      text-rendering: optimizeLegibility;
    }}
    a {{ color: var(--teal); text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    header {{
      position: relative;
      overflow: hidden;
      max-width: 100vw;
      background:
        radial-gradient(circle at 85% 8%, rgba(75, 137, 174, .36), transparent 28%),
        radial-gradient(circle at 12% 14%, rgba(217, 155, 36, .18), transparent 30%),
        linear-gradient(135deg, var(--hero), var(--hero-2));
      color: #f5fbfb;
      border-bottom: 1px solid rgba(255, 255, 255, .12);
    }}
    header::after {{
      content: "";
      position: absolute;
      inset: auto 0 0;
      height: 1px;
      background: linear-gradient(90deg, transparent, rgba(111, 213, 199, .55), transparent);
    }}
    .wrap {{ width: min(1180px, calc(100% - 32px)); margin: 0 auto; }}
    .hero-shell {{ position: relative; z-index: 1; padding: 22px 0 28px; }}
    .topline {{ display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-bottom: 30px; }}
    .brand {{
      display: inline-flex;
      align-items: center;
      gap: 10px;
      color: #dff8f5;
      font-size: 13px;
      font-weight: 800;
      letter-spacing: .12em;
      text-transform: uppercase;
    }}
    .brand-mark {{ width: 10px; height: 10px; border-radius: 999px; background: #67d5c9; box-shadow: 0 0 0 5px rgba(103, 213, 201, .14); }}
    .report-tag {{ color: rgba(245, 251, 251, .72); font-size: 13px; white-space: nowrap; }}
    .hero-grid {{ display: grid; grid-template-columns: minmax(0, 1.05fr) minmax(320px, .95fr); gap: 22px; align-items: end; }}
    .hero-grid > *, .grid-2 > *, .grid-3 > * {{ min-width: 0; }}
    .hero-copy {{ width: 100%; max-width: 720px; min-width: 0; }}
    .eyebrow {{ color: var(--teal); font-weight: 700; font-size: 13px; text-transform: uppercase; letter-spacing: .08em; line-height: 1.35; overflow-wrap: anywhere; }}
    header .eyebrow {{ color: #8be1d8; margin-bottom: 10px; }}
    h1 {{ margin: 10px 0 10px; font-size: clamp(36px, 5vw, 66px); line-height: .98; letter-spacing: 0; overflow-wrap: break-word; }}
    header h1 {{ color: #f8fbff; max-width: 680px; }}
    h2 {{ margin: 0 0 16px; font-size: 24px; letter-spacing: 0; }}
    h3 {{ margin: 0 0 8px; font-size: 17px; letter-spacing: 0; }}
    p {{ color: var(--muted); line-height: 1.6; margin: 0; }}
    .intro {{ max-width: 760px; font-size: 17px; }}
    header .intro {{ color: rgba(245, 251, 251, .78); font-size: 18px; }}
    .hero-card {{
      border: 1px solid rgba(174, 220, 216, .24);
      border-radius: 14px;
      background: rgba(255, 255, 255, .08);
      box-shadow: 0 22px 60px rgba(0, 0, 0, .18);
      backdrop-filter: blur(16px);
      padding: 16px;
      min-width: 0;
    }}
    .hero-card-label {{ color: #8be1d8; font-size: 12px; font-weight: 800; letter-spacing: .1em; text-transform: uppercase; margin-bottom: 12px; }}
    .hero-metrics {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }}
    .hero-metric {{
      min-height: 128px;
      border: 1px solid rgba(255, 255, 255, .14);
      border-radius: 12px;
      background: rgba(255, 255, 255, .08);
      padding: 14px;
      min-width: 0;
    }}
    .hero-metric.primary {{ background: rgba(103, 213, 201, .14); border-color: rgba(103, 213, 201, .32); }}
    .hero-metric span {{ display: block; color: rgba(245, 251, 251, .7); font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: .08em; }}
    .hero-metric strong {{ display: block; margin: 8px 0 5px; color: #fff; font-size: 34px; line-height: 1; }}
    .hero-metric small {{ color: rgba(245, 251, 251, .7); line-height: 1.35; }}
    .hero-metric small {{ display: block; overflow-wrap: anywhere; }}
    .layer-note {{ max-width: 920px; margin-top: 18px; padding: 14px 16px; border: 1px solid #c9dada; border-radius: 10px; background: #f3fbfa; color: var(--ink); line-height: 1.55; }}
    .hero-card .layer-note {{ max-width: none; margin-top: 12px; border-color: rgba(103, 213, 201, .28); background: rgba(9, 30, 31, .45); color: rgba(245, 251, 251, .82); }}
    .layer-note strong {{ color: var(--teal); }}
    .hero-card .layer-note strong {{ color: #8be1d8; }}
    .meta {{ display: flex; flex-wrap: wrap; gap: 10px; margin-top: 18px; }}
    .pill {{ border: 1px solid var(--line); border-radius: 999px; padding: 7px 11px; background: #fff; color: var(--muted); font-size: 13px; }}
    header .meta {{ margin-top: 18px; gap: 8px; }}
    header .pill {{ border-color: rgba(255, 255, 255, .16); background: rgba(255, 255, 255, .08); color: rgba(245, 251, 251, .72); }}
    section {{ padding: 28px 0; }}
    .kpis {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 12px; }}
    .overview-kpis {{ margin-top: -18px; position: relative; z-index: 2; }}
    .kpi, .chart, .note, .table-panel {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 12px;
      box-shadow: 0 1px 2px rgba(25, 33, 42, .04);
    }}
    .kpi {{ padding: 18px; min-height: 126px; box-shadow: var(--shadow); }}
    .kpi strong {{ display: block; font-size: 30px; margin-bottom: 7px; letter-spacing: 0; }}
    .kpi span {{ color: var(--muted); font-size: 13px; line-height: 1.4; }}
    .grid-2 {{ display: grid; grid-template-columns: minmax(0, 1.25fr) minmax(0, .75fr); gap: 16px; }}
    .grid-3 {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 16px; }}
    .chart {{ --chart-h: 320px; padding: 18px; min-height: calc(var(--chart-h) + 70px); overflow: hidden; }}
    .chart-note {{ margin: -6px 0 12px; font-size: 13px; line-height: 1.45; color: #71808d; }}
    .chart.compact {{ --chart-h: 280px; }}
    .chart.tall {{ --chart-h: 410px; }}
    .chart.x-tall {{ --chart-h: 500px; }}
    .chart canvas {{ display: block; width: 100% !important; max-width: 100%; height: var(--chart-h) !important; }}
    .note {{ padding: 18px; }}
    .note ul {{ margin: 12px 0 0; padding-left: 20px; color: var(--muted); line-height: 1.55; }}
    .bars {{ display: grid; gap: 9px; margin-top: 14px; }}
    .bar-row {{ display: grid; grid-template-columns: minmax(120px, 210px) 1fr 44px; gap: 10px; align-items: center; font-size: 13px; }}
    .bar-label {{ color: var(--ink); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
    .bar-track {{ height: 10px; background: #edf1f3; border-radius: 999px; overflow: hidden; }}
    .bar-fill {{ height: 100%; background: var(--teal); border-radius: inherit; }}
    .toolbar {{ display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 12px; }}
    input, select {{
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
      padding: 10px 12px;
      color: var(--ink);
      min-height: 40px;
    }}
    input {{ flex: 1 1 260px; }}
    .table-panel {{ padding: 16px; overflow: hidden; }}
    .table-scroll {{ overflow-x: auto; }}
    table {{ width: 100%; border-collapse: collapse; min-width: 880px; }}
    th, td {{ border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; padding: 12px 10px; font-size: 14px; }}
    th {{ color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: .06em; background: #fbfcfd; }}
    td small {{ display: block; color: var(--muted); margin-top: 4px; line-height: 1.4; }}
    .chips {{ display: flex; flex-wrap: wrap; gap: 6px; }}
    .chips span {{ background: #eef5f4; color: #24575a; border: 1px solid #d3e4e2; border-radius: 999px; padding: 4px 7px; font-size: 12px; white-space: nowrap; }}
    .source-list {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; margin-top: 14px; }}
    .source-list a {{ border: 1px solid var(--line); border-radius: 8px; padding: 10px 12px; background: #fff; color: var(--ink); }}
    .linkedin-links {{ margin-top: 12px; }}
    .link-grid {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin-top: 14px; }}
    .link-grid a {{ border: 1px solid var(--line); border-radius: 8px; padding: 11px 12px; background: #fbfcfd; color: var(--ink); }}
    .link-grid span {{ display: block; color: var(--muted); font-size: 12px; line-height: 1.35; }}
    .link-grid strong {{ display: block; margin-top: 4px; color: var(--teal); font-size: 16px; }}
    .actions {{ display: flex; flex-wrap: wrap; gap: 10px; margin-top: 16px; width: 100%; min-width: 0; }}
    .button {{ display: inline-flex; align-items: center; justify-content: center; min-height: 42px; border: 1px solid var(--line); border-radius: 10px; padding: 10px 14px; background: #fff; color: var(--ink); font-weight: 800; font-size: 13px; min-width: 0; text-align: center; white-space: normal; overflow-wrap: anywhere; }}
    .button.primary {{ background: var(--teal); border-color: var(--teal); color: #fff; }}
    header .button {{ border-color: rgba(255, 255, 255, .18); background: rgba(255, 255, 255, .09); color: #f7fbfb; }}
    header .button.primary {{ background: #67d5c9; border-color: #67d5c9; color: #0f2425; }}
    .callout-grid {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; margin-top: 14px; }}
    .callout {{ border: 1px solid var(--line); border-radius: 8px; padding: 14px; background: #fbfcfd; }}
    .callout strong {{ display: block; margin-bottom: 6px; }}
    .table-intro {{ display: flex; justify-content: space-between; gap: 16px; align-items: flex-start; margin-bottom: 14px; }}
    .signal-note {{ margin-bottom: 12px; }}
    .signal-note h2 {{ margin-top: 8px; }}
    .signal-kpis {{ margin-top: 12px; }}
    footer {{ border-top: 1px solid var(--line); padding: 24px 0 36px; color: var(--muted); font-size: 13px; }}
    @media (max-width: 900px) {{
      .hero-grid, .grid-2, .grid-3, .source-list, .callout-grid, .link-grid {{ grid-template-columns: 1fr; }}
      .table-intro {{ display: block; }}
      .wrap {{ width: min(100% - 20px, 1180px); }}
      .hero-shell {{ padding: 20px 0 24px; }}
      .topline {{ margin-bottom: 24px; }}
      .hero-card {{ max-width: 680px; }}
      section {{ padding: 18px 0; }}
      h2 {{ font-size: 20px; line-height: 1.2; }}
      .chart {{ --chart-h: 360px; padding: 14px; min-height: calc(var(--chart-h) + 62px); }}
      .chart.compact {{ --chart-h: 320px; }}
      .chart.tall {{ --chart-h: 520px; }}
      .chart.x-tall {{ --chart-h: 640px; }}
      .bar-row {{ grid-template-columns: minmax(96px, 140px) 1fr 38px; gap: 8px; font-size: 12px; }}
      .kpi {{ min-height: 112px; }}
    }}
    @media (max-width: 640px) {{
      .wrap {{ width: calc(100% - 16px); }}
      .hero-shell {{ padding: 18px 0 18px; }}
      .topline {{ margin-bottom: 18px; }}
      .brand {{ font-size: 11px; letter-spacing: .1em; }}
      .report-tag {{ display: none; }}
      h1 {{ font-size: 34px; line-height: 1.03; }}
      h2 {{ font-size: 19px; }}
      .intro, header .intro {{ font-size: 15px; line-height: 1.55; }}
      .meta {{ gap: 8px; }}
      .pill {{ max-width: 100%; line-height: 1.35; }}
      .hero-grid {{ gap: 16px; }}
      .hero-card {{ border-radius: 12px; padding: 12px; }}
      .hero-metrics {{ grid-template-columns: 1fr; gap: 8px; }}
      .hero-metric {{ min-height: 0; padding: 12px; }}
      .hero-metric strong {{ font-size: 28px; }}
      .hero-metric span {{ font-size: 10px; }}
      .hero-metric small {{ font-size: 12px; }}
      .hero-card .layer-note {{ font-size: 13px; padding: 12px; }}
      .kpis {{ grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }}
      .overview-kpis {{ margin-top: -6px; }}
      .chart {{ --chart-h: 420px; padding: 12px; min-height: calc(var(--chart-h) + 58px); }}
      .chart.compact {{ --chart-h: 380px; }}
      .chart.tall {{ --chart-h: 600px; }}
      .chart.x-tall {{ --chart-h: 760px; }}
      .kpi {{ min-height: 106px; padding: 14px; }}
      .kpi strong {{ font-size: 24px; }}
      .kpi span {{ font-size: 12px; }}
      .bar-row {{ grid-template-columns: minmax(0, 1fr) 42px; }}
      .bar-label {{ white-space: normal; grid-column: 1 / -1; }}
      .bar-track {{ grid-column: 1; }}
      .actions {{ display: grid; grid-template-columns: 1fr; align-items: stretch; }}
      .hero-actions .button.primary {{ grid-column: auto; }}
      .button {{ width: auto; min-height: 44px; padding-inline: 10px; }}
    }}
  </style>
</head>
<body>
  <header>
    <div class="wrap hero-shell">
      <div class="topline">
        <div class="brand"><span class="brand-mark"></span><span>SAP Market Observatory</span></div>
        <div class="report-tag">Baseline snapshot · Updated {html.escape(generated[:10])}</div>
      </div>
      <div class="hero-grid">
        <div class="hero-copy">
          <div class="eyebrow">Global SAP labor market research</div>
          <h1>Global SAP Job Market Report</h1>
          <p class="intro">A public, chart-driven snapshot separating LinkedIn market scale from source-linked evidence across LinkedIn, company career pages, ATS sources, and open job feeds.</p>
          <div class="meta">
            <span class="pill">Baseline: 2026-07-19</span>
            <span class="pill">Salary disclosed: {pct(salary_disclosed, total)}</span>
            <span class="pill">Downloadable evidence pool</span>
          </div>
          <div class="actions hero-actions">
            <a class="button primary" href="#job-pool">Explore the report</a>
            <a class="button" href="{html.escape(LINKEDIN_JOBS_CSV_URL)}">Download LinkedIn pool</a>
            <a class="button" href="#methodology">Methodology</a>
          </div>
        </div>
        <div class="hero-card">
          <div class="hero-card-label">Read the headline correctly</div>
          <div class="hero-metrics">
            <div class="hero-metric primary">
              <span>Market signal</span>
              <strong>{html.escape(linkedin_global_text)}</strong>
              <small>LinkedIn rounded live estimate for SAP worldwide.</small>
            </div>
            <div class="hero-metric">
              <span>Evidence pool</span>
              <strong>{linkedin_guest_text}</strong>
              <small>Deduplicated LinkedIn posting links collected and downloadable.</small>
            </div>
          </div>
          <div class="layer-note"><strong>Not a drop:</strong> these are different metrics. LinkedIn results overlap across keyword, location, work-model, and recency searches before deduplication.</div>
        </div>
      </div>
    </div>
  </header>

  <section>
    <div class="wrap kpis overview-kpis">
      <div class="kpi"><strong>{html.escape(linkedin_global_text)}</strong><span>LinkedIn SAP worldwide market signal</span></div>
      <div class="kpi"><strong>{html.escape(linkedin_week_text)}</strong><span>LinkedIn SAP market signal from the past week</span></div>
      <div class="kpi"><strong>{linkedin_guest_text}</strong><span>Collected, deduplicated LinkedIn posting links</span></div>
      <div class="kpi"><strong>{company_career_text}</strong><span>Direct company career / ATS postings collected and analyzed</span></div>
      <div class="kpi"><strong>{total_text}</strong><span>Open-feed SAP postings analyzed in detail</span></div>
      <div class="kpi"><strong>{fmt_int(unique_locations)}</strong><span>Open-feed locations represented</span></div>
      <div class="kpi"><strong>{pct(salary_disclosed, total)}</strong><span>Jobs with salary information</span></div>
    </div>
  </section>

  {linkedin_section}

  {linkedin_guest_section}

  {company_career_section}

  <section>
    <div class="wrap grid-2">
      <div class="note">
        <h2>What This Baseline Says</h2>
        <div class="callout-grid">
          <div class="callout"><strong>SAP demand is broad, not niche.</strong><p>LinkedIn's {html.escape(linkedin_global_text)} rounded worldwide count is the market-size signal. The {linkedin_guest_text} LinkedIn guest links, {company_career_text} direct company career postings, and {total_text} open-feed postings are the current evidence layers used for detailed analysis.</p></div>
          <div class="callout"><strong>Technical roles dominate the open dataset.</strong><p>Technical / Development is the largest role family, followed by Data / Analytics, Basis / Security, Functional Consulting, and Architecture.</p></div>
          <div class="callout"><strong>Salary remains the biggest blind spot.</strong><p>Only {pct(salary_disclosed, total)} of deduplicated open postings include salary information. The next phase should focus on salary ranges by module, country, seniority, and work model.</p></div>
        </div>
      </div>
      <div class="note" id="community">
        <h2>Contribute to the Research</h2>
        <p>If you work in SAP, hire SAP talent, or recently interviewed for SAP roles, message me on LinkedIn. I am collecting anonymous input on salary ranges, interview processes, working conditions, role risk, stress level, remote/hybrid reality, and what people genuinely enjoy in their SAP work.</p>
        <ul>
          <li>No names or company-identifying details will be published without explicit permission.</li>
          <li>Anonymous insights will be aggregated into future versions of this report.</li>
          <li>The goal is to make SAP career decisions more transparent for candidates, consultants, and hiring teams.</li>
        </ul>
      </div>
    </div>
  </section>

  <section>
    <div class="wrap grid-2">
      <div class="chart x-tall">
        <h2>Location Concentration</h2>
        <canvas id="locationsChart"></canvas>
      </div>
      <div class="chart compact">
        <h2>Salary Transparency</h2>
        <canvas id="salaryChart"></canvas>
      </div>
    </div>
  </section>

  <section>
    <div class="wrap grid-3">
      <div class="chart tall">
        <h2>Role Families</h2>
        <canvas id="rolesChart"></canvas>
      </div>
      <div class="chart compact">
        <h2>Seniority</h2>
        <canvas id="seniorityChart"></canvas>
      </div>
      <div class="chart compact">
        <h2>SAP Focus Level</h2>
        <canvas id="focusChart"></canvas>
      </div>
    </div>
  </section>

  <section>
    <div class="wrap grid-2">
      <div class="note">
        <h2>Leading SAP Modules</h2>
        <div class="bars" id="moduleBars"></div>
      </div>
      <div class="note">
        <h2>Technical Requirements</h2>
        <div class="bars" id="skillBars"></div>
      </div>
    </div>
  </section>

  <section>
    <div class="wrap grid-2">
      <div class="chart x-tall">
        <h2>Soft Skill Signals</h2>
        <canvas id="softSkillsChart"></canvas>
      </div>
      <div class="chart tall">
        <h2>Education Field Signals</h2>
        <canvas id="degreeFieldsChart"></canvas>
      </div>
    </div>
  </section>

  <section>
    <div class="wrap grid-2">
      <div class="chart compact">
        <h2>Degree Level Mentions</h2>
        <canvas id="degreeLevelsChart"></canvas>
      </div>
      <div class="note">
        <h2>Common Job Description Terms</h2>
        <p>Terms are counted by posting, using the available job-description excerpts. This favors recurring market language rather than one-off wording.</p>
        <div class="bars" id="descriptionTermBars"></div>
      </div>
    </div>
  </section>

  <section>
    <div class="wrap grid-2">
      <div class="note">
        <h2>Candidate Interpretation</h2>
        <div class="callout-grid">
          <div class="callout"><strong>Build a T-shaped SAP profile.</strong><p>The strongest signal is still module depth: S/4HANA, BTP / Integration, ABAP, HANA / Data, and FI / CO / FICO appear repeatedly. Pair one core module with implementation, integration, and business-process evidence.</p></div>
          <div class="callout"><strong>Soft skills are not optional.</strong><p>Consulting, leadership, change management, analytical thinking, collaboration, and training appear as explicit job-description signals. SAP work is usually cross-functional, not isolated development.</p></div>
          <div class="callout"><strong>Degrees help, but roles are skills-led.</strong><p>Computer science, engineering, finance/accounting, and logistics/supply chain show up as education-field signals. Explicit degree-level mentions are much rarer than domain and tool requirements.</p></div>
        </div>
      </div>
      <div class="note">
        <h2>University & Early-Career Direction</h2>
        <p>For students choosing a path into SAP, the data points to four practical routes rather than one perfect degree: computer science or informatics for ABAP/BTP/Fiori work, information systems or business informatics for consulting, finance/accounting for FI/CO, and logistics/supply chain or industrial engineering for MM, SD, EWM, PP, and planning roles.</p>
        <ul>
          <li>Best early portfolio signal: one SAP module plus one integration/data project.</li>
          <li>Best business signal: process knowledge in finance, procurement, sales, manufacturing, HR, or supply chain.</li>
          <li>Best communication signal: documented stakeholder work, training, migration, rollout, or change-management experience.</li>
        </ul>
      </div>
    </div>
  </section>

  <section id="methodology">
    <div class="wrap grid-2">
      <div class="note">
        <h2>Methodology</h2>
        <ul>
          <li>Open job data was collected from public job-board feeds and normalized into one common structure: title, company, location, salary fields, source link, SAP focus, role family, seniority, module, and skills.</li>
          <li>Deduplication removes repeated or near-identical postings by comparing normalized title, company, location, and source URL signals, so the same job is less likely to be counted multiple times across feeds.</li>
          <li>SAP matching used strong keyword signals such as SAP, S/4HANA, ABAP, SuccessFactors, Ariba, Fiori, UI5, BTP, HANA, BW/4HANA, and related terms.</li>
          <li>Salary was not estimated. A posting was marked as salary-disclosed only when the source provided salary fields or the description explicitly mentioned compensation.</li>
          <li>LinkedIn has two separate layers: rounded LinkedIn Jobs search-result counts, and a collected public guest job-link pool gathered through partitioned searches.</li>
          <li>LinkedIn result overlap is expected. The same posting may appear across multiple keyword, location, work-model, and recency searches; deduplication mainly uses LinkedIn job id to avoid counting those repeated appearances as separate evidence records.</li>
          <li>Company career data is collected from public career pages and ATS endpoints such as jobs2web / SuccessFactors, SmartRecruiters, Greenhouse, and Workday CXS. These runs are parallel to the LinkedIn crawler and stored as a separate source-linked layer.</li>
          <li>The LinkedIn guest scraper does not use logged-in cookies, proxy rotation, CAPTCHA bypass, or private profile/session data. The 371,000+ figure is treated as market size; the collected guest pool is the source-linked subset available for analysis and download.</li>
        </ul>
      </div>
      <div class="note">
        <h2>Sources</h2>
        <p>Open sources used during report generation:</p>
        <div class="source-list">
          <a href="https://himalayas.app/jobs" target="_blank" rel="noopener">Himalayas</a>
          <a href="https://remotefirstjobs.com/" target="_blank" rel="noopener">Remote First Jobs</a>
          <a href="https://jobicy.com/" target="_blank" rel="noopener">Jobicy</a>
          <a href="https://remotive.com/" target="_blank" rel="noopener">Remotive</a>
          <a href="https://remoteok.com/" target="_blank" rel="noopener">Remote OK</a>
          <a href="https://www.arbeitnow.com/" target="_blank" rel="noopener">Arbeitnow</a>
          <a href="https://www.linkedin.com/jobs/" target="_blank" rel="noopener">LinkedIn Jobs signal and public job pages</a>
          <a href="https://jobs.sap.com/" target="_blank" rel="noopener">SAP Careers</a>
          <a href="https://jobs.atos.net/" target="_blank" rel="noopener">Atos Careers</a>
          <a href="https://jobs.adesso-group.com/" target="_blank" rel="noopener">adesso Careers</a>
          <a href="https://api.smartrecruiters.com/" target="_blank" rel="noopener">SmartRecruiters public postings</a>
          <a href="https://boards.greenhouse.io/" target="_blank" rel="noopener">Greenhouse public boards</a>
          <a href="https://www.myworkday.com/" target="_blank" rel="noopener">Workday public career sites</a>
        </div>
      </div>
    </div>
  </section>

  <section>
    <div class="wrap grid-2">
      <div class="note">
        <h2>How This Will Stay Alive</h2>
        <ul>
          <li>This first release is a baseline snapshot. Every future run writes a dated snapshot under <code>data/snapshots/YYYY-MM-DD</code> instead of replacing history.</li>
          <li>A daily delta LaunchAgent runs at 06:15 local time. It uses a lightweight LinkedIn <code>past_24h</code> pass and a merge-mode company career / ATS pass instead of re-running the full market crawl every day.</li>
          {daily_delta_note}
          <li>Trend charts will compare snapshots across time: module demand, country mix, seniority, remote/hybrid/on-site, salary transparency, LinkedIn signal shifts, and collected LinkedIn guest-pool growth.</li>
          <li>The public page can be mirrored to GitHub Pages or any static host, with the source and data snapshots versioned in Git for transparency.</li>
          <li>Community inputs will be anonymized and added as a separate qualitative layer, so market data and human experience remain distinguishable.</li>
        </ul>
      </div>
      <div class="chart compact">
        <h2>Historical Snapshot Count</h2>
        <canvas id="historyJobsChart"></canvas>
      </div>
      <div class="chart compact">
        <h2>Historical LinkedIn Pool</h2>
        <canvas id="historyLinkedInGuestChart"></canvas>
      </div>
    </div>
  </section>

  <section>
    <div class="wrap grid-2">
      <div class="note">
        <h2>Next Research Questions</h2>
        <ul>
          <li>Which SAP modules pay best by country and seniority?</li>
          <li>Which roles are most exposed to outsourcing, automation, or project-cycle risk?</li>
          <li>How do interview processes differ for consulting, in-house, implementation partner, and product-company SAP roles?</li>
          <li>Where do SAP professionals report the best balance between pay, learning, stress, and long-term stability?</li>
        </ul>
      </div>
      <div class="chart compact">
        <h2>Historical LinkedIn Signal</h2>
        <canvas id="historyLinkedInChart"></canvas>
      </div>
    </div>
  </section>

  <section>
    <div class="wrap">
      <div class="note">
        <h2>Next Data Expansion</h2>
        <ul>
          <li>Expand the LinkedIn crawler grid by adding more SAP keywords, countries, recency windows, and work-model filters while preserving source links and dated snapshots.</li>
          <li>Add more source-linked job boards and direct employer career pages before increasing claims about the full market.</li>
          <li>Store fuller job-description text where source terms allow it, so soft skill, degree, and keyword analysis becomes more reliable.</li>
          <li>Add anonymous community submissions for salary, interviews, stress, working conditions, and satisfaction.</li>
        </ul>
      </div>
    </div>
  </section>

  <section>
    <div class="wrap table-panel" id="job-pool">
      <div class="table-intro">
        <div>
          <h2>Source-Linked Open Job Pool</h2>
          <p>This table contains {total_text} deduplicated open-feed postings with original source links. Separate evidence pools contain {linkedin_guest_text} collected LinkedIn posting links and {company_career_text} direct company career postings. The full market-size signal remains LinkedIn's rounded {html.escape(linkedin_global_text)} SAP worldwide count.</p>
        </div>
        <div class="actions">
          <a class="button primary" href="{html.escape(SAP_JOBS_CSV_URL)}">CSV</a>
          <a class="button" href="{html.escape(SAP_JOBS_JSON_URL)}">JSON</a>
          <a class="button" href="{html.escape(LINKEDIN_SIGNAL_URL)}">LinkedIn signal</a>
          <a class="button" href="{html.escape(LINKEDIN_JOBS_CSV_URL)}">LinkedIn links</a>
        </div>
      </div>
      <div class="toolbar">
        <input id="jobSearch" type="search" placeholder="Search by job, company, location, or role">
        <select id="roleFilter"><option value="">All roles</option></select>
        <select id="sourceFilter"><option value="">All sources</option></select>
      </div>
      <div class="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Job / Company</th>
              <th>Location</th>
              <th>Role</th>
              <th>SAP Areas</th>
              <th>Salary</th>
              <th>Source</th>
            </tr>
          </thead>
          <tbody id="jobsBody">
            {build_table_rows(jobs)}
          </tbody>
        </table>
      </div>
    </div>
  </section>

  <footer>
    <div class="wrap">This report is for research purposes. It links to original postings instead of republishing source listings.</div>
  </footer>

  <script>
    const chartData = {json.dumps(chart_payload, ensure_ascii=False)};
    const palette = ["#2f6f73", "#3f6db5", "#d99b24", "#c84e3a", "#4f8a5b", "#725ca8", "#8a6a3b", "#64748b"];
    const isMobile = window.matchMedia("(max-width: 700px)").matches;

    function entries(obj) {{
      return Object.entries(obj || {{}}).filter(([, value]) => value > 0);
    }}

    function chartLabel(label) {{
      const text = String(label || "");
      const limit = isMobile ? 17 : 24;
      if (text.length <= limit) return text;
      return text.slice(0, limit - 2) + "...";
    }}

    function compactNumber(value) {{
      const number = Number(value);
      if (!Number.isFinite(number)) return value;
      if (!isMobile) return number.toLocaleString();
      if (Math.abs(number) >= 1000000) return `${{Math.round(number / 1000000)}}M`;
      if (Math.abs(number) >= 1000) return `${{Math.round(number / 1000)}}k`;
      return number;
    }}

    function roundedEstimate(value) {{
      const number = Number(value);
      if (!Number.isFinite(number)) return value;
      if (Math.abs(number) >= 1000000) return `~${{Math.round(number / 1000000)}}M+`;
      if (Math.abs(number) >= 1000) return `~${{Math.round(number / 1000)}}k+`;
      return `~${{number.toLocaleString()}}+`;
    }}

    function formatChartValue(value, mode) {{
      return mode === "roundedEstimate" ? roundedEstimate(value) : compactNumber(value);
    }}

    function makeBarChart(id, data, label, horizontal = false, valueMode = "count") {{
      const ctx = document.getElementById(id);
      if (!ctx) return;
      const rows = entries(data);
      new Chart(ctx, {{
        type: "bar",
        data: {{
          labels: rows.map(([key]) => key),
          datasets: [{{ label, data: rows.map(([, value]) => value), backgroundColor: rows.map((_, i) => palette[i % palette.length]), borderWidth: 0 }}]
        }},
        options: {{
          indexAxis: horizontal ? "y" : "x",
          responsive: true,
          maintainAspectRatio: false,
          layout: {{ padding: isMobile ? {{ right: 12, bottom: 6, left: 0 }} : {{ right: 10 }} }},
          plugins: {{
            legend: {{ display: false }},
            tooltip: {{ callbacks: {{ label: function(context) {{ return `${{label}}: ${{formatChartValue(context.parsed[horizontal ? "x" : "y"], valueMode)}}`; }} }} }}
          }},
          scales: {{
            x: {{ ticks: {{ color: "#5f6b77", font: {{ size: isMobile ? 10 : 12 }}, maxTicksLimit: isMobile ? 4 : 8, maxRotation: isMobile && !horizontal ? 35 : 0, autoSkip: !isMobile || horizontal, callback: function(value) {{ return horizontal ? formatChartValue(value, valueMode) : chartLabel(this.getLabelForValue(value)); }} }}, grid: {{ color: "#edf1f3" }} }},
            y: {{ ticks: {{ color: "#5f6b77", font: {{ size: isMobile ? 10 : 12 }}, autoSkip: false, callback: function(value) {{ return horizontal ? chartLabel(this.getLabelForValue(value)) : formatChartValue(value, valueMode); }} }}, grid: {{ color: "#edf1f3" }} }}
          }}
        }}
      }});
    }}

    function makeDoughnut(id, data, valueMode = "count") {{
      const ctx = document.getElementById(id);
      if (!ctx) return;
      const rows = entries(data);
      new Chart(ctx, {{
        type: "doughnut",
        data: {{
          labels: rows.map(([key]) => key),
          datasets: [{{ data: rows.map(([, value]) => value), backgroundColor: rows.map((_, i) => palette[i % palette.length]), borderWidth: 2, borderColor: "#fff" }}]
        }},
        options: {{
          responsive: true,
          maintainAspectRatio: false,
          radius: isMobile ? "82%" : "95%",
          plugins: {{
            legend: {{ position: "bottom", labels: {{ boxWidth: 12, color: "#5f6b77", font: {{ size: isMobile ? 10 : 12 }} }} }},
            tooltip: {{ callbacks: {{ label: function(context) {{ return `${{context.label}}: ${{formatChartValue(context.parsed, valueMode)}}`; }} }} }}
          }}
        }}
      }});
    }}

    function renderBars(id, data) {{
      const root = document.getElementById(id);
      const rows = entries(data);
      const max = Math.max(...rows.map(([, value]) => value), 1);
      root.innerHTML = rows.map(([label, value], index) => `
        <div class="bar-row">
          <div class="bar-label" title="${{label}}">${{label}}</div>
          <div class="bar-track"><div class="bar-fill" style="width:${{Math.max(4, value / max * 100)}}%; background:${{palette[index % palette.length]}}"></div></div>
          <div>${{value}}</div>
        </div>
      `).join("");
    }}

    makeBarChart("locationsChart", chartData.locations, "Job count", true);
    makeDoughnut("salaryChart", chartData.salary);
    makeBarChart("linkedinKeywordsChart", chartData.linkedinKeywords, "Rounded LinkedIn estimate", true, "roundedEstimate");
    makeBarChart("linkedinLocationsChart", chartData.linkedinLocations, "Rounded LinkedIn estimate", true, "roundedEstimate");
    makeDoughnut("linkedinWorkModelChart", chartData.linkedinWorkModel, "roundedEstimate");
    makeBarChart("linkedinRecencyChart", chartData.linkedinRecency, "Rounded LinkedIn estimate", true, "roundedEstimate");
    makeBarChart("linkedinGuestQueriesChart", chartData.linkedinGuestQueries, "Collected job links", true);
    makeBarChart("linkedinGuestLocationsChart", chartData.linkedinGuestLocations, "Collected job links", true);
    makeBarChart("linkedinGuestRolesChart", chartData.linkedinGuestRoles, "Collected job links", true);
    makeBarChart("linkedinGuestSoftSkillsChart", chartData.linkedinGuestSoftSkills, "Posting count", true);
    makeBarChart("linkedinGuestDegreeFieldsChart", chartData.linkedinGuestDegreeFields, "Posting count", true);
    makeBarChart("rolesChart", chartData.roles, "Job count", true);
    makeBarChart("seniorityChart", chartData.seniority, "Job count", true);
    makeDoughnut("focusChart", chartData.focus);
    makeBarChart("softSkillsChart", chartData.softSkills, "Posting count", true);
    makeBarChart("degreeFieldsChart", chartData.degreeFields, "Posting count", true);
    makeBarChart("degreeLevelsChart", chartData.degreeLevels, "Posting count", true);
    makeBarChart("historyJobsChart", chartData.historyJobs, "Open-feed jobs", false);
    makeBarChart("historyLinkedInChart", chartData.historyLinkedIn, "LinkedIn SAP signal", false);
    makeBarChart("historyLinkedInGuestChart", chartData.historyLinkedInGuest, "Collected LinkedIn links", false);
    renderBars("moduleBars", chartData.modules);
    renderBars("skillBars", chartData.skills);
    renderBars("linkedinGuestModuleBars", chartData.linkedinGuestModules);
    renderBars("linkedinGuestSkillBars", chartData.linkedinGuestSkills);
    renderBars("descriptionTermBars", chartData.descriptionTerms);

    const searchInput = document.getElementById("jobSearch");
    const roleFilter = document.getElementById("roleFilter");
    const sourceFilter = document.getElementById("sourceFilter");
    const rows = Array.from(document.querySelectorAll("#jobsBody tr"));

    function fillSelect(select, attr) {{
      const values = [...new Set(rows.map(row => row.dataset[attr]).filter(Boolean))].sort();
      values.forEach(value => {{
        const option = document.createElement("option");
        option.value = value;
        option.textContent = value;
        select.appendChild(option);
      }});
    }}

    function applyFilters() {{
      const query = searchInput.value.trim().toLowerCase();
      const role = roleFilter.value;
      const source = sourceFilter.value;
      rows.forEach(row => {{
        const okQuery = !query || row.dataset.search.includes(query);
        const okRole = !role || row.dataset.role === role;
        const okSource = !source || row.dataset.source === source;
        row.style.display = okQuery && okRole && okSource ? "" : "none";
      }});
    }}

    fillSelect(roleFilter, "role");
    fillSelect(sourceFilter, "source");
    searchInput.addEventListener("input", applyFilters);
    roleFilter.addEventListener("change", applyFilters);
    sourceFilter.addEventListener("change", applyFilters);
  </script>
</body>
</html>
"""
    report_html = "\n".join(line.rstrip() for line in report_html.splitlines()) + "\n"

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORT_DIR / "index.html"
    root_path = ROOT / "index.html"
    report_path.write_text(report_html, encoding="utf-8")
    root_path.write_text(report_html, encoding="utf-8")
    print(report_path)
    print(root_path)


if __name__ == "__main__":
    main()

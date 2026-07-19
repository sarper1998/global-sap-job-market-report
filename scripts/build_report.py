#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import html
import json
from pathlib import Path
from typing import Dict, List, Tuple


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "processed"
REPORT_DIR = ROOT / "report"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def pct(part: int, total: int) -> str:
    if not total:
        return "0%"
    return f"{(part / total) * 100:.1f}%"


def top_items(counts: Dict[str, int], n: int = 8) -> List[Tuple[str, int]]:
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:n]


def list_counts(items: List[Dict], label_key: str) -> Dict[str, int]:
    return {str(item[label_key]): int(item["count"]) for item in items if item.get(label_key) and item.get("count") is not None}


def chip_list(values: List[str], limit: int = 4) -> str:
    visible = values[:limit]
    chips = "".join(f"<span>{html.escape(value)}</span>" for value in visible)
    if len(values) > limit:
        chips += f"<span>+{len(values) - limit}</span>"
    return chips


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


def main() -> None:
    jobs = load_json(DATA_DIR / "sap_jobs.json")
    summary = load_json(DATA_DIR / "summary.json")
    linkedin_path = DATA_DIR / "linkedin_signal.json"
    linkedin = load_json(linkedin_path) if linkedin_path.exists() else None
    total = len(jobs)
    salary_disclosed = sum(1 for job in jobs if job.get("salary_status") != "Not disclosed")
    remote_count = sum(1 for job in jobs if job.get("remote"))
    unique_locations = len(summary.get("primary_locations", {}))
    top_module = top_items(summary.get("modules", {}), 1)[0][0] if total else "N/A"
    top_role = top_items(summary.get("role_families", {}), 1)[0][0] if total else "N/A"
    generated = summary.get("generated_at") or dt.datetime.now().isoformat(timespec="seconds")

    chart_payload = {
        "sources": summary.get("sources", {}),
        "focus": summary.get("sap_focus", {}),
        "locations": dict(top_items(summary.get("primary_locations", {}), 14)),
        "roles": summary.get("role_families", {}),
        "seniority": summary.get("seniority", {}),
        "modules": dict(top_items(summary.get("modules", {}), 16)),
        "skills": dict(top_items(summary.get("skills", {}), 18)),
        "salary": summary.get("salary_disclosure", {}),
        "linkedinKeywords": list_counts(linkedin.get("keyword_counts", []), "keyword") if linkedin else {},
        "linkedinLocations": list_counts(linkedin.get("location_counts", []), "location") if linkedin else {},
        "linkedinWorkModel": list_counts(linkedin.get("work_model_counts", []), "label") if linkedin else {},
        "linkedinRecency": list_counts(linkedin.get("recency_counts", []), "label") if linkedin else {},
    }

    linkedin_section = ""
    if linkedin:
        keyword_leader = next((item for item in linkedin.get("keyword_counts", []) if item.get("keyword") != "SAP"), None)
        location_leader = linkedin.get("location_counts", [{}])[0]
        remote_item = next((item for item in linkedin.get("work_model_counts", []) if item.get("label") == "Remote"), {})
        week_item = next((item for item in linkedin.get("recency_counts", []) if item.get("label") == "Past week"), {})
        linkedin_section = f"""
  <section>
    <div class="wrap">
      <div class="note signal-note">
        <div class="eyebrow">LinkedIn Market Signal</div>
        <h2>LinkedIn Confirms Much Larger SAP Demand Than Open Sources Alone</h2>
        <p>Using the logged-in LinkedIn Jobs UI on {html.escape(linkedin.get("observed_at", ""))}, a read-only search for <strong>SAP</strong> in <strong>Worldwide</strong> showed <strong>{html.escape(linkedin.get("global_count", {}).get("count_text", ""))}</strong> results. These are rounded LinkedIn UI counts, not a deduplicated posting dataset, so they are used as directional market signal rather than merged with the open-source job pool.</p>
      </div>
      <div class="kpis signal-kpis">
        <div class="kpi"><strong>{html.escape(linkedin.get("global_count", {}).get("count_text", ""))}</strong><span>LinkedIn Jobs results for SAP worldwide</span></div>
        <div class="kpi"><strong>{html.escape(week_item.get("count_text", ""))}</strong><span>LinkedIn SAP results posted in the past week</span></div>
        <div class="kpi"><strong>{html.escape(remote_item.get("count_text", ""))}</strong><span>LinkedIn SAP results marked remote</span></div>
        <div class="kpi"><strong>{html.escape(location_leader.get("location", ""))}</strong><span>Largest sampled LinkedIn country: {html.escape(location_leader.get("count_text", ""))}</span></div>
        <div class="kpi"><strong>{html.escape(keyword_leader.get("keyword", "") if keyword_leader else "")}</strong><span>Largest sampled specialist query: {html.escape(keyword_leader.get("count_text", "") if keyword_leader else "")}</span></div>
      </div>
    </div>
  </section>

  <section>
    <div class="wrap grid-2">
      <div class="chart">
        <h2>LinkedIn Keyword Demand</h2>
        <canvas id="linkedinKeywordsChart"></canvas>
      </div>
      <div class="chart">
        <h2>LinkedIn Country Signal</h2>
        <canvas id="linkedinLocationsChart"></canvas>
      </div>
    </div>
  </section>

  <section>
    <div class="wrap grid-2">
      <div class="chart">
        <h2>LinkedIn Work Model</h2>
        <canvas id="linkedinWorkModelChart"></canvas>
      </div>
      <div class="chart">
        <h2>LinkedIn Recency</h2>
        <canvas id="linkedinRecencyChart"></canvas>
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
      --ink: #19212a;
      --muted: #5f6b77;
      --line: #d9e0e6;
      --panel: #ffffff;
      --soft: #f4f7f8;
      --teal: #2f6f73;
      --blue: #3f6db5;
      --amber: #d99b24;
      --red: #c84e3a;
      --green: #4f8a5b;
      --violet: #725ca8;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: var(--ink);
      background: var(--soft);
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; }}
    a {{ color: var(--teal); text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    header {{
      background: #fff;
      border-bottom: 1px solid var(--line);
      padding: 36px 28px 24px;
    }}
    .wrap {{ width: min(1180px, calc(100% - 32px)); margin: 0 auto; }}
    .eyebrow {{ color: var(--teal); font-weight: 700; font-size: 13px; text-transform: uppercase; letter-spacing: .08em; }}
    h1 {{ margin: 10px 0 10px; font-size: clamp(32px, 4vw, 56px); line-height: 1.02; letter-spacing: 0; }}
    h2 {{ margin: 0 0 16px; font-size: 24px; letter-spacing: 0; }}
    h3 {{ margin: 0 0 8px; font-size: 17px; letter-spacing: 0; }}
    p {{ color: var(--muted); line-height: 1.6; margin: 0; }}
    .intro {{ max-width: 860px; font-size: 17px; }}
    .meta {{ display: flex; flex-wrap: wrap; gap: 10px; margin-top: 18px; }}
    .pill {{ border: 1px solid var(--line); border-radius: 999px; padding: 7px 11px; background: #fff; color: var(--muted); font-size: 13px; }}
    section {{ padding: 28px 0; }}
    .kpis {{ display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 12px; }}
    .kpi, .chart, .note, .table-panel {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: 0 1px 2px rgba(25, 33, 42, .04);
    }}
    .kpi {{ padding: 18px; min-height: 132px; }}
    .kpi strong {{ display: block; font-size: 30px; margin-bottom: 6px; }}
    .kpi span {{ color: var(--muted); font-size: 13px; line-height: 1.4; }}
    .grid-2 {{ display: grid; grid-template-columns: minmax(0, 1.25fr) minmax(0, .75fr); gap: 16px; }}
    .grid-3 {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 16px; }}
    .chart {{ padding: 18px; min-height: 360px; }}
    .chart canvas {{ width: 100% !important; height: 282px !important; }}
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
    .actions {{ display: flex; flex-wrap: wrap; gap: 10px; margin-top: 16px; }}
    .button {{ display: inline-flex; align-items: center; justify-content: center; min-height: 40px; border: 1px solid var(--line); border-radius: 8px; padding: 10px 13px; background: #fff; color: var(--ink); font-weight: 700; font-size: 13px; }}
    .button.primary {{ background: var(--teal); border-color: var(--teal); color: #fff; }}
    .callout-grid {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; margin-top: 14px; }}
    .callout {{ border: 1px solid var(--line); border-radius: 8px; padding: 14px; background: #fbfcfd; }}
    .callout strong {{ display: block; margin-bottom: 6px; }}
    .table-intro {{ display: flex; justify-content: space-between; gap: 16px; align-items: flex-start; margin-bottom: 14px; }}
    .signal-note {{ margin-bottom: 12px; }}
    .signal-note h2 {{ margin-top: 8px; }}
    .signal-kpis {{ margin-top: 12px; }}
    footer {{ border-top: 1px solid var(--line); padding: 24px 0 36px; color: var(--muted); font-size: 13px; }}
    @media (max-width: 900px) {{
      .kpis, .grid-2, .grid-3, .source-list, .callout-grid {{ grid-template-columns: 1fr; }}
      .table-intro {{ display: block; }}
      header {{ padding-inline: 16px; }}
      .chart {{ min-height: 320px; }}
    }}
  </style>
</head>
<body>
  <header>
    <div class="wrap">
      <div class="eyebrow">SAP market observatory · Baseline snapshot</div>
      <h1>Global SAP Job Market Report</h1>
      <p class="intro">This report analyzes SAP-focused job demand across open job-posting sources and a separate LinkedIn Jobs market signal. It is designed to become a living research page: the current version is the baseline, and future snapshots will track how SAP demand, module focus, remote work, salary transparency, and candidate experience change over time.</p>
      <div class="meta">
        <span class="pill">Generated at: {html.escape(generated)}</span>
        <span class="pill">Baseline: 2026-07-19</span>
        <span class="pill">Deduplicated jobs: {total}</span>
      </div>
      <div class="actions">
        <a class="button primary" href="#job-pool">Explore job pool</a>
        <a class="button" href="/data/sap_jobs.csv">Download CSV</a>
        <a class="button" href="#methodology">How it was built</a>
        <a class="button" href="#community">Contribute anonymously</a>
      </div>
    </div>
  </header>

  <section>
    <div class="wrap kpis">
      <div class="kpi"><strong>{total}</strong><span>Deduplicated SAP-related jobs</span></div>
      <div class="kpi"><strong>{unique_locations}</strong><span>Country, region, or location labels</span></div>
      <div class="kpi"><strong>{pct(remote_count, total)}</strong><span>Remote or remote-source job share</span></div>
      <div class="kpi"><strong>{pct(salary_disclosed, total)}</strong><span>Jobs with salary information</span></div>
      <div class="kpi"><strong>{html.escape(top_module)}</strong><span>Most frequent SAP area; top role: {html.escape(top_role)}</span></div>
    </div>
  </section>

  {linkedin_section}

  <section>
    <div class="wrap grid-2">
      <div class="note">
        <h2>What This Baseline Says</h2>
        <div class="callout-grid">
          <div class="callout"><strong>SAP demand is broad, not niche.</strong><p>LinkedIn's rounded worldwide count is far larger than the open-feed dataset, which confirms that open sources are useful for detail while LinkedIn is useful for market scale.</p></div>
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
      <div class="chart">
        <h2>Location Concentration</h2>
        <canvas id="locationsChart"></canvas>
      </div>
      <div class="chart">
        <h2>Salary Transparency</h2>
        <canvas id="salaryChart"></canvas>
      </div>
    </div>
  </section>

  <section>
    <div class="wrap grid-3">
      <div class="chart">
        <h2>Role Families</h2>
        <canvas id="rolesChart"></canvas>
      </div>
      <div class="chart">
        <h2>Seniority</h2>
        <canvas id="seniorityChart"></canvas>
      </div>
      <div class="chart">
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

  <section id="methodology">
    <div class="wrap grid-2">
      <div class="note">
        <h2>Methodology</h2>
        <ul>
          <li>Open job data was collected from public job-board feeds and normalized into one common structure: title, company, location, salary fields, source link, SAP focus, role family, seniority, module, and skills.</li>
          <li>SAP matching used strong keyword signals such as SAP, S/4HANA, ABAP, SuccessFactors, Ariba, Fiori, UI5, BTP, HANA, BW/4HANA, and related terms.</li>
          <li>Salary was not estimated. A posting was marked as salary-disclosed only when the source provided salary fields or the description explicitly mentioned compensation.</li>
          <li>Closed platforms such as LinkedIn and Indeed were not scraped into the job dataset; this report is not an official statistic for the entire market.</li>
          <li>LinkedIn is included only as a separate market-signal layer: rounded search-result counts observed through the logged-in LinkedIn Jobs UI, without bulk extraction or republication of individual postings.</li>
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
          <a href="https://www.linkedin.com/jobs/" target="_blank" rel="noopener">LinkedIn Jobs signal</a>
        </div>
      </div>
    </div>
  </section>

  <section>
    <div class="wrap grid-2">
      <div class="note">
        <h2>How This Will Stay Alive</h2>
        <ul>
          <li>This first release is a baseline snapshot. Future runs will save dated snapshots instead of replacing history.</li>
          <li>Trend charts will compare snapshots across time: module demand, country mix, seniority, remote/hybrid/on-site, salary transparency, and LinkedIn signal shifts.</li>
          <li>The public page can be mirrored to GitHub Pages or any static host, with the source and data snapshots versioned in Git for transparency.</li>
          <li>Community inputs will be anonymized and added as a separate qualitative layer, so market data and human experience remain distinguishable.</li>
        </ul>
      </div>
      <div class="note">
        <h2>Next Research Questions</h2>
        <ul>
          <li>Which SAP modules pay best by country and seniority?</li>
          <li>Which roles are most exposed to outsourcing, automation, or project-cycle risk?</li>
          <li>How do interview processes differ for consulting, in-house, implementation partner, and product-company SAP roles?</li>
          <li>Where do SAP professionals report the best balance between pay, learning, stress, and long-term stability?</li>
        </ul>
      </div>
    </div>
  </section>

  <section>
    <div class="wrap table-panel" id="job-pool">
      <div class="table-intro">
        <div>
          <h2>Open Job Pool</h2>
          <p>All {total} deduplicated open-source postings used in the analysis are listed below with their original source links. LinkedIn postings are not included in this pool because they were used only as rounded market-signal counts.</p>
        </div>
        <div class="actions">
          <a class="button primary" href="/data/sap_jobs.csv">CSV</a>
          <a class="button" href="/data/sap_jobs.json">JSON</a>
          <a class="button" href="/data/linkedin_signal.json">LinkedIn signal</a>
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

    function entries(obj) {{
      return Object.entries(obj || {{}}).filter(([, value]) => value > 0);
    }}

    function makeBarChart(id, data, label, horizontal = false) {{
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
          plugins: {{ legend: {{ display: false }} }},
          scales: {{
            x: {{ ticks: {{ color: "#5f6b77" }}, grid: {{ color: "#edf1f3" }} }},
            y: {{ ticks: {{ color: "#5f6b77" }}, grid: {{ color: "#edf1f3" }} }}
          }}
        }}
      }});
    }}

    function makeDoughnut(id, data) {{
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
          plugins: {{ legend: {{ position: "bottom", labels: {{ boxWidth: 12, color: "#5f6b77" }} }} }}
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
    makeBarChart("linkedinKeywordsChart", chartData.linkedinKeywords, "LinkedIn result count", true);
    makeBarChart("linkedinLocationsChart", chartData.linkedinLocations, "LinkedIn result count", true);
    makeDoughnut("linkedinWorkModelChart", chartData.linkedinWorkModel);
    makeBarChart("linkedinRecencyChart", chartData.linkedinRecency, "LinkedIn result count", true);
    makeBarChart("rolesChart", chartData.roles, "Job count", true);
    makeBarChart("seniorityChart", chartData.seniority, "Job count", true);
    makeDoughnut("focusChart", chartData.focus);
    renderBars("moduleBars", chartData.modules);
    renderBars("skillBars", chartData.skills);

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

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORT_DIR / "index.html"
    root_path = ROOT / "index.html"
    report_path.write_text(report_html, encoding="utf-8")
    root_path.write_text(report_html, encoding="utf-8")
    print(report_path)
    print(root_path)


if __name__ == "__main__":
    main()

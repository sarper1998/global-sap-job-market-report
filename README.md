# Global SAP Job Market Report

This project collects SAP-focused job postings from public job sources and analyzes them by module, technical requirement, role family, seniority, location, remote availability, and salary transparency. It also includes two LinkedIn layers: rounded LinkedIn Jobs result counts as a market-size signal, and a growing source-linked LinkedIn guest job pool collected through partitioned public searches.

Public report: https://sarper1998.github.io/global-sap-job-market-report/

## Plan

1. Define scope honestly: separate market-size signals from source-linked job records.
2. Collect raw data from open job sources: Himalayas, Remote First Jobs, Jobicy, Remotive, Remote OK, and Arbeitnow.
3. Normalize postings: title, company, location, remote status, salary fields, source, and original link.
4. Deduplicate repeated or near-identical postings by normalized title, company, location, and URL signals.
5. Apply SAP matching: SAP, S/4HANA, ABAP, SuccessFactors, Ariba, Fiori, UI5, BTP, HANA, BW/4HANA, and related strong terms.
6. Tag each posting by SAP module, technical skill, role family, seniority, and SAP focus level.
7. Extract job-description signals for recurring terms, soft skills, education fields, and degree mentions.
8. Collect LinkedIn guest job links through public guest job endpoints, partitioned by keyword, location, recency, and work-model filters.
9. Save dated snapshots under `data/snapshots/YYYY-MM-DD` for historical tracking.
10. Generate a publishable HTML report with KPIs, charts, filterable tables, methodology, interpretation, and source attribution.

## Run

```bash
python3 scripts/fetch_sap_jobs.py
python3 scripts/fetch_linkedin_guest_jobs.py
python3 scripts/build_report.py
open report/index.html
```

Expanded LinkedIn crawl batches:

```bash
LINKEDIN_QUERY_FILE=data/config/linkedin_queries_expanded.txt \
LINKEDIN_LOCATION_FILE=data/config/linkedin_locations_expanded.txt \
LINKEDIN_FILTERS=past_24h,past_month,onsite,hybrid,past_week_remote,past_week_hybrid \
LINKEDIN_MAX_PAGES_PER_SEARCH=8 \
LINKEDIN_MAX_DETAILS=0 \
LINKEDIN_MAX_PARTITIONS=720 \
python3 scripts/fetch_linkedin_guest_jobs.py
```

Backfill missing LinkedIn descriptions after link collection:

```bash
LINKEDIN_BACKFILL_ONLY=1 \
LINKEDIN_MAX_DETAILS=1000 \
python3 scripts/fetch_linkedin_guest_jobs.py
```

## Local Long-Running LinkedIn Crawl

The LinkedIn target should be collected locally, not through an LLM session. The local runner keeps its own state in `data/run_state/linkedin_local_crawl_state.json`, writes logs under `logs/`, and resumes from the next partition.

Plan the full grid without crawling:

```bash
python3 scripts/run_linkedin_local_crawl.py --dry-run --target-jobs 371000
```

Current expanded grid:

- 67 SAP queries
- 60 locations
- 9 recency/work-model filters
- 36,180 search partitions
- 7,236,000 theoretical card requests before LinkedIn pagination limits and deduplication

Start a local background crawl:

```bash
scripts/start_linkedin_local_crawl.sh
```

By default this runs locally for up to 12 hours, targets 371,000 collected LinkedIn jobs, processes 720 partitions per batch, skips description backfill during the main collection pass, rebuilds the report, and then exits. It can be restarted any time; it resumes from the saved offset.

Check status:

```bash
scripts/linkedin_local_crawl_status.sh
```

Stop the local crawl:

```bash
scripts/linkedin_local_crawl_status.sh stop
```

## Multi-PC LinkedIn Worker Mode

For faster broad reconciliation runs, split the LinkedIn search grid across multiple always-on PCs. Do not let multiple PCs write to `data/processed/linkedin_jobs.json` directly. Each worker writes an isolated output folder under `data/worker_outputs/<worker-id>/`, and the main PC merges those outputs by LinkedIn job id.

Print a fresh three-PC plan from the beginning of the grid:

```bash
scripts/print_linkedin_worker_commands.py --workers 3 --start-offset 0 --background
```

Example output:

```bash
./scripts/start_linkedin_worker_shard.sh --background pc-1 0 12060
./scripts/start_linkedin_worker_shard.sh --background pc-2 12060 12060
./scripts/start_linkedin_worker_shard.sh --background pc-3 24120 12060
```

If a single-machine crawl is already in progress, stop it first or start worker shards after a conservative future offset to avoid overlap. Overlap is not fatal because merge deduplicates by job id, but it wastes time.

Check worker status on each PC:

```bash
scripts/linkedin_worker_status.sh
```

When workers finish, copy each `data/worker_outputs/<worker-id>/` folder back to the main PC under the same path, then merge:

```bash
scripts/merge_linkedin_worker_outputs.py
python3 scripts/build_report.py
npm run build
```

Run a longer local session:

```bash
LINKEDIN_MAX_RUNTIME_HOURS=72 \
LINKEDIN_MAX_PARTITIONS=720 \
LINKEDIN_BACKFILL_DETAILS=0 \
scripts/start_linkedin_local_crawl.sh --cycle-when-complete
```

Install monthly local automation on macOS:

```bash
scripts/install_monthly_local_crawl.sh
```

This installs a LaunchAgent that starts the local crawl on the 1st day of every month at 02:30 local time. It does not require Codex or ChatGPT to stay open.

macOS privacy note: if this repo lives under `~/Documents`, `~/Desktop`, or `~/Downloads`, LaunchAgent may fail with `Operation not permitted` unless Terminal/Python has Full Disk Access. For unattended monthly crawling, move the repo to a non-protected folder such as `~/Projects/global-sap-job-market-report`, or grant Full Disk Access. Manual Terminal runs from the current folder still work.

## Parallel Company Career / ATS Crawl

The company career crawler runs independently from LinkedIn and writes a separate source-linked pool:

```bash
scripts/start_company_career_crawl.sh
scripts/company_career_crawl_status.sh
```

It collects public SAP postings from configured company career and ATS sources under `data/config/company_career_sources.json`, including jobs2web / SuccessFactors pages, SmartRecruiters, Greenhouse, and Workday CXS where public access works. Outputs are written to:

```text
data/processed/company_career_jobs.csv
data/processed/company_career_jobs.json
data/processed/company_career_jobs_summary.json
```

Install the monthly macOS LaunchAgent:

```bash
scripts/install_company_career_crawl.sh
```

This schedules the company career crawl on the 1st day of every month at 03:30 local time, after the LinkedIn monthly crawler starts.

## Daily Delta Mode

Daily delta mode keeps the report alive without re-running the full 371,000+ LinkedIn market crawl every day.

```bash
scripts/install_daily_delta.sh
scripts/daily_delta_status.sh
```

The daily LaunchAgent runs every day at 06:15 local time. It:

- skips LinkedIn delta if the full LinkedIn crawler is still running, to avoid concurrent writes
- otherwise runs a lightweight LinkedIn `past_24h` crawl over the daily location set in `data/config/linkedin_locations_daily_delta.txt`
- runs the company career / ATS crawler in merge mode, preserving `first_seen_*` and updating `last_seen_*`
- skips jobs2web / SuccessFactors detail-page fetching during daily runs, preserving existing descriptions and leaving new description enrichment to broader reconciliation/backfill runs
- rebuilds the report and static bundle
- writes `data/processed/daily_delta_summary.json` and `data/snapshots/YYYY-MM-DD/daily_delta_summary.json`

The daily LinkedIn delta intentionally uses fewer locations, one recency filter, and two pages per search. The broad/full crawler should be treated as occasional reconciliation, not the normal daily workflow.

## Current Snapshot

The latest run on 2026-07-19 collected 3,485 raw records from open sources. After SAP filtering and deduplication, 1,565 postings were included in the report.

- Salary transparency: 319 postings include salary information; 1,246 do not.
- Top locations: United States, Germany, India, Canada, United Kingdom.
- Top role families: Technical / Development, Data / Analytics, Basis / Security, Functional Consulting.
- Most frequent SAP areas: S/4HANA, BTP / Integration, ABAP / Development, HANA / Data, FI / CO / FICO.
- LinkedIn Jobs search signal: SAP in Worldwide showed 371,000+ rounded results on 2026-07-19.
- LinkedIn guest pool: 21,085 deduplicated LinkedIn job links collected across 1,051 keyword/location/filter partitions.
- LinkedIn description detail: 4,020 collected LinkedIn rows have fetched job-description detail.
- Top collected LinkedIn guest skill signals: S/4HANA, FICO, ABAP, SAP SD, SAP BTP.
- Top collected LinkedIn guest soft-skill signals: consulting mindset, communication, leadership, collaboration, analytical thinking.
- Description analysis now includes soft skill signals, education-field signals, degree-level mentions, and common job-description terms.

Processed data files:

- `data/processed/sap_jobs.csv`
- `data/processed/sap_jobs.json`
- `data/processed/summary.json`
- `data/processed/linkedin_signal.json`
- `data/processed/linkedin_jobs.csv`
- `data/processed/linkedin_jobs.json.gz`
- `data/processed/linkedin_jobs_summary.json`
- `data/snapshots/index.json`
- Deployed data links: `data/sap_jobs.csv`, `data/sap_jobs.json`, `data/summary.json`, `data/linkedin_signal.json`, `data/linkedin_jobs.csv`, `data/linkedin_jobs.json.gz`, `data/linkedin_jobs_summary.json`, `data/snapshots/index.json`

## Scope Limits

- The 371,000+ LinkedIn number is a rounded LinkedIn Jobs result count and should be read as market-size signal, not as a complete downloadable dataset.
- The LinkedIn guest job pool is collected from public LinkedIn guest job endpoints/search pages only. It does not use logged-in cookies, proxy rotation, CAPTCHA bypass, or private LinkedIn session data.
- LinkedIn public pagination is limited. The pool grows by partitioning searches across keywords, countries, recency windows, and work-model filters, then deduplicating by LinkedIn job id.
- The expanded LinkedIn crawl uses `data/config/linkedin_queries_expanded.txt` and `data/config/linkedin_locations_expanded.txt`, with batch offsets so the full grid can be collected gradually instead of forcing one fragile run.
- Salary is not estimated; only salary information explicitly available in source fields or posting text is marked.
- Job-description keyword analysis currently uses the stored public excerpt field. Fuller description analysis is planned where source terms allow it.
- Some sources provide city or region labels rather than normalized countries. These records are shown using the source-provided location when a reliable country mapping is not available.
- Source feeds change continuously, so report counts are expected to change on each run.

## Next Improvements

- Expand the LinkedIn crawler grid and save trend charts for country mix, module demand, seniority, remote/hybrid/on-site, salary transparency, LinkedIn signal shifts, and LinkedIn guest-pool growth.
- Add broader source coverage such as Adzuna, TheirStack, and direct employer career pages.
- Refine SAP module matching with manually reviewed examples.
- Normalize salary-bearing postings by currency and compensation period.
- Mirror the report to GitHub Pages or another static host with scheduled data refreshes.
- Add an anonymous community-input layer for salary ranges, interview processes, working conditions, risk, stress, and job satisfaction.

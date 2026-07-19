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
- `data/processed/linkedin_jobs.json`
- `data/processed/linkedin_jobs_summary.json`
- `data/snapshots/index.json`
- Deployed data links: `/data/sap_jobs.csv`, `/data/sap_jobs.json`, `/data/summary.json`, `/data/linkedin_signal.json`, `/data/linkedin_jobs.csv`, `/data/linkedin_jobs.json`, `/data/linkedin_jobs_summary.json`, `/data/snapshots/index.json`

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

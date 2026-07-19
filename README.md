# Global SAP Job Market Report

This project collects SAP-focused job postings from public job sources and analyzes them by module, technical requirement, role family, seniority, location, remote availability, and salary transparency. It also includes a separate LinkedIn Jobs market-signal layer based on read-only UI result counts.

Public report: https://sarper1998.github.io/global-sap-job-market-report/

## Plan

1. Define scope honestly: this is a current snapshot of accessible open job-posting sources, without scraping closed platforms.
2. Collect raw data from open job sources: Himalayas, Remote First Jobs, Jobicy, Remotive, Remote OK, and Arbeitnow.
3. Normalize postings: title, company, location, remote status, salary fields, source, and original link.
4. Apply SAP matching: SAP, S/4HANA, ABAP, SuccessFactors, Ariba, Fiori, UI5, BTP, HANA, BW/4HANA, and related strong terms.
5. Tag each posting by SAP module, technical skill, role family, seniority, and SAP focus level.
6. Generate a publishable HTML report with KPIs, charts, a filterable job table, methodology, and source attribution.

## Run

```bash
python3 scripts/fetch_sap_jobs.py
python3 scripts/build_report.py
open report/index.html
```

## Current Snapshot

The latest run on 2026-07-19 collected 3,485 raw records from open sources. After SAP filtering and deduplication, 1,565 postings were included in the report.

- Salary transparency: 319 postings include salary information; 1,246 do not.
- Top locations: United States, Germany, India, Canada, United Kingdom.
- Top role families: Technical / Development, Data / Analytics, Basis / Security, Functional Consulting.
- Most frequent SAP areas: S/4HANA, BTP / Integration, ABAP / Development, HANA / Data, FI / CO / FICO.
- LinkedIn Jobs signal: SAP in Worldwide showed 371,000+ results in the logged-in LinkedIn UI on 2026-07-19.

Processed data files:

- `data/processed/sap_jobs.csv`
- `data/processed/sap_jobs.json`
- `data/processed/summary.json`
- `data/processed/linkedin_signal.json`
- Deployed data links: `/data/sap_jobs.csv`, `/data/sap_jobs.json`, `/data/summary.json`, `/data/linkedin_signal.json`

## Scope Limits

- Closed platforms such as LinkedIn and Indeed are not scraped into the job dataset.
- LinkedIn is included only as a separate market-signal layer using rounded UI result counts; individual LinkedIn postings are not bulk extracted or republished.
- Salary is not estimated; only salary information explicitly available in source fields or posting text is marked.
- Some sources provide city or region labels rather than normalized countries. These records are shown using the source-provided location when a reliable country mapping is not available.
- Source feeds change continuously, so report counts are expected to change on each run.

## Next Improvements

- Save dated snapshots and add trend charts for country mix, module demand, seniority, remote/hybrid/on-site, salary transparency, and LinkedIn signal shifts.
- Add broader source coverage such as Adzuna, TheirStack, and direct employer career pages.
- Refine SAP module matching with manually reviewed examples.
- Normalize salary-bearing postings by currency and compensation period.
- Mirror the report to GitHub Pages or another static host with scheduled data refreshes.
- Add an anonymous community-input layer for salary ranges, interview processes, working conditions, risk, stress, and job satisfaction.

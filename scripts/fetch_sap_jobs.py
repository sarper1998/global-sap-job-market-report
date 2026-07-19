#!/usr/bin/env python3
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import html
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw" / dt.date.today().isoformat()
PROCESSED_DIR = ROOT / "data" / "processed"

USER_AGENT = "sap-market-report/1.0 (+research-report)"

SAP_SEARCH_QUERIES = ["sap", "abap", "s/4hana", "successfactors", "ariba", "fiori", "sap btp"]
JOBICY_TAGS = ["sap", "abap", "hana", "fiori", "successfactors", "ariba"]

MAX_HIMALAYAS_SAP_PAGES = int(os.environ.get("MAX_HIMALAYAS_SAP_PAGES", "55"))
MAX_HIMALAYAS_OTHER_PAGES = int(os.environ.get("MAX_HIMALAYAS_OTHER_PAGES", "8"))
MAX_REMOTEFIRST_PAGES = int(os.environ.get("MAX_REMOTEFIRST_PAGES", "5"))
MAX_ARBEITNOW_PAGES = int(os.environ.get("MAX_ARBEITNOW_PAGES", "35"))
REQUEST_DELAY_SECONDS = float(os.environ.get("REQUEST_DELAY_SECONDS", "0.15"))


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: List[str] = []

    def handle_data(self, data: str) -> None:
        if data:
            self.parts.append(data)

    def text(self) -> str:
        return " ".join(self.parts)


def html_to_text(value: Any) -> str:
    if value is None:
        return ""
    parser = TextExtractor()
    parser.feed(str(value))
    return normalize_space(html.unescape(parser.text() or str(value)))


def normalize_space(value: Any) -> str:
    return re.sub(r"\s+", " ", html.unescape(str(value or ""))).strip()


def fetch_json(url: str, params: Optional[Dict[str, Any]] = None) -> Any:
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json,text/plain,*/*",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = resp.read().decode("utf-8", errors="replace")
    return json.loads(body)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def stable_id(parts: Iterable[Any]) -> str:
    text = "|".join(normalize_space(p).lower() for p in parts if p is not None)
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


def split_locations(raw: Any) -> List[str]:
    if raw is None:
        return []
    if isinstance(raw, list):
        out: List[str] = []
        for item in raw:
            if isinstance(item, dict):
                out.append(item.get("name") or item.get("country") or item.get("location") or "")
            else:
                out.append(str(item))
        return clean_locations(out)
    if isinstance(raw, str):
        return clean_locations(re.split(r",|/|;|\bor\b|\band\b", raw))
    return clean_locations([str(raw)])


def clean_locations(values: Iterable[str]) -> List[str]:
    city_to_country = {
        "Berlin": "Germany",
        "Bochum": "Germany",
        "Cologne": "Germany",
        "Dingolfing": "Germany",
        "Dresden": "Germany",
        "Düsseldorf": "Germany",
        "Essen": "Germany",
        "Gudow": "Germany",
        "Hamm": "Germany",
        "Heidelberg": "Germany",
        "Langen": "Germany",
        "Lübeck": "Germany",
        "Mannheim": "Germany",
        "Munich": "Germany",
        "Paderborn": "Germany",
        "Remscheid": "Germany",
        "Solingen": "Germany",
        "Stuttgart": "Germany",
        "Sömmerda": "Germany",
        "Waiblingen": "Germany",
        "Wangen im Allgäu": "Germany",
        "Wetzlar": "Germany",
    }
    cleaned = []
    for item in values:
        value = normalize_space(item)
        if not value:
            continue
        value = city_to_country.get(value, value)
        aliases = {
            "USA": "United States",
            "US": "United States",
            "U.S.": "United States",
            "U.S.A.": "United States",
            "United States of America": "United States",
            "United States Of America": "United States",
            "United States of America": "United States",
            "United States timezones": "United States",
            "UK": "United Kingdom",
            "U.K.": "United Kingdom",
            "American timezones": "Americas",
            "European timezones": "Europe",
            "LATAM": "Latin America",
            "EU": "Europe",
            "EMEA": "Europe / Middle East / Africa",
            "APAC": "Asia-Pacific",
            "Czech Republic": "Czechia",
        }
        value = aliases.get(value, value)
        if value not in cleaned:
            cleaned.append(value)
    return cleaned


STRONG_SAP_PATTERNS: List[Tuple[str, str]] = [
    ("SAP", r"\bSAP\b"),
    ("S/4HANA", r"\bS\s*[/.-]?\s*4\s*HANA\b|\bS4HANA\b"),
    ("ABAP", r"\bABAP\b"),
    ("SuccessFactors", r"\bSuccess\s*Factors\b|\bSuccessFactors\b"),
    ("Ariba", r"\bAriba\b"),
    ("Concur", r"\bConcur\b"),
    ("Fiori", r"\bFiori\b"),
    ("UI5", r"\bSAPUI5\b|\bUI5\b"),
    ("BTP", r"\bBTP\b|\bBusiness Technology Platform\b"),
    ("HANA", r"\bHANA\b"),
    ("BW/4HANA", r"\bBW\s*[/.-]?\s*4\s*HANA\b|\bBW4HANA\b"),
    ("BusinessObjects", r"\bBusiness\s*Objects\b|\bBOBJ\b"),
    ("Hybris / Commerce Cloud", r"\bHybris\b|\bSAP CX\b|\bCommerce Cloud\b"),
    ("ByDesign", r"\bByDesign\b"),
    ("Business One", r"\bBusiness One\b"),
    ("SAP Analytics Cloud", r"\bSAP Analytics Cloud\b|\bSAC\b"),
    ("SAP Basis", r"\bSAP Basis\b|\bBasis Administrator\b"),
    ("IDoc", r"\bIDoc[s]?\b"),
]


MODULE_PATTERNS: List[Tuple[str, str]] = [
    ("S/4HANA", r"\bS\s*[/.-]?\s*4\s*HANA\b|\bS4HANA\b"),
    ("ABAP / Development", r"\bABAP\b|\bRAP\b|\bCAP\b|\bCDS\b"),
    ("BTP / Integration", r"\bBTP\b|\bBusiness Technology Platform\b|\bIntegration Suite\b|\bCPI\b|\bPI/PO\b|\bIDoc[s]?\b|\bOData\b"),
    ("Fiori / UI5", r"\bFiori\b|\bSAPUI5\b|\bUI5\b"),
    ("Basis / Security", r"\bSAP Basis\b|\bBasis Administrator\b|\bGRC\b|\bauthori[sz]ation\b|\brole administration\b|\bSAP Security\b|\bsecurity consultant\b"),
    ("HANA / Data", r"\bHANA\b|\bBW\s*[/.-]?\s*4\s*HANA\b|\bBW4HANA\b|\bSAP BW\b|\bSAP BI\b|\bDatasphere\b|\bSAP Analytics Cloud\b|\bBusinessObjects\b"),
    ("FI / CO / FICO", r"\bSAP\s*(FI|CO|FICO|FI/CO)\b|\bFICO\b|\bFI/CO\b|\bSAP.{0,60}Finance\b|\bSAP.{0,60}Controlling\b"),
    ("MM / Procurement", r"\bSAP\s*MM\b|\bSAP.{0,70}Materials Management\b|\bSAP.{0,70}Procurement\b|\bAriba\b"),
    ("SD / Sales", r"\bSAP\s*SD\b|\bSAP.{0,70}Sales and Distribution\b|\bSAP.{0,70}Order to Cash\b"),
    ("PP / QM / Manufacturing", r"\bSAP\s*PP\b|\bSAP\s*QM\b|\bSAP.{0,70}Production Planning\b|\bSAP.{0,70}Quality Management\b"),
    ("EWM / WM / Logistics", r"\bSAP\s*EWM\b|\bSAP\s*WM\b|\bSAP.{0,70}Warehouse\b|\bSAP.{0,70}Logistics\b"),
    ("TM / GTS / Supply Chain", r"\bSAP\s*TM\b|\bSAP\s*GTS\b|\bSAP\s*IBP\b|\bSAP.{0,70}Supply Chain\b|\bSAP.{0,70}Transportation\b"),
    ("HCM / SuccessFactors", r"\bSAP\s*HCM\b|\bSuccess\s*Factors\b|\bSuccessFactors\b|\bSAP.{0,70}HR\b"),
    ("CRM / CX / Commerce", r"\bSAP\s*CRM\b|\bSAP CX\b|\bHybris\b|\bCommerce Cloud\b"),
    ("PM / Asset Management", r"\bSAP\s*PM\b|\bSAP.{0,70}Plant Maintenance\b|\bSAP.{0,70}Asset Management\b"),
    ("MDG / Master Data", r"\bSAP\s*MDG\b|\bMaster Data Governance\b"),
]


SKILL_PATTERNS: List[Tuple[str, str]] = [
    ("ABAP", r"\bABAP\b"),
    ("S/4HANA", r"\bS\s*[/.-]?\s*4\s*HANA\b|\bS4HANA\b"),
    ("SAP HANA", r"\bHANA\b"),
    ("SAP BTP", r"\bBTP\b|\bBusiness Technology Platform\b"),
    ("SAP Fiori", r"\bFiori\b"),
    ("SAPUI5 / UI5", r"\bSAPUI5\b|\bUI5\b"),
    ("CPI / Integration Suite", r"\bCPI\b|\bIntegration Suite\b|\bCloud Platform Integration\b"),
    ("PI/PO", r"\bPI/PO\b|\bSAP PI\b|\bSAP PO\b"),
    ("OData", r"\bOData\b"),
    ("CDS Views", r"\bCDS\b"),
    ("RAP / CAP", r"\bRAP\b|\bCAP\b"),
    ("IDoc", r"\bIDoc[s]?\b"),
    ("FICO", r"\bFICO\b|\bFI/CO\b|\bSAP FI\b|\bSAP CO\b"),
    ("SAP MM", r"\bSAP MM\b"),
    ("SAP SD", r"\bSAP SD\b"),
    ("SAP PP", r"\bSAP PP\b"),
    ("SAP QM", r"\bSAP QM\b"),
    ("SAP EWM", r"\bSAP EWM\b"),
    ("SAP TM", r"\bSAP TM\b"),
    ("SAP GTS", r"\bSAP GTS\b"),
    ("SuccessFactors", r"\bSuccess\s*Factors\b|\bSuccessFactors\b"),
    ("Ariba", r"\bAriba\b"),
    ("Concur", r"\bConcur\b"),
    ("SAP BW / BI", r"\bSAP BW\b|\bSAP BI\b|\bBW/4HANA\b|\bBW4HANA\b"),
    ("SAP Analytics Cloud", r"\bSAP Analytics Cloud\b|\bSAC\b"),
    ("Datasphere", r"\bDatasphere\b"),
    ("GRC / Security", r"\bGRC\b|\bauthori[sz]ation\b|\bSAP Security\b|\brole administration\b"),
    ("MDG", r"\bSAP MDG\b|\bMaster Data Governance\b"),
    ("Agile / Scrum", r"\bAgile\b|\bScrum\b"),
    ("English", r"\bEnglish\b"),
    ("German", r"\bGerman\b|\bDeutsch\b"),
]


def regex_hits(patterns: List[Tuple[str, str]], text: str) -> List[str]:
    hits = []
    for label, pattern in patterns:
        if re.search(pattern, text, flags=re.IGNORECASE):
            hits.append(label)
    return hits


def is_sap_job(text: str) -> bool:
    hits = regex_hits(STRONG_SAP_PATTERNS, text)
    if not hits:
        return False
    # Guard against the most common false positives when only short tags match.
    lowered = text.lower()
    if hits == ["SAP"] and "whatsapp" in lowered and re.search(r"\bSAP\b", text, flags=re.IGNORECASE) is None:
        return False
    return True


def classify_role(title: str, text: str) -> str:
    title_l = title.lower()
    text_l = text.lower()
    if re.search(r"\b(program|project|delivery|engagement)\s+manager\b|\bproduct owner\b|\bscrum master\b", title_l):
        return "Project / Program"
    if re.search(r"\barchitect\b|\bsolution architect\b|\benterprise architect\b", title_l):
        return "Architecture"
    if re.search(r"\bsap basis\b|\bbasis administrator\b|\bsap security\b|\bauthori[sz]ation\b|\bgrc\b|\brole administration\b", text_l):
        return "Basis / Security"
    if re.search(r"\babap\b|\bdeveloper\b|\bengineer\b|\bfiori\b|\bui5\b|\bintegration\b|\bbtp\b|\bcpi\b|\bpi/po\b", text_l):
        return "Technical / Development"
    if re.search(r"\bdata\b|\banalytics\b|\bbw\b|\bbi\b|\bhana\b|\bsac\b|\bdatasphere\b", text_l):
        return "Data / Analytics"
    if re.search(r"\bconsultant\b|\bfunctional\b|\bbusiness analyst\b|\bprocess\b", text_l):
        return "Functional Consulting"
    if re.search(r"\bsupport\b|\boperations\b|\badministrator\b", text_l):
        return "Support / Operations"
    return "Other SAP-Related"


def classify_focus(title: str, text: str, modules: List[str]) -> str:
    title_l = title.lower()
    text_l = text.lower()
    title_has_core = re.search(
        r"\bsap\b|\babap\b|\bs/4hana\b|\bs4hana\b|\bsuccessfactors\b|\bariba\b|\bfiori\b|\bui5\b|\bbtp\b|\bhana\b",
        title_l,
    )
    delivery_role = re.search(
        r"\bconsultant\b|\bdeveloper\b|\bengineer\b|\barchitect\b|\badministrator\b|\bspecialist\b|\banalyst\b|\bsupport\b|\bmanager\b|\blead\b",
        title_l,
    )
    if title_has_core and delivery_role:
        return "Core SAP delivery role"
    if title_has_core:
        return "SAP-titled role"
    if modules and modules != ["Unspecified SAP"]:
        return "SAP module/technical requirement"
    if re.search(r"\bexperience with SAP\b|\bSAP experience\b|\bSAP knowledge\b|\bSAP system\b|\bSAP ERP\b", text_l):
        return "SAP required as business tool"
    return "SAP mentioned"


def classify_seniority(title: str, text: str) -> str:
    sample = f"{title} {text[:1000]}".lower()
    if re.search(r"\bintern(ship)?\b|\btrainee\b|\bgraduate\b|\bentry[- ]level\b", sample):
        return "Entry / Intern"
    if re.search(r"\bjunior\b|\bassociate\b", sample):
        return "Junior"
    if re.search(r"\bprincipal\b|\bstaff\b|\blead\b|\bhead\b|\bdirector\b|\bmanager\b", sample):
        return "Lead / Manager"
    if re.search(r"\bsenior\b|\bsr\.?\b|\bexpert\b|\b[5-9]\+?\s+years\b|\b10\+?\s+years\b", sample):
        return "Senior"
    return "Mid / Unspecified"


def salary_state(*values: Any, text: str = "") -> str:
    for value in values:
        if value in (None, "", 0, "0"):
            continue
        return "Disclosed"
    if re.search(r"(?i)\b(salary|compensation|pay range|base pay)\b.{0,80}[$€£]\s?\d", text):
        return "Mentioned in text"
    return "Not disclosed"


def normalize_job(source: str, raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if source == "himalayas":
        title = normalize_space(raw.get("title"))
        company = normalize_space(raw.get("companyName"))
        description = html_to_text(raw.get("description") or raw.get("excerpt"))
        url = raw.get("applicationLink") or raw.get("url") or f"https://himalayas.app/companies/{raw.get('companySlug', '')}/jobs/{raw.get('id', '')}"
        locations = split_locations(raw.get("locationRestrictions"))
        salary_min = raw.get("minSalary")
        salary_max = raw.get("maxSalary")
        currency = raw.get("currency")
        salary_period = raw.get("salaryPeriod")
        posted_at = raw.get("pubDate") or raw.get("updatedAt") or raw.get("createdAt")
        remote = True
    elif source == "remotefirst":
        title = normalize_space(raw.get("title"))
        company = normalize_space(raw.get("company_name") or raw.get("company"))
        description = html_to_text(raw.get("description") or raw.get("excerpt"))
        url = raw.get("url") or raw.get("apply_url") or raw.get("job_url")
        locations = split_locations(raw.get("locations"))
        salary_min = raw.get("salary_min") or None
        salary_max = raw.get("salary_max") or None
        currency = raw.get("salary_currency") or raw.get("currency")
        salary_period = raw.get("salary_period")
        posted_at = raw.get("publication_date") or raw.get("posted_at") or raw.get("created_at")
        remote = True
    elif source == "jobicy":
        title = normalize_space(raw.get("jobTitle"))
        company = normalize_space(raw.get("companyName"))
        description = html_to_text(raw.get("jobDescription") or raw.get("jobExcerpt"))
        url = raw.get("url")
        locations = split_locations(raw.get("jobGeo"))
        salary_min = raw.get("annualSalaryMin") or raw.get("salaryMin") or None
        salary_max = raw.get("annualSalaryMax") or raw.get("salaryMax") or None
        currency = raw.get("salaryCurrency")
        salary_period = "annual" if salary_min or salary_max else None
        posted_at = raw.get("pubDate") or raw.get("postedAt")
        remote = True
    elif source == "remotive":
        title = normalize_space(raw.get("title"))
        company = normalize_space(raw.get("company_name"))
        description = html_to_text(raw.get("description"))
        url = raw.get("url")
        locations = split_locations(raw.get("candidate_required_location"))
        salary_min = None
        salary_max = None
        currency = None
        salary_period = None
        posted_at = raw.get("publication_date")
        remote = True
    elif source == "remoteok":
        title = normalize_space(raw.get("position"))
        company = normalize_space(raw.get("company"))
        description = html_to_text(raw.get("description"))
        url = raw.get("url") or f"https://remoteok.com/remote-jobs/{raw.get('id')}"
        locations = split_locations(raw.get("location"))
        salary_min = raw.get("salary_min") or None
        salary_max = raw.get("salary_max") or None
        currency = "USD" if salary_min or salary_max else None
        salary_period = "annual" if salary_min or salary_max else None
        posted_at = raw.get("date")
        remote = True
    elif source == "arbeitnow":
        title = normalize_space(raw.get("title"))
        company = normalize_space(raw.get("company_name"))
        description = html_to_text(raw.get("description"))
        url = raw.get("url")
        locations = split_locations(raw.get("location"))
        salary_min = None
        salary_max = None
        currency = None
        salary_period = None
        created = raw.get("created_at")
        posted_at = dt.datetime.utcfromtimestamp(created).isoformat() if isinstance(created, int) else created
        remote = bool(raw.get("remote"))
    else:
        return None

    text = normalize_space(f"{title} {company} {description}")
    if not title or not company or not is_sap_job(text):
        return None

    modules = regex_hits(MODULE_PATTERNS, text)
    skills = regex_hits(SKILL_PATTERNS, text)
    if not locations:
        locations = ["Worldwide / Not specified"] if remote else ["Not specified"]

    return {
        "id": stable_id([source, url, title, company]),
        "source": source,
        "title": title,
        "company": company,
        "url": url,
        "posted_at": posted_at,
        "locations": locations,
        "primary_location": locations[0] if locations else "Not specified",
        "remote": remote,
        "salary_status": salary_state(salary_min, salary_max, text=description),
        "salary_min": salary_min,
        "salary_max": salary_max,
        "salary_currency": currency,
        "salary_period": salary_period,
        "sap_focus": classify_focus(title, text, modules or ["Unspecified SAP"]),
        "role_family": classify_role(title, text),
        "seniority": classify_seniority(title, description),
        "modules": modules or ["Unspecified SAP"],
        "skills": skills,
        "description_excerpt": description[:420],
        "match_terms": regex_hits(STRONG_SAP_PATTERNS, text),
    }


def collect_himalayas() -> List[Dict[str, Any]]:
    collected: List[Dict[str, Any]] = []
    raw: Dict[str, Any] = {}
    for query in SAP_SEARCH_QUERIES:
        max_pages = MAX_HIMALAYAS_SAP_PAGES if query == "sap" else MAX_HIMALAYAS_OTHER_PAGES
        raw[query] = []
        empty_pages = 0
        for page in range(1, max_pages + 1):
            payload = fetch_json(
                "https://himalayas.app/jobs/api/search",
                {"q": query, "sort": "recent", "page": page},
            )
            jobs = payload.get("jobs", [])
            raw[query].append({"page": page, "count": len(jobs), "payload": payload})
            collected.extend(jobs)
            empty_pages = empty_pages + 1 if not jobs else 0
            if empty_pages >= 2:
                break
            time.sleep(REQUEST_DELAY_SECONDS)
    write_json(RAW_DIR / "himalayas.json", raw)
    return collected


def collect_remotefirst() -> List[Dict[str, Any]]:
    collected: List[Dict[str, Any]] = []
    raw: Dict[str, Any] = {}
    for query in SAP_SEARCH_QUERIES:
        raw[query] = []
        for page in range(0, MAX_REMOTEFIRST_PAGES):
            payload = fetch_json(
                "https://remotefirstjobs.com/api/search-jobs",
                {"query": query, "page": page},
            )
            jobs = payload.get("jobs") or []
            raw[query].append({"page": page, "count": len(jobs), "payload": payload})
            collected.extend(jobs)
            if not jobs:
                break
            time.sleep(REQUEST_DELAY_SECONDS)
    write_json(RAW_DIR / "remotefirst.json", raw)
    return collected


def collect_jobicy() -> List[Dict[str, Any]]:
    collected: List[Dict[str, Any]] = []
    raw: Dict[str, Any] = {}
    for tag in JOBICY_TAGS:
        payload = fetch_json("https://jobicy.com/api/v2/remote-jobs", {"tag": tag, "count": 50})
        jobs = payload.get("jobs", [])
        raw[tag] = payload
        collected.extend(jobs)
        time.sleep(REQUEST_DELAY_SECONDS)
    write_json(RAW_DIR / "jobicy.json", raw)
    return collected


def collect_remotive() -> List[Dict[str, Any]]:
    collected: List[Dict[str, Any]] = []
    raw: Dict[str, Any] = {}
    for query in SAP_SEARCH_QUERIES:
        payload = fetch_json("https://remotive.com/api/remote-jobs", {"search": query})
        jobs = payload.get("jobs", [])
        raw[query] = payload
        collected.extend(jobs)
        time.sleep(REQUEST_DELAY_SECONDS)
    write_json(RAW_DIR / "remotive.json", raw)
    return collected


def collect_remoteok() -> List[Dict[str, Any]]:
    payload = fetch_json("https://remoteok.com/api")
    jobs = [item for item in payload if isinstance(item, dict) and item.get("id")]
    write_json(RAW_DIR / "remoteok.json", payload)
    return jobs


def collect_arbeitnow() -> List[Dict[str, Any]]:
    collected: List[Dict[str, Any]] = []
    raw: List[Dict[str, Any]] = []
    for page in range(1, MAX_ARBEITNOW_PAGES + 1):
        payload = fetch_json("https://www.arbeitnow.com/api/job-board-api", {"page": page})
        jobs = payload.get("data", [])
        raw.append({"page": page, "count": len(jobs), "payload": payload})
        collected.extend(jobs)
        if not jobs or not payload.get("links", {}).get("next"):
            break
        time.sleep(REQUEST_DELAY_SECONDS)
    write_json(RAW_DIR / "arbeitnow.json", raw)
    return collected


COLLECTORS = {
    "himalayas": collect_himalayas,
    "remotefirst": collect_remotefirst,
    "jobicy": collect_jobicy,
    "remotive": collect_remotive,
    "remoteok": collect_remoteok,
    "arbeitnow": collect_arbeitnow,
}


def dedupe(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    deduped = []
    for row in rows:
        key = normalize_space(f"{row['title']}|{row['company']}|{row.get('url') or ''}").lower()
        fallback = normalize_space(f"{row['title']}|{row['company']}|{row['primary_location']}").lower()
        hashed = hashlib.sha1((key or fallback).encode("utf-8")).hexdigest()
        if hashed in seen:
            continue
        seen.add(hashed)
        deduped.append(row)
    return deduped


def write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "id",
        "source",
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
        "url",
        "description_excerpt",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            copy = row.copy()
            copy["locations"] = "; ".join(row.get("locations", []))
            copy["modules"] = "; ".join(row.get("modules", []))
            copy["skills"] = "; ".join(row.get("skills", []))
            writer.writerow({field: copy.get(field, "") for field in fields})


def build_summary(rows: List[Dict[str, Any]], source_counts: Dict[str, int]) -> Dict[str, Any]:
    def count_values(field: str, multi: bool = False) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for row in rows:
            values = row.get(field, [])
            if not multi:
                values = [values]
            for value in values:
                if not value:
                    continue
                counts[str(value)] = counts.get(str(value), 0) + 1
        return dict(sorted(counts.items(), key=lambda x: (-x[1], x[0])))

    return {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "raw_source_counts": source_counts,
        "sap_jobs_after_filter": len(rows),
        "salary_disclosure": count_values("salary_status"),
        "sources": count_values("source"),
        "sap_focus": count_values("sap_focus"),
        "primary_locations": count_values("primary_location"),
        "role_families": count_values("role_family"),
        "seniority": count_values("seniority"),
        "modules": count_values("modules", multi=True),
        "skills": count_values("skills", multi=True),
    }


def main() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    normalized: List[Dict[str, Any]] = []
    source_counts: Dict[str, int] = {}
    errors: Dict[str, str] = {}

    for source, collector in COLLECTORS.items():
        try:
            raw_jobs = collector()
            source_counts[source] = len(raw_jobs)
            for raw in raw_jobs:
                item = normalize_job(source, raw)
                if item:
                    normalized.append(item)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError, TypeError) as exc:
            errors[source] = str(exc)
            source_counts[source] = 0

    rows = sorted(dedupe(normalized), key=lambda row: (row["source"], row["company"], row["title"]))
    summary = build_summary(rows, source_counts)
    summary["errors"] = errors

    write_json(PROCESSED_DIR / "sap_jobs.json", rows)
    write_csv(PROCESSED_DIR / "sap_jobs.csv", rows)
    write_json(PROCESSED_DIR / "summary.json", summary)

    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

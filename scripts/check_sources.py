"""Read-only careers portal and first-page feed checks, emitted as JSON lines.

Run ``.venv/bin/python scripts/check_sources.py --company browserstack`` from
this repository. A reachable careers page alone does not verify collection.
This script never calls Collector.collect(), discovers/persists adapters, or
writes the application's database.
"""
import argparse
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from urllib.parse import parse_qsl, urlencode, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.companies import COMPANIES
from app.collectors import Collector, SourceError, http_client
from app.sources import atlassian_postings


def select_companies(companies, filters):
    """Accept IDs, names, or case-insensitive name fragments; reject typos."""
    if not filters:
        return list(companies)
    selected = set()
    for value in filters:
        query = value.strip().casefold()
        exact = [c for c in companies if query in (c["id"].casefold(), c["name"].casefold())]
        matches = exact or [c for c in companies if query and (query in c["id"].casefold() or query in c["name"].casefold())]
        if not matches:
            raise ValueError(f"No company matches {value!r}.")
        selected.update(c["id"] for c in matches)
    return [c for c in companies if c["id"] in selected]


def feed_request(adapter, cfg, source_url=None):
    """Return a bounded, read-only listing request, or None for an HTML source."""
    if adapter == "amazon":
        parts = urlparse(source_url or "https://www.amazon.jobs/en/search?base_query=software&normalized_country_code[]=IND")
        query = [(key, value) for key, value in parse_qsl(parts.query) if key not in ("offset", "result_limit")]
        query.extend((("offset", "0"), ("result_limit", "100")))
        return "GET", parts._replace(path="/en/search.json", query=urlencode(query), fragment="").geturl(), {}
    if adapter == "eightfold":
        parts = urlparse(source_url)
        filters = dict(parse_qsl(parts.query))
        query = {"domain": cfg["domain"], "start": "0"}
        for key in ("location", "query", "sort_by", "filter_include_remote", "filter_include_relocation"):
            value = cfg.get(key, filters.get(key))
            if value is not None and value != "":
                query[key] = value
        return "GET", parts._replace(netloc=cfg.get("host") or parts.netloc, path="/api/pcsx/search", query=urlencode(query), fragment="").geturl(), {}
    if adapter == "workday":
        return ("POST", f"https://{cfg['host']}/wday/cxs/{cfg['tenant']}/{cfg['site']}/jobs",
                {"json": {"limit": 20, "offset": 0, "appliedFacets": {}, "searchText": ""}})
    if adapter == "greenhouse":
        return "GET", f"https://boards-api.greenhouse.io/v1/boards/{cfg['token']}/jobs?content=true", {}
    if adapter == "lever":
        region = ".eu" if cfg.get("region") == "eu" else ""
        return "GET", f"https://api{region}.lever.co/v0/postings/{cfg['token']}?mode=json&limit=100", {}
    if adapter == "smartrecruiters":
        return "GET", f"https://api.smartrecruiters.com/v1/companies/{cfg['token']}/postings?limit=10&offset=0", {}
    if adapter == "ashby":
        return "GET", f"https://api.ashbyhq.com/posting-api/job-board/{cfg['token']}", {}
    if adapter == "oracle":
        finder = f"findReqs;siteNumber={cfg['site']},keyword=software,limit=25,offset=0,sortBy=POSTING_DATES_DESC"
        return ("GET", f"https://{cfg['host']}/hcmRestApi/resources/latest/recruitingCEJobRequisitions",
                {"params": {"finder": finder, "expand": "requisitionList", "onlyData": "true"}})
    return None


def validate_feed(adapter, data):
    """Validate each adapter's real list schema, including valid empty boards."""
    fields = {
        "workday": ("jobPostings", ("title", "externalPath"), "total"),
        "greenhouse": ("jobs", ("id", "title", "absolute_url"), None),
        "lever": (None, ("id", "text", "hostedUrl"), None),
        "smartrecruiters": ("content", ("id", "name"), "totalFound"),
        "ashby": ("jobs", ("title", "jobUrl"), None),
        "oracle": ("requisitionList", ("Id", "Title"), None),
        "amazon": ("jobs", ("id_icims", "title", "job_path"), "hits"),
        "eightfold": ("positions", ("id", "name"), "count"),
        "goldman": ("items", ("roleId", "jobTitle", "externalSource"), "totalCount"),
    }
    key, required, total_key = fields[adapter]
    container = data
    if adapter == "goldman":
        if not isinstance(data, dict) or data.get("errors") or not isinstance(data.get("data"), dict):
            raise ValueError("Goldman Sachs returned a GraphQL error instead of a jobs listing.")
        container = data["data"].get("roleSearch")
    if adapter == "amazon" and (not isinstance(data, dict) or data.get("error") is not None):
        raise ValueError("Amazon returned a search error instead of a jobs listing.")
    if adapter == "eightfold":
        if not isinstance(data, dict) or data.get("status") != 200 or not isinstance(data.get("data"), dict):
            raise ValueError("Eightfold response is missing its successful data/positions container.")
        container = data["data"]
    if adapter == "oracle":
        if not isinstance(data, dict) or not isinstance(data.get("items"), list) or not data["items"]:
            raise ValueError("Oracle response is missing its items/requisitionList container.")
        container = data["items"][0]
    rows = container if key is None else container.get(key) if isinstance(container, dict) else None
    if not isinstance(rows, list):
        raise ValueError(f"{adapter} response is missing its jobs array ({key or 'root'}).")
    if any(not isinstance(row, dict) or any(row.get(field) in (None, "") for field in required) for row in rows):
        raise ValueError(f"{adapter} job records are missing required fields: {', '.join(required)}.")
    total = None
    if total_key:
        total = container.get(total_key) if isinstance(container, dict) else None
        if type(total) is not int or total < len(rows) or (total and not rows):
            raise ValueError(f"{adapter} response has an invalid {total_key} or an incomplete first page.")
    return len(rows), total


def error_details(exc):
    """Collector wraps HTTP failures; retain their status without bypassing it."""
    details = {"status": "unavailable", "error": str(exc) or type(exc).__name__}
    if "robots.txt" in str(exc) and "restricts automated" in str(exc):
        details["status"] = "restricted"
    cause = exc
    while cause is not None:
        response = getattr(cause, "response", None)
        if response is not None:
            details.update(http_status=response.status_code, url=str(response.url))
            if response.status_code in (401, 403, 429):
                details["status"] = "restricted"
            break
        cause = cause.__cause__
    return details


async def probe_company(company, collector, timeout=45):
    report = {
        "company_id": company["id"], "company": company["name"], "adapter": company["adapter"],
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "portal": {"status": "pending", "url": company["url"]},
        "feed": {"status": "pending"},
        "scope": "Portal reachability and first-page listing schema only; job details and coverage are unverified.",
    }

    async def probe():
        portal_response = None
        try:
            portal_response = await collector.request(company["url"])
            report["portal"] = {"status": "reachable", "http_status": portal_response.status_code, "url": str(portal_response.url)}
        except Exception as exc:
            report["portal"].update(error_details(exc))

        cfg = company["config"]
        cfg = json.loads(cfg) if isinstance(cfg, str) else cfg
        request = feed_request(company["adapter"], cfg, company["url"])
        if company["adapter"] == "goldman":
            from app.goldman import GRAPHQL_URL, goldman_search_payload
            report["feed"]["url"] = GRAPHQL_URL
            try:
                payload = await goldman_search_payload(company, collector=collector)
                response = await collector.request(GRAPHQL_URL, method='POST', json=payload)
                report["feed"].update(http_status=response.status_code, url=str(response.url))
                try:
                    count, total = validate_feed("goldman", response.json())
                except (ValueError, TypeError) as exc:
                    report["feed"].update(status="invalid_schema", error=str(exc))
                    return
                report["feed"].update(status="verified", count=count, total=total)
            except Exception as exc:
                report["feed"].update(error_details(exc))
        elif request:
            method, url, kwargs = request
            report["feed"]["url"] = url
            try:
                if company["adapter"] in ("amazon", "eightfold"):
                    await collector.allowed(url)
                response = await collector.request(url, method=method, **kwargs)
                report["feed"].update(http_status=response.status_code, url=str(response.url))
                try:
                    data = response.json()
                    count, total = validate_feed(company["adapter"], data)
                except (ValueError, TypeError) as exc:
                    report["feed"].update(status="invalid_schema", error=str(exc))
                    return
                report["feed"].update(status="verified", count=count)
                if total is not None:
                    report["feed"]["total"] = total
            except Exception as exc:
                report["feed"].update(error_details(exc))
        elif company["adapter"] in ("atlassian", "google") and portal_response is not None:
            try:
                # A browser portal can answer while prohibiting automated collection.
                await collector.allowed(str(portal_response.url))
                if company["adapter"] == "google":
                    from app.google_careers import google_postings
                    try:
                        rows, total, page_size = google_postings(portal_response.text)
                        if len(rows) != min(total, page_size):
                            raise SourceError("Google returned an incomplete first search page.")
                    except SourceError as exc:
                        report["feed"].update(status="invalid_schema", error=str(exc))
                        return
                    report["feed"] = {"status": "verified", "count": len(rows), "total": total,
                                      "page_size": page_size, "url": str(portal_response.url)}
                else:
                    rows = atlassian_postings(portal_response.text)
                    report["feed"] = {"status": "verified", "count": len(rows), "url": str(portal_response.url)} if rows else {
                        "status": "unverified", "reason": "No embedded Atlassian job listing was readable."}
            except Exception as exc:
                report["feed"].update(error_details(exc))
        else:
            report["feed"] = {"status": "unverified", "reason": cfg.get("manual_reason") or "HTML job extraction was not checked; portal reachability alone does not establish collection."}

    try:
        await asyncio.wait_for(probe(), timeout=timeout)
    except asyncio.TimeoutError:
        for key in ("portal", "feed"):
            if report[key]["status"] == "pending":
                report[key].update(status="timeout", error=f"Company check exceeded {timeout:g} seconds.")
    except Exception as exc:
        report["feed"].update(status="invalid_configuration", error=str(exc) or type(exc).__name__)

    if report["feed"]["status"] == "verified":
        report["outcome"] = "feed_verified"
    elif report["feed"]["status"] not in ("unverified", "pending"):
        report["outcome"] = "feed_unavailable"
    elif report["portal"]["status"] == "reachable":
        report["outcome"] = "collection_unverified"
    else:
        report["outcome"] = "portal_unavailable"
    return report


async def check_companies(companies, concurrency=5, timeout=45, report_file=None):
    gate = asyncio.Semaphore(concurrency)
    async with http_client() as client:
        collector = Collector(client)

        async def one(company):
            async with gate:
                report = await probe_company(company, collector, timeout)
                line = json.dumps(report, ensure_ascii=False)
                print(line, flush=True)
                if report_file is not None:
                    report_file.write(line + "\n")
                    report_file.flush()
                return report

        return await asyncio.gather(*(one(company) for company in companies))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("companies", nargs="*", help="Company IDs, names, or name fragments (default: all).")
    parser.add_argument("--company", action="append", default=[], help="Filter by company ID or name; may be repeated.")
    parser.add_argument("--concurrency", type=int, choices=range(1, 13), default=5, metavar="1-12")
    parser.add_argument("--timeout", type=float, default=45, help="Maximum seconds per company, including retries (default: 45).")
    parser.add_argument("--report", type=Path, help="Also save these JSON lines to this file.")
    args = parser.parse_args(argv)
    if not 0 < args.timeout <= 300:
        parser.error("--timeout must be greater than 0 and no more than 300 seconds.")
    try:
        companies = select_companies(COMPANIES, args.companies + args.company)
    except ValueError as exc:
        parser.error(str(exc))
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        with args.report.open("w", encoding="utf-8") as report_file:
            asyncio.run(check_companies(companies, args.concurrency, args.timeout, report_file))
    else:
        asyncio.run(check_companies(companies, args.concurrency, args.timeout))


if __name__ == "__main__":
    main()

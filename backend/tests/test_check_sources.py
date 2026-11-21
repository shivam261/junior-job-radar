"""A portal response is not proof that its listing feed can be collected."""
import asyncio
import importlib.util
import json
from pathlib import Path

import httpx
import pytest

from app.collectors import Collector

spec = importlib.util.spec_from_file_location("check_sources", Path(__file__).resolve().parents[2] / "scripts" / "check_sources.py")
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


def company(adapter="workday", **config):
    return {"id": "example", "name": "Example", "adapter": adapter,
            "url": "https://example.com/careers", "config": config or {"host": "example.com", "tenant": "example", "site": "External"}}


def test_company_filters_match_ids_names_and_fragments_without_duplicates():
    companies = [company(), dict(company(), id="ion-group", name="ION Group")]
    assert checker.select_companies(companies, ["EXAMPLE", "Example"]) == companies[:1]
    assert checker.select_companies(companies, ["ion"]) == companies[1:]
    with pytest.raises(ValueError, match="No company matches"):
        checker.select_companies(companies, ["no such employer"])


@pytest.mark.parametrize(("adapter", "data", "expected"), [
    ("workday", {"total": 53, "jobPostings": [{"title": "Engineer", "externalPath": "/job/one"}]}, (1, 53)),
    ("greenhouse", {"jobs": []}, (0, None)),
    ("lever", [{"id": "1", "text": "Engineer", "hostedUrl": "https://example.com/1"}], (1, None)),
    ("smartrecruiters", {"totalFound": 12, "content": [{"id": "1", "name": "Engineer"}]}, (1, 12)),
    ("ashby", {"jobs": [{"title": "Engineer", "jobUrl": "https://example.com/1"}]}, (1, None)),
    ("oracle", {"items": [{"requisitionList": [{"Id": "1", "Title": "Engineer"}]}]}, (1, None)),
])
def test_feed_schemas_and_sample_counts(adapter, data, expected):
    assert checker.validate_feed(adapter, data) == expected


@pytest.mark.parametrize(("adapter", "data"), [
    ("workday", {"total": 7, "jobs": []}),
    ("workday", {"total": 7, "jobPostings": []}),
    ("workday", {"total": "0", "jobPostings": []}),
    ("greenhouse", {"jobs": [{"message": "Moved"}]}),
    ("lever", {"message": "not found"}),
    ("smartrecruiters", {"content": [], "totalFound": 1}),
    ("ashby", {"jobs": {}}),
    ("oracle", {"items": []}),
])
def test_rejects_error_json_or_incomplete_listings(adapter, data):
    with pytest.raises(ValueError):
        checker.validate_feed(adapter, data)


@pytest.mark.asyncio
async def test_workday_verifies_real_array_and_separates_browser_portal_failures():
    requests = []

    def respond(request):
        requests.append(request)
        if request.url.path == "/careers":
            return httpx.Response(403, text="Restricted")
        return httpx.Response(200, json={"total": 1, "jobPostings": [{"title": "Engineer", "externalPath": "/job/one"}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        result = await checker.probe_company(company(), Collector(client))
    assert result["portal"]["status"] == "restricted"
    assert result["portal"]["http_status"] == 403
    assert result["feed"]["status"] == "verified"
    assert result["feed"]["count"] == result["feed"]["total"] == 1
    assert result["outcome"] == "feed_verified"
    assert requests[1].method == "POST"
    assert json.loads(requests[1].content)["offset"] == 0
    assert len(requests) == 2  # No details, pagination, or collection side effects.


@pytest.mark.asyncio
async def test_html_http_success_does_not_claim_working_collection():
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, text="<div id='app'></div>"))) as client:
        result = await checker.probe_company(company("html"), Collector(client))
    assert result["portal"]["status"] == "reachable"
    assert result["feed"]["status"] == "unverified"
    assert result["outcome"] == "collection_unverified"


@pytest.mark.asyncio
async def test_json_error_page_is_not_a_working_feed():
    def respond(request):
        return httpx.Response(200, json={"error": "Board moved"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        result = await checker.probe_company(company("greenhouse", token="example"), Collector(client))
    assert result["portal"]["status"] == "reachable"
    assert result["feed"]["status"] == "invalid_schema"
    assert result["outcome"] == "feed_unavailable"


@pytest.mark.asyncio
async def test_redirects_keep_collector_public_url_checks():
    def respond(request):
        return httpx.Response(302, headers={"location": "https://127.0.0.1/private"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        result = await checker.probe_company(company("html"), Collector(client))
    assert result["outcome"] == "portal_unavailable"
    assert "private network" in result["portal"]["error"]


@pytest.mark.asyncio
async def test_timeout_is_bounded_and_retains_a_finished_portal_probe():
    class SlowFeed:
        async def request(self, url, **kwargs):
            if url.endswith("/careers"):
                return httpx.Response(200, request=httpx.Request("GET", url))
            await asyncio.sleep(60)

    result = await checker.probe_company(company(), SlowFeed(), timeout=0.01)
    assert result["portal"]["status"] == "reachable"
    assert result["feed"]["status"] == "timeout"
    assert result["outcome"] == "feed_unavailable"


def test_lever_eu_endpoint_and_oracle_query_are_actual_listing_requests():
    assert checker.feed_request("lever", {"token": "example", "region": "eu"})[1].startswith("https://api.eu.lever.co/")
    method, url, kwargs = checker.feed_request("oracle", {"host": "example.oraclecloud.com", "site": "CX_1"})
    assert method == "GET"
    assert url.endswith("/recruitingCEJobRequisitions")
    assert "siteNumber=CX_1" in kwargs["params"]["finder"]


def test_eightfold_probe_uses_configured_stable_order_and_supported_filters():
    from urllib.parse import parse_qs, urlparse
    _, url, _ = checker.feed_request('eightfold', {'domain': 'qualcomm.com', 'sort_by': 'timestamp'},
                                     'https://careers.qualcomm.com/careers?location=India&pid=42&sort_by=distance')
    assert parse_qs(urlparse(url).query) == {'domain': ['qualcomm.com'], 'start': ['0'], 'location': ['India'], 'sort_by': ['timestamp']}


@pytest.mark.asyncio
async def test_goldman_smoke_uses_public_search_without_collecting_details():
    source = {**company('goldman'), 'url': 'https://higher.gs.com/results?search=software', 'config': {}}
    posted = []

    def respond(request):
        if request.url.path == '/robots.txt':
            return httpx.Response(404)
        if request.method == 'POST':
            posted.append(json.loads(request.content))
            return httpx.Response(200, json={'data': {'roleSearch': {'totalCount': 1, 'items': [
                {'roleId': '42_GS_EARLY_CAREER', 'jobTitle': 'Software Engineer', 'externalSource': {'sourceId': '42'}}]}}})
        return httpx.Response(200, text='<div id="app"></div>')

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        result = await checker.probe_company(source, Collector(client))
    assert result['feed']['status'] == 'verified' and result['feed']['total'] == 1
    assert len(posted) == 1 and 'GetRoles' in posted[0]['query']


@pytest.mark.parametrize('payload', [{'errors': [{'message': 'failed'}], 'data': None}, {'data': {'roleSearch': {'totalCount': 3, 'items': []}}}])
def test_goldman_smoke_rejects_graphql_errors_and_missing_rows(payload):
    with pytest.raises(ValueError):
        checker.validate_feed('goldman', payload)


@pytest.mark.parametrize(("adapter", "data", "expected"), [
    ("amazon", {"error": None, "hits": 3, "jobs": [{"id_icims": "1", "title": "Engineer", "job_path": "/en/jobs/1"}]}, (1, 3)),
    ("eightfold", {"status": 200, "data": {"count": 7, "positions": [{"id": "1", "name": "Engineer"}]}}, (1, 7)),
])
def test_new_listing_schemas(adapter, data, expected):
    assert checker.validate_feed(adapter, data) == expected


@pytest.mark.parametrize(("adapter", "data"), [
    ("amazon", {"error": "invalid filter", "hits": 0, "jobs": []}),
    ("eightfold", {"status": 200, "data": {"count": 7, "positions": []}}),
    ("eightfold", {"status": 404, "data": {"count": 0, "positions": []}}),
])
def test_new_listing_envelopes_reject_false_success(adapter, data):
    with pytest.raises(ValueError):
        checker.validate_feed(adapter, data)


def test_public_search_probes_preserve_filters_and_reset_pagination():
    from urllib.parse import parse_qs, urlparse
    _, url, _ = checker.feed_request("amazon", {}, "https://www.amazon.jobs/en/search?base_query=python&normalized_country_code[]=IND&normalized_country_code[]=USA&offset=200")
    query = parse_qs(urlparse(url).query)
    assert urlparse(url).path == "/en/search.json"
    assert query["base_query"] == ["python"]
    assert query["normalized_country_code[]"] == ["IND", "USA"]
    assert query["offset"] == ["0"]
    _, url, _ = checker.feed_request("eightfold", {"domain": "ericsson.com"}, "https://jobs.ericsson.com/careers?pid=123&location=India&start=20&filter_include_remote=1")
    query = parse_qs(urlparse(url).query)
    assert urlparse(url).path == "/api/pcsx/search"
    assert "pid" not in query
    assert query["start"] == ["0"]
    assert query["domain"] == ["ericsson.com"]
    assert query["location"] == ["India"]
    assert query["filter_include_remote"] == ["1"]


@pytest.mark.asyncio
async def test_manual_source_reason_is_preserved():
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, text="Career page"))) as client:
        result = await checker.probe_company(company("html", manual_reason="This employer links to LinkedIn; no supported public feed."), Collector(client))
    assert result["outcome"] == "collection_unverified"
    assert "LinkedIn" in result["feed"]["reason"]


@pytest.mark.asyncio
async def test_embedded_feed_checks_respect_robots_even_when_portal_answers():
    def respond(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /careers")
        return httpx.Response(200, text="Careers app")

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        result = await checker.probe_company(company("google"), Collector(client))
    assert result["portal"]["status"] == "reachable"
    assert result["feed"]["status"] == "restricted"
    assert result["outcome"] == "feed_unavailable"


@pytest.mark.asyncio
async def test_json_lines_stdout_and_saved_report_match(monkeypatch, capsys):
    import io

    monkeypatch.setattr(checker, "http_client", lambda: httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, text="Career portal"))))
    saved = io.StringIO()
    reports = await checker.check_companies([company("html")], concurrency=1, timeout=2, report_file=saved)
    line = capsys.readouterr().out
    assert line == saved.getvalue()
    assert json.loads(line) == reports[0]
    assert reports[0]["outcome"] == "collection_unverified"


@pytest.mark.asyncio
@pytest.mark.parametrize(("total", "status"), [(0, "verified"), (3, "invalid_schema")])
async def test_embedded_google_feed_distinguishes_empty_board_from_incomplete_page(total, status):
    def respond(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /")
        html = "<script>AF_initDataCallback({key:'ds:1',data:" + json.dumps([[], None, total, 20]) + ",sideChannel:{}});</script>"
        return httpx.Response(200, text=html)

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        result = await checker.probe_company(company("google"), Collector(client))
    assert result["feed"]["status"] == status

import json

import httpx
import pytest

from app.collectors import Collector, SourceError
from app.google_careers import collect_google, google_postings


def posting(identity='123', title='Software Engineer II', qualifications='2 years of software development experience.'):
    row = [None] * 21
    row[0], row[1] = identity, title
    row[2] = 'https://www.google.com/about/careers/applications/signin?jobId=private-application-link'
    row[3] = [None, '<p>Build and test Python services.</p>']
    row[4] = [None, '<h3>Minimum qualifications:</h3><p>' + qualifications + '</p>']
    row[9] = [['Bengaluru, Karnataka, India'], ['Hyderabad, Telangana, India']]
    row[10] = [None, '<p>Develop Google software.</p>']
    row[12] = [1791821336, 572000000]
    return row


def embedded(rows, total=None, size=2):
    data = [rows, None, len(rows or []) if total is None else total, size]
    return '<script>AF_initDataCallback({key: \'ds:1\', hash: \'2\', data:' + json.dumps(data) + ', sideChannel: {}});</script>'


COMPANY = {'id': 'google', 'url': 'https://www.google.com/about/careers/applications/jobs/results/?location=India&company=Google&company=YouTube&page=4', 'config': {}}


def test_google_data_is_read_as_json_and_accepts_explicit_empty_results():
    row = posting()
    row[10][1] = '<p>Text with } and data: and AF_initDataCallback() stays data.</p>'
    assert google_postings(embedded([row])) == ([row], 1, 2)
    assert google_postings(embedded(None, total=0)) == ([], 0, 2)
    with pytest.raises(SourceError):
        google_postings('<script>AF_initDataCallback({key: \'ds:1\', data:dangerousFunction()});</script>')


@pytest.mark.parametrize('html', [
    '<h1>Sign in to Google Careers</h1>',
    embedded(None, total=5),
    embedded([['123', 'Software Engineer']]),
    embedded([posting(identity='https://invalid.example')]),
    embedded([posting()], total=-1),
    embedded([posting()], size=0),
])
def test_google_missing_or_changed_schema_fails_closed(html):
    with pytest.raises(SourceError):
        google_postings(html)


@pytest.mark.asyncio
async def test_google_paginates_preserves_filters_and_reads_full_postings():
    requests = []
    pages = {
        '1': embedded([posting(), posting('124', 'Senior Software Engineer')], total=3),
        '2': embedded([posting('125', qualifications='5 years of software development experience.')], total=3),
    }
    def respond(request):
        requests.append(request)
        if request.url.path == '/robots.txt':
            return httpx.Response(200, text='User-agent: *\nAllow: /')
        assert request.url.params.get_list('company') == ['Google', 'YouTube']
        assert request.url.params['location'] == 'India'
        return httpx.Response(200, text=pages[request.url.params.get('page', '1')])
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        result = await collect_google(Collector(client), COMPANY, {})
    assert not result.complete  # The India/Google/YouTube filters are a partial board.
    assert result.source_ids == {'123', '124', '125'}
    assert len(result.jobs) == 1
    job = result.jobs[0]
    assert job['url'] == 'https://www.google.com/about/careers/applications/jobs/results/123/'
    assert job['location'] == 'Bengaluru, Karnataka, India · Hyderabad, Telangana, India'
    assert job['posted_at'] == '2026-10-12T16:08:56+00:00'
    assert job['skills'] == ['Python']
    assert job['employment_type'] == 'Not specified'
    assert sum(request.url.path == '/robots.txt' for request in requests) == 1
    assert 'page' not in requests[1].url.params


@pytest.mark.asyncio
@pytest.mark.parametrize('second', [
    embedded([posting()], total=3),  # Repeated page ID.
    embedded([], total=3),  # Missing final row.
    embedded([posting('125')], total=4),  # Changing result count.
])
async def test_google_incomplete_or_repeated_pagination_retains_old_jobs(second):
    def respond(request):
        if request.url.path == '/robots.txt':
            return httpx.Response(200, text='User-agent: *\nAllow: /')
        html = embedded([posting(), posting('124')], total=3) if request.url.params.get('page', '1') == '1' else second
        return httpx.Response(200, text=html)
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(SourceError):
            await collect_google(Collector(client), COMPANY, {})


@pytest.mark.asyncio
async def test_google_safety_cap_marks_snapshot_partial(monkeypatch):
    monkeypatch.setattr('app.collectors.MAX_PAGES', 1)
    def respond(request):
        if request.url.path == '/robots.txt':
            return httpx.Response(200, text='User-agent: *\nAllow: /')
        return httpx.Response(200, text=embedded([posting(), posting('124')], total=3))
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        result = await collect_google(Collector(client), COMPANY, {})
    assert not result.complete
    assert result.source_ids == {'123', '124'}
    assert 'safety limit' in result.warning


@pytest.mark.asyncio
async def test_google_obeys_robots_before_reading_pages():
    paths = []
    def respond(request):
        paths.append(request.url.path)
        return httpx.Response(200, text='User-agent: *\nDisallow: /about/careers/')
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(SourceError, match='robots.txt'):
            await collect_google(Collector(client), COMPANY, {})
    assert paths == ['/robots.txt']


@pytest.mark.asyncio
async def test_google_retains_first_page_when_robots_disallows_pagination():
    requests = []
    def respond(request):
        requests.append(request)
        if request.url.path == '/robots.txt':
            return httpx.Response(200, text='User-agent: *\nDisallow: /about/careers/applications/jobs/results/?*&page=')
        assert 'page' not in request.url.params
        return httpx.Response(200, text=embedded([posting(), posting('124')], total=3))
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        result = await collect_google(Collector(client), COMPANY, {})
    assert len(result.jobs) == 2
    assert result.source_ids == {'123', '124'}
    assert not result.complete
    assert 'restricts automated pagination' in result.warning
    assert len(requests) == 2


@pytest.mark.asyncio
async def test_google_explicit_empty_unfiltered_board_is_complete():
    def respond(request):
        if request.url.path == '/robots.txt':
            return httpx.Response(200, text='User-agent: *\nAllow: /')
        return httpx.Response(200, text=embedded(None, total=0))
    company = dict(COMPANY, url='https://www.google.com/about/careers/applications/jobs/results/')
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        result = await collect_google(Collector(client), company, {})
    assert result.complete
    assert result.jobs == []
    assert result.source_ids == set()

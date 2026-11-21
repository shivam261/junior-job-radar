import httpx
import pytest

from app.collectors import Collector, SourceError
from app.eightfold import collect_eightfold


def company(url='https://careers.example.com/careers'):
    return {'id': 'example', 'name': 'Example', 'url': url}


def listing(identity, title='Software Engineer I'):
    return {'id': identity, 'name': title, 'locations': ['Bengaluru, India'],
            'positionUrl': f'/careers/job/{identity}', 'atsJobId': f'REQ-{identity}'}


def details(identity):
    return {'status': 200, 'data': {**listing(identity),
            'jobDescription': '<p>Required: 1–2 years of professional experience. Python.</p>',
            'postedTs': 1767225600, 'workLocationOption': 'hybrid'}}


@pytest.mark.asyncio
async def test_eightfold_paginates_and_reads_full_job_details():
    requests = []

    def response(request):
        requests.append(request)
        if request.url.path == '/robots.txt':
            return httpx.Response(200, text='User-agent: *\nAllow: /')
        if request.url.path.endswith('/search'):
            start = int(request.url.params['start'])
            rows = [listing(11), listing(12, 'Product Manager')] if start == 0 else [listing(13)]
            return httpx.Response(200, json={'status': 200, 'data': {'positions': rows, 'count': 3}})
        return httpx.Response(200, json=details(int(request.url.params['position_id'])))

    async with httpx.AsyncClient(transport=httpx.MockTransport(response)) as client:
        snapshot = await collect_eightfold(Collector(client), company(), {'domain': 'example.com'})
    assert snapshot.complete
    assert [job['source_id'] for job in snapshot.jobs] == ['11', '13']
    assert snapshot.source_ids == {'11', '12', '13', 'REQ-11', 'REQ-12', 'REQ-13'}
    assert snapshot.jobs[0]['url'] == 'https://careers.example.com/careers/job/11'
    assert snapshot.jobs[0]['posted_at'] == '2026-01-01T00:00:00+00:00'
    assert snapshot.jobs[0]['work_mode'] == 'Hybrid'
    assert snapshot.jobs[0]['skills'] == ['Python']
    assert [r.url.params['start'] for r in requests if r.url.path.endswith('/search')] == ['0', '2']
    assert len([r for r in requests if r.url.path.endswith('/position_details')]) == 2


@pytest.mark.asyncio
async def test_eightfold_preserves_search_filters_and_does_not_expire_global_jobs():
    def response(request):
        if request.url.path == '/robots.txt':
            return httpx.Response(200, text='User-agent: *\nAllow: /')
        assert dict(request.url.params) == {'domain': 'example.com', 'location': 'India',
                                           'filter_include_remote': '1', 'start': '0'}
        return httpx.Response(200, json={'data': {'positions': [], 'count': 0}})

    source = company('https://careers.example.com/careers?location=India&pid=99&filter_include_remote=1')
    async with httpx.AsyncClient(transport=httpx.MockTransport(response)) as client:
        snapshot = await collect_eightfold(Collector(client), source, {'domain': 'example.com'})
    assert not snapshot.complete
    assert snapshot.jobs == []


@pytest.mark.parametrize('data', [
    {'positions': [], 'count': 2},
    {'positions': 'changed', 'count': 2},
    {'positions': [], 'count': '0'},
    {'positions': [{'name': 'Software Engineer'}], 'count': 1},
])
@pytest.mark.asyncio
async def test_eightfold_rejects_incomplete_or_changed_search_results(data):
    def response(request):
        if request.url.path == '/robots.txt':
            return httpx.Response(200, text='User-agent: *\nAllow: /')
        return httpx.Response(200, json={'status': 200, 'data': data})

    async with httpx.AsyncClient(transport=httpx.MockTransport(response)) as client:
        with pytest.raises(SourceError):
            await collect_eightfold(Collector(client), company(), {'domain': 'example.com'})


@pytest.mark.asyncio
async def test_eightfold_repeated_pagination_is_not_complete_success():
    def response(request):
        if request.url.path == '/robots.txt':
            return httpx.Response(200, text='User-agent: *\nAllow: /')
        return httpx.Response(200, json={'data': {'positions': [listing(11)], 'count': 2}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(response)) as client:
        with pytest.raises(SourceError, match='repeated'):
            await collect_eightfold(Collector(client), company(), {'domain': 'example.com'})


@pytest.mark.asyncio
async def test_eightfold_deduplicates_overlapping_pages_and_retains_earlier_jobs():
    def response(request):
        if request.url.path == '/robots.txt':
            return httpx.Response(200, text='User-agent: *\nAllow: /')
        if request.url.path.endswith('/search'):
            rows = [listing(11), listing(12)] if request.url.params['start'] == '0' else [listing(12), listing(13)]
            return httpx.Response(200, json={'data': {'positions': rows, 'count': 4}})
        return httpx.Response(200, json=details(int(request.url.params['position_id'])))

    async with httpx.AsyncClient(transport=httpx.MockTransport(response)) as client:
        snapshot = await collect_eightfold(Collector(client), company(), {'domain': 'example.com'})
    assert not snapshot.complete
    assert [job['source_id'] for job in snapshot.jobs] == ['11', '12', '13']
    assert 'overlapped 1' in snapshot.warning


@pytest.mark.asyncio
async def test_eightfold_retains_other_jobs_when_one_detail_fails():
    def response(request):
        if request.url.path == '/robots.txt':
            return httpx.Response(200, text='User-agent: *\nAllow: /')
        if request.url.path.endswith('/search'):
            return httpx.Response(200, json={'data': {'positions': [listing(11), listing(12)], 'count': 2}})
        if request.url.params['position_id'] == '12':
            return httpx.Response(404, json={'status': 404, 'data': {}})
        return httpx.Response(200, json=details(11))

    async with httpx.AsyncClient(transport=httpx.MockTransport(response)) as client:
        snapshot = await collect_eightfold(Collector(client), company(), {'domain': 'example.com'})
    assert not snapshot.complete
    assert len(snapshot.jobs) == 1
    assert '1 of 2' in snapshot.warning


@pytest.mark.asyncio
async def test_eightfold_robot_restrictions_are_respected():
    def response(request):
        assert request.url.path == '/robots.txt'
        return httpx.Response(200, text='User-agent: *\nDisallow: /api/')

    async with httpx.AsyncClient(transport=httpx.MockTransport(response)) as client:
        with pytest.raises(SourceError, match='robots.txt'):
            await collect_eightfold(Collector(client), company(), {'domain': 'example.com'})

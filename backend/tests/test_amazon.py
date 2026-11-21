import json

import httpx
import pytest

from app.collectors import Collector, SourceError
from app.companies import COMPANIES


COMPANY = next(c for c in COMPANIES if c['id'] == 'amazon')


def posting(identity='42', qualifications='1–2 years of experience.', **overrides):
    return dict(id_icims=identity, title='Software Engineer I', job_path='/en/jobs/' + identity + '/software-engineer',
                description='Build services with Python.', basic_qualifications=qualifications,
                preferred_qualifications='', normalized_location='Bengaluru, Karnataka, IND',
                posted_date='October 18, 2026', job_schedule_type='full-time', **overrides)


@pytest.mark.asyncio
async def test_search_pagination_keeps_country_filters_and_full_qualifications():
    requests = []

    def respond(request):
        if request.url.path == '/robots.txt':
            return httpx.Response(200, text='User-agent: *\nAllow: /')
        requests.append(request)
        assert request.url.params['normalized_country_code[]'] == 'IND'
        offset = int(request.url.params['offset'])
        return httpx.Response(200, json={'hits': 2, 'error': None, 'jobs': [posting()] if offset == 0 else [posting('43', '4+ years of experience.')]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        snapshot = await Collector(client).collect(COMPANY)
    assert not snapshot.complete and snapshot.source_ids == {'42', '43'}
    assert len(requests) == 2 and len(snapshot.jobs) == 1
    job = snapshot.jobs[0]
    assert job['url'] == 'https://www.amazon.jobs/en/jobs/42/software-engineer'
    assert job['posted_at'] == '2026-10-18T00:00:00+00:00'
    assert job['confidence'] == 'confirmed' and job['skills'] == ['Python']


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', ['repeat', 'empty', 'error', 'qualifications', 'invalid-link'])
async def test_changed_or_incomplete_feeds_cannot_become_empty_success(failure):
    def respond(request):
        if request.url.path == '/robots.txt':
            return httpx.Response(200, text='User-agent: *\nAllow: /')
        offset = int(request.url.params['offset'])
        row = posting()
        if failure == 'qualifications':
            row['basic_qualifications'] = ''
        if failure == 'invalid-link':
            row['job_path'] = 'https://other.example/jobs/42'
        rows = [] if failure == 'empty' and offset else [row]
        return httpx.Response(200, json={'hits': 2, 'jobs': rows, 'error': 'Unavailable' if failure == 'error' else None})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(SourceError):
            await Collector(client).collect(COMPANY)


@pytest.mark.asyncio
async def test_empty_search_is_partial_and_page_cap_keeps_matches(monkeypatch):
    monkeypatch.setattr('app.collectors.MAX_PAGES', 1)

    def respond(request):
        if request.url.path == '/robots.txt':
            return httpx.Response(200, text='User-agent: *\nAllow: /')
        return httpx.Response(200, json={'hits': 200, 'jobs': [posting()]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        snapshot = await Collector(client).collect(COMPANY)
    assert not snapshot.complete and len(snapshot.jobs) == 1


@pytest.mark.asyncio
async def test_robots_disallow_prevents_feed_request():
    requested = []

    def respond(request):
        requested.append(request.url.path)
        return httpx.Response(200, text='User-agent: *\nDisallow: /en/search')

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(SourceError, match='robots.txt'):
            await Collector(client).collect(COMPANY)
    assert requested == ['/robots.txt']

import json

import httpx
import pytest

from app.collectors import Collector, SourceError
from app.goldman import collect_goldman


SOURCE = {'id': 'goldman-sachs', 'name': 'Goldman Sachs', 'url':
          'https://higher.gs.com/results?EXPERIENCE_LEVEL=Analyst&LOCATION=Bengaluru%7CMumbai%7CHyderabad&page=1&search=software&sort=RELEVANCE'}


def node(value, children=None):
    return {'filter': value, 'subFilters': children or []}


METADATA = [
    {'filterCategoryType': {'code': 'EXPERIENCE_LEVEL'}, 'filters': [node('Analyst'), node('Associate')]},
    {'filterCategoryType': {'code': 'LOCATION'}, 'filters': [node('India', [
        node('Karnataka', [node('Bengaluru')]), node('Maharashtra', [node('Mumbai')]),
        node('Telangana', [node('Hyderabad')]), node('Delhi', [node('New Delhi')])])]},
]


def role(identity='100', title='Software Engineer I'):
    return {'roleId': identity + '_GS_EARLY_CAREER', 'jobTitle': title, 'corporateTitle': 'Analyst',
            'status': 'POSTED', 'externalSource': {'sourceId': identity},
            'locations': [{'city': 'Hyderabad', 'state': 'Telangana', 'country': 'India'}]}


def detail(identity='100'):
    return {**role(identity), 'descriptionHtml': '<p>1–2 years of software development experience. Java.</p>',
            'applyActive': True, 'jobType': {'description': 'Full time'}}


@pytest.mark.asyncio
async def test_goldman_uses_exact_url_filters_and_public_full_descriptions():
    searches = []

    def response(request):
        if request.url.path == '/robots.txt':
            if request.url.host == 'higher.gs.com':
                return httpx.Response(200, text='User-agent: *\nAllow: /roles/\nDisallow: /')
            return httpx.Response(404)
        assert request.url.host == 'api-higher.gs.com'
        assert request.method == 'POST'
        payload = json.loads(request.content)
        if 'GetRoleFilters' in payload['query']:
            return httpx.Response(200, json={'data': {'roleSearchFilters': METADATA}})
        if 'GetRoles' in payload['query']:
            searches.append(payload['variables']['searchQueryInput'])
            return httpx.Response(200, json={'data': {'roleSearch': {'totalCount': 1, 'items': [role()]}}})
        assert payload['variables'] == {'externalSourceId': '100', 'externalSourceFetch': True}
        return httpx.Response(200, json={'data': {'role': detail()}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(response)) as client:
        snapshot = await collect_goldman(Collector(client), SOURCE, {})
    assert not snapshot.complete
    assert len(snapshot.jobs) == 1
    assert snapshot.jobs[0]['url'] == 'https://higher.gs.com/roles/100'
    assert snapshot.jobs[0]['experience_min'] == 1
    assert snapshot.jobs[0]['skills'] == ['Java']
    assert searches[0]['searchTerm'] == 'software'
    assert searches[0]['sort'] == {'sortStrategy': 'RELEVANCE', 'sortOrder': 'DESC'}
    assert searches[0]['filters'] == [
        {'filterCategoryType': 'EXPERIENCE_LEVEL', 'filters': [node('Analyst')]},
        {'filterCategoryType': 'LOCATION', 'filters': [node('India', [
            node('Karnataka', [node('Bengaluru')]), node('Maharashtra', [node('Mumbai')]),
            node('Telangana', [node('Hyderabad')])])]},
    ]


@pytest.mark.asyncio
async def test_goldman_does_not_silently_drop_unknown_location_filters():
    source = {**SOURCE, 'url': SOURCE['url'].replace('Mumbai', 'UnknownCity')}

    def response(request):
        if request.url.path == '/robots.txt':
            return httpx.Response(404)
        assert 'GetRoleFilters' in json.loads(request.content)['query']
        return httpx.Response(200, json={'data': {'roleSearchFilters': METADATA}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(response)) as client:
        with pytest.raises(SourceError, match='requested LOCATION'):
            await collect_goldman(Collector(client), source, {})


@pytest.mark.asyncio
async def test_goldman_paginates_before_declaring_a_filtered_snapshot():
    pages = []
    source = {**SOURCE, 'url': 'https://higher.gs.com/results?search=software'}

    def response(request):
        if request.url.path == '/robots.txt':
            return httpx.Response(404)
        payload = json.loads(request.content)
        page = payload['variables']['searchQueryInput']['page']
        pages.append(page['pageNumber'])
        rows = [role(str(i), 'Product Manager') for i in range(20)] if page['pageNumber'] == 0 else [role('20', 'Product Manager')]
        return httpx.Response(200, json={'data': {'roleSearch': {'totalCount': 21, 'items': rows}}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(response)) as client:
        snapshot = await collect_goldman(Collector(client), source, {})
    assert pages == [0, 1]
    assert len(snapshot.source_ids) == 42
    assert snapshot.jobs == []


@pytest.mark.parametrize('payload', [
    {'errors': [{'message': 'Search unavailable'}], 'data': None},
    {'data': {'roleSearch': {'totalCount': 2, 'items': []}}},
])
@pytest.mark.asyncio
async def test_goldman_api_failure_is_not_empty_success(payload):
    source = {**SOURCE, 'url': 'https://higher.gs.com/results?search=software'}

    def response(request):
        return httpx.Response(404) if request.url.path == '/robots.txt' else httpx.Response(200, json=payload)

    async with httpx.AsyncClient(transport=httpx.MockTransport(response)) as client:
        with pytest.raises(SourceError):
            await collect_goldman(Collector(client), source, {})


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', ['missing', 'locations', 'jobType', 'jobTitle'])
async def test_goldman_failed_details_do_not_discard_other_valid_jobs(failure):
    source = {**SOURCE, 'url': 'https://higher.gs.com/results?search=software'}

    def response(request):
        if request.url.path == '/robots.txt':
            return httpx.Response(404)
        payload = json.loads(request.content)
        if 'GetRoles' in payload['query']:
            return httpx.Response(200, json={'data': {'roleSearch': {'totalCount': 2, 'items': [role(), role('101')]}}})
        if payload['variables']['externalSourceId'] == '101':
            malformed = None if failure == 'missing' else detail('101')
            if malformed is not None:
                malformed[failure] = [None] if failure == 'locations' else 42
            return httpx.Response(200, json={'data': {'role': malformed}})
        return httpx.Response(200, json={'data': {'role': detail()}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(response)) as client:
        snapshot = await collect_goldman(Collector(client), source, {})
    assert len(snapshot.jobs) == 1
    assert '1 of 2' in snapshot.warning

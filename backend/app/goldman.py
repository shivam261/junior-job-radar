"""Goldman Sachs' public role search, preserving the official URL's filters."""
import asyncio
from urllib.parse import parse_qs, quote, urlparse

from .matching import software_title
from .sources import InvalidSource

GRAPHQL_URL = 'https://api-higher.gs.com/gateway/api/v1/graphql'
PORTAL = 'https://higher.gs.com'
EXPERIENCES = ['EARLY_CAREER', 'PROFESSIONAL']
FILTER_QUERY = '''query GetRoleFilters($filterCategories: [RoleSearchFilterCategoryType!], $experiences: [RoleSearchExperience!]!) {
  roleSearchFilters(categories: $filterCategories, experiences: $experiences) {
    filterCategoryType { code }
    filters { filter subFilters { filter subFilters { filter subFilters { filter } } } }
  }
}'''
SEARCH_QUERY = '''query GetRoles($searchQueryInput: RoleSearchQueryInput!) {
  roleSearch(searchQueryInput: $searchQueryInput) {
    totalCount items { roleId jobTitle corporateTitle status locations { city state country }
      externalSource { sourceId } }
  }
}'''
DETAIL_QUERY = '''query GetRoleById($externalSourceId: String!, $externalSourceFetch: Boolean) {
  role(externalSourceId: $externalSourceId, externalSourceFetch: $externalSourceFetch) {
    roleId jobTitle descriptionHtml status applyActive locations { city state country }
    jobType { description } externalSource { sourceId }
  }
}'''


def selected_filters(nodes, wanted, matched):
    """Retain matching leaves and their actual ancestors from the live board."""
    selected = []
    for node in nodes:
        value = node['filter']
        children = selected_filters(node.get('subFilters') or [], wanted, matched)
        if value in wanted:
            matched.add(value)
            # A selected parent means its whole geographic branch, as in the UI.
            children = []
        if value in wanted or children:
            selected.append({'filter': value, 'subFilters': children})
    return selected


async def goldman_graphql(collector, operation, variables):
    from .collectors import SourceError

    payload = await collector.json(GRAPHQL_URL, method='POST', json={'query': operation, 'variables': variables})
    if not isinstance(payload, dict) or payload.get('errors') or not isinstance(payload.get('data'), dict):
        raise SourceError('Goldman Sachs public jobs API did not return usable data. Earlier jobs were retained.')
    return payload['data']


async def goldman_search_payload(company, page_number=0, page_size=20, *, collector):
    """Prepare a public search request after resolving every requested filter."""
    from .collectors import SourceError

    query = parse_qs(urlparse(company['url']).query)
    categories = ('EXPERIENCE_LEVEL', 'LOCATION')
    unsupported = set(query) - {*categories, 'page', 'search', 'sort'}
    if unsupported:
        raise SourceError('Goldman Sachs search contains unsupported filters: ' + ', '.join(sorted(unsupported)))
    sort = query.get('sort', ['RELEVANCE'])[0]
    if sort not in ('RELEVANCE', 'POSTED_DATE'):
        raise SourceError('Goldman Sachs returned an unsupported search order.')
    await collector.allowed(GRAPHQL_URL)

    wanted = {key: {value for item in query.get(key, []) for value in item.split('|') if value}
              for key in categories if query.get(key)}
    filters = []
    if wanted:
        data = await goldman_graphql(collector, FILTER_QUERY, {'filterCategories': list(wanted), 'experiences': EXPERIENCES})
        metadata = data.get('roleSearchFilters')
        if not isinstance(metadata, list):
            raise SourceError('Goldman Sachs did not expose its current search filters.')
        found_categories = set()
        try:
            for category in metadata:
                code = category['filterCategoryType']['code']
                if code not in wanted:
                    continue
                matched = set()
                values = selected_filters(category['filters'], wanted[code], matched)
                if matched != wanted[code]:
                    raise SourceError('Goldman Sachs no longer offers a requested ' + code + ' filter. Earlier jobs were retained.')
                found_categories.add(code)
                filters.append({'filterCategoryType': code, 'filters': values})
        except (KeyError, TypeError) as exc:
            raise SourceError('Goldman Sachs search filter format changed.') from exc
        if found_categories != set(wanted):
            raise SourceError('Goldman Sachs did not expose every requested search filter.')
    return {'query': SEARCH_QUERY, 'variables': {'searchQueryInput': {
        'page': {'pageSize': page_size, 'pageNumber': page_number},
        'sort': {'sortStrategy': sort, 'sortOrder': 'DESC'}, 'filters': filters,
        'experiences': EXPERIENCES, 'searchTerm': query.get('search', [''])[0]}}}


async def collect_goldman(collector, company, config):
    from .collectors import MAX_PAGES, Snapshot, SourceError, normalize

    payload = await goldman_search_payload(company, collector=collector)
    rows, seen, source_ids = [], set(), set()
    for page in range(MAX_PAGES):
        payload['variables']['searchQueryInput']['page']['pageNumber'] = page
        data = await goldman_graphql(collector, payload['query'], payload['variables'])
        search = data.get('roleSearch')
        if not isinstance(search, dict) or not isinstance(search.get('items'), list) or type(search.get('totalCount')) is not int:
            raise SourceError('Goldman Sachs job search format changed; earlier jobs were retained.')
        items, count = search['items'], search['totalCount']
        if count < 0 or (not items and page * 20 < count):
            raise SourceError('Goldman Sachs returned an incomplete search page; earlier jobs were retained.')
        for row in items:
            identity = row.get('roleId') if isinstance(row, dict) else None
            external = row.get('externalSource') if isinstance(row, dict) else None
            source_id = external.get('sourceId') if isinstance(external, dict) else None
            if not identity or not source_id or not isinstance(row.get('jobTitle'), str):
                raise SourceError('Goldman Sachs returned an invalid role record.')
            if identity in seen:
                raise SourceError('Goldman Sachs pagination repeated jobs; earlier jobs were retained.')
            seen.add(identity)
            source_ids.update((str(identity), str(source_id)))
            if software_title(row['jobTitle']):
                rows.append(row)
        if (page + 1) * 20 >= count:
            break
        if len(items) < 20:
            raise SourceError('Goldman Sachs returned an incomplete search page; earlier jobs were retained.')

    gate = asyncio.Semaphore(3)

    async def detail(row):
        async with gate:
            source_id = str(row['externalSource']['sourceId'])
            url = PORTAL + '/roles/' + quote(source_id, safe='')
            await collector.allowed(url)
            data = await goldman_graphql(collector, DETAIL_QUERY, {'externalSourceId': source_id, 'externalSourceFetch': True})
            role = data.get('role')
            if (not isinstance(role, dict) or role.get('roleId') != row['roleId']
                    or not isinstance(role.get('descriptionHtml'), str) or not role['descriptionHtml'].strip()):
                raise SourceError('A Goldman Sachs job detail was unavailable; earlier jobs were retained.')
            if role.get('applyActive') is False or role.get('status') not in ('POSTED', 'OPEN'):
                return None
            locations = role.get('locations') or row.get('locations') or []
            title = role.get('jobTitle') or row['jobTitle']
            job_type = role.get('jobType')
            if (not isinstance(title, str) or not title.strip()
                    or not isinstance(locations, list)
                    or any(not isinstance(place, dict) or any(
                        place.get(key) is not None and not isinstance(place[key], str)
                        for key in ('city', 'state', 'country')) for place in locations)
                    or (job_type is not None and not isinstance(job_type, dict))):
                raise SourceError('A Goldman Sachs job detail had unreadable metadata; earlier jobs were retained.')
            location = ' · '.join(', '.join(str(place[key]) for key in ('city', 'state', 'country') if place.get(key))
                                  for place in locations)
            kind = (job_type or {}).get('description')
            return normalize(company, row['roleId'], title, location,
                             role['descriptionHtml'], url, employment_type=kind)

    results = await asyncio.gather(*(detail(row) for row in rows), return_exceptions=True)
    jobs, failures = [], []
    for row, result in zip(rows, results):
        if isinstance(result, (SourceError, InvalidSource)):
            failures.append(f"Job {row['roleId']}: {result}")
        elif isinstance(result, BaseException):
            raise result
        elif result:
            jobs.append(result)
    warning = None
    if failures:
        warning = (f'Goldman Sachs: {len(failures)} of {len(rows)} candidate job details could not be read. '
                   f'Earlier jobs were retained. {failures[0]}')
        if len(failures) == len(rows):
            raise SourceError(warning)
    # The portal searches experienced/early-career roles with URL filters.
    return Snapshot(jobs, complete=False, source_ids=source_ids, warning=warning)

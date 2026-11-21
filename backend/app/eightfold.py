"""Read the public Eightfold search and position-detail APIs used by careers pages."""
import asyncio
from datetime import datetime, timezone
from urllib.parse import parse_qs, urljoin, urlparse

from .matching import software_title
from .sources import InvalidSource, public_url


async def collect_eightfold(collector, company, config):
    # Import lazily so Collector can delegate here without a circular import.
    from .collectors import MAX_PAGES, Snapshot, SourceError, normalize

    source = urlparse(company['url'])
    root = public_url('https://' + (config.get('host') or source.netloc))
    domain = config.get('domain')
    if not isinstance(domain, str) or not domain.strip():
        raise SourceError('The Eightfold careers source needs an employer domain.')
    query = parse_qs(source.query)
    params = {'domain': domain}
    # A selected job (pid) is a UI detail, not a search constraint. Keep the
    # employer's useful search filters while collecting every page of results.
    filter_keys = ('location', 'query', 'sort_by', 'filter_include_remote', 'filter_include_relocation')
    for key in filter_keys:
        value = config.get(key, query.get(key, [''])[0])
        if value != '' and value is not None:
            params[key] = value
    scoped = any(params.get(key) for key in ('location', 'query'))
    search_url = root + '/api/pcsx/search'
    await collector.allowed(search_url)
    rows, seen, source_ids, offset, complete = [], set(), set(), 0, not scoped
    overlaps = 0
    for _ in range(MAX_PAGES):
        payload = await collector.json(search_url, params={**params, 'start': offset})
        data = payload.get('data') if isinstance(payload, dict) else None
        if not isinstance(data, dict) or payload.get('status', 200) != 200:
            raise SourceError('Eightfold did not return a public job search response.')
        page, count = data.get('positions'), data.get('count')
        if not isinstance(page, list) or type(count) is not int or count < 0:
            raise SourceError('Eightfold job search format changed; earlier jobs were retained.')
        if not page and offset < count:
            raise SourceError('Eightfold returned an incomplete search page; earlier jobs were retained.')
        new_rows = 0
        for row in page:
            if not isinstance(row, dict) or not row.get('id') or not isinstance(row.get('name'), str):
                raise SourceError('Eightfold returned an invalid job record; earlier jobs were retained.')
            identity = str(row['id'])
            if identity in seen:
                # The live board can move a posting between pages while a
                # snapshot is being read. Keep unique jobs, but never expire
                # earlier results from an overlapping snapshot.
                overlaps += 1
                complete = False
                continue
            new_rows += 1
            seen.add(identity)
            source_ids.add(identity)
            source_ids.update(str(row[key]) for key in ('atsJobId', 'displayJobId') if row.get(key))
            if software_title(row['name']):
                rows.append(row)
        if page and not new_rows:
            raise SourceError('Eightfold pagination repeated jobs; earlier jobs were retained.')
        offset += len(page)
        if offset >= count:
            break
    else:
        complete = False

    gate = asyncio.Semaphore(3)

    async def detail(row):
        async with gate:
            detail_url = root + '/api/pcsx/position_details'
            await collector.allowed(detail_url)
            payload = await collector.json(detail_url, params={'domain': domain, 'position_id': row['id']})
            data = payload.get('data') if isinstance(payload, dict) else None
            if (not isinstance(data, dict) or payload.get('status', 200) != 200
                    or str(data.get('id')) != str(row['id'])
                    or not isinstance(data.get('jobDescription'), str) or not data['jobDescription'].strip()):
                raise SourceError('An Eightfold job detail was unavailable; earlier jobs were retained.')
            path = data.get('positionUrl') or row.get('positionUrl') or '/careers/job/' + str(row['id'])
            url = public_url(urljoin(root, path))
            # Keep application links on the verified employer careers portal.
            if urlparse(url).netloc != urlparse(root).netloc:
                raise SourceError('Eightfold returned an unexpected job detail URL.')
            locations = data.get('locations') or row.get('locations') or []
            if isinstance(locations, str):
                locations = [locations]
            location = ' · '.join(str(value) for value in locations if value)
            mode = data.get('workLocationOption') or row.get('workLocationOption')
            if mode and mode.lower() in ('remote', 'hybrid'):
                location = ' · '.join(filter(None, (location, mode.title())))
            posted = data.get('postedTs', row.get('postedTs'))
            try:
                posted = datetime.fromtimestamp(posted, timezone.utc).isoformat() if posted else None
            except (TypeError, ValueError, OverflowError, OSError):
                posted = None
            return normalize(company, row['id'], data.get('name') or row['name'], location,
                             data['jobDescription'], url, posted)

    results = await asyncio.gather(*(detail(row) for row in rows), return_exceptions=True)
    jobs, failures = [], []
    for row, result in zip(rows, results):
        if isinstance(result, (SourceError, InvalidSource)):
            failures.append(f"Job {row['id']}: {result}")
        elif isinstance(result, BaseException):
            raise result
        elif result:
            jobs.append(result)
    warnings = []
    if overlaps:
        warnings.append(f'Eightfold search pages overlapped {overlaps} job records. Earlier jobs were retained.')
    if failures:
        warning = (f"Eightfold: {len(failures)} of {len(rows)} candidate job details could not be read. "
                   f"Earlier jobs were retained. {failures[0]}")
        if len(failures) == len(rows):
            raise SourceError(warning)
        warnings.append(warning)
        complete = False
    return Snapshot(jobs, complete=complete, source_ids=source_ids, warning=' '.join(warnings) or None)

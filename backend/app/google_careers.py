"""Read Google's public server-rendered careers data without executing scripts."""
import json
import re
from urllib.parse import parse_qsl, urlencode, urlparse

from bs4 import BeautifulSoup


_DATA = re.compile(
    r"AF_initDataCallback\(\s*\{\s*key:\s*(['\"])ds:1\1\s*,[^{}]*?\bdata:\s*"
)
_ROOT = 'https://www.google.com/about/careers/applications/jobs/results/'


def _html_field(row, index):
    value = row[index]
    return value[1] if isinstance(value, list) and len(value) > 1 and isinstance(value[1], str) else None


def google_postings(html):
    """Return (rows, total, page_size) from the embedded search response.

    The surrounding callback is JavaScript, but its data value is plain JSON.
    Decode only that literal and reject changed or incomplete response shapes.
    """
    from .collectors import SourceError

    for script in BeautifulSoup(html, 'html.parser').find_all('script'):
        content = script.string or script.get_text()
        marker = _DATA.search(content)
        if not marker:
            continue
        try:
            data, _ = json.JSONDecoder().raw_decode(content[marker.end():])
        except ValueError as exc:
            raise SourceError('Google careers returned unreadable embedded job data. Earlier jobs were retained.') from exc
        if not isinstance(data, list) or len(data) != 4:
            break
        rows, _, total, page_size = data
        if type(total) is not int or total < 0 or type(page_size) is not int or page_size < 1:
            break
        if rows is None and total == 0:
            rows = []
        if not isinstance(rows, list) or len(rows) > page_size:
            break
        valid = True
        for row in rows:
            if (not isinstance(row, list) or len(row) < 11
                    or not isinstance(row[0], str) or not re.fullmatch(r'\d+', row[0])
                    or not isinstance(row[1], str) or not row[1].strip()
                    or not isinstance(row[9], list) or not row[9]
                    or any(not isinstance(place, list) or not place
                           or not isinstance(place[0], str) or not place[0].strip() for place in row[9])
                    or any(not _html_field(row, index) for index in (3, 4, 10))):
                valid = False
                break
        if valid:
            return rows, total, page_size
        break
    raise SourceError('Google careers did not expose a supported job list. Earlier jobs were retained.')


async def collect_google(collector, company, config):
    """Collect every search page; a truncated snapshot cannot close older jobs."""
    from .collectors import MAX_PAGES, Snapshot, SourceError, normalize

    source = urlparse(company['url'])
    # Keep repeated company/location filters, while starting at the first page.
    params = [(key, value) for key, value in parse_qsl(source.query, keep_blank_values=True) if key != 'page']
    jobs, seen = [], set()
    initial_total = initial_size = None
    for page in range(1, MAX_PAGES + 1):
        query = params + ([('page', str(page))] if page > 1 else [])
        url = _ROOT + ('?' + urlencode(query) if query else '')
        try:
            await collector.allowed(url)
        except SourceError as exc:
            if page > 1 and 'robots.txt' in str(exc):
                return Snapshot(jobs, complete=False, source_ids=seen,
                    warning='Google permits its first search page but restricts automated pagination in robots.txt. '
                            'Only the first page was read; earlier jobs were retained. Open the careers page for all results.')
            raise
        response = await collector.request(url)
        rows, total, page_size = google_postings(response.text)
        if initial_total is None:
            initial_total, initial_size = total, page_size
        elif total != initial_total or page_size != initial_size:
            raise SourceError('Google careers changed its result count during pagination. Earlier jobs were retained; retry the source.')
        expected = min(page_size, max(0, total - (page - 1) * page_size))
        if len(rows) != expected:
            raise SourceError('Google careers returned an incomplete page. Earlier jobs were retained.')
        for row in rows:
            identity, title = row[:2]
            if identity in seen:
                raise SourceError('Google careers pagination repeated a job. Earlier jobs were retained.')
            seen.add(identity)
            description = '\n'.join(_html_field(row, index) for index in (4, 10, 3))
            locations = ' · '.join(dict.fromkeys(place[0] for place in row[9]))
            published = row[12] if len(row) > 12 else None
            posted_at = (published[0] * 1000 if isinstance(published, list) and published
                         and type(published[0]) is int else None)
            job = normalize(company, identity, title, locations, description, _ROOT + identity + '/',
                            posted_at, 'Not specified')
            if job:
                jobs.append(job)
        if len(seen) == total:
            return Snapshot(jobs, complete=not params, source_ids=seen,
                warning='Google careers results are filtered; earlier jobs outside these search filters were retained.' if params else None)
    return Snapshot(jobs, complete=False, source_ids=seen,
                    warning=f'Google careers reached the {MAX_PAGES}-page safety limit. Earlier jobs were retained.')

"""Amazon's public search feed, including the full qualification text."""
from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlencode, urlparse


def search_url(company, offset=0, limit=100):
    # Only the employer's public endpoint is used; URL filters remain data.
    params = [(key, value) for key, value in parse_qsl(urlparse(company['url']).query)
              if key not in ('offset', 'result_limit')]
    params.extend((('offset', str(offset)), ('result_limit', str(limit))))
    return 'https://www.amazon.jobs/en/search.json?' + urlencode(params)


async def collect_amazon(collector, company, config):
    from .collectors import MAX_PAGES, Snapshot, SourceError, normalize
    from .matching import software_title

    jobs, seen = [], set()
    offset = 0
    for _ in range(MAX_PAGES):
        url = search_url(company, offset)
        await collector.allowed(url)
        data = await collector.json(url)
        if (not isinstance(data, dict) or data.get('error') or
                not isinstance(data.get('jobs'), list) or type(data.get('hits')) is not int):
            raise SourceError('Amazon search feed changed or is unavailable. Earlier jobs were retained.')
        rows, total = data['jobs'], data['hits']
        if total < 0 or (not rows and offset < total):
            raise SourceError('Amazon returned an incomplete page. Earlier jobs were retained.')
        for row in rows:
            if not isinstance(row, dict) or not all(row.get(key) for key in ('id_icims', 'title', 'job_path')):
                raise SourceError('Amazon returned an unreadable job record. Earlier jobs were retained.')
            source_id = str(row['id_icims'])
            if source_id in seen:
                raise SourceError('Amazon pagination repeated. Earlier jobs were retained.')
            seen.add(source_id)
            if not software_title(row['title']):
                continue
            # Qualifications are separate from the marketing/role description.
            # Omitting them would incorrectly include experienced roles.
            if not row.get('description') or not row.get('basic_qualifications'):
                raise SourceError('Amazon did not return full job qualifications. Earlier jobs were retained.')
            path = urlparse(row['job_path'])
            if path.scheme or path.netloc or not path.path.startswith('/en/jobs/'):
                raise SourceError('Amazon returned an invalid public job link.')
            description = '\n'.join(row.get(key) or '' for key in
                                    ('description', 'basic_qualifications', 'preferred_qualifications'))
            posted_at = None
            if row.get('posted_date'):
                try:
                    posted_at = datetime.strptime(row['posted_date'], '%B %d, %Y').replace(tzinfo=timezone.utc).isoformat()
                except ValueError:
                    pass
            job = normalize(company, source_id, row['title'], row.get('normalized_location') or row.get('location'),
                            description, 'https://www.amazon.jobs' + row['job_path'], posted_at,
                            row.get('job_schedule_type'))
            if job:
                jobs.append(job)
        offset += len(rows)
        if offset >= total:
            break
    # Search filters and the employer's result ceiling do not represent a
    # complete global board, even when every search result was read.
    return Snapshot(jobs, False, seen, 'Amazon search is scoped by its URL filters and result limits. Earlier jobs were retained.')

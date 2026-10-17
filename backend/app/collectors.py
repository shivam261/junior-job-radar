"""Public feed adapters. No login, CAPTCHA bypass, or fabricated openings."""
import asyncio
import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse, urlencode, parse_qsl
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup
from .matching import plain, software_title, match_job, skills_from, work_mode
from .sources import resolve_public, identify, linked_sources, atlassian_postings, atlassian_matches, InvalidSource

MAX_PAGES = int(os.getenv("MAX_SOURCE_PAGES", "150"))
USER_AGENT = "LaunchpadJobCollector/1.0 (public career listings; personal use)"


@dataclass
class Snapshot:
    jobs: list[dict]
    complete: bool = True
    source_ids: set[str] | None = None
    warning: str | None = None


class SourceError(Exception):
    pass


def normalize(company, source_id, title, location, description, url, posted_at=None, employment_type="Full time"):
    match = match_job(title, description)
    parsed = urlparse(url)
    if not match or parsed.scheme != 'https' or not parsed.hostname:
        return None
    text = plain(description)
    if posted_at:
        try:
            if isinstance(posted_at, (float, int)):
                posted_at = datetime.fromtimestamp(posted_at / 1000, timezone.utc).isoformat()
            else:
                posted_at = datetime.fromisoformat(str(posted_at).replace('Z', '+00:00')).isoformat()
        except (ValueError, OverflowError):
            posted_at = None
    return dict(id=hashlib.sha256(f"{company['id']}:{source_id}".encode()).hexdigest()[:24],
        source_id=str(source_id), title=title, location=location or 'Location not specified',
        description=text, url=url, posted_at=posted_at, employment_type=employment_type or 'Not specified',
        experience_min=match.experience_min, experience_max=match.experience_max,
        confidence=match.confidence, evidence=match.evidence, skills=skills_from(text),
        work_mode=work_mode(title, location or '', text))


class Collector:
    def __init__(self, client):
        self.client = client
        self.semaphore = asyncio.Semaphore(6)
        self.robots = {}
        self.public_hosts = set()

    async def request(self, url, method='GET', allowed_status=(), **kwargs):
        from .sources import public_url
        url=public_url(url)
        host=urlparse(url).hostname
        if host not in self.public_hosts:
            await resolve_public(url)
            self.public_hosts.add(host)
        for attempt in range(3):
            async with self.semaphore:
                try:
                    await asyncio.sleep(0.12)
                    current_url,current_method,current_kwargs=url,method,dict(kwargs)
                    for hop in range(6):
                        # Validate every redirect before issuing another request.
                        target_host=urlparse(current_url).hostname
                        if target_host not in self.public_hosts:
                            await resolve_public(current_url)
                            self.public_hosts.add(target_host)
                        response = await self.client.request(current_method,current_url,follow_redirects=False,**current_kwargs)
                        if not response.is_redirect:break
                        if hop==5:raise SourceError('The careers page redirected too many times.')
                        location=response.headers.get('location')
                        if not location:raise SourceError('The careers page returned an invalid redirect.')
                        current_url=public_url(urljoin(current_url,location))
                        if response.status_code==303 or (response.status_code in (301,302) and current_method=='POST'):
                            current_method='GET'
                            for key in ('json','data','content'):current_kwargs.pop(key,None)

                    if response.status_code in (429, 500, 502, 503, 504) and attempt < 2:
                        retry = response.headers.get('Retry-After', '2')
                        await asyncio.sleep(min(float(retry) if retry.isdigit() else 2 ** (attempt+1), 20))
                        continue
                    if response.status_code not in allowed_status:response.raise_for_status()
                    return response
                except httpx.HTTPStatusError as exc:
                    raise SourceError(f"Employer source returned HTTP {exc.response.status_code}. It may have moved or restricted automated access.") from exc
                except httpx.RequestError as exc:
                    if attempt == 2:
                        raise SourceError(f"Could not reach source ({type(exc).__name__}). Try again later.") from exc
            await asyncio.sleep(attempt + 1)
        raise SourceError('Source did not return a response.')

    async def json(self, url, **kwargs):
        response = await self.request(url, **kwargs)
        try:
            return response.json()
        except ValueError as exc:
            raise SourceError('Source returned a web page instead of the expected feed. Check its configuration.') from exc

    async def collect(self, company):
        config = json.loads(company['config']) if isinstance(company['config'], str) else company['config']
        return await getattr(self, company['adapter'])(company, config)

    async def auto(self,c,cfg):
        source=identify(c['url'])
        if not source:
            await self.allowed(c['url'])
            response=await self.request(c['url'])
            source=identify(str(response.url))
            discovered=linked_sources(response.text,str(response.url))
            if not source and discovered:source=discovered[0]
            if not source:
                soup=BeautifulSoup(response.text,'html.parser')
                # Look through at most three same-site links to the jobs page.
                links=[]
                for link in soup.select('a[href]'):
                    url=urljoin(str(response.url),link['href'])
                    label=link.get_text(' ',strip=True).lower()
                    if urlparse(url).netloc==urlparse(str(response.url)).netloc and url!=str(response.url) and any(term in label for term in ('open roles','open jobs','view jobs','current openings','all jobs','see jobs')):
                        if url not in links:links.append(url)
                for url in links[:3]:
                    await self.allowed(url)
                    page=await self.request(url)
                    discovered=linked_sources(page.text,str(page.url))
                    if discovered:
                        source=discovered[0]
                        break
        adapter,config=source or ('html',{})
        # Preserve the user-entered official URL, and persist detected feed settings.
        from . import db
        with db.connection() as conn:
            conn.execute('UPDATE companies SET adapter=?,config=? WHERE id=?',(adapter,json.dumps(config),c['id']))
        return await getattr(self,adapter)(c,config)

    async def atlassian(self,c,cfg):
        url='https://www.atlassian.com/company/careers/all-jobs'
        source_url=c.get('url',url)
        filters=[(key,value) for key,value in parse_qsl(urlparse(source_url).query) if key in ('team','location')]
        if filters:url+='?'+urlencode(filters)
        await self.allowed(url)
        response=await self.request(url)
        rows=atlassian_postings(response.text)
        if not rows:raise SourceError('Atlassian did not expose its embedded job list. Earlier jobs were retained.')
        gate=asyncio.Semaphore(3)
        async def detail(row):
            async with gate:
                detail_url='https://www.atlassian.com/company/careers/details/'+str(row['id'])
                await self.allowed(detail_url)
                page=await self.request(detail_url)
                soup=BeautifulSoup(page.text,'html.parser')
                found=[]
                def walk(value):
                    if isinstance(value,dict):
                        kind=value.get('@type')
                        if kind=='JobPosting' or (isinstance(kind,list) and 'JobPosting' in kind):found.append(value)
                        for child in value.values():
                            if isinstance(child,(dict,list)):walk(child)
                    elif isinstance(value,list):
                        for child in value:walk(child)
                for script in soup.select('script[type="application/ld+json"]'):
                    try:walk(json.loads(script.string or script.get_text()))
                    except ValueError:continue
                if found and found[0].get('description'):
                    posting=found[0]
                    return normalize(c,row['id'],posting.get('title',row['title']), ' · '.join(str(value) for value in (row.get('locations') or []) if value),
                        posting['description'],detail_url,posting.get('datePosted'),row.get('type'))
                # Atlassian currently publishes the actual role in its main
                # content, while its JSON-LD describes other page entities.
                heading=soup.select_one('main h1')
                main=soup.select_one('main')
                if not heading or not main or heading.get_text(' ',strip=True)!=row['title']:
                    raise SourceError(f"Atlassian job {row['id']} did not expose a matching detail page. Earlier jobs were retained.")
                description=main.get_text('\n',strip=True).split('Join the Atlassian Talent Community',1)[0]
                if len(description)<200:
                    raise SourceError(f"Atlassian job {row['id']} had no readable description. Earlier jobs were retained.")
                locations=' · '.join(str(value) for value in (row.get('locations') or []) if value)
                if not locations:
                    lines=description.splitlines()
                    if len(lines)>1 and '|' in lines[1]:locations=lines[1].split('|',1)[1].strip()
                return normalize(c,row['id'],row['title'],locations,description,detail_url,None,row.get('type'))
        candidates=[row for row in rows if software_title(row['title']) and atlassian_matches(row,source_url)]
        results=await asyncio.gather(*(detail(row) for row in candidates),return_exceptions=True)
        jobs,failures=[],[]
        for row,result in zip(candidates,results):
            if isinstance(result,(SourceError,InvalidSource)):
                failures.append(f"Job {row['id']}: {result}")
            elif isinstance(result,BaseException):
                raise result
            elif result:
                jobs.append(result)
        warning=None
        if failures:
            warning=(f"Atlassian: {len(failures)} of {len(candidates)} candidate job details could not be read. "
                     f"Earlier jobs were retained. {failures[0]}")
            if len(failures)==len(candidates):raise SourceError(warning)
        return Snapshot(jobs,complete=not failures,source_ids={str(row['id']) for row in rows},warning=warning)

    async def workday(self, c, cfg):
        base = f"https://{cfg['host']}/wday/cxs/{cfg['tenant']}/{cfg['site']}"
        items, seen, source_ids, complete = [], set(), set(), True
        # Empty search text means a full board snapshot, not just one title spelling.
        for page in range(MAX_PAGES):
            data = await self.json(base + '/jobs', method='POST', json=dict(limit=20, offset=page*20, appliedFacets={}, searchText=''))
            if 'jobPostings' not in data or 'total' not in data:
                raise SourceError('Workday feed format changed or site is unavailable.')
            rows = data['jobPostings']
            if not rows and page*20 < data['total']:
                raise SourceError('Workday returned an incomplete page; prior jobs were retained.')
            async def detail_job(row):
                path = row['externalPath']
                detail = await self.json(base + path)
                info = detail.get('jobPostingInfo', {})
                if not info.get('jobDescription'):
                    raise SourceError('A Workday job detail was unavailable; prior jobs were retained.')
                locations = [info.get('location', row.get('locationsText', ''))] + info.get('additionalLocations', [])
                locations = [v if isinstance(v,str) else v.get('name', '') for v in locations]
                return normalize(c, info.get('jobReqId', path), row['title'], ' · '.join(filter(None, locations)),
                    info['jobDescription'], f"https://{cfg['host']}/{cfg['site']}{path}", info.get('startDate'), info.get('timeType'))
            candidates = []
            for row in rows:
                path = row.get('externalPath')
                if not path or path in seen:
                    continue
                seen.add(path)
                source_ids.update(str(v) for v in row.get('bulletFields',[]))
                tail=path.rsplit('_',1)[-1]
                source_ids.update((tail,re.sub(r'-\d+$','',tail)))
                if software_title(row.get('title', '')): candidates.append(row)
            details = await asyncio.gather(*(detail_job(row) for row in candidates))
            items.extend(job for job in details if job)
            source_ids.update(job['source_id'] for job in details if job)
            if (page+1)*20 >= data['total']:
                break
        else:
            complete = False
        return Snapshot(items, complete and data['total'] < 2000,source_ids)

    async def greenhouse(self, c, cfg):
        data = await self.json(f"https://boards-api.greenhouse.io/v1/boards/{cfg['token']}/jobs?content=true")
        if not isinstance(data.get('jobs'), list):
            raise SourceError('Greenhouse board did not return a jobs array.')
        jobs = []
        for row in data['jobs']:
            job = normalize(c, row['id'], row['title'], row.get('location', {}).get('name'),
                row.get('content', ''), row['absolute_url'], row.get('first_published'))
            if job: jobs.append(job)
        return Snapshot(jobs,source_ids={str(row['id']) for row in data['jobs']})

    async def lever(self, c, cfg):
        jobs, seen = [], set()
        for page in range(MAX_PAGES):
            data = await self.json(f"https://api{'.eu' if cfg.get('region')=='eu' else ''}.lever.co/v0/postings/{cfg['token']}?mode=json&limit=100&skip={page*100}")
            if not isinstance(data, list):
                raise SourceError('Lever board did not return a jobs array.')
            for row in data:
                if row['id'] in seen:
                    raise SourceError('Lever pagination repeated; prior jobs were retained.')
                seen.add(row['id'])
                description = row.get('description', '') + '\n' + '\n'.join(x.get('content', '') for x in row.get('lists', [])) + '\n' + row.get('additional', '')
                cat = row.get('categories', {})
                job = normalize(c, row['id'], row['text'], cat.get('location'), description, row['hostedUrl'], row.get('createdAt'), cat.get('commitment'))
                if job: jobs.append(job)
            if len(data) < 100:
                return Snapshot(jobs,source_ids=seen)
        return Snapshot(jobs, False,seen)

    async def smartrecruiters(self, c, cfg):
        base = f"https://api.smartrecruiters.com/v1/companies/{cfg['token']}/postings"
        jobs, seen = [], set()
        for page in range(MAX_PAGES):
            data = await self.json(f"{base}?limit=100&offset={page*100}")
            if 'content' not in data or 'totalFound' not in data:
                raise SourceError('SmartRecruiters feed format changed.')
            rows = data['content']
            if not rows and page*100 < data['totalFound']:
                raise SourceError('SmartRecruiters returned an incomplete snapshot.')
            for row in rows:
                if row['id'] in seen:
                    continue
                seen.add(row['id'])
                if not software_title(row['name']): continue
                detail = await self.json(base + '/' + row['id'])
                sections = detail.get('jobAd', {}).get('sections', {})
                description = '\n'.join(s.get('text', '') for s in sections.values() if isinstance(s,dict))
                if not description:
                    raise SourceError('A SmartRecruiters job detail was unavailable.')
                loc = detail.get('location', row.get('location', {}))
                url = detail.get('postingUrl') or f"https://jobs.smartrecruiters.com/{cfg['token']}/{row['id']}"
                job = normalize(c, row['id'], row['name'], ', '.join(filter(None, [loc.get('city'),loc.get('region'),loc.get('country')])),
                    description, url, detail.get('releasedDate'), detail.get('typeOfEmployment', {}).get('label'))
                if job: jobs.append(job)
            if (page+1)*100 >= data['totalFound']: return Snapshot(jobs,source_ids=seen)
        return Snapshot(jobs, False)

    async def ashby(self, c, cfg):
        data = await self.json(f"https://api.ashbyhq.com/posting-api/job-board/{cfg['token']}")
        if not isinstance(data.get('jobs'), list): raise SourceError('Ashby feed format changed.')
        jobs = []
        for row in data['jobs']:
            if not row.get('isListed', True): continue
            job = normalize(c, row.get('id',row['jobUrl']), row['title'], row.get('location'),
                row.get('descriptionHtml', row.get('descriptionPlain','')), row['jobUrl'], row.get('publishedAt'), row.get('employmentType'))
            if job: jobs.append(job)
        return Snapshot(jobs,source_ids={str(row.get('id',row['jobUrl'])) for row in data['jobs'] if row.get('isListed',True)})

    async def oracle(self, c, cfg):
        base = f"https://{cfg['host']}/hcmRestApi/resources/latest"
        jobs = []
        for page in range(MAX_PAGES):
            finder = f"findReqs;siteNumber={cfg['site']},keyword=software,limit=25,offset={page*25},sortBy=POSTING_DATES_DESC"
            data = await self.json(base + '/recruitingCEJobRequisitions', params={'finder': finder, 'expand':'requisitionList', 'onlyData':'true'})
            container = data.get('items', [])
            if not container or 'requisitionList' not in container[0]:
                raise SourceError('Oracle candidate feed is unavailable or has changed.')
            rows = container[0]['requisitionList']
            for row in rows:
                title = row.get('Title','')
                if not software_title(title): continue
                details = await self.json(base + '/recruitingCEJobRequisitionDetails', params={'finder':f"ById;Id={row['Id']},siteNumber={cfg['site']}", 'onlyData':'true'})
                detail = details.get('items', [{}])[0] if details.get('items') else {}
                description = '\n'.join(str(detail.get(k,'')) for k in ('ExternalDescriptionStr','ExternalQualificationsStr','ExternalResponsibilitiesStr'))
                if not description.strip(): raise SourceError('Oracle job details were unavailable.')
                job = normalize(c, row['Id'], title, row.get('PrimaryLocation'), description,
                    f"https://{cfg['host']}/hcmUI/CandidateExperience/en/sites/{cfg['site']}/job/{row['Id']}", row.get('PostedDate'))
                if job: jobs.append(job)
            if len(rows) < 25: break
        # Keyword-scoped Oracle searches cannot guarantee a whole-board snapshot.
        return Snapshot(jobs, False)

    async def allowed(self, url):
        parts = urlparse(url)
        root = f"{parts.scheme}://{parts.netloc}"
        if root not in self.robots:
            response = await self.request(root + '/robots.txt',allowed_status=(404,))
            parser = RobotFileParser()
            if response.status_code == 404:
                parser.parse([])
            elif response.status_code == 200:
                parser.parse(response.text.splitlines())
            else:
                raise SourceError('Could not verify robots.txt permissions for this careers page.')
            self.robots[root] = parser
        if not self.robots[root].can_fetch(USER_AGENT, url):
            raise SourceError('This careers page restricts automated crawling in robots.txt. Open the official careers page instead.')

    def structured(self, c, html, url):
        soup, jobs = BeautifulSoup(html, 'html.parser'), []
        def walk(node):
            if isinstance(node, list):
                for item in node: walk(item)
            elif isinstance(node, dict):
                kind = node.get('@type', '')
                if kind == 'JobPosting' or (isinstance(kind,list) and 'JobPosting' in kind):
                    locations = node.get('jobLocation', [])
                    if not isinstance(locations,list): locations=[locations]
                    texts=[]
                    for loc in locations:
                        addr=loc.get('address', {}) if isinstance(loc,dict) else {}
                        texts.append(', '.join(str(addr.get(k,'')) for k in ('addressLocality','addressRegion','addressCountry') if addr.get(k)))
                    if node.get('jobLocationType') == 'TELECOMMUTE': texts.append('Remote')
                    identity = node.get('identifier', {})
                    identity = identity.get('value', url) if isinstance(identity,dict) else str(identity)
                    types = node.get('employmentType', 'Not specified')
                    job=normalize(c, identity or url, node.get('title',''), ' · '.join(texts), node.get('description',''),
                        urljoin(url,node.get('url') or url), node.get('datePosted'), ', '.join(types) if isinstance(types,list) else types)
                    if job: jobs.append(job)
                else:
                    for value in node.values():
                        if isinstance(value,(dict,list)): walk(value)
        for script in soup.select('script[type="application/ld+json"]'):
            try: walk(json.loads(script.string or script.get_text()))
            except (ValueError,TypeError): continue
        return soup, jobs

    async def html(self, c, cfg):
        # Crawl official job links and pagination with robots checks. HTML sources
        # are always partial: absence from a page is not proof a job closed.
        queue, visited, jobs, detail_count = [c['url']], set(), {}, 0
        readable = False
        for _ in range(min(MAX_PAGES, 60)):
            if not queue: break
            url = queue.pop(0)
            if url in visited: continue
            visited.add(url)
            await self.allowed(url)
            response = await self.request(url)
            soup, found = self.structured(c, response.text, str(response.url))
            # SuccessFactors and similar server-rendered detail pages may publish
            # visible job text without JobPosting JSON-LD.
            if not found and any(part in urlparse(str(response.url)).path.lower() for part in ('/job/','/jobs/')):
                title_node = soup.select_one('[itemprop="title"], h1')
                desc_node = soup.select_one('[itemprop="description"], .jobdescription, .job-description, .jobDescription')
                loc_node = soup.select_one('[itemprop="jobLocation"], .jobGeoLocation, .jobLocation')
                if title_node and desc_node:
                    readable = True
                    job = normalize(c, str(response.url), title_node.get_text(' ',strip=True),
                        loc_node.get_text(' ',strip=True) if loc_node else '',
                        str(desc_node), str(response.url))
                    if job: found.append(job)
            if found or any('JobPosting' in script.get_text() for script in soup.select('script[type="application/ld+json"]')): readable = True
            for job in found: jobs[job['id']] = job
            for link in soup.select('a[href]'):
                href=urljoin(str(response.url), link['href'])
                if urlparse(href).netloc != urlparse(str(response.url)).netloc: continue
                label=link.get_text(' ',strip=True)
                is_job=software_title(label) and any(s in urlparse(href).path.lower() for s in ('/job/','/jobs/','/jobdetail/','/requisition/'))
                is_next=label.lower() in ('next','next page','›','»') or 'next' in link.get('rel', []) or link.get('aria-label','').lower() == 'next page'
                if (is_job or is_next) and href not in visited and href not in queue:
                    queue.append(href)
                    if is_job: detail_count += 1
            if cfg.get('pagination') and url == c['url']:
                # SuccessFactors exposes its public search through startrow.
                for page in range(1,min(MAX_PAGES,20)):
                    params=dict(parse_qsl(urlparse(url).query))
                    params[cfg['pagination']]=str(page*cfg.get('page_size',25))
                    queue.append(urlparse(url)._replace(query=urlencode(params)).geturl())
        if not readable:
            raise SourceError('No matching structured postings could be read. The page may need JavaScript, have no matching roles, or require a dedicated adapter. Use the official careers link.')
        return Snapshot(list(jobs.values()), False)


def http_client():
    return httpx.AsyncClient(timeout=httpx.Timeout(25,connect=12), follow_redirects=True,
        headers={'User-Agent': USER_AGENT, 'Accept': 'application/json, text/html;q=0.9'},
        limits=httpx.Limits(max_connections=12, max_keepalive_connections=8))

"""Public careers URL validation and ATS discovery; never execute page scripts."""
import asyncio
import ipaddress
import json
import re
import socket
from urllib.parse import urlparse, parse_qs, unquote, urljoin
from bs4 import BeautifulSoup


class InvalidSource(ValueError):
    pass


def public_url(value):
    parsed=urlparse(str(value).strip())
    host=(parsed.hostname or '').lower().rstrip('.')
    if parsed.scheme!='https' or not host or parsed.username or parsed.password:
        raise InvalidSource('Enter a public HTTPS careers URL without login credentials.')
    if parsed.port not in (None,443) or host=='localhost' or host.endswith(('.localhost','.local','.internal')) or '.' not in host:
        raise InvalidSource('Only public careers websites on HTTPS port 443 are supported.')
    try:
        address=ipaddress.ip_address(host)
    except ValueError:
        address=None
    if address and not address.is_global:
        raise InvalidSource('Local and private network URLs are not careers sources.')
    return parsed._replace(fragment='').geturl()


async def resolve_public(url):
    url=public_url(url)
    host=urlparse(url).hostname
    try:
        records=await asyncio.get_running_loop().getaddrinfo(host,443,type=socket.SOCK_STREAM)
    except OSError as exc:
        raise InvalidSource('The careers website could not be resolved. Check its URL.') from exc
    if not records or any(not ipaddress.ip_address(record[4][0]).is_global for record in records):
        raise InvalidSource('The careers URL must resolve to a public website.')
    return url


def identify(url):
    p=urlparse(url)
    host=(p.hostname or '').lower()
    parts=[unquote(v) for v in p.path.split('/') if v]
    if host in ('www.atlassian.com','atlassian.com') and '/company/careers' in p.path:
        return 'atlassian', {}
    if host.endswith('.myworkdayjobs.com') and parts:
        if parts[0].lower() in ('en-us','en-gb'): parts=parts[1:]
        if parts:
            return 'workday',dict(host=host,tenant=host.split('.')[0],site=parts[0])
    if host in ('job-boards.greenhouse.io','boards.greenhouse.io','boards.eu.greenhouse.io'):
        token=parse_qs(p.query).get('for',[None])[0] if parts and parts[0]=='embed' else (parts[0] if parts else None)
        if token: return 'greenhouse',dict(token=token)
    if host in ('jobs.lever.co','jobs.eu.lever.co') and parts:
        return 'lever',dict(token=parts[0],region='eu' if host=='jobs.eu.lever.co' else 'global')
    if host in ('jobs.smartrecruiters.com','careers.smartrecruiters.com') and parts:
        return 'smartrecruiters',dict(token=parts[0])
    if host=='jobs.ashbyhq.com' and parts:
        return 'ashby',dict(token=parts[0])
    if host.endswith('.oraclecloud.com'):
        match=re.search(r'/sites/([^/]+)',p.path)
        if match:return 'oracle',dict(host=host,site=match[1])
    return None


def linked_sources(html,base):
    soup=BeautifulSoup(html,'html.parser')
    candidates=[urljoin(base,node.get('href') or node.get('src','')) for node in soup.select('a[href], iframe[src]')]
    # ATS URLs embedded in script configuration are data, never executable code.
    candidates+=re.findall(r'https://[a-zA-Z0-9.-]+(?:myworkdayjobs\.com|greenhouse\.io|lever\.co|smartrecruiters\.com|ashbyhq\.com)/[^\s"<>\\]+',html)
    found=[]
    for url in candidates:
        source=identify(url)
        if source and source not in found:found.append(source)
    return found


def atlassian_postings(html):
    soup=BeautifulSoup(html,'html.parser')
    found={}
    def walk(value):
        if isinstance(value,dict):
            if all(k in value for k in ('applyUrl','title','id','locations')):
                found[str(value['id'])]=value
            for child in value.values():walk(child)
        elif isinstance(value,list):
            for child in value:walk(child)
    for script in soup.select('script'):
        text=script.string or script.get_text()
        marker=re.search(r'window\._uniformPreloadedComposition\s*=\s*',text)
        if marker:
            try:
                value,_=json.JSONDecoder().raw_decode(text[marker.end():])
                walk(value)
            except ValueError:continue
    return list(found.values())

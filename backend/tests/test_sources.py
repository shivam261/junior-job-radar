import asyncio
import json
import socket
import httpx
import pytest
from app.sources import identify,linked_sources,atlassian_postings,public_url,resolve_public,InvalidSource
from app.collectors import Collector
from app import db

@pytest.mark.parametrize('url,adapter,token',[
 ('https://job-boards.greenhouse.io/acme/jobs/123','greenhouse','acme'),
 ('https://boards.greenhouse.io/embed/job_board?for=acme','greenhouse','acme'),
 ('https://jobs.lever.co/acme/123','lever','acme'),
 ('https://jobs.ashbyhq.com/acme','ashby','acme'),
 ('https://careers.smartrecruiters.com/Acme','smartrecruiters','Acme'),
 ('https://example.wd5.myworkdayjobs.com/en-US/External','workday',None),
 ('https://www.atlassian.com/company/careers/all-jobs','atlassian',None),
 ('https://example.fa.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1/jobs','oracle',None),
])
def test_ats_detection(url,adapter,token):
    kind,cfg=identify(url)
    assert kind==adapter
    if token:assert cfg['token']==token
    if kind=='workday':assert cfg==dict(host='example.wd5.myworkdayjobs.com',tenant='example',site='External')

@pytest.mark.parametrize('url',['http://example.com/careers','https://localhost/careers','https://127.0.0.1/x','https://10.0.0.1/jobs','https://169.254.169.254/x','https://secret:password@example.com/jobs','https://example.com:8080/jobs','https://company.local/jobs'])
def test_nonpublic_urls_are_rejected(url):
    with pytest.raises(InvalidSource):public_url(url)

@pytest.mark.asyncio
async def test_dns_private_address_is_rejected(monkeypatch):
    async def fake_dns(*args,**kwargs):return [(socket.AF_INET,socket.SOCK_STREAM,6,'',('10.0.0.2',443))]
    monkeypatch.setattr(asyncio.get_running_loop(),'getaddrinfo',fake_dns)
    with pytest.raises(InvalidSource):await resolve_public('https://careers.example.com/')

@pytest.mark.asyncio
async def test_private_redirect_is_not_followed():
    requested=[]
    def respond(request):
        requested.append(str(request.url))
        return httpx.Response(302,headers={'Location':'https://127.0.0.1/admin'})
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(InvalidSource):await Collector(client).request('https://example.com/careers')
    assert requested==['https://example.com/careers']


def test_discovery_from_careers_links_and_iframes():
    assert linked_sources('<iframe src="https://job-boards.greenhouse.io/acme"></iframe>','https://example.com/careers')==[('greenhouse',{'token':'acme'})]

@pytest.mark.asyncio
async def test_auto_company_discovers_feed_and_collects(database):
    c={'id':'custom-acme','url':'https://example.com/careers','adapter':'auto','config':{}}
    with db.connection() as conn:
        conn.execute("INSERT INTO companies(id,name,adapter,url,config,custom) VALUES(?,?,?,?,?,1)",(c['id'],'Acme','auto',c['url'],'{}'))
    def respond(request):
        if request.url.path=='/robots.txt':return httpx.Response(200,text='User-agent: *\nAllow: /')
        if request.url.host=='example.com':return httpx.Response(200,text='<a href="https://job-boards.greenhouse.io/acme">Open jobs</a>')
        return httpx.Response(200,json={'jobs':[{'id':42,'title':'Software Engineer I','location':{'name':'Mumbai, India'},'content':'0–2 years of experience.','absolute_url':'https://job-boards.greenhouse.io/acme/jobs/42'}]})
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        snapshot=await Collector(client).collect(c)
    assert len(snapshot.jobs)==1 and snapshot.complete
    with db.connection() as conn:assert conn.execute('SELECT adapter FROM companies WHERE id=?',(c['id'],)).fetchone()[0]=='greenhouse'

@pytest.mark.asyncio
async def test_atlassian_embedded_list_and_public_detail():
    rows=[{'id':'42','applyUrl':'https://careers.icims.com/jobs/42','title':'Graduate Software Engineer','locations':['Bengaluru - India'],'type':'Full time'},
          {'id':'43','applyUrl':'https://careers.icims.com/jobs/43','title':'Senior Software Engineer','locations':['India'],'type':'Full time'}]
    html='<script>window._uniformPreloadedComposition='+json.dumps({'jobs':rows})+'; window.thisMustNeverRun();</script>'
    assert len(atlassian_postings(html))==2
    paths=[]
    def respond(request):
        paths.append(request.url.path)
        if request.url.path=='/robots.txt':return httpx.Response(200,text='User-agent: *\nAllow: /')
        if request.url.path.endswith('all-jobs'):return httpx.Response(200,text=html)
        return httpx.Response(200,text='<script type="application/ld+json">'+json.dumps({'@type':'JobPosting','title':'Graduate Software Engineer','description':'0–2 years of experience. Python.'})+'</script>')
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        snapshot=await Collector(client).collect({'id':'atlassian','adapter':'atlassian','config':{}})
    assert snapshot.complete and len(snapshot.jobs)==1
    assert snapshot.jobs[0]['url']=='https://www.atlassian.com/company/careers/details/42'
    assert snapshot.source_ids=={'42','43'}
    assert '/company/careers/details/43' not in paths

@pytest.mark.asyncio
async def test_atlassian_visible_main_description_without_jobposting_jsonld():
    rows=[{'id':'42','applyUrl':'https://careers.icims.com/jobs/42','title':'Graduate Software Engineer','locations':None,'type':None}]
    html='<script>window._uniformPreloadedComposition='+json.dumps({'jobs':rows})+';</script>'
    desc='0–2 years of experience. Develop reliable systems using Python. Collaborate with a team to build maintainable software. '*3
    def respond(request):
        if request.url.path=='/robots.txt':return httpx.Response(200,text='User-agent: *\nAllow: /')
        if request.url.path.endswith('all-jobs'):return httpx.Response(200,text=html)
        return httpx.Response(200,text='<main><h1>Graduate Software Engineer</h1><p>Engineering | Bengaluru, India</p><p>'+desc+'</p><h2>Join the Atlassian Talent Community</h2><p>Unrelated marketing.</p></main>')
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        snapshot=await Collector(client).collect({'id':'atlassian','adapter':'atlassian','config':{}})
    assert len(snapshot.jobs)==1 and snapshot.complete
    assert 'Unrelated marketing' not in snapshot.jobs[0]['description']
    assert snapshot.jobs[0]['location']=='Bengaluru, India'

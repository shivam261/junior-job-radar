import json
import httpx
import pytest
from app.collectors import Collector,SourceError
from app.companies import COMPANIES

@pytest.mark.asyncio
async def test_workday_pagination_and_original_link():
    requests=[]
    def respond(request):
        requests.append(request)
        if request.method=='POST':
            offset=json.loads(request.content)['offset']
            rows=[{'title':'Software Engineer I','externalPath':'/job/Pune/Test_123','locationsText':'Pune, India'}] if offset==0 else []
            if offset==0: rows += [{'title':'Senior Software Engineer','externalPath':f'/job/senior-{i}'} for i in range(19)]
            return httpx.Response(200,json={'total':21,'jobPostings':rows if offset==0 else [{'title':'Product Manager','externalPath':'/job/pm'}]})
        return httpx.Response(200,json={'jobPostingInfo':{'jobReqId':'123','location':'Pune, India','jobDescription':'Required: 0–2 years of experience.'}})
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        snapshot=await Collector(client).collect(COMPANIES[0])
    assert snapshot.complete
    assert len(snapshot.jobs)==1
    assert snapshot.jobs[0]['url']=='https://autodesk.wd1.myworkdayjobs.com/Ext/job/Pune/Test_123'
    assert len([r for r in requests if r.method=='POST'])==2

@pytest.mark.asyncio
async def test_feed_failures_do_not_produce_empty_success():
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r:httpx.Response(403,text='Forbidden'))) as client:
        with pytest.raises(SourceError): await Collector(client).collect(COMPANIES[0])

@pytest.mark.asyncio
async def test_greenhouse_description_and_senior_exclusion():
    data={'jobs':[{'id':1,'title':'Junior Software Engineer','content':'1–2 years of professional experience. React','absolute_url':'https://job-boards.greenhouse.io/razorpay/jobs/1','location':{'name':'Bengaluru, India'}},
                  {'id':2,'title':'Senior Software Engineer','content':'10 years of experience','absolute_url':'https://job-boards.greenhouse.io/razorpay/jobs/2'}]}
    company=next(c for c in COMPANIES if c['id']=='razorpay')
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r:httpx.Response(200,json=data))) as client:
        snapshot=await Collector(client).collect(company)
    assert len(snapshot.jobs)==1
    assert snapshot.jobs[0]['confidence']=='confirmed'
    assert snapshot.jobs[0]['skills']==['React']

@pytest.mark.asyncio
async def test_html_robot_restrictions():
    company=next(c for c in COMPANIES if c['id']=='zomato')
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r:httpx.Response(200,text='User-agent: *\nDisallow: /careers'))) as client:
        with pytest.raises(SourceError,match='robots.txt'): await Collector(client).collect(company)


def test_structured_data_graph_and_xss_as_plain_text():
    c=COMPANIES[0]
    collector=Collector(None)
    html='<script type="application/ld+json">'+json.dumps({'@graph':[{'@type':'JobPosting','title':'Graduate Software Engineer','description':'<p>1–2 years of experience.</p>','url':'https://example.com/job/1','jobLocation':{'address':{'addressLocality':'Pune','addressCountry':'India'}}}]})+'</script>'
    _,jobs=collector.structured(c,html,'https://example.com/careers')
    assert jobs[0]['location']=='Pune, India'
    assert '<p>' not in jobs[0]['description']

@pytest.mark.asyncio
async def test_readable_html_without_matching_experience_is_partial_success():
    company={'id':'test','url':'https://example.com/job/one','config':{},'adapter':'html'}
    def response(request):
        if request.url.path=='/robots.txt': return httpx.Response(200,text='User-agent: *\nAllow: /')
        return httpx.Response(200,text='<h1>Software Engineer</h1><div class="jobdescription">5 years of experience.</div>')
    async with httpx.AsyncClient(transport=httpx.MockTransport(response)) as client:
        result=await Collector(client).collect(company)
    assert result.jobs==[]
    assert not result.complete

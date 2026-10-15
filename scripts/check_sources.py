"""Read-only feed smoke test: run from backend with ../.venv/bin/python ../scripts/check_sources.py."""
import asyncio
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from app.companies import COMPANIES
from app.collectors import http_client

async def main():
    gate=asyncio.Semaphore(5)
    async with http_client() as client:
        async def one(c):
            cfg=c['config']; kind=c['adapter']; url=c['url']; method='GET'; args={}
            if kind=='workday':
                url=f"https://{cfg['host']}/wday/cxs/{cfg['tenant']}/{cfg['site']}/jobs";method='POST';args={'json':{'limit':20,'offset':0,'appliedFacets':{},'searchText':''}}
            elif kind=='greenhouse': url=f"https://boards-api.greenhouse.io/v1/boards/{cfg['token']}/jobs?content=true"
            elif kind=='lever': url=f"https://api.lever.co/v0/postings/{cfg['token']}?mode=json&limit=100"
            elif kind=='smartrecruiters': url=f"https://api.smartrecruiters.com/v1/companies/{cfg['token']}/postings?limit=10"
            elif kind=='ashby': url=f"https://api.ashbyhq.com/posting-api/job-board/{cfg['token']}"
            async with gate:
                try:
                    response=await client.request(method,url,**args)
                    data=response.json() if kind not in ('html','oracle') else {}
                    count=data.get('total',data.get('totalFound',len(data.get('jobs',[])))) if isinstance(data,dict) else len(data)
                    item=dict(company=c['name'],adapter=kind,status=response.status_code,count=count,url=str(response.url))
                except Exception as exc: item=dict(company=c['name'],adapter=kind,error=str(exc))
                print(json.dumps(item),flush=True)
        await asyncio.gather(*(one(c) for c in COMPANIES))
asyncio.run(main())

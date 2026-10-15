"""Sequential targeted refresh through the running backend's single worker."""
import asyncio
import sys
import httpx

async def main():
    async with httpx.AsyncClient(base_url='http://127.0.0.1:8000',timeout=15) as client:
        for company in sys.argv[1:]:
            response=await client.post('/api/refresh',json={'company_id':company})
            response.raise_for_status()
            result=response.json()
            if not result['started']:
                print('An existing refresh is running; no overlapping collection started.',flush=True)
                return
            while True:
                rows=(await client.get('/api/runs')).json()
                run=next(r for r in rows if r['id']==result['run_id'])
                if run['status']!='running':
                    print(company,run['status'],run['matched'],'matches',flush=True)
                    break
                await asyncio.sleep(2)
asyncio.run(main())

import asyncio
import json
import os
import re
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
from . import db
from .service import RefreshService
from .sources import public_url, identify

service = RefreshService()


@asynccontextmanager
async def lifespan(app):
    db.initialize()
    scheduler = asyncio.create_task(service.scheduler())
    yield
    scheduler.cancel()
    await asyncio.gather(scheduler,return_exceptions=True)
    await service.close()


app = FastAPI(title='Launchpad — Early-career jobs',version='1.0.0',lifespan=lifespan)
app.add_middleware(CORSMiddleware,allow_origins=os.getenv('CORS_ORIGINS','http://localhost:5173,http://127.0.0.1:5173').split(','),allow_credentials=False,allow_methods=['GET','POST','PUT','DELETE','PATCH'],allow_headers=['Content-Type'])


@app.get('/api/health')
def health():
    with db.connection() as conn: conn.execute('SELECT 1')
    return {'status':'ok'}


@app.get('/api/companies')
def companies():
    rows=db.company_rows()
    for row in rows: row.pop('config',None)
    return rows


class NewCompany(BaseModel):
    name: str = Field(min_length=2,max_length=100)
    url: str = Field(max_length=2048)
    sector: str = Field(default='Technology',min_length=2,max_length=60)
    refresh: bool = True

    @field_validator('name','sector')
    @classmethod
    def nonempty(cls,value):
        value=value.strip()
        if len(value)<2:raise ValueError('Enter at least two characters.')
        return value

    @field_validator('url')
    @classmethod
    def career_url(cls,value):
        return public_url(value)


@app.post('/api/companies',status_code=201)
async def add_company(request: NewCompany):
    detected=identify(request.url)
    adapter,config=detected or ('auto',{})
    slug=re.sub(r'[^a-z0-9]+','-',request.name.lower()).strip('-') or 'company'
    company_id=slug+'-'+uuid.uuid4().hex[:8]
    with db.connection() as conn:
        if conn.execute('SELECT 1 FROM companies WHERE lower(name)=lower(?) OR url=?',(request.name,request.url)).fetchone():
            raise HTTPException(409,'This company or careers page is already in your directory.')
        conn.execute('INSERT INTO companies(id,name,sector,adapter,url,config,custom) VALUES(?,?,?,?,?,?,1)',
            (company_id,request.name,request.sector,adapter,request.url,json.dumps(config)))
    queued=False
    if request.refresh:
        service.enqueue(company_id)
        queued=True
    row=next(c for c in db.company_rows() if c['id']==company_id)
    row.pop('config',None)
    return {**row,'refresh_queued':queued}


class CompanySettings(BaseModel):
    enabled: bool


@app.patch('/api/companies/{company_id}')
def company_settings(company_id: str, settings: CompanySettings):
    with db.connection() as conn:
        cur=conn.execute('UPDATE companies SET enabled=? WHERE id=?',(int(settings.enabled),company_id))
        if not cur.rowcount: raise HTTPException(404,'Company not found')
    return {'enabled':settings.enabled}


@app.get('/api/jobs')
def jobs(q: str='', location: str='', company: str='', confidence: str='', mode: str='',
         saved: bool=False, demo: bool=False, status: str=Query('open',pattern='^(open|closed|all)$'), sort: str=Query('newest',pattern='^(newest|company|relevance)$'),
         page: int=Query(1,ge=1), page_size: int=Query(12,ge=1,le=100)):
    where=['j.demo=?']
    params=[int(demo)]
    if status!='all':where.append('j.active='+('1' if status=='open' else '0'))
    if q:
        for word in q.split()[:8]:
            where.append("(j.title LIKE ? ESCAPE '\\' OR j.description LIKE ? ESCAPE '\\' OR c.name LIKE ? ESCAPE '\\')")
            value='%' + word.replace('\\','\\\\').replace('%','\\%').replace('_','\\_') + '%'
            params += [value]*3
    if location:
        aliases={'bengaluru':['Bengaluru','Bangalore'],'gurugram':['Gurugram','Gurgaon'],
            'india':['India','IND','Bengaluru','Bangalore','Pune','Hyderabad','Mumbai','Chennai','Gurugram','Gurgaon','Noida','Delhi','Kolkata']}
        terms=aliases.get(location.lower(),[location])
        where.append('j.location REGEXP ?')
        pattern=r'\b(?:'+'|'.join(re.escape(term) for term in terms)+r')\b'
        if location.lower()=='india':pattern+=r'|(?:^|[,;|·-]\s*)IN(?:$|\s*[,;|·-])'
        params.append(pattern)
    if company:
        ids=[x for x in company.split(',') if x]
        where.append('j.company_id IN ('+','.join('?' for _ in ids)+')')
        params.extend(ids)
    if confidence:
        where.append('j.confidence=?'); params.append(confidence)
    if mode:
        where.append('j.work_mode=?'); params.append(mode)
    if saved: where.append('b.job_id IS NOT NULL')
    base='FROM jobs j JOIN companies c ON c.id=j.company_id LEFT JOIN bookmarks b ON b.job_id=j.id WHERE '+ ' AND '.join(where)
    order={'newest':'COALESCE(j.posted_at,j.first_seen) DESC,j.id','company':'c.name,j.title,j.id','relevance':"CASE WHEN j.confidence='confirmed' THEN 0 ELSE 1 END,COALESCE(j.posted_at,j.first_seen) DESC,j.id"}[sort]
    with db.connection() as conn:
        total=conn.execute('SELECT COUNT(*) '+base,params).fetchone()[0]
        rows=conn.execute('SELECT j.*,c.name AS company,c.sector,c.adapter,c.status AS source_status,c.last_success AS source_last_success,(b.job_id IS NOT NULL) AS saved '+base+' ORDER BY '+order+' LIMIT ? OFFSET ?',params+[page_size,(page-1)*page_size]).fetchall()
    return {'items':[db.serialize_job(r) for r in rows],'total':total,'page':page,'page_size':page_size}


@app.get('/api/jobs/{job_id}')
def job_details(job_id: str):
    with db.connection() as conn:
        row=conn.execute('SELECT j.*,c.name AS company,c.sector,c.adapter,c.status AS source_status,c.last_success AS source_last_success,(b.job_id IS NOT NULL) AS saved FROM jobs j JOIN companies c ON c.id=j.company_id LEFT JOIN bookmarks b ON b.job_id=j.id WHERE j.id=?',(job_id,)).fetchone()
    if not row: raise HTTPException(404,'Job not found')
    return db.serialize_job(row)


@app.put('/api/bookmarks/{job_id}')
def save(job_id: str):
    with db.connection() as conn:
        if not conn.execute('SELECT id FROM jobs WHERE id=?',(job_id,)).fetchone(): raise HTTPException(404,'Job not found')
        conn.execute('INSERT OR IGNORE INTO bookmarks VALUES(?,?)',(job_id,db.now()))
    return {'saved':True}


@app.delete('/api/bookmarks/{job_id}')
def unsave(job_id: str):
    with db.connection() as conn: conn.execute('DELETE FROM bookmarks WHERE job_id=?',(job_id,))
    return {'saved':False}


@app.get('/api/stats')
def stats(demo: bool=False):
    with db.connection() as conn:
        def count(sql, args=()): return conn.execute(sql,args).fetchone()[0]
        scope='active=1 AND demo=?'
        total=count('SELECT COUNT(*) FROM jobs WHERE '+scope,(int(demo),))
        confirmed=count("SELECT COUNT(*) FROM jobs WHERE "+scope+" AND confidence='confirmed'",(int(demo),))
        saved=count('SELECT COUNT(*) FROM bookmarks b JOIN jobs j ON j.id=b.job_id WHERE j.demo=?',(int(demo),))
        recent=count("SELECT COUNT(*) FROM jobs WHERE "+scope+" AND julianday(first_seen)>=julianday('now','-7 days')",(int(demo),))
        healthy=count("SELECT COUNT(*) FROM companies WHERE status='healthy'")
        tracked=count('SELECT COUNT(*) FROM companies WHERE enabled=1')
        run=conn.execute('SELECT * FROM runs ORDER BY started_at DESC LIMIT 1').fetchone()
        return dict(total=total,confirmed=confirmed,saved=saved,new_this_week=recent,healthy_sources=healthy,tracked_companies=tracked,total_companies=count('SELECT COUNT(*) FROM companies'),latest_run=dict(run) if run else None)


class RefreshRequest(BaseModel):
    company_id: str | None = None


@app.post('/api/refresh',status_code=202)
async def refresh(request: RefreshRequest):
    if request.company_id:
        with db.connection() as conn:
            row=conn.execute('SELECT enabled FROM companies WHERE id=?',(request.company_id,)).fetchone()
            if not row: raise HTTPException(404,'Company not found')
            if not row['enabled']: raise HTTPException(400,'Enable this company before refreshing')
    run_id, started=service.start(request.company_id)
    return {'run_id':run_id,'started':started}


@app.get('/api/runs')
def runs():
    with db.connection() as conn:
        return [dict(r) for r in conn.execute('SELECT * FROM runs ORDER BY started_at DESC LIMIT 20')]


# One-host production deployment after building React. API routes retain /api.
frontend=Path(__file__).resolve().parents[2]/'frontend'/'dist'
if frontend.exists():
    app.mount('/', StaticFiles(directory=frontend,html=True),name='frontend')

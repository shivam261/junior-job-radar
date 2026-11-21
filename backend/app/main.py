import asyncio
import json
import re
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, HTTPException, Query, Depends
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
from . import config, db, auth, accounts, notifications
from .service import RefreshService
from .sources import public_url, identify

service = RefreshService()


@asynccontextmanager
async def lifespan(app):
    config.validate()
    db.initialize()
    auth.bootstrap_admin()
    scheduler = asyncio.create_task(service.scheduler())
    mailer = asyncio.create_task(notifications.scheduler())
    try:
        yield
    finally:
        scheduler.cancel()
        mailer.cancel()
        await asyncio.gather(scheduler, mailer, return_exceptions=True)
        await service.close()


app = FastAPI(title='Launchpad — Early-career jobs',version='2.0.0',lifespan=lifespan,
              docs_url=None, redoc_url=None, openapi_url=None)
app.middleware('http')(auth.protect_api)
app.include_router(auth.router)
app.include_router(accounts.router)


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
async def add_company(request: NewCompany, user=Depends(auth.require_admin)):
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
def company_settings(company_id: str, settings: CompanySettings, user=Depends(auth.require_admin)):
    with db.connection() as conn:
        cur=conn.execute('UPDATE companies SET enabled=? WHERE id=?',(int(settings.enabled),company_id))
        if not cur.rowcount: raise HTTPException(404,'Company not found')
    return {'enabled':settings.enabled}


@app.get('/api/jobs')
def jobs(q: str='', location: str='', company: str='', confidence: str='', mode: str='',
         saved: bool=False, demo: bool=False, status: str=Query('open',pattern='^(open|closed|all)$'), sort: str=Query('newest',pattern='^(newest|company|relevance)$'),
         page: int=Query(1,ge=1), page_size: int=Query(12,ge=1,le=100), user=Depends(auth.current_user)):
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
    base='FROM jobs j JOIN companies c ON c.id=j.company_id LEFT JOIN user_bookmarks b ON b.job_id=j.id AND b.user_id=? WHERE '+ ' AND '.join(where)
    params=[user['id'],*params]
    order={'newest':'COALESCE(j.posted_at,j.first_seen) DESC,j.id','company':'c.name,j.title,j.id','relevance':"CASE WHEN j.confidence='confirmed' THEN 0 ELSE 1 END,COALESCE(j.posted_at,j.first_seen) DESC,j.id"}[sort]
    with db.connection() as conn:
        total=conn.execute('SELECT COUNT(*) '+base,params).fetchone()[0]
        rows=conn.execute('SELECT j.*,c.name AS company,c.sector,c.adapter,c.status AS source_status,c.last_success AS source_last_success,(b.job_id IS NOT NULL) AS saved '+base+' ORDER BY '+order+' LIMIT ? OFFSET ?',params+[page_size,(page-1)*page_size]).fetchall()
    return {'items':[db.serialize_job(r) for r in rows],'total':total,'page':page,'page_size':page_size}


@app.get('/api/jobs/{job_id}')
def job_details(job_id: str, user=Depends(auth.current_user)):
    with db.connection() as conn:
        row=conn.execute('SELECT j.*,c.name AS company,c.sector,c.adapter,c.status AS source_status,c.last_success AS source_last_success,(b.job_id IS NOT NULL) AS saved FROM jobs j JOIN companies c ON c.id=j.company_id LEFT JOIN user_bookmarks b ON b.job_id=j.id AND b.user_id=? WHERE j.id=?',(user['id'],job_id)).fetchone()
    if not row: raise HTTPException(404,'Job not found')
    return db.serialize_job(row)


@app.put('/api/bookmarks/{job_id}')
def save(job_id: str, user=Depends(auth.current_user)):
    with db.connection() as conn:
        if not conn.execute('SELECT id FROM jobs WHERE id=?',(job_id,)).fetchone(): raise HTTPException(404,'Job not found')
        conn.execute('INSERT OR IGNORE INTO user_bookmarks(user_id,job_id,saved_at) VALUES(?,?,?)',(user['id'],job_id,db.now()))
    return {'saved':True}


@app.delete('/api/bookmarks/{job_id}')
def unsave(job_id: str, user=Depends(auth.current_user)):
    with db.connection() as conn: conn.execute('DELETE FROM user_bookmarks WHERE job_id=? AND user_id=?',(job_id,user['id']))
    return {'saved':False}


@app.get('/api/stats')
def stats(demo: bool=False, user=Depends(auth.current_user)):
    with db.connection() as conn:
        def count(sql, args=()): return conn.execute(sql,args).fetchone()[0]
        scope='active=1 AND demo=?'
        total=count('SELECT COUNT(*) FROM jobs WHERE '+scope,(int(demo),))
        confirmed=count("SELECT COUNT(*) FROM jobs WHERE "+scope+" AND confidence='confirmed'",(int(demo),))
        saved=count('SELECT COUNT(*) FROM user_bookmarks b JOIN jobs j ON j.id=b.job_id WHERE j.demo=? AND b.user_id=?',(int(demo),user['id']))
        recent=count("SELECT COUNT(*) FROM jobs WHERE "+scope+" AND julianday(first_seen)>=julianday('now','-7 days')",(int(demo),))
        healthy=count("SELECT COUNT(*) FROM companies WHERE status='healthy'")
        tracked=count('SELECT COUNT(*) FROM companies WHERE enabled=1')
        run=conn.execute('SELECT * FROM runs ORDER BY started_at DESC LIMIT 1').fetchone()
        return dict(total=total,confirmed=confirmed,saved=saved,new_this_week=recent,healthy_sources=healthy,tracked_companies=tracked,total_companies=count('SELECT COUNT(*) FROM companies'),latest_run=dict(run) if run else None)


class RefreshRequest(BaseModel):
    company_id: str | None = None


@app.post('/api/refresh',status_code=202)
async def refresh(request: RefreshRequest, user=Depends(auth.require_admin)):
    if request.company_id:
        with db.connection() as conn:
            row=conn.execute('SELECT enabled FROM companies WHERE id=?',(request.company_id,)).fetchone()
            if not row: raise HTTPException(404,'Company not found')
            if not row['enabled']: raise HTTPException(400,'Enable this company before refreshing')
    run_id, started=service.start(request.company_id)
    return {'run_id':run_id,'started':started}


@app.get('/api/runs')
def runs(user=Depends(auth.require_admin)):
    with db.connection() as conn:
        return [dict(r) for r in conn.execute('SELECT * FROM runs ORDER BY started_at DESC LIMIT 20')]


# One-host production deployment after building React. API routes retain /api.
frontend=Path(__file__).resolve().parents[2]/'frontend'/'dist'
if frontend.exists():
    app.mount('/', StaticFiles(directory=frontend,html=True),name='frontend')

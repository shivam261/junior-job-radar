from fastapi.testclient import TestClient
from app.main import app
from app.collectors import normalize
from app.companies import COMPANIES


def add_job(database,title='Software Engineer I',location='Pune, India',source='123'):
    job=normalize(COMPANIES[0],source,title,location,'Required: 1–2 years of professional experience. Python and React.','https://autodesk.wd1.myworkdayjobs.com/Ext/job/test')
    database.upsert_jobs('autodesk',[job],False)
    return job


def test_registry_and_search(database):
    add_job(database)
    with TestClient(app) as client:
        assert len(client.get('/api/companies').json())>=61
        assert client.get('/api/jobs?q=Python&location=India').json()['total']==1
        assert client.get('/api/jobs?location=London').json()['total']==0
        assert client.get('/api/jobs?q=%25').json()['total']==0
        assert client.get('/api/jobs?sort=invalid').status_code==422
        assert client.get('/api/jobs?page=0').status_code==422


def test_bookmarks_persist_and_idempotent(database):
    job=add_job(database)
    with TestClient(app) as client:
        assert client.put('/api/bookmarks/'+job['id']).status_code==200
        client.put('/api/bookmarks/'+job['id'])
        assert client.get('/api/jobs?saved=true').json()['total']==1
        assert client.get('/api/stats').json()['saved']==1
        assert client.get('/api/jobs/'+job['id']).json()['saved'] is True
    with TestClient(app) as client:
        assert client.get('/api/jobs?saved=true').json()['total']==1
        client.delete('/api/bookmarks/'+job['id'])
        assert client.get('/api/jobs?saved=true').json()['total']==0
        assert client.put('/api/bookmarks/missing').status_code==404


def test_snapshot_lifecycle(database):
    job=add_job(database)
    database.upsert_jobs('autodesk',[],False)
    with TestClient(app) as client:
        assert client.get('/api/jobs').json()['total']==1
        client.put('/api/bookmarks/'+job['id'])
        database.upsert_jobs('autodesk',[],True)
        assert client.get('/api/jobs').json()['total']==0
        assert client.get('/api/jobs/'+job['id']).json()['active'] is False
        database.upsert_jobs('autodesk',[job],True)
        assert client.get('/api/jobs').json()['total']==1
        assert client.get('/api/jobs/'+job['id']).json()['saved'] is True


def test_demo_isolation(database):
    job=add_job(database)
    with database.connection() as conn: conn.execute('UPDATE jobs SET demo=1 WHERE id=?',(job['id'],))
    with TestClient(app) as client:
        assert client.get('/api/jobs').json()['total']==0
        assert client.get('/api/jobs?demo=true').json()['total']==1
        assert client.get('/api/stats').json()['total']==0


def test_company_settings_and_missing_ids(database):
    with TestClient(app) as client:
        assert client.patch('/api/companies/autodesk',json={'enabled':False}).json()['enabled'] is False
        assert client.post('/api/refresh',json={'company_id':'autodesk'}).status_code==400
        assert client.post('/api/refresh',json={'company_id':'missing'}).status_code==404
        assert client.get('/api/jobs/missing').status_code==404


def test_location_aliases_and_country_boundaries(database):
    first=add_job(database,location='Bangalore, IND',source='bangalore')
    second=add_job(database,location='Indianapolis, United States',source='indianapolis')
    with TestClient(app) as client:
        assert client.get('/api/jobs?location=Bengaluru').json()['total']==1
        assert client.get('/api/jobs?location=India').json()['total']==1


def test_add_company_detects_source_and_persists(database):
    with TestClient(app) as client:
        payload={'name':'Acme Systems','url':'https://job-boards.greenhouse.io/acmesystems','refresh':False}
        response=client.post('/api/companies',json=payload)
        assert response.status_code==201
        c=response.json()
        assert c['adapter']=='greenhouse' and c['custom']==1 and not c['refresh_queued']
        assert client.post('/api/companies',json=payload).status_code==409
        assert client.post('/api/companies',json={**payload,'url':'https://localhost/careers'}).status_code==422
        custom_id=c['id']
    with TestClient(app) as client:
        assert any(c['id']==custom_id for c in client.get('/api/companies').json())


def test_closed_saved_jobs_remain_visible_and_reopen(database):
    job=add_job(database)
    with TestClient(app) as client:
        client.put('/api/bookmarks/'+job['id'])
        database.upsert_jobs('autodesk',[],True,source_ids=set())
        assert client.get('/api/jobs').json()['total']==0
        archive=client.get('/api/jobs?saved=true&status=all').json()
        assert archive['total']==1
        row=archive['items'][0]
        assert row['closed_at'] and row['closed_reason']=='removed' and not row['active']
        assert client.get('/api/jobs?saved=true&status=closed').json()['total']==1
        timestamp=row['closed_at']
        database.upsert_jobs('autodesk',[],True,source_ids=set())
        assert client.get('/api/jobs/'+job['id']).json()['closed_at']==timestamp
        database.upsert_jobs('autodesk',[job],True,source_ids={job['source_id']})
        row=client.get('/api/jobs/'+job['id']).json()
        assert row['active'] and row['closed_at'] is None and row['saved']
        assert client.get('/api/jobs?status=bad').status_code==422


def test_no_longer_matching_is_distinct_from_removed(database):
    job=add_job(database)
    database.upsert_jobs('autodesk',[],True,source_ids={job['source_id']})
    with TestClient(app) as client:
        assert client.get('/api/jobs/'+job['id']).json()['closed_reason']=='no_longer_matches'


def test_india_country_code_matches(database):
    add_job(database,location='Remote, IN',source='country-code')
    add_job(database,location='Remote in United States',source='preposition')
    with TestClient(app) as client:
        assert client.get('/api/jobs?location=India').json()['total']==1

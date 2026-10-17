import asyncio
import pytest
from app import db
from app.service import RefreshService
from app.collectors import SourceError, normalize
from app.companies import COMPANIES

@pytest.mark.asyncio
async def test_failure_retains_last_snapshot_and_records_failure(database,monkeypatch):
    job=normalize(COMPANIES[0],'one','Software Engineer I','Pune, India','Required: 1–2 years of experience.','https://example.com/job/one')
    db.upsert_jobs('autodesk',[job],True)
    async def fail(self,c): raise SourceError('Employer source returned HTTP 403.')
    monkeypatch.setattr('app.service.Collector.collect',fail)
    worker=RefreshService()
    run_id,_=worker.start('autodesk')
    await worker.task
    with db.connection() as conn:
        assert conn.execute('SELECT active FROM jobs').fetchone()[0]==1
        row=conn.execute('SELECT * FROM companies WHERE id="autodesk"').fetchone()
        assert row['status']=='error'
        assert row['last_success'] is not None
        assert conn.execute('SELECT failed FROM runs WHERE id=?',(run_id,)).fetchone()[0]==1

@pytest.mark.asyncio
async def test_concurrent_refresh_reuses_existing_run(database,monkeypatch):
    event=asyncio.Event()
    async def wait(self,c):
        await event.wait()
        raise SourceError('Test source unavailable')
    monkeypatch.setattr('app.service.Collector.collect',wait)
    worker=RefreshService()
    first,started=worker.start('autodesk')
    second,again=worker.start('cisco')
    assert started and not again and first==second
    event.set()
    await worker.task


def test_demo_seed_does_not_change_live_health(database):
    from app.demo import seed
    job=normalize(COMPANIES[0],'live','Software Engineer I','Pune, India','1–2 years of experience.','https://example.com/live')
    db.upsert_jobs('autodesk',[job],True)
    seed()
    with db.connection() as conn:
        assert conn.execute('SELECT status FROM companies WHERE id="autodesk"').fetchone()[0]=='healthy'
        assert conn.execute('SELECT COUNT(*) FROM jobs WHERE demo=0 AND active=1').fetchone()[0]==1
        assert conn.execute('SELECT COUNT(*) FROM jobs WHERE demo=1').fetchone()[0]==16

@pytest.mark.asyncio
async def test_new_company_is_queued_after_running_refresh(database,monkeypatch):
    from app.collectors import Snapshot
    entered=asyncio.Event()
    finish=asyncio.Event()
    calls=[]
    async def collect(self,c):
        calls.append(c['id'])
        if c['id']=='autodesk':
            entered.set()
            await finish.wait()
        return Snapshot([])
    monkeypatch.setattr('app.service.Collector.collect',collect)
    worker=RefreshService()
    worker.start('autodesk')
    await entered.wait()
    worker.enqueue('cisco')
    await asyncio.sleep(0)
    assert calls==['autodesk']
    finish.set()
    await worker.queue_task
    assert calls==['autodesk','cisco']
    await worker.close()


@pytest.mark.asyncio
async def test_partial_atlassian_refresh_saves_matches_and_preserves_old_jobs(database,monkeypatch):
    from app.collectors import Snapshot
    company=next(c for c in COMPANIES if c['id']=='atlassian')
    old=normalize(company,'old','Graduate Software Engineer','India','0–2 years of experience.','https://www.atlassian.com/company/careers/details/old')
    new=normalize(company,'new','Graduate Software Engineer','India','0–2 years of experience.','https://www.atlassian.com/company/careers/details/new')
    db.upsert_jobs('atlassian',[old],True)
    with db.connection() as conn:
        conn.execute('INSERT INTO bookmarks(job_id,saved_at) VALUES(?,?)',(old['id'],db.now()))
    warning='Atlassian: 1 of 2 candidate job details could not be read. Earlier jobs were retained.'
    async def collect(self,c):return Snapshot([new],False,{'new'},warning)
    monkeypatch.setattr('app.service.Collector.collect',collect)
    worker=RefreshService()
    worker.start('atlassian')
    await worker.task
    with db.connection() as conn:
        source=conn.execute("SELECT * FROM companies WHERE id='atlassian'").fetchone()
        assert source['status']=='partial' and source['error']==warning and source['last_count']==1
        assert conn.execute("SELECT COUNT(*) FROM jobs WHERE company_id='atlassian' AND active=1").fetchone()[0]==2
        assert conn.execute('SELECT job_id FROM bookmarks').fetchone()[0]==old['id']

import asyncio
import logging
import os
import uuid
from . import db
from .collectors import Collector, http_client

log = logging.getLogger(__name__)


class RefreshService:
    def __init__(self):
        self.task = None
        self.run_id = None
        self.pending_companies = set()
        self.queue_task = None

    def start(self, company_id=None):
        if self.task and not self.task.done():
            return self.run_id, False
        companies = db.company_rows(enabled_only=True)
        if company_id:
            companies = [c for c in companies if c['id'] == company_id]
        self.run_id = uuid.uuid4().hex
        with db.connection() as conn:
            conn.execute("INSERT INTO runs(id,started_at,status,total) VALUES(?,?,?,?)", (self.run_id,db.now(),'running',len(companies)))
        self.task = asyncio.create_task(self.run(self.run_id, companies))
        return self.run_id, True

    def enqueue(self,company_id):
        self.pending_companies.add(company_id)
        if not self.queue_task or self.queue_task.done():
            self.queue_task=asyncio.create_task(self.drain_queue())

    async def drain_queue(self):
        while self.pending_companies:
            if self.task and not self.task.done():
                await asyncio.gather(self.task,return_exceptions=True)
            company_id=self.pending_companies.pop()
            self.start(company_id)
            if self.task:await asyncio.gather(self.task,return_exceptions=True)

    async def run(self, run_id, companies):
        gate = asyncio.Semaphore(4)
        try:
            async with http_client() as client:
                collector = Collector(client)
                async def collect_one(company):
                    async with gate:
                        with db.connection() as conn:
                            conn.execute("UPDATE companies SET status='refreshing' WHERE id=?",(company['id'],))
                        try:
                            snapshot = await collector.collect(company)
                            db.upsert_jobs(company['id'], snapshot.jobs, snapshot.complete,snapshot.source_ids,snapshot.warning)
                            success, count = 1, len(snapshot.jobs)
                        except Exception as exc:
                            log.warning("Collection failed for %s: %s",company['name'],exc)
                            message = str(exc) if str(exc) else type(exc).__name__
                            with db.connection() as conn:
                                conn.execute("UPDATE companies SET status='error',last_checked=?,error=? WHERE id=?",(db.now(),message[:500],company['id']))
                            success, count = 0, 0
                        with db.connection() as conn:
                            conn.execute('''UPDATE runs SET completed=completed+1,succeeded=succeeded+?,failed=failed+?,matched=matched+? WHERE id=?''',(success,1-success,count,run_id))
                await asyncio.gather(*(collect_one(c) for c in companies))
            with db.connection() as conn:
                conn.execute("UPDATE runs SET status=CASE WHEN failed=0 THEN 'complete' ELSE 'completed_with_errors' END,finished_at=? WHERE id=?",(db.now(),run_id))
        except asyncio.CancelledError:
            with db.connection() as conn:
                conn.execute("UPDATE runs SET status='interrupted',finished_at=? WHERE id=?",(db.now(),run_id))
                conn.execute("UPDATE companies SET status='pending' WHERE status='refreshing'")
            raise
        except Exception:
            log.exception('Refresh worker failed')
            with db.connection() as conn:
                conn.execute("UPDATE runs SET status='failed',finished_at=? WHERE id=?",(db.now(),run_id))
                conn.execute("UPDATE companies SET status='error',error='Refresh worker stopped unexpectedly' WHERE status='refreshing'")

    async def scheduler(self):
        interval=max(300,int(os.getenv('REFRESH_INTERVAL_SECONDS','21600')))
        if os.getenv('AUTO_REFRESH','true').lower() == 'true' and os.getenv('REFRESH_ON_STARTUP','true').lower() == 'true':
            self.start()
        while True:
            await asyncio.sleep(interval)
            if os.getenv('AUTO_REFRESH','true').lower() == 'true': self.start()

    async def close(self):
        if self.queue_task and not self.queue_task.done():
            self.queue_task.cancel()
            await asyncio.gather(self.queue_task,return_exceptions=True)
        if self.task and not self.task.done():
            self.task.cancel()
            await asyncio.gather(self.task,return_exceptions=True)

"""One-off live sync: python -m app.refresh [company-id ...]."""
import asyncio
import sys
import uuid
from . import db
from .service import RefreshService


async def main():
    db.initialize()
    companies=db.company_rows(enabled_only=True)
    if len(sys.argv)>1: companies=[c for c in companies if c['id'] in sys.argv[1:]]
    service=RefreshService()
    run_id=uuid.uuid4().hex
    with db.connection() as conn:
        conn.execute('INSERT INTO runs(id,started_at,status,total) VALUES(?,?,?,?)',(run_id,db.now(),'running',len(companies)))
    await service.run(run_id,companies)
    with db.connection() as conn:
        print(dict(conn.execute('SELECT * FROM runs WHERE id=?',(run_id,)).fetchone()))
    for company in db.company_rows():
        if company['last_checked']: print(company['name'], company['status'], company['job_count'], company['error'] or '')


if __name__=='__main__': asyncio.run(main())

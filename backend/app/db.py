import json
import os
import re
import sqlite3
from pathlib import Path
from contextlib import contextmanager
from datetime import datetime, timezone
from .companies import COMPANIES

DB_PATH = os.getenv("DATABASE_PATH", str(Path(__file__).resolve().parents[1] / "data" / "jobs.sqlite3"))


def now():
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def connection():
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH, timeout=30)
    db.row_factory = sqlite3.Row
    db.create_function("REGEXP",2,lambda pattern,value: bool(re.search(pattern,value or "",re.I)),deterministic=True)
    db.execute("PRAGMA foreign_keys=ON")
    try:
        yield db
        db.commit()
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()


def initialize(mark_interrupted=True):
    with connection() as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.executescript('''
        CREATE TABLE IF NOT EXISTS companies (
          id TEXT PRIMARY KEY, name TEXT NOT NULL, sector TEXT, adapter TEXT, url TEXT,
          config TEXT, enabled INTEGER NOT NULL DEFAULT 1, status TEXT DEFAULT 'pending',
          last_checked TEXT, last_success TEXT, error TEXT, last_count INTEGER DEFAULT 0, custom INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS jobs (
          id TEXT PRIMARY KEY, company_id TEXT REFERENCES companies(id), source_id TEXT,
          title TEXT NOT NULL, location TEXT, description TEXT, url TEXT NOT NULL,
          experience_min REAL, experience_max REAL, confidence TEXT, evidence TEXT,
          skills TEXT, work_mode TEXT, employment_type TEXT, posted_at TEXT,
          first_seen TEXT, last_seen TEXT, active INTEGER DEFAULT 1, demo INTEGER DEFAULT 0, closed_at TEXT, closed_reason TEXT,
          UNIQUE(company_id, source_id));
        CREATE INDEX IF NOT EXISTS jobs_active ON jobs(active, company_id, confidence);
        CREATE TABLE IF NOT EXISTS bookmarks (job_id TEXT PRIMARY KEY REFERENCES jobs(id) ON DELETE CASCADE, saved_at TEXT);
        CREATE TABLE IF NOT EXISTS runs (
          id TEXT PRIMARY KEY, started_at TEXT, finished_at TEXT, status TEXT,
          total INTEGER, completed INTEGER DEFAULT 0, succeeded INTEGER DEFAULT 0,
          failed INTEGER DEFAULT 0, matched INTEGER DEFAULT 0);
        ''')
        # Additive migrations preserve existing live jobs and saved jobs.
        for table,column,definition in [('companies','custom','INTEGER DEFAULT 0'),('jobs','closed_at','TEXT'),('jobs','closed_reason','TEXT')]:
            if column not in {r[1] for r in db.execute(f'PRAGMA table_info({table})')}:
                db.execute(f'ALTER TABLE {table} ADD COLUMN {column} {definition}')
        for c in COMPANIES:
            db.execute('''INSERT INTO companies(id,name,sector,adapter,url,config) VALUES(?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET name=excluded.name,sector=excluded.sector,
            adapter=excluded.adapter,url=excluded.url,config=excluded.config WHERE companies.custom=0''',
            (c['id'], c['name'], c['sector'], c['adapter'], c['url'], json.dumps(c['config'])))
        # A process restart must not leave refresh history stuck in "running".
        if mark_interrupted:
            db.execute("UPDATE runs SET status='interrupted',finished_at=? WHERE status='running'", (now(),))
            db.execute("UPDATE companies SET status='pending' WHERE status='refreshing'")


def company_rows(enabled_only=False):
    with connection() as db:
        return [dict(r) for r in db.execute('''SELECT c.*, (SELECT COUNT(*) FROM jobs j WHERE
          j.company_id=c.id AND j.active=1 AND j.demo=0) AS job_count FROM companies c ''' +
          ("WHERE enabled=1 " if enabled_only else "") + "ORDER BY name COLLATE NOCASE")]


def upsert_jobs(company_id, jobs, complete,source_ids=None,warning=None):
    timestamp = now()
    with connection() as db:
        # Retire only after a fully successful, authoritative snapshot.
        if complete:
            identifiers=sorted(source_ids or [])
            if identifiers:
                marks=','.join('?' for _ in identifiers)
                db.execute(f"UPDATE jobs SET active=0,closed_at=COALESCE(closed_at,?),closed_reason=CASE WHEN source_id IN ({marks}) THEN 'no_longer_matches' ELSE 'removed' END WHERE company_id=? AND demo=0 AND active=1",[timestamp,*identifiers,company_id])
            else:
                db.execute("UPDATE jobs SET active=0,closed_at=COALESCE(closed_at,?),closed_reason='removed' WHERE company_id=? AND demo=0 AND active=1", (timestamp,company_id))
        for j in jobs:
            fields = ["id", "company_id", "source_id", "title", "location", "description", "url", "experience_min", "experience_max", "confidence", "evidence", "skills", "work_mode", "employment_type", "posted_at", "first_seen", "last_seen", "active", "demo"]
            values = {**j, 'company_id': company_id, 'first_seen': timestamp, 'last_seen': timestamp, 'active': 1, 'demo': 0}
            values['skills'] = json.dumps(values['skills'])
            updates = 'closed_at=NULL,closed_reason=NULL,' + ','.join(f"{k}=excluded.{k}" for k in fields if k not in ('id', 'company_id', 'source_id', 'first_seen', 'demo'))
            db.execute(f"INSERT INTO jobs({','.join(fields)}) VALUES({','.join('?' for _ in fields)}) ON CONFLICT(company_id,source_id) DO UPDATE SET {updates}", [values.get(f) for f in fields])
        db.execute("UPDATE companies SET status=?,last_checked=?,last_success=?,error=?,last_count=? WHERE id=?",
            ('healthy' if complete else 'partial', timestamp, timestamp,
             None if complete else (warning or 'This page exposes only a partial snapshot. Older listings are retained; check the employer site for complete coverage.')[:500], len(jobs), company_id))


def serialize_job(row):
    result = dict(row)
    result['skills'] = json.loads(result['skills'] or '[]')
    result['saved'] = bool(result.get('saved', 0))
    result['active'] = bool(result['active'])
    result['demo'] = bool(result['demo'])
    return result

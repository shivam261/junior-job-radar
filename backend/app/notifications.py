"""Per-account Gmail digests. A single EC2 worker owns collection and delivery."""
import asyncio
import html
import logging
import os
import smtplib
import ssl
import time
from datetime import datetime
from email.message import EmailMessage
from urllib.parse import urlsplit
from . import config, db

log = logging.getLogger(__name__)


def build_digest(user, jobs):
    message = EmailMessage()
    message['From'] = os.environ['GMAIL_ADDRESS']
    message['To'] = user['email']
    message['Subject'] = f'Launchpad: {len(jobs)} new job opportunities'
    lines = ['New jobs matching your Launchpad email preferences:', '']
    rows = []
    for job in jobs:
        title, company, location = (str(job[key] or '') for key in ('title', 'company', 'location'))
        url = job['url']
        if urlsplit(url).scheme not in ('http', 'https'):
            continue
        lines.extend([f'{title} — {company}', location, url, ''])
        rows.append(f'<li><a href="{html.escape(url, quote=True)}">{html.escape(title)}</a>'
                    f'<br>{html.escape(company)} · {html.escape(location)}</li>')
    account_url = config.app_url() + '/#account'
    lines.append(f'Manage or unsubscribe from job emails: {account_url}')
    message.set_content('\n'.join(lines))
    message.add_alternative('<h2>Your latest job opportunities</h2><ul>' + ''.join(rows) +
                            '</ul><p><a href="' + html.escape(account_url, quote=True) +
                            '">Manage email preferences or unsubscribe</a></p>', subtype='html')
    return message


def send_message(message):
    # Only Google's authenticated TLS endpoint is used; no user-controlled SMTP host.
    with smtplib.SMTP_SSL('smtp.gmail.com', 465, context=ssl.create_default_context(), timeout=30) as smtp:
        smtp.login(os.environ['GMAIL_ADDRESS'], os.environ['GMAIL_APP_PASSWORD'].replace(' ', ''))
        smtp.send_message(message)


def pending_jobs(user):
    clauses = ['j.active=1', 'j.demo=0', 'j.first_seen>=?', 'd.job_id IS NULL']
    params = [user['id'], user['alerts_since']]
    for word in user['alert_keywords'].lower().split():
        clauses.append("instr(lower(j.title || ' ' || COALESCE(j.description,'')),?)>0")
        params.append(word)
    if user['alert_location'].strip():
        clauses.append("instr(lower(COALESCE(j.location,'')),?)>0")
        params.append(user['alert_location'].strip().lower())
    with db.connection() as conn:
        return [dict(row) for row in conn.execute('''SELECT j.*,c.name AS company FROM jobs j
            JOIN companies c ON c.id=j.company_id
            LEFT JOIN email_deliveries d ON d.job_id=j.id AND d.user_id=? WHERE ''' +
            ' AND '.join(clauses) + ' ORDER BY j.first_seen DESC,j.id LIMIT 100', params)]


async def send_due():
    if not config.mail_configured():
        return 0
    with db.connection() as conn:
        # Wait for the collection to finish so a digest combines company results.
        if conn.execute("SELECT 1 FROM runs WHERE status='running'").fetchone():
            return 0
        users = [dict(row) for row in conn.execute('''SELECT * FROM users WHERE active=1
            AND alerts_enabled=1 AND email IS NOT NULL AND email_retry_at<=?''', (time.time(),))]
    sent = 0
    for user in users:
        if user['last_email_at'] and time.time() - datetime.fromisoformat(user['last_email_at']).timestamp() < user['alert_interval']:
            continue
        jobs = pending_jobs(user)
        if not jobs:
            continue
        try:
            # Recheck consent/active status immediately before delivery.
            with db.connection() as conn:
                enabled = conn.execute('SELECT active AND alerts_enabled FROM users WHERE id=?', (user['id'],)).fetchone()
            if not enabled or not enabled[0]:
                continue
            await asyncio.to_thread(send_message, build_digest(user, jobs))
        except Exception as exc:
            # Do not log SMTP payloads, recipients, or authentication responses.
            log.warning('Email digest failed (%s)', type(exc).__name__)
            with db.connection() as conn:
                conn.execute('UPDATE users SET email_error=?,email_retry_at=? WHERE id=?',
                             ('Email could not be delivered. The service will retry.', time.time() + 900, user['id']))
            continue
        timestamp = db.now()
        with db.connection() as conn:
            conn.executemany('INSERT OR IGNORE INTO email_deliveries VALUES(?,?,?)',
                             [(user['id'], job['id'], timestamp) for job in jobs])
            conn.execute('UPDATE users SET last_email_at=?,email_error=NULL,email_retry_at=0 WHERE id=?', (timestamp, user['id']))
        sent += 1
    return sent


async def scheduler():
    while True:
        await asyncio.sleep(60)
        try:
            await send_due()
        except Exception:
            log.exception('Email scheduler failed; retrying on the next tick')

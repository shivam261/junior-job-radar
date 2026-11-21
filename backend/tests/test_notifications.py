import time
import pytest
from app import auth, db, notifications
from test_api import add_job


@pytest.fixture
def mail_user(database, monkeypatch):
    monkeypatch.setenv('GMAIL_ADDRESS', 'sender@gmail.com')
    monkeypatch.setenv('GMAIL_APP_PASSWORD', 'test-app-password')
    user_id = auth.google_user({'sub':'alice','email':'alice@example.com','email_verified':True,'nonce':'nonce'}, 'nonce')
    with db.connection() as conn:
        return dict(conn.execute('SELECT * FROM users WHERE id=?', (user_id,)).fetchone())


@pytest.mark.asyncio
async def test_digest_has_jobs_links_and_never_repeats_successful_delivery(mail_user, monkeypatch):
    job = add_job(db)
    sent = []
    monkeypatch.setattr(notifications, 'send_message', sent.append)
    assert await notifications.send_due() == 1
    assert len(sent) == 1 and sent[0]['To'] == 'alice@example.com'
    plain = sent[0].get_body(preferencelist=('plain',)).get_content()
    assert job['title'] in plain and job['url'] in plain and 'unsubscribe' in plain
    with db.connection() as conn:
        conn.execute('UPDATE users SET last_email_at=NULL')
    assert await notifications.send_due() == 0
    assert len(sent) == 1


@pytest.mark.asyncio
async def test_failure_keeps_jobs_pending_and_backs_off_then_retries(mail_user, monkeypatch):
    add_job(db)
    def fail(message):
        raise RuntimeError('SMTP credentials should never appear in user-visible errors')
    monkeypatch.setattr(notifications, 'send_message', fail)
    assert await notifications.send_due() == 0
    with db.connection() as conn:
        assert conn.execute('SELECT COUNT(*) FROM email_deliveries').fetchone()[0] == 0
        row = conn.execute('SELECT * FROM users').fetchone()
        assert row['email_retry_at'] > time.time()
        assert 'credentials' not in row['email_error']
    sent = []
    monkeypatch.setattr(notifications, 'send_message', sent.append)
    assert await notifications.send_due() == 0
    with db.connection() as conn:
        conn.execute('UPDATE users SET email_retry_at=0')
    assert await notifications.send_due() == 1
    with db.connection() as conn:
        assert conn.execute('SELECT email_error FROM users').fetchone()[0] is None


@pytest.mark.asyncio
async def test_no_mail_without_consent_credentials_or_matches(mail_user, monkeypatch):
    sent = []
    monkeypatch.setattr(notifications, 'send_message', sent.append)
    assert await notifications.send_due() == 0
    add_job(db)
    with db.connection() as conn:
        conn.execute('UPDATE users SET alerts_enabled=0')
    assert await notifications.send_due() == 0
    with db.connection() as conn:
        conn.execute('UPDATE users SET alerts_enabled=1,active=0')
    assert await notifications.send_due() == 0
    with db.connection() as conn:
        conn.execute('UPDATE users SET active=1')
    monkeypatch.setenv('GMAIL_APP_PASSWORD', '')
    assert await notifications.send_due() == 0
    assert not sent


@pytest.mark.asyncio
async def test_filters_old_jobs_demo_closed_and_interval_isolation(database, monkeypatch):
    old = add_job(db, source='old')
    user = auth.google_user({'sub':'alice','email':'alice@example.com','email_verified':True,'nonce':'n'}, 'n')
    monkeypatch.setenv('GMAIL_ADDRESS', 'sender@gmail.com')
    monkeypatch.setenv('GMAIL_APP_PASSWORD', 'secret')
    wanted = add_job(db, source='wanted')
    other = add_job(db, source='other', location='London')
    demo = add_job(db, source='demo')
    closed = add_job(db, source='closed')
    with db.connection() as conn:
        conn.execute('UPDATE jobs SET demo=1 WHERE id=?', (demo['id'],))
        conn.execute('UPDATE jobs SET active=0 WHERE id=?', (closed['id'],))
        conn.execute("UPDATE users SET alert_keywords='Python React',alert_location='India' WHERE id=?", (user,))
    sent = []
    monkeypatch.setattr(notifications, 'send_message', sent.append)
    assert await notifications.send_due() == 1
    text = sent[0].get_body(preferencelist=('plain',)).get_content()
    with db.connection() as conn:
        delivered = {r[0] for r in conn.execute('SELECT job_id FROM email_deliveries')}
    assert delivered == {wanted['id']}
    add_job(db, source='new-after-email')
    assert await notifications.send_due() == 0
    assert len(sent) == 1
    with db.connection() as conn:
        conn.execute('UPDATE users SET last_email_at=NULL')
    assert await notifications.send_due() == 1


@pytest.mark.asyncio
async def test_each_user_receives_only_their_matches_and_opt_out_is_respected(mail_user, monkeypatch):
    auth.google_user({'sub':'bob','email':'bob@example.com','email_verified':True,'nonce':'n'}, 'n')
    india = add_job(db, source='india', location='India')
    london = add_job(db, source='london', location='London')
    with db.connection() as conn:
        conn.execute("UPDATE users SET alert_location='India' WHERE google_sub='alice'")
        conn.execute("UPDATE users SET alert_location='London' WHERE google_sub='bob'")
    sent = []
    monkeypatch.setattr(notifications, 'send_message', sent.append)
    assert await notifications.send_due() == 2
    messages = {m['To']: m.get_body(preferencelist=('plain',)).get_content() for m in sent}
    assert india['url'] in messages['alice@example.com']
    # Check delivery ownership directly; helper jobs share an employer URL.
    with db.connection() as conn:
        rows = conn.execute('SELECT u.email,d.job_id FROM email_deliveries d JOIN users u ON u.id=d.user_id').fetchall()
    assert {(r['email'],r['job_id']) for r in rows} == {('alice@example.com',india['id']),('bob@example.com',london['id'])}


def test_html_digest_escapes_provider_content(mail_user, monkeypatch):
    job = {'title':'<script>alert(1)</script>', 'company':'A & B', 'location':'<India>', 'url':'https://example.com/job?q="x"'}
    body = notifications.build_digest(mail_user, [job]).get_body(preferencelist=('html',)).get_content()
    assert '<script>' not in body and '&lt;script&gt;' in body and 'A &amp; B' in body


@pytest.mark.asyncio
async def test_digest_waits_for_collection_completion(mail_user, monkeypatch):
    add_job(db)
    sent = []
    monkeypatch.setattr(notifications, 'send_message', sent.append)
    with db.connection() as conn:
        conn.execute("INSERT INTO runs(id,status) VALUES('refresh','running')")
    assert await notifications.send_due() == 0
    with db.connection() as conn:
        conn.execute("UPDATE runs SET status='complete'")
    assert await notifications.send_due() == 1

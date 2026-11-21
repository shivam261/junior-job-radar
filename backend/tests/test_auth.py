import time
from urllib.parse import parse_qs, urlsplit
from fastapi.testclient import TestClient
import pytest
from app import auth, db
from app.main import app
from test_api import add_job


def login_master(client):
    response = client.post('/api/auth/master/login', json={
        'username': 'test-master', 'password': 'test-master-password-123'})
    assert response.status_code == 200
    client.headers['X-CSRF-Token'] = client.cookies[auth.CSRF_COOKIE]
    return response.json()


def login_google(client, monkeypatch, sub='alice', email='alice@example.com', **overrides):
    monkeypatch.setenv('GOOGLE_CLIENT_ID', 'test-client')
    monkeypatch.setenv('GOOGLE_CLIENT_SECRET', 'test-secret')
    start = client.get('/api/auth/google', follow_redirects=False)
    query = parse_qs(urlsplit(start.headers['location']).query)
    async def exchange(code, verifier):
        return {'sub': sub, 'email': email, 'email_verified': True,
                'name': sub.title(), 'nonce': query['nonce'][0], **overrides}
    monkeypatch.setattr(auth, 'exchange_google', exchange)
    response = client.get('/api/auth/google/callback', params={'state': query['state'][0], 'code': 'test-code'}, follow_redirects=False)
    if response.status_code == 303:
        client.headers['X-CSRF-Token'] = client.cookies[auth.CSRF_COOKIE]
    return response


def test_all_data_and_mutations_require_authentication(database):
    with TestClient(app) as client:
        for method, path in [
            ('GET', '/api/jobs'), ('GET', '/api/jobs/example'), ('GET', '/api/companies'),
            ('GET', '/api/stats'), ('GET', '/api/runs'), ('GET', '/api/auth/me'),
            ('GET', '/api/admin/users'), ('GET', '/api/account/email-status'),
            ('POST', '/api/refresh'), ('POST', '/api/companies'),
            ('PATCH', '/api/companies/autodesk'), ('PUT', '/api/bookmarks/example'),
            ('DELETE', '/api/bookmarks/example'), ('PUT', '/api/account/alerts'),
            ('POST', '/api/auth/logout'), ('PATCH', '/api/admin/users/example'),
        ]:
            response = client.request(method, path, json={})
            assert response.status_code == 401, (method, path, response.text)
        assert client.get('/api/health').status_code == 200


def test_csrf_origin_logout_expiry_and_hashed_sessions(database):
    with TestClient(app) as client:
        login_master(client)
        token = client.cookies[auth.SESSION_COOKIE]
        with db.connection() as conn:
            assert conn.execute('SELECT token_hash FROM sessions').fetchone()[0] == auth.digest(token)
        assert client.put('/api/bookmarks/missing', headers={'X-CSRF-Token': ''}).status_code == 403
        assert client.post('/api/auth/logout', headers={'Origin': 'https://attacker.example'}).status_code == 403
        assert client.get('/api/auth/me').status_code == 200
        assert client.post('/api/auth/logout').status_code == 200
        assert client.get('/api/auth/me').status_code == 401
        client.cookies.set(auth.SESSION_COOKIE, token)
        assert client.get('/api/auth/me').status_code == 401
        client.cookies.clear()
        login_master(client)
        with db.connection() as conn:
            conn.execute('UPDATE sessions SET expires_at=?', (time.time() - 1,))
        assert client.get('/api/auth/me').status_code == 401


def test_google_signup_login_and_bookmark_isolation(database, monkeypatch):
    job = add_job(database)
    with TestClient(app) as alice, TestClient(app) as bob:
        assert login_google(alice, monkeypatch).status_code == 303
        alice_id = alice.get('/api/auth/me').json()['id']
        assert alice.put('/api/bookmarks/' + job['id']).status_code == 200
        assert login_google(bob, monkeypatch, 'bob', 'bob@example.com').status_code == 303
        assert bob.get('/api/jobs?saved=true').json()['total'] == 0
        assert bob.get('/api/stats').json()['saved'] == 0
        assert bob.get('/api/jobs/' + job['id']).json()['saved'] is False
        bob.delete('/api/bookmarks/' + job['id'])
        assert alice.get('/api/jobs?saved=true').json()['total'] == 1
        assert alice.get('/api/jobs').json()['total'] == 1  # Joins never duplicate shared jobs.
        bob.put('/api/bookmarks/' + job['id'])
        assert alice.get('/api/jobs').json()['total'] == 1
        assert login_google(alice, monkeypatch).status_code == 303
        assert alice.get('/api/auth/me').json()['id'] == alice_id
        with db.connection() as conn:
            assert conn.execute("SELECT COUNT(*) FROM users WHERE google_sub='alice'").fetchone()[0] == 1


def test_regular_user_cannot_administer_or_modify_other_preferences(database, monkeypatch):
    with TestClient(app) as alice, TestClient(app) as master:
        owner = login_master(master)
        login_google(alice, monkeypatch)
        for method, path in [('GET','/api/admin/users'), ('GET','/api/runs'), ('POST','/api/companies'),
                             ('POST','/api/refresh'), ('PATCH','/api/companies/autodesk'),
                             ('PATCH','/api/admin/users/' + owner['id']), ('PUT','/api/auth/master/credentials')]:
            payload = {'name':'Test Co','url':'https://example.com/careers','enabled':False,
                       'active':False,'current_password':'x','username':'test-master','password':'long-new-password-123'}
            assert alice.request(method, path, json=payload).status_code == 403, path
        before = master.get('/api/auth/me').json()
        response = alice.put('/api/account/alerts', json={'user_id': owner['id'], 'enabled':False, 'keywords':'Python'})
        assert response.status_code == 200
        assert master.get('/api/auth/me').json()['alert_keywords'] == before['alert_keywords']
        assert alice.get('/api/auth/me').json()['alert_keywords'] == 'Python'
        users = master.get('/api/admin/users').json()
        assert len(users) == 2
        assert all('password_hash' not in u and 'google_sub' not in u and 'csrf_hash' not in u for u in users)


def test_disable_revokes_existing_sessions_and_blocks_google_login(database, monkeypatch):
    with TestClient(app) as alice, TestClient(app) as master:
        owner = login_master(master)
        login_google(alice, monkeypatch)
        user_id = alice.get('/api/auth/me').json()['id']
        assert master.patch('/api/admin/users/' + owner['id'], json={'active':False}).status_code == 400
        assert master.patch('/api/admin/users/' + user_id, json={'active':False}).status_code == 200
        assert alice.get('/api/auth/me').status_code == 401
        assert login_google(alice, monkeypatch).status_code == 403
        master.patch('/api/admin/users/' + user_id, json={'active':True})
        assert login_google(alice, monkeypatch).status_code == 303


@pytest.mark.parametrize('claims', [{'email_verified':False}, {'nonce':'wrong'}, {'sub':''}])
def test_invalid_google_identity_cannot_create_accounts(database, monkeypatch, claims):
    with TestClient(app) as client:
        assert login_google(client, monkeypatch, **claims).status_code == 400
        assert client.get('/api/auth/me').status_code == 401


def test_oauth_state_browser_binding_expiry_and_replay(database, monkeypatch):
    monkeypatch.setenv('GOOGLE_CLIENT_ID', 'client')
    monkeypatch.setenv('GOOGLE_CLIENT_SECRET', 'secret')
    with TestClient(app) as client, TestClient(app) as other:
        start = client.get('/api/auth/google', follow_redirects=False)
        query = parse_qs(urlsplit(start.headers['location']).query)
        assert query['scope'] == ['openid email profile']
        assert query['code_challenge_method'] == ['S256']
        callback = '/api/auth/google/callback?state=' + query['state'][0] + '&code=code'
        assert other.get(callback).status_code == 400
        assert client.get('/api/auth/google/callback?state=wrong&code=code').status_code == 400
        with db.connection() as conn:
            conn.execute('UPDATE oauth_flows SET expires_at=0')
        assert client.get(callback).status_code == 400
        assert login_google(client, monkeypatch).status_code == 303
        assert client.get(callback).status_code == 400


def test_same_email_never_promotes_google_account_to_master(database, monkeypatch):
    with TestClient(app) as client:
        assert login_google(client, monkeypatch, email='owner@example.com').status_code == 303
        assert client.get('/api/auth/me').json()['role'] == 'user'
        assert client.get('/api/admin/users').status_code == 403


def test_master_login_rate_limit_and_cross_site_login(database):
    with TestClient(app) as client:
        payload = {'username':'test-master','password':'wrong'}
        assert client.post('/api/auth/master/login', json=payload, headers={'Origin':'https://evil.example'}).status_code == 403
        for _ in range(10):
            assert client.post('/api/auth/master/login', json=payload).status_code == 401
        assert client.post('/api/auth/master/login', json=payload).status_code == 429


def test_master_credential_rotation_revokes_other_sessions_and_survives_restart(database):
    with TestClient(app) as first, TestClient(app) as second:
        login_master(first)
        login_master(second)
        response = first.put('/api/auth/master/credentials', json={
            'current_password':'test-master-password-123','username':'new-master','password':'new-secure-password-123'})
        assert response.status_code == 200
        assert first.get('/api/auth/me').json()['username'] == 'new-master'
        assert second.get('/api/auth/me').status_code == 401
        auth.bootstrap_admin()
        with db.connection() as conn:
            assert conn.execute("SELECT username FROM users WHERE role='admin'").fetchone()[0] == 'new-master'


def test_legacy_bookmarks_belong_only_to_master(database, monkeypatch):
    job = add_job(database)
    with db.connection() as conn:
        conn.execute('INSERT INTO bookmarks VALUES(?,?)', (job['id'], db.now()))
    with TestClient(app) as client:
        login_master(client)
        assert client.get('/api/jobs?saved=true').json()['total'] == 1
        login_google(client, monkeypatch)
        assert client.get('/api/jobs?saved=true').json()['total'] == 0


def test_production_cookies_are_secure_and_secrets_not_exposed(database, monkeypatch):
    monkeypatch.setenv('APP_URL', 'https://radar.shivam-tripathi.com')
    with TestClient(app, base_url='https://radar.shivam-tripathi.com') as client:
        response = client.post('/api/auth/master/login', json={'username':'test-master','password':'test-master-password-123'})
        assert response.status_code == 200
        cookies = response.headers.get_list('set-cookie')
        assert all('Secure' in cookie and 'SameSite=lax' in cookie for cookie in cookies)
        assert 'HttpOnly' in next(c for c in cookies if c.startswith(auth.SESSION_COOKIE))
        assert client.get('/api/auth/config').json() == {'google_enabled':False,'mail_enabled':False}

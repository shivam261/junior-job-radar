"""Google OIDC sign-up/sign-in and revocable server-side sessions."""
import asyncio
import base64
import hashlib
import hmac
import os
import secrets
import time
import uuid
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2 import id_token
from pydantic import BaseModel, Field
from . import config, db

router = APIRouter(prefix='/api/auth', tags=['authentication'])
SESSION_COOKIE = 'launchpad_session'
CSRF_COOKIE = 'launchpad_csrf'
FLOW_COOKIE = 'launchpad_oauth'
SESSION_SECONDS = 7 * 86400
PUBLIC_API = frozenset({
    '/api/health', '/api/auth/config', '/api/auth/google',
    '/api/auth/google/callback', '/api/auth/master/login',
})


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def password_hash(password):
    salt = secrets.token_hex(16)
    value = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()
    return f'scrypt${salt}${value}'


def password_matches(password, encoded):
    try:
        algorithm, salt, expected = encoded.split('$')
        if algorithm != 'scrypt':
            return False
        actual = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def bootstrap_admin():
    username = os.getenv('MASTER_USERNAME', '').strip()
    encoded = os.getenv('MASTER_PASSWORD_HASH', '')
    if not username or not encoded:
        return  # Remains locked until the operator runs scripts/setup_accounts.py.
    timestamp = db.now()
    with db.connection() as conn:
        if conn.execute("SELECT 1 FROM users WHERE role='admin'").fetchone():
            return
        user_id = uuid.uuid4().hex
        conn.execute('''INSERT INTO users(id,username,email,name,role,password_hash,created_at,alerts_since)
            VALUES(?,?,?,?,'admin',?,?,?)''',
            (user_id, username, os.getenv('MASTER_EMAIL') or None, 'Master account', encoded, timestamp, timestamp))
        # Pre-account saves are preserved and assigned only to the operator.
        conn.execute('''INSERT OR IGNORE INTO user_bookmarks(user_id,job_id,saved_at)
            SELECT ?,job_id,COALESCE(saved_at,?) FROM bookmarks''', (user_id, timestamp))


def public_user(user):
    return {key: user[key] for key in (
        'id', 'email', 'username', 'name', 'role', 'active', 'created_at', 'last_login',
        'alerts_enabled', 'alert_interval', 'alert_keywords', 'alert_location', 'last_email_at', 'email_error')}


def current_user(request: Request):
    user = getattr(request.state, 'user', None)
    if not user:
        raise HTTPException(401, 'Please sign in.')
    return user


def require_admin(user=Depends(current_user)):
    if user['role'] != 'admin':
        raise HTTPException(403, 'Master account required.')
    return user


def check_origin(request):
    origin = request.headers.get('origin')
    allowed = {config.app_url()}
    if not config.secure_cookies():
        allowed.update({'http://localhost:5173', 'http://127.0.0.1:5173'})
    if origin and origin not in allowed:
        raise HTTPException(403, 'Request origin is not allowed.')
    if request.headers.get('sec-fetch-site') == 'cross-site':
        raise HTTPException(403, 'Cross-site requests are not allowed.')


async def protect_api(request: Request, call_next):
    path = request.url.path
    try:
        if path.startswith('/api/') and path not in PUBLIC_API:
            token = request.cookies.get(SESSION_COOKIE, '')
            with db.connection() as conn:
                row = conn.execute('''SELECT u.*,s.csrf_hash FROM sessions s
                    JOIN users u ON u.id=s.user_id WHERE s.token_hash=? AND s.expires_at>? AND u.active=1''',
                    (digest(token), time.time())).fetchone()
            if not row:
                raise HTTPException(401, 'Please sign in.')
            request.state.user = dict(row)
            if request.method not in ('GET', 'HEAD', 'OPTIONS'):
                check_origin(request)
                csrf = request.headers.get('x-csrf-token', '')
                if not csrf or not hmac.compare_digest(digest(csrf), row['csrf_hash']):
                    raise HTTPException(403, 'Invalid security token. Reload the page.')
        response = await call_next(request)
    except HTTPException as exc:
        response = JSONResponse({'detail': exc.detail}, status_code=exc.status_code)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'same-origin'
    response.headers['X-Frame-Options'] = 'DENY'
    if path.startswith('/api/'):
        response.headers['Cache-Control'] = 'no-store'
    return response


def create_session(response, user_id, old_token=''):
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    with db.connection() as conn:
        conn.execute('BEGIN IMMEDIATE')
        active = conn.execute('SELECT active FROM users WHERE id=?', (user_id,)).fetchone()
        if not active or not active['active']:
            raise HTTPException(403, 'This account has been disabled.')
        conn.execute('DELETE FROM sessions WHERE expires_at<=? OR token_hash=?', (time.time(), digest(old_token)))
        conn.execute('INSERT INTO sessions VALUES(?,?,?,?)',
                     (digest(token), user_id, digest(csrf), time.time() + SESSION_SECONDS))
        conn.execute('UPDATE users SET last_login=? WHERE id=?', (db.now(), user_id))
    for key, value, httponly in ((SESSION_COOKIE, token, True), (CSRF_COOKIE, csrf, False)):
        response.set_cookie(key, value, max_age=SESSION_SECONDS, httponly=httponly,
                            secure=config.secure_cookies(), samesite='lax', path='/')


@router.get('/config')
def auth_config():
    return {'google_enabled': config.google_configured(), 'mail_enabled': config.mail_configured()}


@router.get('/me')
def me(user=Depends(current_user)):
    return public_user(user)


def rate_limit(bucket, limit=10, window=900):
    now = time.time()
    with db.connection() as conn:
        conn.execute('BEGIN IMMEDIATE')
        conn.execute('DELETE FROM login_attempts WHERE attempted_at<?', (now - window,))
        count = conn.execute('SELECT COUNT(*) FROM login_attempts WHERE bucket=?', (bucket,)).fetchone()[0]
        if count >= limit:
            raise HTTPException(429, 'Too many attempts. Try again in 15 minutes.')
        conn.execute('INSERT INTO login_attempts VALUES(?,?)', (bucket, now))


@router.get('/google')
def google_start(request: Request):
    if not config.google_configured():
        raise HTTPException(503, 'Google sign-in is not configured yet.')
    rate_limit('oauth:' + request.client.host, limit=30)
    state, nonce, verifier = (secrets.token_urlsafe(32) for _ in range(3))
    with db.connection() as conn:
        conn.execute('DELETE FROM oauth_flows WHERE expires_at<=?', (time.time(),))
        conn.execute('INSERT INTO oauth_flows VALUES(?,?,?,?)', (digest(state), nonce, verifier, time.time() + 600))
    query = urlencode({
        'client_id': os.environ['GOOGLE_CLIENT_ID'],
        'redirect_uri': config.app_url() + '/api/auth/google/callback',
        'response_type': 'code', 'scope': 'openid email profile', 'state': state,
        'nonce': nonce, 'code_challenge': base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode(),
        'code_challenge_method': 'S256', 'prompt': 'select_account',
    })
    response = RedirectResponse('https://accounts.google.com/o/oauth2/v2/auth?' + query, status_code=302)
    response.set_cookie(FLOW_COOKIE, state, max_age=600, httponly=True,
                        secure=config.secure_cookies(), samesite='lax', path='/api/auth/google')
    return response


async def exchange_google(code, verifier):
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post('https://oauth2.googleapis.com/token', data={
            'client_id': os.environ['GOOGLE_CLIENT_ID'], 'client_secret': os.environ['GOOGLE_CLIENT_SECRET'],
            'code': code, 'code_verifier': verifier, 'grant_type': 'authorization_code',
            'redirect_uri': config.app_url() + '/api/auth/google/callback',
        })
        response.raise_for_status()
        token = response.json()['id_token']
    # Verify signature, issuer, audience and expiry with Google's maintained library.
    def verify():
        import requests
        with requests.Session() as session:
            def bounded_request(*args, **kwargs):
                kwargs.setdefault('timeout', 20)
                return GoogleRequest(session)(*args, **kwargs)
            return id_token.verify_oauth2_token(token, bounded_request, os.environ['GOOGLE_CLIENT_ID'])
    return await asyncio.to_thread(verify)


def google_user(claims, nonce):
    if (not claims.get('sub') or not claims.get('email') or claims.get('email_verified') is not True
            or not hmac.compare_digest(str(claims.get('nonce', '')), nonce)):
        raise ValueError('Invalid Google identity')
    timestamp = db.now()
    with db.connection() as conn:
        conn.execute('BEGIN IMMEDIATE')
        row = conn.execute('SELECT * FROM users WHERE google_sub=?', (claims['sub'],)).fetchone()
        if row and not row['active']:
            raise HTTPException(403, 'This account has been disabled.')
        if row:
            conn.execute('UPDATE users SET email=?,name=? WHERE id=?',
                         (claims['email'], claims.get('name') or claims['email'], row['id']))
            return row['id']
        user_id = uuid.uuid4().hex
        # Never grant a Google login admin access by matching an email address.
        conn.execute('''INSERT INTO users(id,google_sub,email,name,role,created_at,alerts_since,alerts_enabled)
            VALUES(?,?,?,?,'user',?,?,1)''',
            (user_id, claims['sub'], claims['email'], claims.get('name') or claims['email'], timestamp, timestamp))
        return user_id


@router.get('/google/callback')
async def google_callback(request: Request, state: str = '', code: str = '', error: str = ''):
    cookie = request.cookies.get(FLOW_COOKIE, '')
    if not state or not cookie or not hmac.compare_digest(state, cookie):
        raise HTTPException(400, 'Google sign-in expired or was invalid. Please try again.')
    with db.connection() as conn:
        conn.execute('BEGIN IMMEDIATE')
        flow = conn.execute('SELECT * FROM oauth_flows WHERE state_hash=? AND expires_at>?',
                            (digest(state), time.time())).fetchone()
        conn.execute('DELETE FROM oauth_flows WHERE state_hash=?', (digest(state),))
    if not flow:
        raise HTTPException(400, 'Google sign-in expired or was already used.')
    response = RedirectResponse(config.app_url(), status_code=303)
    response.delete_cookie(FLOW_COOKIE, path='/api/auth/google', secure=config.secure_cookies(), httponly=True, samesite='lax')
    if error or not code:
        return RedirectResponse(config.app_url() + '/?auth_error=cancelled', status_code=303,
                                headers={'set-cookie': response.headers['set-cookie']})
    try:
        claims = await exchange_google(code, flow['verifier'])
        user_id = google_user(claims, flow['nonce'])
    except HTTPException:
        raise
    except Exception:
        # Provider payloads, authorization codes and tokens must not enter logs/responses.
        raise HTTPException(400, 'Could not verify Google sign-in. Please try again.') from None
    create_session(response, user_id, request.cookies.get(SESSION_COOKIE, ''))
    return response


class MasterLogin(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=256)


@router.post('/master/login')
def master_login(payload: MasterLogin, request: Request):
    check_origin(request)
    rate_limit('master-ip:' + request.client.host)
    rate_limit('master-global', limit=30)
    with db.connection() as conn:
        user = conn.execute("SELECT * FROM users WHERE username=? AND role='admin' AND active=1", (payload.username,)).fetchone()
    # A dummy hash keeps nonexistent usernames on the same expensive verification path.
    encoded = user['password_hash'] if user else 'scrypt$' + '00' * 16 + '$' + '00' * 64
    if not password_matches(payload.password, encoded):
        raise HTTPException(401, 'Invalid username or password.')
    response = JSONResponse(public_user(user))
    create_session(response, user['id'], request.cookies.get(SESSION_COOKIE, ''))
    return response


@router.post('/logout')
def logout(request: Request, user=Depends(current_user)):
    with db.connection() as conn:
        conn.execute('DELETE FROM sessions WHERE token_hash=?', (digest(request.cookies.get(SESSION_COOKIE, '')),))
    response = JSONResponse({'signed_out': True})
    for key in (SESSION_COOKIE, CSRF_COOKIE):
        response.delete_cookie(key, path='/', secure=config.secure_cookies(), samesite='lax')
    return response


class MasterCredentials(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    username: str = Field(min_length=3, max_length=100, pattern=r'^[a-zA-Z0-9_.-]+$')
    password: str = Field(min_length=16, max_length=256)


@router.put('/master/credentials')
def change_master_credentials(payload: MasterCredentials, request: Request, user=Depends(require_admin)):
    rate_limit('master-change:' + user['id'])
    if not password_matches(payload.current_password, user['password_hash']):
        raise HTTPException(400, 'Current password is incorrect.')
    with db.connection() as conn:
        conn.execute('UPDATE users SET username=?,password_hash=? WHERE id=?',
                     (payload.username, password_hash(payload.password), user['id']))
        conn.execute('DELETE FROM sessions WHERE user_id=?', (user['id'],))
    response = JSONResponse({'updated': True})
    create_session(response, user['id'])
    return response

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from . import auth, config, db

router = APIRouter(prefix='/api', tags=['accounts'])


class AlertSettings(BaseModel):
    enabled: bool
    interval: int = Field(default=21600)
    keywords: str = Field(default='', max_length=200)
    location: str = Field(default='', max_length=100)


@router.put('/account/alerts')
def update_alerts(settings: AlertSettings, user=Depends(auth.current_user)):
    if settings.interval not in (21600, 86400):
        raise HTTPException(422, 'Choose six-hourly or daily alerts.')
    if settings.enabled and not user['email']:
        raise HTTPException(400, 'An email address is required for alerts.')
    with db.connection() as conn:
        conn.execute('''UPDATE users SET alerts_enabled=?,alert_interval=?,alert_keywords=?,alert_location=?
            WHERE id=?''', (int(settings.enabled), settings.interval, settings.keywords.strip(), settings.location.strip(), user['id']))
        row = conn.execute('SELECT * FROM users WHERE id=?', (user['id'],)).fetchone()
    return auth.public_user(row)


@router.get('/account/email-status')
def email_status(user=Depends(auth.current_user)):
    return {'configured': config.mail_configured(), 'last_sent': user['last_email_at'], 'error': user['email_error']}


@router.get('/admin/users')
def users(user=Depends(auth.require_admin)):
    with db.connection() as conn:
        rows = conn.execute('''SELECT u.*,
            (SELECT COUNT(*) FROM user_bookmarks b WHERE b.user_id=u.id) AS saved_count,
            (SELECT COUNT(*) FROM email_deliveries d WHERE d.user_id=u.id) AS emailed_jobs
            FROM users u ORDER BY u.created_at DESC''').fetchall()
    return [{**auth.public_user(row), 'saved_count': row['saved_count'], 'emailed_jobs': row['emailed_jobs']} for row in rows]


class AccountStatus(BaseModel):
    active: bool


@router.patch('/admin/users/{user_id}')
def set_account_status(user_id: str, settings: AccountStatus, user=Depends(auth.require_admin)):
    with db.connection() as conn:
        target = conn.execute('SELECT * FROM users WHERE id=?', (user_id,)).fetchone()
        if not target:
            raise HTTPException(404, 'Account not found.')
        if target['role'] == 'admin':
            raise HTTPException(400, 'The master account cannot be disabled here.')
        conn.execute('UPDATE users SET active=? WHERE id=?', (int(settings.active), user_id))
        if not settings.active:
            conn.execute('DELETE FROM sessions WHERE user_id=?', (user_id,))
    return {'active': settings.active}

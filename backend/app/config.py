"""Server-only configuration. Never expose credential values through an API."""
import os
from pathlib import Path
from urllib.parse import urlsplit
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / '.env')


def app_url():
    return os.getenv('APP_URL', 'http://localhost:8000').rstrip('/')


def secure_cookies():
    return app_url().startswith('https://')


def validate():
    url = urlsplit(app_url())
    if (url.scheme not in ('http', 'https') or not url.hostname or url.username
            or url.password or url.path or url.query or url.fragment):
        raise RuntimeError('APP_URL must be an origin, e.g. https://jobs.example.com')
    if url.scheme != 'https' and url.hostname not in ('localhost', '127.0.0.1', '::1'):
        raise RuntimeError('Public deployments require an HTTPS APP_URL.')


def google_configured():
    return bool(os.getenv('GOOGLE_CLIENT_ID') and os.getenv('GOOGLE_CLIENT_SECRET'))


def mail_configured():
    return bool(os.getenv('GMAIL_ADDRESS') and os.getenv('GMAIL_APP_PASSWORD'))

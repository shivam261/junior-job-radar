import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import db

@pytest.fixture
def database(tmp_path,monkeypatch):
    from app.auth import password_hash
    monkeypatch.setattr(db,'DB_PATH',str(tmp_path/'test.sqlite3'))
    monkeypatch.setenv('AUTO_REFRESH','false')
    monkeypatch.setenv('APP_URL','http://localhost:8000')
    monkeypatch.setenv('MASTER_USERNAME','test-master')
    monkeypatch.setenv('MASTER_PASSWORD_HASH',password_hash('test-master-password-123'))
    monkeypatch.setenv('MASTER_EMAIL','owner@example.com')
    monkeypatch.setenv('GOOGLE_CLIENT_ID','')
    monkeypatch.setenv('GOOGLE_CLIENT_SECRET','')
    monkeypatch.setenv('GMAIL_APP_PASSWORD','')
    db.initialize()
    return db

@pytest.fixture(autouse=True)
def collector_dns_is_mocked(monkeypatch):
    # HTTP collector tests use MockTransport; keep DNS offline as well.
    async def mock_public(url):
        from app.sources import public_url
        return public_url(url)
    monkeypatch.setattr('app.collectors.resolve_public',mock_public)

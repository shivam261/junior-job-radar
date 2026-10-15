import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import db

@pytest.fixture
def database(tmp_path,monkeypatch):
    monkeypatch.setattr(db,'DB_PATH',str(tmp_path/'test.sqlite3'))
    monkeypatch.setenv('AUTO_REFRESH','false')
    db.initialize()
    return db

@pytest.fixture(autouse=True)
def collector_dns_is_mocked(monkeypatch):
    # HTTP collector tests use MockTransport; keep DNS offline as well.
    async def mock_public(url):
        from app.sources import public_url
        return public_url(url)
    monkeypatch.setattr('app.collectors.resolve_public',mock_public)

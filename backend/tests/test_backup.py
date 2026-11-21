import sqlite3
import pytest
from app import backup, db
from test_api import add_job


def test_online_backup_preserves_live_data_and_is_private(database, tmp_path, monkeypatch):
    job = add_job(database)
    target = tmp_path / 'backups' / 'saved.sqlite3'
    monkeypatch.setattr('sys.argv', ['backup', str(target)])
    backup.main()
    with sqlite3.connect(target) as conn:
        assert conn.execute('SELECT id FROM jobs').fetchone()[0] == job['id']
        assert conn.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    assert target.stat().st_mode & 0o777 == 0o600
    with pytest.raises(SystemExit):
        backup.main()
    with sqlite3.connect(target) as conn:
        assert conn.execute('SELECT id FROM jobs').fetchone()[0] == job['id']


def test_backup_refuses_to_create_an_empty_source_database(database, tmp_path, monkeypatch):
    monkeypatch.setattr(db, 'DB_PATH', str(tmp_path / 'missing.sqlite3'))
    target = tmp_path / 'backup.sqlite3'
    monkeypatch.setattr('sys.argv', ['backup', str(target)])
    with pytest.raises(SystemExit):
        backup.main()
    assert not target.exists() and not (tmp_path / 'missing.sqlite3').exists()

#!/usr/bin/env python3
"""Generate private master credentials once; preserve all existing .env values."""
import os
from pathlib import Path
import secrets
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.auth import password_hash
from dotenv import dotenv_values


def main():
    env_path = ROOT / '.env'
    credentials_path = ROOT / 'master-credentials.txt'
    values = dotenv_values(env_path) if env_path.exists() else {}
    if values.get('MASTER_PASSWORD_HASH'):
        print('Master credentials are already configured; no changes made.')
        return
    if credentials_path.exists():
        raise SystemExit('master-credentials.txt already exists. Move it somewhere private before setup.')
    password = secrets.token_urlsafe(24)
    username = values.get('MASTER_USERNAME') or 'radar-master'
    original = env_path.read_text() if env_path.exists() else (ROOT / '.env.example').read_text()
    lines = original.splitlines()
    updates = {'MASTER_USERNAME': username, 'MASTER_PASSWORD_HASH': "'" + password_hash(password) + "'"}
    for key, value in updates.items():
        lines = [line for line in lines if not line.startswith(key + '=')]
        lines.append(key + '=' + value)
    # Private from the moment they are created; no credentials on the command line.
    fd = os.open(credentials_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as file:
        file.write(f'Master username: {username}\nMaster password: {password}\n\n'
                   'Keep this in a password manager. You can change both in My account & emails.\n')
    fd = os.open(env_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, 'w') as file:
        file.write('\n'.join(lines) + '\n')
    print('Created .env and master-credentials.txt with owner-only permissions.')
    print('Add GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET and GMAIL_APP_PASSWORD to .env.')
    print('Never commit or share these files.')


if __name__ == '__main__':
    main()

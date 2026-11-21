#!/usr/bin/env bash
# Run on Amazon Linux 2023 from a GitHub checkout or an extracted native bundle.
set -euo pipefail

if [[ "$EUID" -ne 0 ]]; then
  echo "Run with sudo bash deploy/install-native.sh" >&2
  exit 1
fi
source /etc/os-release
if [[ "${ID:-}" != amzn || "${VERSION_ID:-}" != 2023 ]]; then
  echo "This installer targets Amazon Linux 2023." >&2
  exit 1
fi

source_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cert_source="${1:-/home/ec2-user/launchpad-certs}"
if [[ ! -s "$source_root/.env" || ! -s "$source_root/frontend/dist/index.html" ]]; then
  echo "Build frontend/dist and create the configured .env in the project root first." >&2
  exit 1
fi
for certificate_file in certificate.pem certificate_chain.pem private_key.pem; do
  if [[ ! -s "$cert_source/$certificate_file" ]]; then
    echo "Missing certificate file: $cert_source/$certificate_file" >&2
    exit 1
  fi
done

dnf install -y python3.12 python3.12-pip openssl ca-certificates rsync
if ! getent group launchpad >/dev/null; then
  groupadd --system launchpad
fi
if ! id -u launchpad >/dev/null 2>&1; then
  useradd --system --gid launchpad --home-dir /var/lib/launchpad --shell /sbin/nologin launchpad
fi

bash "$source_root/deploy/install-tls.sh" "$cert_source"

# Check public configuration without printing server credentials.
python3.12 - "$source_root/.env" <<'PY'
import sys
from pathlib import Path
content = Path(sys.argv[1]).read_text()
if not any(line.strip().startswith('MASTER_PASSWORD_HASH=') and line.strip().split('=',1)[1].strip(" '\"") for line in content.splitlines()):
    raise SystemExit('MASTER_PASSWORD_HASH is missing. Run scripts/setup_accounts.py on your Mac and copy .env again.')
PY

if systemctl is-active --quiet launchpad.service; then
  systemctl stop launchpad.service
fi
if [[ -n "$(ss -H -ltn 'sport = :443')" ]]; then
  echo "Another process is using TCP 443. Check sudo ss -ltnp 'sport = :443'." >&2
  exit 1
fi

umask 077
install -d -o launchpad -g launchpad -m 0700 /var/lib/launchpad
if [[ -s /var/lib/launchpad/jobs.sqlite3 ]]; then
  python3.12 - <<'PY'
from pathlib import Path
import sqlite3
import time
directory = Path('/var/lib/launchpad/backups')
directory.mkdir(mode=0o700, exist_ok=True)
destination = directory / f'pre-deploy-{time.time_ns()}.sqlite3'
with sqlite3.connect('/var/lib/launchpad/jobs.sqlite3') as source, sqlite3.connect(destination) as target:
    source.backup(target)
print('Saved a pre-deployment database backup.')
PY
  chown -R launchpad:launchpad /var/lib/launchpad/backups
fi

install -d -o root -g root -m 0755 /opt/launchpad /opt/launchpad/backend /opt/launchpad/backend/app /opt/launchpad/frontend /opt/launchpad/frontend/dist
rsync -a --delete --exclude '__pycache__' "$source_root/backend/app/" /opt/launchpad/backend/app/
rsync -a --delete "$source_root/frontend/dist/" /opt/launchpad/frontend/dist/
install -m 0644 "$source_root/backend/requirements.lock" /opt/launchpad/backend/requirements.lock
chown -R root:root /opt/launchpad/backend /opt/launchpad/frontend
chmod -R a+rX /opt/launchpad/backend /opt/launchpad/frontend

python3.12 -m venv /opt/launchpad/.venv
/opt/launchpad/.venv/bin/python -m pip install --no-cache-dir --upgrade pip
/opt/launchpad/.venv/bin/python -m pip install --no-cache-dir --only-binary=:all: -r /opt/launchpad/backend/requirements.lock
chmod -R a+rX /opt/launchpad/.venv

/opt/launchpad/.venv/bin/python - "$source_root/.env" <<'PY'
import os
from pathlib import Path
import sys
from dotenv import dotenv_values
source = Path(sys.argv[1])
values = dotenv_values(source)
missing = [key for key in ('GOOGLE_CLIENT_ID','GOOGLE_CLIENT_SECRET','GMAIL_ADDRESS','GMAIL_APP_PASSWORD') if not values.get(key)]
if missing:
    print('Still needs configuration: ' + ', '.join(missing) + '. Master login remains available.')
updates = {'APP_URL':'https://radar.shivam-tripathi.com', 'DATABASE_PATH':'/var/lib/launchpad/jobs.sqlite3'}
lines = [line for line in source.read_text().splitlines() if not any(line.strip().startswith(key + '=') for key in updates)]
lines += [key + '=' + value for key,value in updates.items()]
destination = Path('/etc/launchpad/launchpad.env')
fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
os.fchmod(fd, 0o600)
with os.fdopen(fd, 'w') as output:
    output.write('\n'.join(lines) + '\n')
PY

install -o root -g root -m 0644 "$source_root/deploy/launchpad.service" /etc/systemd/system/launchpad.service
systemctl daemon-reload
systemctl enable launchpad.service
systemctl restart launchpad.service

# Verify locally with the actual hostname and certificate, before waiting on DNS.
for attempt in {1..20}; do
  if curl --silent --show-error --fail --connect-timeout 2 --max-time 5 --resolve radar.shivam-tripathi.com:443:127.0.0.1 https://radar.shivam-tripathi.com/api/health; then
    echo
    echo "Launchpad is serving HTTPS on TCP 443."
    echo "Check public DNS and the EC2 security group, then open https://radar.shivam-tripathi.com"
    exit 0
  fi
  sleep 1
done
echo "Startup did not pass the HTTPS check. Run sudo journalctl -u launchpad -n 50 --no-pager." >&2
exit 1

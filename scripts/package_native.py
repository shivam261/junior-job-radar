#!/usr/bin/env python3
"""Build React locally and package the server files without secrets or data."""
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
INCLUDE = (
    'backend/app', 'backend/requirements.lock', 'frontend/dist',
    'deploy/launchpad.service', 'deploy/install-native.sh', 'deploy/install-tls.sh',
)


def main():
    subprocess.run(['npm', 'run', 'build'], cwd=ROOT / 'frontend', check=True)
    destination = ROOT / 'dist' / 'launchpad-native.tar.gz'
    destination.parent.mkdir(exist_ok=True)
    def filter_file(info):
        if any(part in ('__pycache__', '.DS_Store') for part in Path(info.name).parts):
            return None
        if info.issym() or info.islnk() or info.name.endswith('.pyc'):
            return None
        # The bundle contains code/assets only. Make them readable by the runtime.
        info.uid = info.gid = 0
        info.uname = info.gname = ''
        info.mode = 0o755 if info.isdir() else 0o644
        return info
    fd, temporary_path = tempfile.mkstemp(prefix='.native-', dir=destination.parent)
    os.close(fd)
    try:
        with tarfile.open(temporary_path, 'w:gz') as archive:
            for relative in INCLUDE:
                archive.add(ROOT / relative, arcname=relative, filter=filter_file)
        os.replace(temporary_path, destination)
    finally:
        Path(temporary_path).unlink(missing_ok=True)
    print(f'Created {destination} ({destination.stat().st_size:,} bytes)')
    print('Upload the bundle and your private .env separately. Certificates and database are excluded.')


if __name__ == '__main__':
    main()

"""Take a consistent online SQLite backup, including data in the WAL."""
import argparse
import os
from pathlib import Path
import sqlite3
from . import db


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination')
    args = parser.parse_args()
    destination = Path(args.destination)
    if not Path(db.DB_PATH).is_file():
        parser.error('Source database does not exist.')
    if destination.exists():
        parser.error('Destination already exists; choose another name.')
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Make the file private before SQLite starts writing account data.
    os.close(os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600))
    with db.connection() as source, sqlite3.connect(destination) as target:
        source.backup(target)
    destination.chmod(0o600)
    print(f'Backup created at {destination}')


if __name__ == '__main__':
    main()

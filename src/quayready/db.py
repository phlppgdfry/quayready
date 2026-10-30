from __future__ import annotations

import contextvars
import hashlib
import os
import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from pathlib import Path

from .common import CONTRACTS, wall_ms

_active = contextvars.ContextVar("quayready_transaction", default=0)


class Database:
    def __init__(self, path: Path, target: bool = False):
        self.path, self.target = path, target

    @property
    def transaction_active(self) -> bool:
        return _active.get() > 0

    def connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, isolation_level=None, timeout=2)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA busy_timeout=2000")
        db.execute("PRAGMA synchronous=FULL")
        if db.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
            raise RuntimeError("Foreign key enforcement unavailable")
        return db

    def initialize(self) -> None:
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if sqlite3.sqlite_version_info < (3, 37):
            raise RuntimeError("SQLite >=3.37 required")
        sql = CONTRACTS.joinpath("001-target.sql" if self.target else "001-app.sql").read_text()
        checksum = hashlib.sha256(sql.encode()).hexdigest()
        with closing(self.connect()) as db:
            db.execute("SELECT json_valid('{}')")
            db.execute("PRAGMA journal_mode=WAL")
            tables = db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            if tables:
                if self.target:
                    version = db.execute("PRAGMA user_version").fetchone()[0]
                    if version != 1:
                        raise RuntimeError("Unknown target schema")
                else:
                    row = db.execute(
                        "SELECT checksum FROM schema_migrations WHERE version=1"
                    ).fetchone()
                    if not row or row[0] != checksum:
                        raise RuntimeError("Unknown or changed migration")
                return
            try:
                db.executescript(sql.rsplit("COMMIT;", 1)[0])
                if self.target:
                    db.execute("PRAGMA user_version=1")
                else:
                    db.execute("INSERT INTO schema_migrations VALUES(1,?,?)", (checksum, wall_ms()))
                db.execute("COMMIT")
            except BaseException:
                if db.in_transaction:
                    db.execute("ROLLBACK")
                raise
        os.chmod(self.path, 0o600)

    @contextmanager
    def transaction(self, write: bool = True) -> Iterator[sqlite3.Connection]:
        db = self.connect()
        token = _active.set(_active.get() + 1)
        try:
            db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            yield db
            db.execute("COMMIT")
        except BaseException:
            if db.in_transaction:
                db.execute("ROLLBACK")
            raise
        finally:
            _active.reset(token)
            db.close()

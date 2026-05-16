"""
CiteMind — SQLite database connection manager.
"""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from typing import Generator

_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "citemind.db")
_SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema.sql")
_initialized = False


def _init_db(conn: sqlite3.Connection) -> None:
    """Run schema.sql to create tables (IF NOT EXISTS is idempotent)."""
    global _initialized
    if _initialized:
        return
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    with open(_SCHEMA_PATH, "r") as f:
        conn.executescript(f.read())
    _initialized = True


@contextmanager
def get_db() -> Generator[sqlite3.Connection, None, None]:
    """
    Context manager that yields a sqlite3 Connection.
    Auto-commits on success, rolls back on exception.
    Row factory is set to sqlite3.Row for dict-like access.
    """
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    _init_db(conn)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

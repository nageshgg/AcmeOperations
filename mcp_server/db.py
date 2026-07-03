"""Lightweight PostgreSQL connection helper.

This is the MCP server's own DB connection -- deliberately separate from
`app/db.py` even though the code is near-identical, because the MCP server
runs as its own container (per the brief's requirement) and must not depend
on the `app` container's internals. A shared library would be a reasonable
refactor at larger scale, but for two small, near-static helper modules the
duplication is cheaper than the coupling it would avoid.
"""

import os
from typing import Any

import psycopg2
import psycopg2.extras
from psycopg2 import pool

_pool: pool.SimpleConnectionPool | None = None


def _get_pool() -> pool.SimpleConnectionPool:
    global _pool
    if _pool is None:
        _pool = pool.SimpleConnectionPool(
            1,
            5,
            host=os.environ["POSTGRES_HOST"],
            port=os.environ["POSTGRES_PORT"],
            user=os.environ["POSTGRES_USER"],
            password=os.environ["POSTGRES_PASSWORD"],
            dbname=os.environ["POSTGRES_DB"],
        )
    return _pool


def query(sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    """Run a SELECT and return rows as plain dicts."""
    p = _get_pool()
    conn = p.getconn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            return [dict(row) for row in cur.fetchall()]
    finally:
        p.putconn(conn)


def execute(sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    """Run an INSERT/UPDATE (optionally with RETURNING) and commit."""
    p = _get_pool()
    conn = p.getconn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            rows = [dict(row) for row in cur.fetchall()] if cur.description else []
            conn.commit()
            return rows
    finally:
        p.putconn(conn)

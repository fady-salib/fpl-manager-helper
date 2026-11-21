"""Append-only public-data snapshots; persistence boundary can be replaced for PostgreSQL."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class SnapshotStore:
    def __init__(self, path: str | Path = "data/fpl.sqlite") -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.path = str(path)
        with self.connect() as con:
            con.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS snapshots (
                    id INTEGER PRIMARY KEY, endpoint TEXT NOT NULL,
                    fetched_at TEXT NOT NULL, sha256 TEXT NOT NULL, payload TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS endpoint_time ON snapshots(endpoint, fetched_at);
            """)

    def connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=30)

    def put(self, endpoint: str, payload: Any, when: datetime | None = None) -> None:
        encoded = json.dumps(payload, allow_nan=False, separators=(",", ":"))
        stamp = (when or datetime.now(UTC)).astimezone(UTC).isoformat()
        digest = hashlib.sha256(encoded.encode()).hexdigest()
        with self.connect() as con:
            con.execute(
                "INSERT INTO snapshots(endpoint,fetched_at,sha256,payload) VALUES(?,?,?,?)",
                (endpoint, stamp, digest, encoded),
            )

    def latest(self, endpoint: str, before: datetime | None = None) -> tuple[datetime, Any] | None:
        query = "SELECT fetched_at,payload FROM snapshots WHERE endpoint=?"
        params: list[Any] = [endpoint]
        if before is not None:
            query += " AND fetched_at<=?"
            params.append(before.astimezone(UTC).isoformat())
        query += " ORDER BY fetched_at DESC,id DESC LIMIT 1"
        with self.connect() as con:
            row = con.execute(query, params).fetchone()
        return (datetime.fromisoformat(row[0]), json.loads(row[1])) if row else None

    def latest_many(self, endpoints: list[str], before: datetime | None = None) -> dict:
        """Read hundreds of player histories with one connection, including on Windows."""
        result = {}
        with self.connect() as con:
            for offset in range(0, len(endpoints), 800):
                chunk = endpoints[offset : offset + 800]
                marks = ",".join("?" for _ in chunk)
                params = list(chunk)
                time_filter = ""
                if before is not None:
                    time_filter = " AND fetched_at<=?"
                    params.append(before.astimezone(UTC).isoformat())
                rows = con.execute(
                    f"""
                    SELECT endpoint, fetched_at, payload FROM (
                        SELECT endpoint, fetched_at, payload,
                               ROW_NUMBER() OVER (
                                   PARTITION BY endpoint ORDER BY fetched_at DESC, id DESC
                               ) AS rank
                        FROM snapshots WHERE endpoint IN ({marks}){time_filter}
                    ) WHERE rank=1
                """,
                    params,
                ).fetchall()
                result.update({e: (datetime.fromisoformat(t), json.loads(p)) for e, t, p in rows})
        return result

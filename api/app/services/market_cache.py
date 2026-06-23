import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CachedSnapshot:
    key: str
    payload: dict[str, Any]
    source: str
    fetched_at: datetime
    ttl_seconds: int

    @property
    def is_stale(self) -> bool:
        return (datetime.now(UTC) - self.fetched_at).total_seconds() > self.ttl_seconds


class MarketSnapshotCache:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def save(
        self,
        key: str,
        payload: dict[str, Any],
        source: str,
        ttl_seconds: int,
        fetched_at: datetime | None = None,
    ) -> None:
        timestamp = fetched_at or datetime.now(UTC)
        with self._connect() as connection:
            connection.execute(
                """
                insert into market_snapshots(key, payload_json, source, fetched_at, ttl_seconds)
                values (?, ?, ?, ?, ?)
                on conflict(key) do update set
                    payload_json = excluded.payload_json,
                    source = excluded.source,
                    fetched_at = excluded.fetched_at,
                    ttl_seconds = excluded.ttl_seconds
                """,
                (key, json.dumps(payload, ensure_ascii=False), source, timestamp.isoformat(), ttl_seconds),
            )

    def get(self, key: str) -> CachedSnapshot | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                select key, payload_json, source, fetched_at, ttl_seconds
                from market_snapshots
                where key = ?
                """,
                (key,),
            ).fetchone()
        if row is None:
            return None
        fetched_at = datetime.fromisoformat(row["fetched_at"])
        if fetched_at.tzinfo is None:
            fetched_at = fetched_at.replace(tzinfo=UTC)
        return CachedSnapshot(
            key=row["key"],
            payload=json.loads(row["payload_json"]),
            source=row["source"],
            fetched_at=fetched_at,
            ttl_seconds=int(row["ttl_seconds"]),
        )

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                create table if not exists market_snapshots (
                    key text primary key,
                    payload_json text not null,
                    source text not null,
                    fetched_at text not null,
                    ttl_seconds integer not null
                )
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

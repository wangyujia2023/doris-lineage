from __future__ import annotations

from pathlib import Path
from types import TracebackType
from typing import Any, Iterable

import aiosqlite


class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn: aiosqlite.Connection | None = None

    async def __aenter__(self) -> "Database":
        await self.connect()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.close()

    async def connect(self) -> None:
        self.conn = await aiosqlite.connect(self.db_path)
        self.conn.row_factory = aiosqlite.Row
        await self.conn.execute("PRAGMA journal_mode=WAL")
        await self.conn.execute("PRAGMA foreign_keys=ON")
        await self.conn.commit()

    async def close(self) -> None:
        if self.conn is not None:
            await self.conn.close()
            self.conn = None

    async def init_schema(self) -> None:
        schema_path = Path(__file__).with_name("schema.sql")
        assert self.conn is not None
        await self.conn.executescript(schema_path.read_text(encoding="utf-8"))
        await self.conn.commit()

    async def execute(self, sql: str, params: Iterable[Any] = ()) -> None:
        assert self.conn is not None
        await self.conn.execute(sql, tuple(params))

    async def execute_many(self, sql: str, params: Iterable[Iterable[Any]]) -> None:
        assert self.conn is not None
        await self.conn.executemany(sql, params)

    async def fetch_all(self, sql: str, params: Iterable[Any] = ()) -> list[dict[str, Any]]:
        assert self.conn is not None
        cursor = await self.conn.execute(sql, tuple(params))
        rows = await cursor.fetchall()
        await cursor.close()
        return [dict(row) for row in rows]

    async def fetch_one(self, sql: str, params: Iterable[Any] = ()) -> dict[str, Any] | None:
        assert self.conn is not None
        cursor = await self.conn.execute(sql, tuple(params))
        row = await cursor.fetchone()
        await cursor.close()
        return dict(row) if row else None

    async def commit(self) -> None:
        assert self.conn is not None
        await self.conn.commit()

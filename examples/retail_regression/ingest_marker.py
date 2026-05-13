from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timedelta

from doris_lineage.config import load_settings
from doris_lineage.graph.nx_graph import LineageGraph
from doris_lineage.store.db import Database
from doris_lineage.store.reader import LineageReader
from doris_lineage.store.writer import LineageWriter
from doris_lineage.tools.context import AppContext
from doris_lineage.tools.ingest import ingest_doris_audit_table


async def main() -> None:
    marker = sys.argv[1]
    settings = load_settings()
    settings.audit_table.system_user_blacklist = [
        user for user in settings.audit_table.system_user_blacklist if user.lower() != settings.doris.user.lower()
    ]
    db = Database(settings.storage.db_path)
    await db.connect()
    await db.init_schema()
    ctx = AppContext(settings, db, LineageReader(db), LineageWriter(db), LineageGraph())
    try:
        result = await ingest_doris_audit_table(
            ctx,
            start_time=(datetime.now() - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S"),
            end_time=(datetime.now() + timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S"),
            limit=200,
            sql_contains=marker,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())

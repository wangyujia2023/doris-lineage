from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import sqlglot
from sqlglot import exp

from doris_lineage.collector.doris_client import connect_doris
from doris_lineage.config import load_settings
from doris_lineage.graph.nx_graph import LineageGraph
from doris_lineage.store.db import Database
from doris_lineage.store.reader import LineageReader
from doris_lineage.store.writer import LineageWriter
from doris_lineage.tools.context import AppContext
from doris_lineage.tools.ingest import ingest_doris_audit_table


ROOT = Path(__file__).resolve().parent
REGRESSION_MARKER_PREFIX = "retail_lineage_regression"


def _statements(path: Path) -> list[str]:
    raw = path.read_text(encoding="utf-8")
    statements: list[str] = []
    current: list[str] = []
    in_single = False
    in_double = False
    i = 0
    while i < len(raw):
        ch = raw[i]
        nxt = raw[i + 1] if i + 1 < len(raw) else ""
        if ch == "-" and nxt == "-" and not in_single and not in_double:
            end = raw.find("\n", i)
            if end == -1:
                break
            i = end + 1
            continue
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        if ch == ";" and not in_single and not in_double:
            statement = "".join(current).strip()
            if statement:
                statements.append(statement)
            current = []
        else:
            current.append(ch)
        i += 1
    tail = "".join(current).strip()
    if tail:
        statements.append(tail)
    return statements


def _declared_databases(path: Path) -> list[str]:
    databases: list[str] = []
    for sql in _statements(path):
        try:
            ast = sqlglot.parse_one(sql, read="doris")
        except sqlglot.errors.ParseError:
            continue
        if isinstance(ast, exp.Create) and str(ast.args.get("kind") or "").upper() == "DATABASE":
            name = ast.this.sql(dialect="doris")
            if name and name not in databases:
                databases.append(name)
    return databases


def _connect():
    settings = load_settings()
    return connect_doris(settings.doris)


def execute_sql_files(marker: str) -> dict[str, Any]:
    schema_file = ROOT / "retail_schema_and_seed.sql"
    etl_file = ROOT / "retail_20_etl.sql"
    executed = 0
    failures: list[dict[str, Any]] = []
    conn = _connect()
    try:
        with conn.cursor() as cursor:
            for database in reversed(_declared_databases(schema_file)):
                try:
                    cursor.execute(f"DROP DATABASE IF EXISTS {database} FORCE")
                except Exception:
                    cursor.execute(f"DROP DATABASE IF EXISTS {database}")

            for index, sql in enumerate(_statements(schema_file), start=1):
                try:
                    cursor.execute(sql)
                    executed += 1
                except Exception as exc:  # noqa: BLE001 - regression output should preserve Doris error text.
                    failures.append({"file": schema_file.name, "statement_index": index, "error": str(exc), "sql": sql[:500]})

            for index, sql in enumerate(_statements(etl_file), start=1):
                marked_sql = f"/* {marker} {index:02d} */ {sql}"
                try:
                    cursor.execute(marked_sql)
                    executed += 1
                except Exception as exc:  # noqa: BLE001 - regression output should preserve Doris error text.
                    failures.append({"file": etl_file.name, "statement_index": index, "error": str(exc), "sql": marked_sql[:500]})
    finally:
        conn.close()
    return {"executed": executed, "failures": failures}


async def validate_lineage(start_time: str, end_time: str, marker: str) -> dict[str, Any]:
    settings = load_settings()
    settings.audit_table.system_user_blacklist = [
        user for user in settings.audit_table.system_user_blacklist if user.lower() != settings.doris.user.lower()
    ]
    db = Database(settings.storage.db_path)
    await db.connect()
    await db.init_schema()
    ctx = AppContext(
        settings=settings,
        db=db,
        reader=LineageReader(db),
        writer=LineageWriter(db),
        graph=LineageGraph(),
    )
    try:
        last_result: dict[str, Any] = {}
        time.sleep(75)
        for _ in range(3):
            last_result = await ingest_doris_audit_table(
                ctx,
                start_time=start_time,
                end_time=end_time,
                limit=200,
                sql_contains=marker,
            )
            if last_result.get("seen", 0) >= 20:
                return last_result
            time.sleep(10)
        return last_result
    finally:
        await db.close()


async def main() -> None:
    marker = f"{REGRESSION_MARKER_PREFIX}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    start_time = (datetime.now() - timedelta(minutes=2)).strftime("%Y-%m-%d %H:%M:%S")
    doris_result = execute_sql_files(marker)
    end_time = (datetime.now() + timedelta(minutes=2)).strftime("%Y-%m-%d %H:%M:%S")
    lineage_result = await validate_lineage(start_time, end_time, marker)
    print(json.dumps({"marker": marker, "doris": doris_result, "lineage": lineage_result}, ensure_ascii=False, indent=2))
    if doris_result["failures"] or lineage_result.get("skipped") or lineage_result.get("parsed") != 20:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())

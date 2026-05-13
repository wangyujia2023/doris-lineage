from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from doris_lineage.models import SqlEvent


def _strip_leading_comments(sql: str) -> str:
    value = sql.strip()
    while value.startswith("/*"):
        end = value.find("*/")
        if end < 0:
            return value
        value = value[end + 2 :].strip()
    return value


def _parse_kv_line(line: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for chunk in line.strip().split("\t"):
        if "=" in chunk:
            key, value = chunk.split("=", 1)
            fields[key.strip().lower()] = value.strip()
    return fields


def classify_stmt(sql: str) -> str:
    normalized = " ".join(_strip_leading_comments(sql).lower().split())
    if normalized.startswith("with") and " insert overwrite " in f" {normalized} ":
        return "INSERT_OVERWRITE_SELECT"
    if normalized.startswith("with") and " insert into " in f" {normalized} ":
        return "INSERT_INTO_SELECT"
    if normalized.startswith("insert overwrite") and " select " in normalized:
        return "INSERT_OVERWRITE_SELECT"
    if normalized.startswith("insert into") and " select " in normalized:
        return "INSERT_INTO_SELECT"
    if normalized.startswith("create table") and " as select " in normalized:
        return "CREATE_TABLE_AS_SELECT"
    if normalized.startswith("create view") and " as select " in normalized:
        return "CREATE_VIEW"
    if normalized.startswith("create materialized view") and " as select " in normalized:
        return "CREATE_MATERIALIZED_VIEW"
    if normalized.startswith("refresh materialized view"):
        return "REFRESH_MATERIALIZED_VIEW"
    return "UNKNOWN"


def _field(fields: dict[str, str], *names: str, default: str = "") -> str:
    for name in names:
        value = fields.get(name.lower())
        if value:
            return value
    return default


def iter_audit_events(
    path: str,
    default_catalog: str = "internal",
    start_time: str | None = None,
    end_time: str | None = None,
) -> Iterable[SqlEvent]:
    start = datetime.fromisoformat(start_time) if start_time else None
    end = datetime.fromisoformat(end_time) if end_time else None
    for line_no, line in enumerate(Path(path).read_text(encoding="utf-8", errors="ignore").splitlines(), start=1):
        fields = _parse_kv_line(line)
        sql = _field(fields, "stmt", "sql", "statement")
        if not sql:
            continue
        executed_at = _field(fields, "time", "timestamp", "query_time", default=datetime.now(timezone.utc).isoformat())
        try:
            executed_dt = datetime.fromisoformat(executed_at)
        except ValueError:
            executed_dt = datetime.now(timezone.utc)
            executed_at = executed_dt.isoformat()
        if start and executed_dt < start:
            continue
        if end and executed_dt > end:
            continue
        yield SqlEvent(
            query_id=_field(fields, "queryid", "query_id", default=f"audit-{line_no}"),
            user=_field(fields, "user", "user_name", default="unknown"),
            database=_field(fields, "db", "database", default="default"),
            catalog=_field(fields, "catalog", default=default_catalog),
            stmt_type=classify_stmt(sql),
            sql_text=sql,
            executed_at=executed_at,
            state=_field(fields, "state", "status", default="EOF"),
        )

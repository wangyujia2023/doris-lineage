from __future__ import annotations

from typing import Any, Iterable

from doris_lineage.collector.audit_reader import classify_stmt
from doris_lineage.collector.doris_client import connect_doris
from doris_lineage.config import AuditTableConfig, DorisConfig
from doris_lineage.models import SqlEvent


def _quote_identifier(identifier: str) -> str:
    parts = [p.strip("` ") for p in identifier.split(".") if p.strip()]
    return ".".join(f"`{part}`" for part in parts)


def _select_expr(column: str, alias: str, default_sql: str | None = None) -> str:
    if column:
        return f"{_quote_identifier(column)} AS `{alias}`"
    if default_sql is not None:
        return f"{default_sql} AS `{alias}`"
    return f"NULL AS `{alias}`"


def _build_query(
    doris: DorisConfig,
    audit: AuditTableConfig,
    start_time: str | None,
    end_time: str | None,
    limit: int,
    sql_contains: str | None = None,
) -> tuple[str, list[Any]]:
    select_columns = [
        _select_expr(audit.query_id_column, "query_id"),
        _select_expr(audit.user_column, "user"),
        _select_expr(audit.database_column, "database"),
        _select_expr(audit.catalog_column, "catalog", f"'{doris.default_catalog}'"),
        _select_expr(audit.sql_column, "sql_text"),
        _select_expr(audit.state_column, "state", "'EOF'"),
        _select_expr(audit.executed_at_column, "executed_at"),
        _select_expr(audit.stmt_type_column, "stmt_type"),
    ]
    predicates: list[str] = []
    params: list[Any] = []
    if start_time:
        predicates.append(f"{_quote_identifier(audit.executed_at_column)} >= %s")
        params.append(start_time)
    if end_time:
        predicates.append(f"{_quote_identifier(audit.executed_at_column)} <= %s")
        params.append(end_time)
    if sql_contains:
        predicates.append(f"{_quote_identifier(audit.sql_column)} LIKE %s")
        params.append(f"%{sql_contains}%")
    predicates.append(f"{_quote_identifier(audit.sql_column)} NOT LIKE %s")
    params.append("%__internal_schema%audit_log%")
    predicates.append(f"{_quote_identifier(audit.sql_column)} NOT LIKE %s")
    params.append("%SELECT `query_id` AS `query_id`%")
    where = f"WHERE {' AND '.join(predicates)}" if predicates else ""
    order = f"ORDER BY {_quote_identifier(audit.executed_at_column)} ASC" if audit.executed_at_column else ""
    sql = f"""
        SELECT {", ".join(select_columns)}
        FROM {_quote_identifier(audit.table)}
        {where}
        {order}
        LIMIT %s
    """
    params.append(limit)
    return sql, params


def fetch_audit_table_events(
    doris: DorisConfig,
    audit: AuditTableConfig,
    start_time: str | None = None,
    end_time: str | None = None,
    limit: int = 1000,
    sql_contains: str | None = None,
) -> Iterable[SqlEvent]:
    query, params = _build_query(doris, audit, start_time, end_time, limit, sql_contains)
    import pymysql.cursors

    conn = connect_doris(doris, cursorclass=pymysql.cursors.DictCursor)
    try:
        with conn.cursor() as cursor:
            cursor.execute(query, params)
            for row in cursor.fetchall():
                sql_text = str(row.get("sql_text") or "")
                stmt_type = classify_stmt(sql_text)
                yield SqlEvent(
                    query_id=str(row.get("query_id") or ""),
                    user=str(row.get("user") or "unknown"),
                    database=str(row.get("database") or ""),
                    catalog=str(row.get("catalog") or ""),
                    stmt_type=stmt_type,
                    sql_text=sql_text,
                    executed_at=str(row.get("executed_at") or ""),
                    state=str(row.get("state") or "EOF"),
                )
    finally:
        conn.close()

from __future__ import annotations

from doris_lineage.models import SqlEvent


STMT_TYPE_WHITELIST = {
    "INSERT_INTO_SELECT",
    "INSERT_OVERWRITE_SELECT",
    "CREATE_TABLE_AS_SELECT",
    "CREATE_VIEW",
    "CREATE_MATERIALIZED_VIEW",
    "REFRESH_MATERIALIZED_VIEW",
}

SYSTEM_DB_BLACKLIST = {
    "information_schema",
    "__internal_schema",
    "_statistics_",
    "mysql",
    "doris_monitor",
}

SYSTEM_USER_BLACKLIST = {
    "root",
    "admin",
    "doris",
    "fe_scheduler",
}


def _has_qualified_table_context(sql: str) -> bool:
    # Allows audit rows with empty current database when the SQL itself carries
    # catalog.database.table references. This is a conservative text-level gate,
    # not a lineage fallback.
    lowered = sql.lower()
    return " internal." in f" {lowered}" or "`internal`." in lowered


def should_keep(
    event: SqlEvent,
    system_user_blacklist: list[str] | None = None,
    system_db_blacklist: list[str] | None = None,
) -> tuple[bool, str | None]:
    users = {u.lower() for u in (system_user_blacklist or SYSTEM_USER_BLACKLIST)}
    dbs = {d.lower() for d in (system_db_blacklist or SYSTEM_DB_BLACKLIST)}
    if not event.query_id or not event.sql_text or not event.executed_at:
        return False, "incomplete_event"
    if not event.catalog:
        return False, "missing_execution_context"
    if not event.database and not _has_qualified_table_context(event.sql_text):
        return False, "missing_execution_context"
    if event.stmt_type not in STMT_TYPE_WHITELIST:
        return False, "stmt_type_not_in_whitelist"
    if event.database.lower() in dbs:
        return False, "system_db"
    if event.user.lower() in users:
        return False, "system_user"
    if event.state not in {"EOF", "OK"}:
        return False, "exec_failed"
    return True, None

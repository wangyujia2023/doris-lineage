from __future__ import annotations

from typing import Any

from doris_lineage.collector.audit_table_reader import fetch_audit_table_events
from doris_lineage.collector.sql_filter import should_keep
from doris_lineage.models import SqlEvent
from doris_lineage.parser.sqlglot_parser import parse
from doris_lineage.tools.context import AppContext


async def ingest_doris_audit_table(
    ctx: AppContext,
    start_time: str | None = None,
    end_time: str | None = None,
    limit: int = 1000,
    sql_contains: str | None = None,
    schemas: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    summary: dict[str, Any] = {"seen": 0, "kept": 0, "parsed": 0, "edges": 0, "skipped": {}}
    for event in fetch_audit_table_events(
        ctx.settings.doris,
        ctx.settings.audit_table,
        start_time,
        end_time,
        limit,
        sql_contains,
    ):
        summary["seen"] += 1
        keep, reason = should_keep(
            event,
            ctx.settings.audit_table.system_user_blacklist,
            ctx.settings.audit_table.system_db_blacklist,
        )
        if not keep:
            await ctx.writer.write_skipped_run(event, reason or "filtered")
            summary["skipped"][reason or "filtered"] = summary["skipped"].get(reason or "filtered", 0) + 1
            continue
        summary["kept"] += 1
        result = parse(event, schemas=schemas)
        if result is None:
            await ctx.writer.write_skipped_run(event, "parse_error")
            summary["skipped"]["parse_error"] = summary["skipped"].get("parse_error", 0) + 1
            continue
        summary["edges"] += await ctx.writer.write_result(event, result)
        summary["parsed"] += 1
    return {"ok": True, **summary}


async def bootstrap_lineage_history(ctx: AppContext, events: list[dict[str, Any]], schemas: dict[str, list[str]] | None = None) -> dict[str, Any]:
    summary: dict[str, Any] = {"seen": 0, "kept": 0, "parsed": 0, "edges": 0, "skipped": {}}
    for raw in events:
        summary["seen"] += 1
        event = SqlEvent.model_validate(raw)
        keep, reason = should_keep(
            event,
            ctx.settings.audit_table.system_user_blacklist,
            ctx.settings.audit_table.system_db_blacklist,
        )
        if not keep:
            await ctx.writer.write_skipped_run(event, reason or "filtered")
            summary["skipped"][reason or "filtered"] = summary["skipped"].get(reason or "filtered", 0) + 1
            continue
        summary["kept"] += 1
        result = parse(event, schemas=schemas)
        if result is None:
            await ctx.writer.write_skipped_run(event, "parse_error")
            summary["skipped"]["parse_error"] = summary["skipped"].get("parse_error", 0) + 1
            continue
        summary["edges"] += await ctx.writer.write_result(event, result)
        summary["parsed"] += 1
    return {"ok": True, **summary}

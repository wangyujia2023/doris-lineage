from __future__ import annotations

from typing import Any

from doris_lineage.tools.context import AppContext


async def lineage_health_check(ctx: AppContext) -> dict[str, Any]:
    summary = await ctx.reader.health_summary()
    proposed = next((row["count"] for row in summary["edges"] if row["edge_status"] == "PROPOSED"), 0)
    parse_errors = next((row["count"] for row in summary["runs"] if row["status"] == "parse_error"), 0)
    total_runs = sum(row["count"] for row in summary["runs"])
    return {
        "ok": True,
        "total_runs": total_runs,
        "parse_error_rate": parse_errors / total_runs if total_runs else 0.0,
        "proposed_backlog": proposed,
        **summary,
    }

from __future__ import annotations

from typing import Any

from doris_lineage.models import EdgeStatus, utc_now
from doris_lineage.tools.context import AppContext


async def list_proposed_edges(
    ctx: AppContext,
    asset_prefix: str | None = None,
    min_confidence: float | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    threshold = min_confidence if min_confidence is not None else ctx.settings.mcp.default_confidence_threshold
    return {"edges": await ctx.reader.proposed_edges(asset_prefix, threshold, limit)}


async def review_edge(
    ctx: AppContext,
    edge_ids: list[str],
    action: str,
    reviewer: str,
    note: str | None = None,
) -> dict[str, Any]:
    if action not in {"confirm", "reject"}:
        return {"ok": False, "error": "action must be confirm or reject"}
    status = EdgeStatus.CONFIRMED if action == "confirm" else EdgeStatus.REJECTED
    reviewed = await ctx.reader.review_edges(edge_ids, status, reviewer, note, utc_now())
    for edge in reviewed:
        if status == EdgeStatus.CONFIRMED:
            ctx.graph.sync_edge(
                edge["source_field"],
                edge["target_field"],
                edge_type=edge["edge_type"],
                confidence=edge["confidence"],
            )
        else:
            ctx.graph.remove_edge(edge["source_field"], edge["target_field"])
    return {"ok": True, "updated": len(reviewed), "status": status.value}

from __future__ import annotations

from typing import Any

from doris_lineage.tools.context import AppContext


async def trace_column_lineage(
    ctx: AppContext,
    field_id: str,
    direction: str = "upstream",
    depth: int | None = 5,
    include_proposed: bool = False,
) -> dict[str, Any]:
    if direction == "both":
        return {
            "field_id": field_id,
            "direction": "both",
            "depth": depth,
            "upstream": await trace_column_lineage(ctx, field_id, "upstream", depth, include_proposed),
            "downstream": await trace_column_lineage(ctx, field_id, "downstream", depth, include_proposed),
        }
    if include_proposed:
        direct = await ctx.reader.edges_for_field(field_id, direction, include_proposed=True)
    else:
        direct = ctx.graph.upstream(field_id, depth) if direction == "upstream" else ctx.graph.downstream(field_id, depth)
    return {"field_id": field_id, "direction": direction, "depth": depth, "edges": direct}


async def trace_table_lineage(ctx: AppContext, asset_id: str, direction: str = "upstream", depth: int | None = 3) -> dict[str, Any]:
    if direction == "both":
        return {
            "asset_id": asset_id,
            "direction": "both",
            "depth": depth,
            "upstream": await trace_table_lineage(ctx, asset_id, "upstream", depth),
            "downstream": await trace_table_lineage(ctx, asset_id, "downstream", depth),
        }
    return {"asset_id": asset_id, "direction": direction, "depth": depth, "edges": ctx.graph.table_lineage(asset_id, direction, depth)}


async def trace_full_column_lineage(ctx: AppContext, field_id: str) -> dict[str, Any]:
    return await trace_column_lineage(ctx, field_id, "both", None, False)


async def trace_full_table_lineage(ctx: AppContext, asset_id: str) -> dict[str, Any]:
    return await trace_table_lineage(ctx, asset_id, "both", None)


async def export_full_lineage_graph(ctx: AppContext) -> dict[str, Any]:
    graph = ctx.graph.full_graph()
    return {"node_count": len(graph["nodes"]), "edge_count": len(graph["edges"]), **graph}


async def explain_lineage_edge(ctx: AppContext, edge_id: str) -> dict[str, Any]:
    edge = await ctx.reader.edge_with_run(edge_id)
    if edge is None:
        return {"ok": False, "error": "edge_not_found"}
    return {"ok": True, "edge": edge}

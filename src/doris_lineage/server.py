from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from doris_lineage.config import load_settings
from doris_lineage.graph.nx_graph import LineageGraph
from doris_lineage.store.db import Database
from doris_lineage.store.reader import LineageReader
from doris_lineage.store.writer import LineageWriter
from doris_lineage.tools.context import AppContext
from doris_lineage.tools.health import lineage_health_check as health_impl
from doris_lineage.tools.impact import analyze_change_impact as impact_impl
from doris_lineage.tools.ingest import bootstrap_lineage_history as bootstrap_impl
from doris_lineage.tools.ingest import ingest_doris_audit_table as ingest_impl
from doris_lineage.tools.review import list_proposed_edges as list_proposed_impl
from doris_lineage.tools.review import review_edge as review_impl
from doris_lineage.tools.trace import explain_lineage_edge as explain_impl
from doris_lineage.tools.trace import export_full_lineage_graph as export_full_graph_impl
from doris_lineage.tools.trace import trace_full_column_lineage as trace_full_column_impl
from doris_lineage.tools.trace import trace_full_table_lineage as trace_full_table_impl
from doris_lineage.tools.trace import trace_column_lineage as trace_column_impl
from doris_lineage.tools.trace import trace_table_lineage as trace_table_impl


mcp = FastMCP("doris-lineage-mcp")
_ctx: AppContext | None = None


async def get_context() -> AppContext:
    global _ctx
    if _ctx is not None:
        return _ctx
    settings = load_settings()
    db = Database(settings.storage.db_path)
    await db.connect()
    await db.init_schema()
    reader = LineageReader(db)
    writer = LineageWriter(db)
    graph = LineageGraph()
    await graph.load_from_db(reader)
    _ctx = AppContext(settings=settings, db=db, reader=reader, writer=writer, graph=graph)
    return _ctx


@mcp.tool
async def ingest_doris_audit_table(
    start_time: str | None = None,
    end_time: str | None = None,
    limit: int = 1000,
    sql_contains: str | None = None,
    schemas: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    """Read Doris audit table rows, filter production lineage SQL, and write PROPOSED edges."""
    return await ingest_impl(await get_context(), start_time, end_time, limit, sql_contains, schemas)


@mcp.tool
async def bootstrap_lineage_history(events: list[dict[str, Any]], schemas: dict[str, list[str]] | None = None) -> dict[str, Any]:
    """Backfill lineage from explicit historical SQL events."""
    return await bootstrap_impl(await get_context(), events, schemas)


@mcp.tool
async def trace_table_lineage(asset_id: str, direction: str = "upstream", depth: int | None = 3) -> dict[str, Any]:
    """Trace confirmed upstream, downstream, or both table lineage for catalog.db.table."""
    return await trace_table_impl(await get_context(), asset_id, direction, depth)


@mcp.tool
async def trace_full_table_lineage(asset_id: str) -> dict[str, Any]:
    """Trace all confirmed upstream and downstream table lineage without depth limit."""
    return await trace_full_table_impl(await get_context(), asset_id)


@mcp.tool
async def trace_column_lineage(
    field_id: str,
    direction: str = "upstream",
    depth: int | None = 5,
    include_proposed: bool = False,
) -> dict[str, Any]:
    """Trace upstream, downstream, or both column lineage for catalog.db.table.column."""
    return await trace_column_impl(await get_context(), field_id, direction, depth, include_proposed)


@mcp.tool
async def trace_full_column_lineage(field_id: str) -> dict[str, Any]:
    """Trace all confirmed upstream and downstream column lineage without depth limit."""
    return await trace_full_column_impl(await get_context(), field_id)


@mcp.tool
async def export_full_lineage_graph() -> dict[str, Any]:
    """Return all confirmed lineage graph nodes and edges currently loaded in memory."""
    return await export_full_graph_impl(await get_context())


@mcp.tool
async def explain_lineage_edge(edge_id: str) -> dict[str, Any]:
    """Return the SQL, user, execution time, expression, and status behind one lineage edge."""
    return await explain_impl(await get_context(), edge_id)


@mcp.tool
async def list_proposed_edges(
    asset_prefix: str | None = None,
    min_confidence: float | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """List PROPOSED edges awaiting human or LLM-assisted review."""
    return await list_proposed_impl(await get_context(), asset_prefix, min_confidence, limit)


@mcp.tool
async def review_edge(edge_ids: list[str], action: str, reviewer: str, note: str | None = None) -> dict[str, Any]:
    """Confirm or reject proposed edges and sync the in-memory graph immediately."""
    return await review_impl(await get_context(), edge_ids, action, reviewer, note)


@mcp.tool
async def analyze_change_impact(field_id: str, change_type: str = "modify") -> dict[str, Any]:
    """Analyze downstream confirmed lineage impact for a field change."""
    return await impact_impl(await get_context(), field_id, change_type)


@mcp.tool
async def lineage_health_check() -> dict[str, Any]:
    """Report skip counts, parse error rate, proposed backlog, and edge status counts."""
    return await health_impl(await get_context())


@mcp.resource("lineage://asset/{db}/{table}")
async def asset_lineage_resource(db: str, table: str) -> dict[str, Any]:
    """Return current confirmed lineage summary for one table in the default catalog."""
    ctx = await get_context()
    asset_id = f"{ctx.settings.doris.default_catalog}.{db}.{table}"
    return {
        "asset_id": asset_id,
        "upstream": await trace_table_impl(ctx, asset_id, "upstream", 3),
        "downstream": await trace_table_impl(ctx, asset_id, "downstream", 3),
    }


@mcp.prompt
def review_guidance() -> str:
    return (
        "Review PROPOSED Doris lineage edges. Confirm edges only when the target column is "
        "clearly derived from the source column in the SQL expression. Reject ambiguous, "
        "unqualified multi-source columns and edges from failed or incomplete SQL."
    )


@mcp.prompt
def impact_analysis_guidance() -> str:
    return (
        "Interpret lineage impact results by grouping affected fields by downstream asset, "
        "highlighting shortest paths, confirmed edge confidence, and any critical views or "
        "materialized views on the path."
    )


def main() -> None:
    settings = load_settings()
    if settings.mcp.transport == "sse":
        mcp.run(transport="sse")
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

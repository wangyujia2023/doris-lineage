from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Awaitable, Callable

import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse
from starlette.routing import Route
from starlette.staticfiles import StaticFiles

from doris_lineage.config import load_settings
from doris_lineage.graph.nx_graph import LineageGraph
from doris_lineage.store.db import Database
from doris_lineage.store.reader import LineageReader
from doris_lineage.store.writer import LineageWriter
from doris_lineage.tools.context import AppContext
from doris_lineage.tools.health import lineage_health_check
from doris_lineage.tools.impact import analyze_change_impact
from doris_lineage.tools.ingest import bootstrap_lineage_history, ingest_doris_audit_table
from doris_lineage.tools.review import list_proposed_edges, review_edge
from doris_lineage.tools.trace import (
    explain_lineage_edge,
    export_full_lineage_graph,
    trace_column_lineage,
    trace_full_column_lineage,
    trace_full_table_lineage,
    trace_table_lineage,
)


ToolHandler = Callable[[AppContext, dict[str, Any]], Awaitable[dict[str, Any]]]

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


async def _ingest(ctx: AppContext, p: dict[str, Any]) -> dict[str, Any]:
    return await ingest_doris_audit_table(
        ctx,
        start_time=p.get("start_time") or None,
        end_time=p.get("end_time") or None,
        limit=int(p.get("limit") or 1000),
        sql_contains=p.get("sql_contains") or None,
        schemas=p.get("schemas") or None,
    )


async def _bootstrap(ctx: AppContext, p: dict[str, Any]) -> dict[str, Any]:
    return await bootstrap_lineage_history(ctx, p.get("events") or [], p.get("schemas") or None)


async def _trace_table(ctx: AppContext, p: dict[str, Any]) -> dict[str, Any]:
    return await trace_table_lineage(ctx, p["asset_id"], p.get("direction", "upstream"), p.get("depth", 3))


async def _trace_full_table(ctx: AppContext, p: dict[str, Any]) -> dict[str, Any]:
    return await trace_full_table_lineage(ctx, p["asset_id"])


async def _trace_column(ctx: AppContext, p: dict[str, Any]) -> dict[str, Any]:
    return await trace_column_lineage(
        ctx,
        p["field_id"],
        p.get("direction", "upstream"),
        p.get("depth", 5),
        bool(p.get("include_proposed", False)),
    )


async def _trace_full_column(ctx: AppContext, p: dict[str, Any]) -> dict[str, Any]:
    return await trace_full_column_lineage(ctx, p["field_id"])


async def _export_graph(ctx: AppContext, p: dict[str, Any]) -> dict[str, Any]:
    if bool(p.get("include_proposed", False)):
        edges = await ctx.reader.graph_edges(include_proposed=True)
        nodes = sorted({edge["source"] for edge in edges} | {edge["target"] for edge in edges})
        return {"node_count": len(nodes), "edge_count": len(edges), "nodes": nodes, "edges": edges}
    return await export_full_lineage_graph(ctx)


async def _explain(ctx: AppContext, p: dict[str, Any]) -> dict[str, Any]:
    return await explain_lineage_edge(ctx, p["edge_id"])


async def _list_proposed(ctx: AppContext, p: dict[str, Any]) -> dict[str, Any]:
    return await list_proposed_edges(
        ctx,
        p.get("asset_prefix") or None,
        p.get("min_confidence"),
        int(p.get("limit") or 100),
    )


async def _review(ctx: AppContext, p: dict[str, Any]) -> dict[str, Any]:
    return await review_edge(ctx, p.get("edge_ids") or [], p["action"], p.get("reviewer") or "web", p.get("note") or None)


async def _impact(ctx: AppContext, p: dict[str, Any]) -> dict[str, Any]:
    return await analyze_change_impact(ctx, p["field_id"], p.get("change_type") or "modify")


async def _health(ctx: AppContext, _p: dict[str, Any]) -> dict[str, Any]:
    return await lineage_health_check(ctx)


async def _asset_resource(ctx: AppContext, p: dict[str, Any]) -> dict[str, Any]:
    asset_id = f"{ctx.settings.doris.default_catalog}.{p['database']}.{p['table']}"
    return {
        "asset_id": asset_id,
        "upstream": await trace_table_lineage(ctx, asset_id, "upstream", 3),
        "downstream": await trace_table_lineage(ctx, asset_id, "downstream", 3),
    }


async def _prompts(_ctx: AppContext, _p: dict[str, Any]) -> dict[str, Any]:
    return {
        "review_guidance": (
            "Review PROPOSED Doris lineage edges. Confirm edges only when the target column is "
            "clearly derived from the source column in the SQL expression. Reject ambiguous, "
            "unqualified multi-source columns and edges from failed or incomplete SQL."
        ),
        "impact_analysis_guidance": (
            "Interpret lineage impact results by grouping affected fields by downstream asset, "
            "highlighting shortest paths, confirmed edge confidence, and any critical views or "
            "materialized views on the path."
        ),
    }


async def _list_assets(ctx: AppContext, p: dict[str, Any]) -> dict[str, Any]:
    return {"assets": await ctx.reader.list_assets(p.get("search") or None, int(p.get("limit") or 500))}


async def _list_fields(ctx: AppContext, p: dict[str, Any]) -> dict[str, Any]:
    return {"fields": await ctx.reader.list_fields(p["asset_id"], p.get("search") or None, int(p.get("limit") or 1000))}


TOOLS: dict[str, ToolHandler] = {
    "ingest_doris_audit_table": _ingest,
    "bootstrap_lineage_history": _bootstrap,
    "trace_table_lineage": _trace_table,
    "trace_full_table_lineage": _trace_full_table,
    "trace_column_lineage": _trace_column,
    "trace_full_column_lineage": _trace_full_column,
    "export_full_lineage_graph": _export_graph,
    "explain_lineage_edge": _explain,
    "list_proposed_edges": _list_proposed,
    "review_edge": _review,
    "analyze_change_impact": _impact,
    "lineage_health_check": _health,
    "asset_lineage_resource": _asset_resource,
    "prompts": _prompts,
    "list_assets": _list_assets,
    "list_fields": _list_fields,
}


TOOL_DEFS: list[dict[str, Any]] = [
    {"name": "ingest_doris_audit_table", "group": "采集", "params": {"start_time": "", "end_time": "", "limit": 1000, "sql_contains": "", "schemas": {}}},
    {"name": "bootstrap_lineage_history", "group": "采集", "params": {"events": [], "schemas": {}}},
    {"name": "trace_table_lineage", "group": "查询", "params": {"asset_id": "internal.retail_dw.dwd_order_detail", "direction": "both", "depth": 5}},
    {"name": "trace_full_table_lineage", "group": "查询", "params": {"asset_id": "internal.retail_dw.dwd_order_detail"}},
    {"name": "trace_column_lineage", "group": "查询", "params": {"field_id": "internal.retail_dw.dwd_order_detail.net_amount", "direction": "both", "depth": 5, "include_proposed": False}},
    {"name": "trace_full_column_lineage", "group": "查询", "params": {"field_id": "internal.retail_dw.dwd_order_detail.net_amount"}},
    {"name": "export_full_lineage_graph", "group": "查询", "params": {"include_proposed": True}},
    {"name": "explain_lineage_edge", "group": "查询", "params": {"edge_id": ""}},
    {"name": "list_proposed_edges", "group": "核验", "params": {"asset_prefix": "", "min_confidence": 0.6, "limit": 100}},
    {"name": "review_edge", "group": "核验", "params": {"edge_ids": [], "action": "confirm", "reviewer": "web", "note": ""}},
    {"name": "analyze_change_impact", "group": "分析", "params": {"field_id": "internal.retail_dw.dwd_order_detail.net_amount", "change_type": "modify"}},
    {"name": "lineage_health_check", "group": "健康", "params": {}},
    {"name": "asset_lineage_resource", "group": "Resource", "params": {"database": "retail_dw", "table": "dwd_order_detail"}},
    {"name": "prompts", "group": "Prompts", "params": {}},
    {"name": "list_assets", "group": "浏览", "params": {"search": "", "limit": 500}},
    {"name": "list_fields", "group": "浏览", "params": {"asset_id": "internal.retail_dw.dwd_order_detail", "search": "", "limit": 1000}},
]


async def index(_request: Request) -> FileResponse:
    return FileResponse(Path(__file__).with_name("web_static") / "index.html")


async def tool_defs(_request: Request) -> JSONResponse:
    return JSONResponse({"tools": TOOL_DEFS})


async def call_tool(request: Request) -> JSONResponse:
    name = request.path_params["name"]
    if name not in TOOLS:
        return JSONResponse({"ok": False, "error": f"unknown tool: {name}"}, status_code=404)
    payload = await request.json()
    try:
        result = await TOOLS[name](await get_context(), payload or {})
        return JSONResponse({"ok": True, "tool": name, "result": result})
    except KeyError as exc:
        return JSONResponse({"ok": False, "tool": name, "error": f"missing parameter: {exc}"}, status_code=400)
    except json.JSONDecodeError as exc:
        return JSONResponse({"ok": False, "tool": name, "error": str(exc)}, status_code=400)
    except Exception as exc:  # noqa: BLE001 - UI should preserve tool errors.
        return JSONResponse({"ok": False, "tool": name, "error": str(exc)}, status_code=500)


routes = [
    Route("/", index),
    Route("/api/tools", tool_defs),
    Route("/api/tools/{name}", call_tool, methods=["POST"]),
]

app = Starlette(routes=routes)
app.mount("/static", StaticFiles(directory=Path(__file__).with_name("web_static")), name="static")


def main() -> None:
    uvicorn.run("doris_lineage.web:app", host="127.0.0.1", port=8888, reload=False)


if __name__ == "__main__":
    main()

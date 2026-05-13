from __future__ import annotations

import hashlib
from typing import Iterable

import sqlglot
from sqlglot import exp

from doris_lineage.models import AssetType, EdgeType, LineageEdgeDraft, LineageResult, SqlEvent
from doris_lineage.parser.confidence import score_lineage
from doris_lineage.parser.schema_resolver import SchemaResolver


AGGREGATES = (exp.AggFunc,)
WINDOWS = (exp.Window,)


def ast_fingerprint(node: exp.Expression) -> str:
    normalized = node.copy()

    def scrub_literals(n: exp.Expression) -> exp.Expression:
        if isinstance(n, exp.Literal):
            return exp.Literal.string("?")
        return n

    normalized = normalized.transform(scrub_literals)
    canonical = normalized.sql(dialect="doris", normalize=True, pretty=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def parse(event: SqlEvent, schemas: dict[str, list[str]] | None = None) -> LineageResult | None:
    try:
        ast = sqlglot.parse_one(event.sql_text, dialect="doris")
    except sqlglot.errors.ParseError:
        return None

    resolver = SchemaResolver(event.catalog, event.database, schemas or {})
    target_asset, target_type, select_expr, target_columns = _extract_target(ast, resolver)
    if target_asset is None or select_expr is None:
        return None

    source_assets, alias_map = _source_assets(select_expr, resolver)
    if not source_assets:
        return None

    edges, expanded_star, schema_exact = _build_column_edges(
        select_expr=select_expr,
        target_asset=target_asset,
        target_columns=target_columns,
        source_assets=source_assets,
        alias_map=alias_map,
        resolver=resolver,
    )
    if not edges:
        return None

    confidence = score_lineage(schema_exact=schema_exact, expanded_star=expanded_star)
    if confidence <= 0:
        return None
    for edge in edges:
        edge.confidence = min(edge.confidence, confidence)

    return LineageResult(
        query_id=event.query_id,
        stmt_type=event.stmt_type,
        sql_fingerprint=ast_fingerprint(ast),
        target_asset=target_asset,
        target_asset_type=target_type,
        edges=edges,
        confidence=confidence,
        metadata={"source_assets": source_assets},
    )


def _extract_target(
    ast: exp.Expression,
    resolver: SchemaResolver,
) -> tuple[str | None, AssetType, exp.Select | None, list[str] | None]:
    if isinstance(ast, exp.Insert):
        target = ast.this
        select_expr = ast.expression if isinstance(ast.expression, exp.Select) else ast.find(exp.Select)
        target_asset = _table_asset(target, resolver) if target is not None else None
        columns = _target_columns_from_schema(target)
        return target_asset, AssetType.TABLE, select_expr, columns

    if isinstance(ast, exp.Create):
        target_asset = _table_asset(ast.this, resolver) if ast.this is not None else None
        select_expr = ast.expression if isinstance(ast.expression, exp.Select) else ast.find(exp.Select)
        kind = (ast.args.get("kind") or "").upper()
        if "VIEW" in kind and "MATERIALIZED" in kind:
            asset_type = AssetType.MATERIALIZED_VIEW
        elif "VIEW" in kind:
            asset_type = AssetType.VIEW
        else:
            asset_type = AssetType.TABLE
        return target_asset, asset_type, select_expr, None

    return None, AssetType.TABLE, None, None


def _target_columns_from_schema(target: exp.Expression | None) -> list[str] | None:
    if target is None:
        return None
    schema = target.find(exp.Schema)
    if not schema:
        return None
    columns = [c.name for c in schema.expressions if isinstance(c, exp.Identifier)]
    return columns or None


def _table_asset(node: exp.Expression, resolver: SchemaResolver) -> str | None:
    table = node if isinstance(node, exp.Table) else node.find(exp.Table)
    if table is None:
        return None
    return _table_to_asset(table, resolver)


def _table_to_asset(table: exp.Table, resolver: SchemaResolver) -> str:
    catalog = table.catalog or resolver.catalog
    database = table.db or resolver.database
    return f"{catalog}.{database}.{table.name}"


def _source_assets(select_expr: exp.Select, resolver: SchemaResolver) -> tuple[list[str], dict[str, str]]:
    assets: list[str] = []
    alias_map: dict[str, str] = {}
    cte_names = {cte.alias for cte in select_expr.find_all(exp.CTE) if cte.alias}
    for table in select_expr.find_all(exp.Table):
        if table.name in cte_names:
            continue
        asset = _table_to_asset(table, resolver)
        if asset not in assets:
            assets.append(asset)
        alias_map[table.alias_or_name] = asset
        alias_map[table.name] = asset
    return assets, alias_map


def _build_column_edges(
    select_expr: exp.Select,
    target_asset: str,
    target_columns: list[str] | None,
    source_assets: list[str],
    alias_map: dict[str, str],
    resolver: SchemaResolver,
) -> tuple[list[LineageEdgeDraft], bool, bool]:
    edges: list[LineageEdgeDraft] = []
    expanded_star = False
    schema_exact = True
    projections = list(select_expr.expressions)
    if not projections:
        return [], False, False

    for idx, projection in enumerate(projections):
        if isinstance(projection, exp.Star):
            expanded = resolver.resolve_star(source_assets)
            if not expanded:
                return [], True, False
            expanded_star = True
            for source_asset, column in expanded:
                target_column = column
                edges.append(
                    LineageEdgeDraft(
                        source_field=f"{source_asset}.{column}",
                        target_field=f"{target_asset}.{target_column}",
                        edge_type=EdgeType.DIRECT,
                        transform_expr="*",
                        is_passthrough=True,
                        confidence=0.75,
                    )
                )
            continue

        target_column = _target_column(projection, idx, target_columns)
        if not target_column:
            return [], expanded_star, False
        source_columns = _projection_source_columns(projection, source_assets, alias_map, resolver)
        if not source_columns:
            return [], expanded_star, False
        edge_type = _edge_type(projection)
        passthrough = edge_type == EdgeType.DIRECT and len(source_columns) == 1
        for source_asset, source_column in source_columns:
            edges.append(
                LineageEdgeDraft(
                    source_field=f"{source_asset}.{source_column}",
                    target_field=f"{target_asset}.{target_column}",
                    edge_type=edge_type,
                    transform_expr=projection.sql(dialect="doris", normalize=True),
                    is_passthrough=passthrough,
                    confidence=0.95,
                )
            )
    return edges, expanded_star, schema_exact


def _target_column(projection: exp.Expression, idx: int, target_columns: list[str] | None) -> str | None:
    if target_columns and idx < len(target_columns):
        return target_columns[idx]
    alias = projection.alias_or_name
    if alias:
        return alias
    if isinstance(projection, exp.Column):
        return projection.name
    return None


def _projection_source_columns(
    projection: exp.Expression,
    source_assets: list[str],
    alias_map: dict[str, str],
    resolver: SchemaResolver,
) -> list[tuple[str, str]]:
    seen: set[tuple[str, str]] = set()
    resolved: list[tuple[str, str]] = []
    for column in projection.find_all(exp.Column):
        table_name = column.table
        if table_name:
            source_asset = alias_map.get(table_name)
            item = (source_asset, column.name) if source_asset else None
        else:
            item = resolver.resolve_column(column.name, source_assets)
        if item and item not in seen:
            seen.add(item)
            resolved.append(item)
    return resolved


def _edge_type(projection: exp.Expression) -> EdgeType:
    if any(True for _ in projection.find_all(*AGGREGATES)):
        return EdgeType.AGGREGATION
    if any(True for _ in projection.find_all(*WINDOWS)):
        return EdgeType.WINDOW
    columns = list(projection.find_all(exp.Column))
    if isinstance(projection, exp.Column) or (isinstance(projection, exp.Alias) and isinstance(projection.this, exp.Column)):
        return EdgeType.DIRECT
    if len(columns) > 1:
        return EdgeType.EXPRESSION
    return EdgeType.EXPRESSION

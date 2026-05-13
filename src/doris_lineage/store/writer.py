from __future__ import annotations

from uuid import uuid4

from doris_lineage.models import LineageResult, SqlEvent, utc_now
from doris_lineage.store.db import Database


def split_asset_id(asset_id: str) -> tuple[str, str, str]:
    parts = asset_id.split(".")
    if len(parts) < 3:
        return "internal", "default", asset_id
    return parts[-3], parts[-2], parts[-1]


def split_field_id(field_id: str) -> tuple[str, str]:
    asset_id, column = field_id.rsplit(".", 1)
    return asset_id, column


class LineageWriter:
    def __init__(self, db: Database):
        self.db = db

    async def write_skipped_run(self, event: SqlEvent, reason: str) -> None:
        await self.db.execute(
            """
            INSERT OR REPLACE INTO lineage_run
            (query_id, user, stmt_type, sql_text, executed_at, ingested_at, skip_reason)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (event.query_id, event.user, event.stmt_type, event.sql_text, event.executed_at, utc_now(), reason),
        )
        await self.db.commit()

    async def write_result(self, event: SqlEvent, result: LineageResult) -> int:
        now = utc_now()
        await self.db.execute(
            """
            INSERT OR REPLACE INTO lineage_run
            (query_id, user, stmt_type, sql_text, sql_fingerprint, executed_at, ingested_at, skip_reason)
            VALUES (?, ?, ?, ?, ?, ?, ?, NULL)
            """,
            (
                event.query_id,
                event.user,
                result.stmt_type,
                event.sql_text,
                result.sql_fingerprint,
                event.executed_at,
                now,
            ),
        )

        assets: dict[str, str] = {result.target_asset: result.target_asset_type.value}
        fields: set[str] = set()
        for edge in result.edges:
            source_asset, _ = split_field_id(edge.source_field)
            target_asset, _ = split_field_id(edge.target_field)
            assets.setdefault(source_asset, "TABLE")
            assets.setdefault(target_asset, result.target_asset_type.value if target_asset == result.target_asset else "TABLE")
            fields.add(edge.source_field)
            fields.add(edge.target_field)

        for asset_id, asset_type in assets.items():
            catalog, database, table_name = split_asset_id(asset_id)
            await self.db.execute(
                """
                INSERT OR IGNORE INTO lineage_asset
                (asset_id, catalog, database, table_name, asset_type, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (asset_id, catalog, database, table_name, asset_type, now),
            )

        for field_id in fields:
            asset_id, column = split_field_id(field_id)
            await self.db.execute(
                """
                INSERT OR IGNORE INTO lineage_field
                (field_id, asset_id, column_name, data_type)
                VALUES (?, ?, ?, NULL)
                """,
                (field_id, asset_id, column),
            )

        for edge in result.edges:
            await self.db.execute(
                """
                INSERT INTO lineage_edge
                (edge_id, source_field, target_field, edge_type, transform_expr, is_passthrough,
                 query_id, confidence, edge_status, valid_from, valid_to)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'PROPOSED', ?, NULL)
                """,
                (
                    str(uuid4()),
                    edge.source_field,
                    edge.target_field,
                    edge.edge_type.value,
                    edge.transform_expr,
                    1 if edge.is_passthrough else 0,
                    event.query_id,
                    edge.confidence,
                    event.executed_at,
                ),
            )
        await self.db.commit()
        return len(result.edges)

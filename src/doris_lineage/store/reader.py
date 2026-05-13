from __future__ import annotations

from typing import Any

from doris_lineage.models import EdgeStatus
from doris_lineage.store.db import Database


class LineageReader:
    def __init__(self, db: Database):
        self.db = db

    async def confirmed_edges(self) -> list[dict[str, Any]]:
        return await self.db.fetch_all(
            """
            SELECT source_field, target_field, edge_type, confidence, transform_expr, query_id
            FROM lineage_edge
            WHERE edge_status = 'CONFIRMED' AND valid_to IS NULL
            """
        )

    async def graph_edges(self, include_proposed: bool = False) -> list[dict[str, Any]]:
        statuses = ["CONFIRMED", "PROPOSED"] if include_proposed else ["CONFIRMED"]
        placeholders = ",".join("?" for _ in statuses)
        return await self.db.fetch_all(
            f"""
            SELECT source_field AS source, target_field AS target, edge_type, confidence,
                   transform_expr, query_id, edge_status
            FROM lineage_edge
            WHERE edge_status IN ({placeholders}) AND valid_to IS NULL
            ORDER BY query_id, source_field, target_field
            """,
            statuses,
        )

    async def edges_for_field(
        self,
        field_id: str,
        direction: str,
        include_proposed: bool = False,
    ) -> list[dict[str, Any]]:
        statuses = ["CONFIRMED", "PROPOSED"] if include_proposed else ["CONFIRMED"]
        placeholders = ",".join("?" for _ in statuses)
        column = "target_field" if direction == "upstream" else "source_field"
        return await self.db.fetch_all(
            f"""
            SELECT * FROM lineage_edge
            WHERE {column} = ? AND edge_status IN ({placeholders}) AND valid_to IS NULL
            ORDER BY confidence DESC
            """,
            (field_id, *statuses),
        )

    async def proposed_edges(
        self,
        asset_prefix: str | None = None,
        min_confidence: float = 0.6,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        params: list[Any] = [min_confidence]
        extra = ""
        if asset_prefix:
            extra = "AND (source_field LIKE ? OR target_field LIKE ?)"
            params.extend([f"{asset_prefix}%", f"{asset_prefix}%"])
        params.append(limit)
        return await self.db.fetch_all(
            f"""
            SELECT e.*, r.sql_text, r.user, r.executed_at
            FROM lineage_edge e
            JOIN lineage_run r ON r.query_id = e.query_id
            WHERE e.edge_status = 'PROPOSED' AND e.confidence >= ?
            {extra}
            ORDER BY e.confidence DESC
            LIMIT ?
            """,
            params,
        )

    async def edge_with_run(self, edge_id: str) -> dict[str, Any] | None:
        return await self.db.fetch_one(
            """
            SELECT e.*, r.sql_text, r.user, r.executed_at, r.stmt_type
            FROM lineage_edge e
            JOIN lineage_run r ON r.query_id = e.query_id
            WHERE e.edge_id = ?
            """,
            (edge_id,),
        )

    async def review_edges(
        self,
        edge_ids: list[str],
        status: EdgeStatus,
        reviewer: str,
        note: str | None,
        reviewed_at: str,
    ) -> list[dict[str, Any]]:
        if not edge_ids:
            return []
        placeholders = ",".join("?" for _ in edge_ids)
        existing = await self.db.fetch_all(
            f"SELECT edge_id, source_field, target_field, edge_type, confidence FROM lineage_edge WHERE edge_id IN ({placeholders})",
            edge_ids,
        )
        await self.db.execute_many(
            """
            UPDATE lineage_edge
            SET edge_status = ?, confirmed_by = ?, confirmed_at = ?, review_note = ?
            WHERE edge_id = ?
            """,
            [(status.value, reviewer, reviewed_at, note, edge_id) for edge_id in edge_ids],
        )
        await self.db.commit()
        return existing

    async def health_summary(self) -> dict[str, Any]:
        run_stats = await self.db.fetch_all(
            """
            SELECT COALESCE(skip_reason, 'success') AS status, COUNT(*) AS count
            FROM lineage_run
            GROUP BY COALESCE(skip_reason, 'success')
            """
        )
        edge_stats = await self.db.fetch_all(
            "SELECT edge_status, COUNT(*) AS count FROM lineage_edge GROUP BY edge_status"
        )
        low_conf = await self.db.fetch_one(
            "SELECT COUNT(*) AS count FROM lineage_edge WHERE confidence < 0.6"
        )
        return {"runs": run_stats, "edges": edge_stats, "low_confidence_edges": low_conf["count"] if low_conf else 0}

    async def list_assets(self, search: str | None = None, limit: int = 500) -> list[dict[str, Any]]:
        params: list[Any] = []
        where = ""
        if search:
            where = "WHERE asset_id LIKE ?"
            params.append(f"%{search}%")
        params.append(limit)
        return await self.db.fetch_all(
            f"""
            SELECT asset_id, catalog, database, table_name, asset_type, created_at
            FROM lineage_asset
            {where}
            ORDER BY catalog, database, table_name
            LIMIT ?
            """,
            params,
        )

    async def list_fields(self, asset_id: str, search: str | None = None, limit: int = 1000) -> list[dict[str, Any]]:
        params: list[Any] = [asset_id]
        extra = ""
        if search:
            extra = "AND column_name LIKE ?"
            params.append(f"%{search}%")
        params.append(limit)
        return await self.db.fetch_all(
            f"""
            SELECT field_id, asset_id, column_name, data_type
            FROM lineage_field
            WHERE asset_id = ?
            {extra}
            ORDER BY column_name
            LIMIT ?
            """,
            params,
        )

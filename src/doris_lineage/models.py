from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class StatementType(StrEnum):
    INSERT_INTO_SELECT = "INSERT_INTO_SELECT"
    INSERT_OVERWRITE_SELECT = "INSERT_OVERWRITE_SELECT"
    CREATE_TABLE_AS_SELECT = "CREATE_TABLE_AS_SELECT"
    CREATE_VIEW = "CREATE_VIEW"
    CREATE_MATERIALIZED_VIEW = "CREATE_MATERIALIZED_VIEW"
    REFRESH_MATERIALIZED_VIEW = "REFRESH_MATERIALIZED_VIEW"


class AssetType(StrEnum):
    TABLE = "TABLE"
    VIEW = "VIEW"
    MATERIALIZED_VIEW = "MATERIALIZED_VIEW"


class EdgeType(StrEnum):
    DIRECT = "DIRECT"
    EXPRESSION = "EXPRESSION"
    AGGREGATION = "AGGREGATION"
    JOIN = "JOIN"
    FILTER = "FILTER"
    WINDOW = "WINDOW"
    UNION = "UNION"


class EdgeStatus(StrEnum):
    PROPOSED = "PROPOSED"
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"
    OUTDATED = "OUTDATED"


class SqlEvent(BaseModel):
    query_id: str
    user: str
    database: str
    catalog: str = "internal"
    stmt_type: str
    sql_text: str
    executed_at: str
    state: str = "EOF"


class LineageEdgeDraft(BaseModel):
    source_field: str
    target_field: str
    edge_type: EdgeType = EdgeType.DIRECT
    transform_expr: str | None = None
    is_passthrough: bool = False
    confidence: float = Field(ge=0.0, le=1.0)


class LineageResult(BaseModel):
    query_id: str
    stmt_type: str
    sql_fingerprint: str
    target_asset: str
    target_asset_type: AssetType
    edges: list[LineageEdgeDraft]
    confidence: float = Field(ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)

from __future__ import annotations

from doris_lineage.models import LineageResult, SqlEvent
from doris_lineage.parser.sqlglot_parser import parse


def parse_materialized_view(event: SqlEvent, schemas: dict[str, list[str]] | None = None) -> LineageResult | None:
    return parse(event, schemas=schemas)

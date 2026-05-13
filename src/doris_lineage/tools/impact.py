from __future__ import annotations

from typing import Any

from doris_lineage.tools.context import AppContext


async def analyze_change_impact(ctx: AppContext, field_id: str, change_type: str = "modify") -> dict[str, Any]:
    impact = ctx.graph.impact(field_id)
    return {"field_id": field_id, "change_type": change_type, **impact}

from __future__ import annotations


def score_lineage(schema_exact: bool, expanded_star: bool, mv_parser: bool = False) -> float:
    if schema_exact and not expanded_star:
        return 0.95
    if schema_exact and expanded_star:
        return 0.75
    if mv_parser:
        return 0.65
    return 0.0

from __future__ import annotations

import json
from pathlib import Path

import sqlglot
from sqlglot import exp


def classify(ast: exp.Expression, sql: str) -> str:
    normalized = " ".join(sql.lower().split())
    if isinstance(ast, exp.Create):
        kind = str(ast.args.get("kind") or "").upper()
        if "MATERIALIZED" in kind and "VIEW" in kind:
            return "CREATE_MATERIALIZED_VIEW"
        if "VIEW" in kind:
            return "CREATE_VIEW"
        return "CREATE_TABLE_AS_SELECT"
    if "insert overwrite" in normalized:
        return "INSERT_OVERWRITE_SELECT"
    return "INSERT_INTO_SELECT"


def main() -> None:
    sql_path = Path(__file__).with_name("retail_20_etl.sql")
    statements = sqlglot.parse(sql_path.read_text(encoding="utf-8"), read="doris")
    events = []
    for index, ast in enumerate(statements, start=1):
        sql = ast.sql(dialect="doris", pretty=False)
        events.append(
            {
                "query_id": f"retail_etl_{index:02d}",
                "user": "retail_etl",
                "database": "retail_dw",
                "catalog": "internal",
                "stmt_type": classify(ast, sql),
                "sql_text": sql,
                "executed_at": f"2026-05-12T00:{index:02d}:00+00:00",
                "state": "EOF",
            }
        )
    print(json.dumps(events, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

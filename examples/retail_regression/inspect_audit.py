from __future__ import annotations

import json
import sys

import pymysql

from doris_lineage.collector.doris_client import connect_doris
from doris_lineage.config import load_settings


def main() -> None:
    settings = load_settings()
    marker = sys.argv[1] if len(sys.argv) > 1 else None
    conn = connect_doris(settings.doris, cursorclass=pymysql.cursors.DictCursor)
    try:
        with conn.cursor() as cursor:
            for sql in [
                "DESC internal.__internal_schema.audit_log",
                "SELECT * FROM internal.__internal_schema.audit_log ORDER BY `time` DESC LIMIT 5",
            ]:
                try:
                    cursor.execute(sql)
                    print("SQL", sql)
                    print(json.dumps(cursor.fetchall(), ensure_ascii=False, default=str, indent=2))
                except Exception as exc:  # noqa: BLE001
                    print("ERR", sql, str(exc))
            if marker:
                cursor.execute(
                    """
                    SELECT `time`, user, catalog, db, state, stmt_type, LEFT(stmt, 500) AS stmt
                    FROM internal.__internal_schema.audit_log
                    WHERE stmt LIKE %s
                    ORDER BY `time` DESC
                    LIMIT 50
                    """,
                    (f"%{marker}%",),
                )
                print("SQL marker lookup", marker)
                print(json.dumps(cursor.fetchall(), ensure_ascii=False, default=str, indent=2))
    finally:
        conn.close()


if __name__ == "__main__":
    main()

from __future__ import annotations

import pymysql
import pymysql.cursors
from pymysql.charset import charset_by_name

from doris_lineage.config import DorisConfig


class DorisConnection(pymysql.connections.Connection):
    def set_character_set(self, charset: str, collation: str | None = None) -> None:
        """Avoid PyMySQL's startup SET NAMES query.

        Doris accepts the charset in the handshake. Sending MySQL compatibility
        setup statements pollutes audit logs, so we only update client-side
        decoding state here.
        """
        encoding = charset_by_name(charset).encoding
        self.charset = charset
        self.encoding = encoding
        self.collation = collation


def connect_doris(doris: DorisConfig, cursorclass: type[pymysql.cursors.Cursor] | None = None) -> pymysql.Connection:
    return DorisConnection(
        host=doris.host,
        port=doris.port,
        user=doris.user,
        password=doris.password,
        charset="utf8mb4",
        cursorclass=cursorclass or pymysql.cursors.Cursor,
        sql_mode=None,
        init_command=None,
        autocommit=None,
    )

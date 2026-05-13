from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from pydantic import BaseModel


class DorisConfig(BaseModel):
    host: str = "localhost"
    port: int = 9030
    user: str = "lineage_reader"
    password: str = ""
    default_catalog: str = "internal"


class AuditTableConfig(BaseModel):
    table: str = "internal.__internal_schema.audit_log"
    query_id_column: str = "query_id"
    user_column: str = "user"
    database_column: str = "db"
    catalog_column: str = "catalog"
    sql_column: str = "stmt"
    state_column: str = "state"
    executed_at_column: str = "time"
    stmt_type_column: str = ""
    system_user_blacklist: list[str] = ["root", "admin", "doris", "fe_scheduler"]
    system_db_blacklist: list[str] = ["information_schema", "__internal_schema", "_statistics_"]


class StorageConfig(BaseModel):
    db_path: str = "./lineage.db"


class McpConfig(BaseModel):
    transport: str = "stdio"
    default_confidence_threshold: float = 0.6


class Settings(BaseModel):
    doris: DorisConfig = DorisConfig()
    audit_table: AuditTableConfig = AuditTableConfig()
    storage: StorageConfig = StorageConfig()
    mcp: McpConfig = McpConfig()


def _parse_scalar(value: str) -> Any:
    value = value.strip()
    if not value:
        return ""
    if value[0:1] in {"'", '"', "["}:
        try:
            return ast.literal_eval(value)
        except (SyntaxError, ValueError):
            return value.strip("'\"")
    if value.lower() in {"true", "false"}:
        return value.lower() == "true"
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value


def _load_simple_yaml(path: Path) -> dict[str, Any]:
    data: dict[str, Any] = {}
    current: dict[str, Any] | None = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line:
            continue
        if not raw.startswith(" ") and line.endswith(":"):
            section = line[:-1].strip()
            current = {}
            data[section] = current
            continue
        if current is None or ":" not in line:
            continue
        key, value = line.split(":", 1)
        current[key.strip()] = _parse_scalar(value)
    return data


def load_settings(config_path: str = "config.yaml") -> Settings:
    path = Path(config_path)
    if not path.exists():
        return Settings()
    return Settings.model_validate(_load_simple_yaml(path))

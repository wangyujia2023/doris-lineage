from __future__ import annotations

from dataclasses import dataclass, field


def normalize_asset(catalog: str, database: str, table: str) -> str:
    parts = [p.strip("`\"") for p in table.split(".") if p]
    if len(parts) >= 3:
        return ".".join(parts[-3:])
    if len(parts) == 2:
        return f"{catalog}.{parts[0]}.{parts[1]}"
    return f"{catalog}.{database}.{parts[0]}"


@dataclass
class SchemaResolver:
    catalog: str
    database: str
    schemas: dict[str, list[str]] = field(default_factory=dict)

    def normalize_asset(self, table: str) -> str:
        return normalize_asset(self.catalog, self.database, table)

    def get_columns(self, asset_id: str) -> list[str] | None:
        return self.schemas.get(asset_id)

    def resolve_star(self, asset_ids: list[str]) -> list[tuple[str, str]] | None:
        fields: list[tuple[str, str]] = []
        for asset_id in asset_ids:
            columns = self.get_columns(asset_id)
            if not columns:
                return None
            fields.extend((asset_id, column) for column in columns)
        return fields

    def resolve_column(self, column: str, source_assets: list[str]) -> tuple[str, str] | None:
        matches: list[tuple[str, str]] = []
        for asset_id in source_assets:
            columns = self.get_columns(asset_id)
            if columns and column in columns:
                matches.append((asset_id, column))
        if len(matches) == 1:
            return matches[0]
        if len(source_assets) == 1:
            return source_assets[0], column
        return None

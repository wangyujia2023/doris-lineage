PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS lineage_run (
    query_id        TEXT PRIMARY KEY,
    user            TEXT NOT NULL,
    stmt_type       TEXT NOT NULL,
    sql_text        TEXT NOT NULL,
    sql_fingerprint TEXT,
    executed_at     TEXT NOT NULL,
    ingested_at     TEXT NOT NULL,
    skip_reason     TEXT
);

CREATE TABLE IF NOT EXISTS lineage_asset (
    asset_id    TEXT PRIMARY KEY,
    catalog     TEXT NOT NULL,
    database    TEXT NOT NULL,
    table_name  TEXT NOT NULL,
    asset_type  TEXT NOT NULL,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS lineage_field (
    field_id    TEXT PRIMARY KEY,
    asset_id    TEXT NOT NULL,
    column_name TEXT NOT NULL,
    data_type   TEXT,
    FOREIGN KEY (asset_id) REFERENCES lineage_asset(asset_id)
);

CREATE TABLE IF NOT EXISTS lineage_edge (
    edge_id          TEXT PRIMARY KEY,
    source_field     TEXT NOT NULL,
    target_field     TEXT NOT NULL,
    edge_type        TEXT NOT NULL,
    transform_expr   TEXT,
    is_passthrough   INTEGER NOT NULL DEFAULT 0,
    query_id         TEXT NOT NULL,
    confidence       REAL NOT NULL,
    edge_status      TEXT NOT NULL DEFAULT 'PROPOSED',
    confirmed_by     TEXT,
    confirmed_at     TEXT,
    review_note      TEXT,
    valid_from       TEXT NOT NULL,
    valid_to         TEXT,
    FOREIGN KEY (query_id) REFERENCES lineage_run(query_id)
);

CREATE INDEX IF NOT EXISTS idx_edge_target ON lineage_edge(target_field, edge_status);
CREATE INDEX IF NOT EXISTS idx_edge_source ON lineage_edge(source_field, edge_status);
CREATE INDEX IF NOT EXISTS idx_edge_status ON lineage_edge(edge_status);
CREATE INDEX IF NOT EXISTS idx_edge_query ON lineage_edge(query_id);

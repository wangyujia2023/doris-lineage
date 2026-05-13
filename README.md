# Doris Lineage MCP

SQL-first Apache Doris data lineage MCP server. The project reads successful SQL
from Doris audit table, parses lineage from AST, persists it in SQLite, and
serves lineage through MCP tools plus a local Web console.

The design deliberately does not depend on Doris Nereids internals. SQL comes
from the audit table, so the collector and parser can be extended to other SQL
engines later.

## Features

- Audit-table ingestion: reads `internal.__internal_schema.audit_log` through
  Doris MySQL protocol.
- SQL-first parser: supports `INSERT SELECT`, `INSERT OVERWRITE`, CTAS, CTE,
  views, materialized views, joins, aggregations, window expressions, and
  `UNION ALL`.
- Four-level identity: column ids use `catalog.database.table.column`; table
  ids use `catalog.database.table`.
- AST semantic fingerprint: fingerprints are based on normalized AST rather
  than raw SQL text.
- Review workflow: parsed edges enter `PROPOSED`; confirmed edges become query
  defaults and are loaded into the in-memory graph.
- Fast graph traversal: SQLite WAL for persistence, `networkx.DiGraph` for
  upstream/downstream and impact analysis.
- Web console: execute MCP-equivalent tools, browse assets, view lineage graph,
  inspect lineage edges in table form.
- Zero external services: no Kafka, Redis, Postgres, or Neo4j required.

## Architecture

```text
Doris audit table
      |
      v
collector/audit_table_reader.py
      |
      v
collector/sql_filter.py
      |
      v
parser/sqlglot_parser.py + schema_resolver.py
      |
      v
SQLite lineage.db  <---- review tools
      |
      v
networkx DiGraph
      |
      v
FastMCP tools / Web console
```

## Project Layout

```text
src/doris_lineage/
  server.py                 FastMCP entrypoint
  web.py                    Web console API and static server
  config.py                 YAML config loader
  collector/                Doris audit table reader and SQL filters
  parser/                   SQLGlot parser, schema resolver, confidence scoring
  store/                    SQLite schema, reader, writer
  graph/                    networkx graph wrapper
  tools/                    MCP tool implementations
  web_static/               Web console UI

examples/retail_regression/
  retail_schema_and_seed.sql  Retail source/schema seed data
  retail_20_etl.sql           20 ETL statements for regression
  run_regression.py           Doris execution + audit ingestion regression
```

## Requirements

- Python 3.12+
- `uv`
- Apache Doris with audit table enabled

Core dependencies are intentionally small:

- `fastmcp`
- `sqlglot`
- `networkx`
- `aiosqlite`
- `pydantic`
- `pymysql`
- `starlette`
- `uvicorn`

## Setup

```bash
uv sync
cp config.example.yaml config.yaml
```

Edit `config.yaml` for your Doris cluster:

```yaml
doris:
  host: "localhost"
  port: 9030
  user: "lineage_reader"
  password: ""
  default_catalog: "internal"

audit_table:
  table: "internal.__internal_schema.audit_log"
```

`config.yaml` is ignored by git because it normally contains local connection
information.

## Run MCP Server

```bash
uv run doris-lineage-mcp
```

Equivalent:

```bash
uv run python -m doris_lineage.server
```

## Run Web Console

```bash
uv run doris-lineage-web
```

Open:

```text
http://127.0.0.1:8888
```

The Web console provides three main tabs:

- Parameters: edit and execute any exposed MCP-equivalent tool payload.
- Lineage Graph: visualize table/column lineage and change impact graphically.
- Table: inspect lineage edges with source, target, type, status, confidence,
  and query id.

## Main Tools

Collection:

- `ingest_doris_audit_table`: query Doris audit table and write parsed edges as
  `PROPOSED`.
- `bootstrap_lineage_history`: backfill from explicit SQL event rows.

Query:

- `trace_table_lineage`: table upstream/downstream lineage.
- `trace_full_table_lineage`: all upstream and downstream table lineage.
- `trace_column_lineage`: column upstream/downstream lineage.
- `trace_full_column_lineage`: all upstream and downstream column lineage.
- `export_full_lineage_graph`: export graph nodes and edges.
- `explain_lineage_edge`: show source SQL, user, time, and metadata for one
  edge.

Review:

- `list_proposed_edges`: list pending lineage edges.
- `review_edge`: confirm or reject edges.

Analysis:

- `analyze_change_impact`: downstream impact analysis for a field change.

Health:

- `lineage_health_check`: ingestion health, skip counts, parse error rate, and
  proposed backlog.

Browser helpers:

- `list_assets`: list known table/view/materialized-view assets.
- `list_fields`: list fields for one asset.

## Ingestion Example

```json
{
  "start_time": "2026-05-12 00:00:00",
  "end_time": "2026-05-12 23:59:59",
  "limit": 1000,
  "sql_contains": "retail_lineage_regression",
  "schemas": {}
}
```

The collector keeps only successful lineage-producing statements. Incomplete
SQL and parser failures are skipped and recorded as skip reasons; no regex
fallback lineage is produced.

## Review Model

New parsed edges are written as `PROPOSED`.

```text
PROPOSED -> CONFIRMED
PROPOSED -> REJECTED
CONFIRMED -> OUTDATED
```

Default trace and impact APIs use confirmed edges. The Web graph can include
`PROPOSED` edges for review-oriented exploration.

## Retail Regression

The retail fixture creates a single-replica Unique Key Doris model covering:

- Direct stores and franchise stores
- Taobao, JD, Douyin ecommerce channels
- Orders, logistics, products, inventory, category, and region dimensions
- 20 ETL statements covering insert-select, insert-overwrite, CTAS, CTE, joins,
  aggregations, windows, unions, views, and materialized views

Run:

```bash
uv run python examples/retail_regression/run_regression.py
```

See [examples/retail_regression/README.md](examples/retail_regression/README.md)
for details.

## Persistence

Lineage is stored in SQLite using WAL mode. Runtime database files are ignored:

```text
lineage.db
lineage.db-shm
lineage.db-wal
```

Back up the `.db` file when you need to preserve local lineage state.

## Notes

- Doris client setup avoids MySQL session `SET` statements that Doris does not
  support in this environment.
- If SQL omits database or catalog names, the collector relies on audit table
  execution context and configured default catalog for resolution.
- The parser prefers high-confidence AST lineage. Ambiguous or failed SQL is
  skipped rather than producing low-quality edges.

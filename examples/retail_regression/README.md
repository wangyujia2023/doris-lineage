# Retail Lineage Regression

This fixture simulates a retail business with direct stores, franchise stores,
Taobao, JD, Douyin ecommerce, orders, logistics, products, inventory, category,
and region models.

Files:

- `retail_schema_and_seed.sql`: Doris databases, Unique Key single-replica tables,
  and minimal seed data.
- `retail_20_etl.sql`: 20 complex ETL statements covering `INSERT SELECT`,
  `INSERT OVERWRITE`, `CTAS`, `CTE`, joins, aggregation, window functions,
  `UNION ALL`, view, and materialized view definitions.
- `make_audit_events.py`: converts the 20 ETL statements into JSON events for
  `bootstrap_lineage_history`.

Generate MCP backfill events:

```bash
uv run python examples/retail_regression/make_audit_events.py > /tmp/retail_audit_events.json
```

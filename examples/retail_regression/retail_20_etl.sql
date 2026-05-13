-- 20 complex Doris ETL statements for lineage regression.

-- 01 CTAS: raw paid order slice
CREATE TABLE internal.retail_dw.tmp_paid_order_raw
UNIQUE KEY(order_id, order_item_id)
DISTRIBUTED BY HASH(order_id) BUCKETS 1
PROPERTIES ("replication_num" = "1")
AS
SELECT
    order_id,
    order_item_id,
    order_time,
    channel_type,
    channel_name,
    store_id,
    platform_shop_id,
    customer_id,
    product_id,
    sku_id,
    quantity,
    sale_price,
    discount_amount,
    pay_amount,
    province,
    city,
    updated_at
FROM internal.retail_ods.stg_channel_order
WHERE pay_status = 'PAID';

-- 02 INSERT SELECT: channel dimension from source order channels
INSERT INTO internal.retail_dw.dim_channel(channel_id, channel_type, channel_name, is_online, updated_at)
SELECT
    CONCAT(channel_type, ':', channel_name) AS channel_id,
    channel_type,
    channel_name,
    CASE WHEN channel_type = 'ECOM' THEN 1 ELSE 0 END AS is_online,
    MAX(updated_at) AS updated_at
FROM internal.retail_ods.stg_channel_order
WHERE pay_status = 'PAID'
GROUP BY channel_type, channel_name;

-- 03 INSERT SELECT with join: store dimension enriched by region
INSERT INTO internal.retail_dw.dim_store(store_id, store_name, store_type, region_id, province, city, city_tier, open_date, updated_at)
SELECT
    s.store_id,
    s.store_name,
    s.store_type,
    s.region_id,
    s.province,
    s.city,
    r.city_tier,
    s.open_date,
    GREATEST(s.updated_at, r.updated_at) AS updated_at
FROM internal.retail_ods.stg_store s
JOIN internal.retail_ods.stg_region r ON s.region_id = r.region_id;

-- 04 INSERT SELECT with category lookup: product dimension
INSERT INTO internal.retail_dw.dim_product(product_id, sku_id, product_name, brand_name, category_id, category_name, list_price, cost_price, updated_at)
SELECT
    p.product_id,
    p.sku_id,
    p.product_name,
    p.brand_name,
    p.category_id,
    c.category_name,
    p.list_price,
    p.cost_price,
    GREATEST(p.updated_at, c.updated_at) AS updated_at
FROM internal.retail_ods.stg_product p
JOIN internal.retail_ods.stg_category c ON p.category_id = c.category_id;

-- 05 INSERT SELECT: DWD order detail with expression lineage
INSERT INTO internal.retail_dw.dwd_order_detail(
    order_id, order_item_id, order_date, order_time, channel_id, channel_type, channel_name,
    store_id, customer_id, product_id, sku_id, category_id, category_name, quantity,
    gross_amount, discount_amount, net_amount, cost_amount, profit_amount, province, city, updated_at
)
SELECT
    o.order_id,
    o.order_item_id,
    CAST(o.order_time AS DATE) AS order_date,
    o.order_time,
    CONCAT(o.channel_type, ':', o.channel_name) AS channel_id,
    o.channel_type,
    o.channel_name,
    o.store_id,
    o.customer_id,
    o.product_id,
    o.sku_id,
    p.category_id,
    p.category_name,
    o.quantity,
    o.quantity * o.sale_price AS gross_amount,
    o.discount_amount,
    o.pay_amount AS net_amount,
    o.quantity * p.cost_price AS cost_amount,
    o.pay_amount - o.quantity * p.cost_price AS profit_amount,
    o.province,
    o.city,
    GREATEST(o.updated_at, p.updated_at) AS updated_at
FROM internal.retail_dw.tmp_paid_order_raw o
JOIN internal.retail_dw.dim_product p ON o.product_id = p.product_id AND o.sku_id = p.sku_id;

-- 06 INSERT OVERWRITE: refresh DWD order detail from canonical sources
INSERT OVERWRITE TABLE internal.retail_dw.dwd_order_detail
SELECT
    o.order_id,
    o.order_item_id,
    CAST(o.order_time AS DATE) AS order_date,
    o.order_time,
    CONCAT(o.channel_type, ':', o.channel_name) AS channel_id,
    o.channel_type,
    o.channel_name,
    o.store_id,
    o.customer_id,
    o.product_id,
    o.sku_id,
    p.category_id,
    p.category_name,
    o.quantity,
    o.quantity * o.sale_price AS gross_amount,
    o.discount_amount,
    o.pay_amount AS net_amount,
    o.quantity * p.cost_price AS cost_amount,
    o.pay_amount - o.quantity * p.cost_price AS profit_amount,
    o.province,
    o.city,
    GREATEST(o.updated_at, p.updated_at) AS updated_at
FROM internal.retail_ods.stg_channel_order o
JOIN internal.retail_dw.dim_product p ON o.product_id = p.product_id AND o.sku_id = p.sku_id
WHERE o.pay_status = 'PAID';

-- 07 CTE + INSERT SELECT: store daily sales
WITH paid_store_orders AS (
    SELECT *
    FROM internal.retail_dw.dwd_order_detail
    WHERE channel_type = 'STORE'
),
store_rollup AS (
    SELECT
        order_date AS biz_date,
        store_id,
        COUNT(DISTINCT order_id) AS order_count,
        COUNT(*) AS item_count,
        SUM(quantity) AS sale_qty,
        SUM(net_amount) AS net_amount,
        SUM(profit_amount) AS profit_amount,
        MAX(updated_at) AS updated_at
    FROM paid_store_orders
    GROUP BY order_date, store_id
)
INSERT INTO internal.retail_dw.dws_store_day_sales(
    biz_date, store_id, store_type, province, city, order_count, item_count, sale_qty, net_amount, profit_amount, updated_at
)
SELECT
    r.biz_date,
    r.store_id,
    s.store_type,
    s.province,
    s.city,
    r.order_count,
    r.item_count,
    r.sale_qty,
    r.net_amount,
    r.profit_amount,
    GREATEST(r.updated_at, s.updated_at) AS updated_at
FROM store_rollup r
JOIN internal.retail_dw.dim_store s ON r.store_id = s.store_id;

-- 08 CTE + INSERT SELECT: ecommerce daily sales
WITH ecom_orders AS (
    SELECT
        order_date,
        channel_id,
        channel_name,
        order_id,
        quantity,
        net_amount,
        profit_amount,
        updated_at
    FROM internal.retail_dw.dwd_order_detail
    WHERE channel_type = 'ECOM'
)
INSERT INTO internal.retail_dw.dws_ecommerce_day_sales(
    biz_date, channel_id, channel_name, order_count, sale_qty, net_amount, profit_amount, updated_at
)
SELECT
    order_date AS biz_date,
    channel_id,
    channel_name,
    COUNT(DISTINCT order_id) AS order_count,
    SUM(quantity) AS sale_qty,
    SUM(net_amount) AS net_amount,
    SUM(profit_amount) AS profit_amount,
    MAX(updated_at) AS updated_at
FROM ecom_orders
GROUP BY order_date, channel_id, channel_name;

-- 09 INSERT SELECT aggregation: product daily sales
INSERT INTO internal.retail_dw.dws_product_day_sales(
    biz_date, product_id, sku_id, category_id, category_name, sale_qty, net_amount, profit_amount, updated_at
)
SELECT
    order_date AS biz_date,
    product_id,
    sku_id,
    category_id,
    category_name,
    SUM(quantity) AS sale_qty,
    SUM(net_amount) AS net_amount,
    SUM(profit_amount) AS profit_amount,
    MAX(updated_at) AS updated_at
FROM internal.retail_dw.dwd_order_detail
GROUP BY order_date, product_id, sku_id, category_id, category_name;

-- 10 INSERT SELECT with region join: regional sales
INSERT INTO internal.retail_dw.dws_region_day_sales(
    biz_date, region_id, region_name, province, city, city_tier, order_count, net_amount, profit_amount, updated_at
)
SELECT
    s.biz_date,
    r.region_id,
    r.region_name,
    r.province,
    r.city,
    r.city_tier,
    SUM(s.order_count) AS order_count,
    SUM(s.net_amount) AS net_amount,
    SUM(s.profit_amount) AS profit_amount,
    MAX(GREATEST(s.updated_at, r.updated_at)) AS updated_at
FROM internal.retail_dw.dws_store_day_sales s
JOIN internal.retail_ods.stg_store st ON s.store_id = st.store_id
JOIN internal.retail_ods.stg_region r ON st.region_id = r.region_id
GROUP BY s.biz_date, r.region_id, r.region_name, r.province, r.city, r.city_tier;

-- 11 INSERT SELECT: inventory snapshot with derived status
INSERT INTO internal.retail_dw.dws_inventory_day_snapshot(
    snapshot_date, store_id, product_id, sku_id, available_qty, safety_stock, stock_status, updated_at
)
SELECT
    snapshot_date,
    store_id,
    product_id,
    sku_id,
    onhand_qty - locked_qty + in_transit_qty AS available_qty,
    safety_stock,
    CASE
        WHEN onhand_qty - locked_qty + in_transit_qty < safety_stock THEN 'LOW'
        WHEN onhand_qty - locked_qty + in_transit_qty > safety_stock * 3 THEN 'HIGH'
        ELSE 'NORMAL'
    END AS stock_status,
    updated_at
FROM internal.retail_ods.stg_inventory_snapshot;

-- 12 INSERT SELECT: logistics DWD detail enriched with order channel
INSERT INTO internal.retail_dw.dwd_logistics_detail(
    logistics_id, order_id, order_date, channel_id, carrier, warehouse_id,
    ship_time, signed_time, delivery_hours, logistics_status, freight_amount, updated_at
)
SELECT
    l.logistics_id,
    l.order_id,
    o.order_date,
    o.channel_id,
    l.carrier,
    l.warehouse_id,
    l.ship_time,
    l.signed_time,
    CASE
        WHEN l.ship_time IS NOT NULL AND l.signed_time IS NOT NULL
        THEN TIMESTAMPDIFF(HOUR, l.ship_time, l.signed_time)
        ELSE NULL
    END AS delivery_hours,
    l.logistics_status,
    l.freight_amount,
    GREATEST(l.updated_at, o.updated_at) AS updated_at
FROM internal.retail_ods.stg_logistics_event l
JOIN internal.retail_dw.dwd_order_detail o ON l.order_id = o.order_id;

-- 13 CREATE VIEW: unified order detail semantic view
CREATE VIEW internal.retail_ads.vw_unified_order_detail AS
SELECT
    order_id,
    order_item_id,
    order_date,
    channel_id,
    channel_type,
    channel_name,
    store_id,
    customer_id,
    product_id,
    sku_id,
    category_id,
    category_name,
    quantity,
    net_amount,
    profit_amount,
    province,
    city
FROM internal.retail_dw.dwd_order_detail;

-- 14 CREATE MATERIALIZED VIEW: product-channel daily sales
CREATE MATERIALIZED VIEW internal.retail_ads.mv_product_channel_day_sales
BUILD IMMEDIATE REFRESH COMPLETE ON MANUAL
DISTRIBUTED BY HASH(product_id) BUCKETS 1
PROPERTIES ("replication_num" = "1")
AS
SELECT
    order_date AS biz_date,
    product_id,
    sku_id,
    channel_id,
    channel_name,
    SUM(quantity) AS sale_qty,
    SUM(net_amount) AS net_amount,
    SUM(profit_amount) AS profit_amount
FROM internal.retail_dw.dwd_order_detail
GROUP BY order_date, product_id, sku_id, channel_id, channel_name;

-- 15 INSERT SELECT + window: channel sales ranking
INSERT INTO internal.retail_ads.ads_channel_sales_rank(
    biz_date, channel_id, channel_name, net_amount, profit_amount, sales_rank, updated_at
)
SELECT
    biz_date,
    channel_id,
    channel_name,
    net_amount,
    profit_amount,
    RANK() OVER (PARTITION BY biz_date ORDER BY net_amount DESC) AS sales_rank,
    updated_at
FROM internal.retail_dw.dws_ecommerce_day_sales;

-- 16 CTE + INSERT SELECT: direct/franchise comparison
WITH store_base AS (
    SELECT
        biz_date,
        store_type,
        store_id,
        order_count,
        net_amount,
        updated_at
    FROM internal.retail_dw.dws_store_day_sales
),
store_type_rollup AS (
    SELECT
        biz_date,
        store_type,
        COUNT(DISTINCT store_id) AS store_count,
        SUM(order_count) AS order_count,
        SUM(net_amount) AS net_amount,
        SUM(net_amount) / COUNT(DISTINCT store_id) AS avg_store_amount,
        MAX(updated_at) AS updated_at
    FROM store_base
    GROUP BY biz_date, store_type
)
INSERT INTO internal.retail_ads.ads_store_franchise_compare(
    biz_date, store_type, store_count, order_count, net_amount, avg_store_amount, updated_at
)
SELECT
    biz_date,
    store_type,
    store_count,
    order_count,
    net_amount,
    avg_store_amount,
    updated_at
FROM store_type_rollup;

-- 17 INSERT SELECT: logistics delay monitor
INSERT INTO internal.retail_ads.ads_logistics_delay_monitor(
    biz_date, carrier, delayed_orders, avg_delivery_hours, freight_amount, updated_at
)
SELECT
    order_date AS biz_date,
    carrier,
    SUM(CASE WHEN delivery_hours > 36 OR logistics_status <> 'SIGNED' THEN 1 ELSE 0 END) AS delayed_orders,
    AVG(COALESCE(delivery_hours, 999)) AS avg_delivery_hours,
    SUM(freight_amount) AS freight_amount,
    MAX(updated_at) AS updated_at
FROM internal.retail_dw.dwd_logistics_detail
GROUP BY order_date, carrier;

-- 18 CTE + INSERT SELECT: inventory replenishment suggestion
WITH seven_day_sales AS (
    SELECT
        product_id,
        sku_id,
        SUM(sale_qty) AS seven_day_qty
    FROM internal.retail_dw.dws_product_day_sales
    WHERE biz_date >= DATE_SUB('2026-05-11', INTERVAL 7 DAY)
    GROUP BY product_id, sku_id
),
inventory_need AS (
    SELECT
        i.snapshot_date,
        i.store_id,
        i.product_id,
        i.sku_id,
        i.available_qty,
        COALESCE(s.seven_day_qty, 0) AS seven_day_qty,
        CASE
            WHEN i.available_qty < i.safety_stock THEN i.safety_stock + COALESCE(s.seven_day_qty, 0) - i.available_qty
            ELSE 0
        END AS suggest_qty,
        i.updated_at
    FROM internal.retail_dw.dws_inventory_day_snapshot i
    LEFT JOIN seven_day_sales s ON i.product_id = s.product_id AND i.sku_id = s.sku_id
)
INSERT INTO internal.retail_ads.ads_inventory_replenishment_suggestion(
    snapshot_date, store_id, product_id, sku_id, available_qty, seven_day_qty, suggest_qty, updated_at
)
SELECT
    snapshot_date,
    store_id,
    product_id,
    sku_id,
    available_qty,
    seven_day_qty,
    suggest_qty,
    updated_at
FROM inventory_need
WHERE suggest_qty > 0;

-- 19 INSERT SELECT: category profit dashboard
INSERT INTO internal.retail_ads.ads_category_profit_dashboard(
    biz_date, category_id, category_name, net_amount, profit_amount, profit_rate, updated_at
)
SELECT
    biz_date,
    category_id,
    category_name,
    SUM(net_amount) AS net_amount,
    SUM(profit_amount) AS profit_amount,
    CASE WHEN SUM(net_amount) = 0 THEN 0 ELSE SUM(profit_amount) / SUM(net_amount) END AS profit_rate,
    MAX(updated_at) AS updated_at
FROM internal.retail_dw.dws_product_day_sales
GROUP BY biz_date, category_id, category_name;

-- 20 INSERT OVERWRITE + CTE + UNION ALL: omni-channel regional dashboard
WITH store_region AS (
    SELECT
        biz_date,
        CONCAT(province, '-', city) AS region_key,
        'STORE' AS channel_group,
        SUM(order_count) AS order_count,
        SUM(net_amount) AS net_amount,
        SUM(profit_amount) AS profit_amount,
        MAX(updated_at) AS updated_at
    FROM internal.retail_dw.dws_store_day_sales
    GROUP BY biz_date, province, city
),
ecom_region AS (
    SELECT
        order_date AS biz_date,
        CONCAT(province, '-', city) AS region_key,
        'ECOM' AS channel_group,
        COUNT(DISTINCT order_id) AS order_count,
        SUM(net_amount) AS net_amount,
        SUM(profit_amount) AS profit_amount,
        MAX(updated_at) AS updated_at
    FROM internal.retail_dw.dwd_order_detail
    WHERE channel_type = 'ECOM'
    GROUP BY order_date, province, city
),
omni AS (
    SELECT * FROM store_region
    UNION ALL
    SELECT * FROM ecom_region
)
INSERT OVERWRITE TABLE internal.retail_ads.ads_region_omni_channel_dashboard
SELECT
    biz_date,
    region_key,
    channel_group,
    order_count,
    net_amount,
    profit_amount,
    updated_at
FROM omni;

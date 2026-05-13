-- Doris retail lineage regression fixture.
-- Single-replica Unique Key model, intended for local/dev Doris clusters.

CREATE DATABASE IF NOT EXISTS internal.retail_ods;
CREATE DATABASE IF NOT EXISTS internal.retail_dw;
CREATE DATABASE IF NOT EXISTS internal.retail_ads;

-- Source / staging layer
CREATE TABLE IF NOT EXISTS internal.retail_ods.stg_channel_order (
    order_id        BIGINT NOT NULL,
    order_item_id   BIGINT NOT NULL,
    order_time      DATETIME NOT NULL,
    channel_type    VARCHAR(16) NOT NULL,      -- STORE / ECOM
    channel_name    VARCHAR(32) NOT NULL,      -- DIRECT / FRANCHISE / TAOBAO / JD / DOUYIN
    store_id        BIGINT,
    platform_shop_id VARCHAR(64),
    customer_id     BIGINT NOT NULL,
    product_id      BIGINT NOT NULL,
    sku_id          BIGINT NOT NULL,
    quantity        INT NOT NULL,
    sale_price      DECIMAL(18,2) NOT NULL,
    discount_amount DECIMAL(18,2) NOT NULL,
    pay_amount      DECIMAL(18,2) NOT NULL,
    pay_status      VARCHAR(16) NOT NULL,
    province        VARCHAR(32),
    city            VARCHAR(32),
    updated_at      DATETIME NOT NULL
)
UNIQUE KEY(order_id, order_item_id)
DISTRIBUTED BY HASH(order_id) BUCKETS 1
PROPERTIES ("replication_num" = "1");

CREATE TABLE IF NOT EXISTS internal.retail_ods.stg_logistics_event (
    logistics_id     BIGINT NOT NULL,
    order_id         BIGINT NOT NULL,
    carrier          VARCHAR(32) NOT NULL,
    warehouse_id     BIGINT NOT NULL,
    ship_time        DATETIME,
    signed_time      DATETIME,
    logistics_status VARCHAR(16) NOT NULL,
    freight_amount   DECIMAL(18,2) NOT NULL,
    updated_at       DATETIME NOT NULL
)
UNIQUE KEY(logistics_id)
DISTRIBUTED BY HASH(logistics_id) BUCKETS 1
PROPERTIES ("replication_num" = "1");

CREATE TABLE IF NOT EXISTS internal.retail_ods.stg_inventory_snapshot (
    snapshot_date DATE NOT NULL,
    warehouse_id  BIGINT NOT NULL,
    store_id      BIGINT NOT NULL,
    product_id    BIGINT NOT NULL,
    sku_id        BIGINT NOT NULL,
    onhand_qty    INT NOT NULL,
    locked_qty    INT NOT NULL,
    in_transit_qty INT NOT NULL,
    safety_stock  INT NOT NULL,
    updated_at    DATETIME NOT NULL
)
UNIQUE KEY(snapshot_date, warehouse_id, store_id, product_id, sku_id)
DISTRIBUTED BY HASH(product_id) BUCKETS 1
PROPERTIES ("replication_num" = "1");

CREATE TABLE IF NOT EXISTS internal.retail_ods.stg_product (
    product_id   BIGINT NOT NULL,
    sku_id       BIGINT NOT NULL,
    product_name VARCHAR(128) NOT NULL,
    brand_name   VARCHAR(64) NOT NULL,
    category_id  BIGINT NOT NULL,
    list_price   DECIMAL(18,2) NOT NULL,
    cost_price   DECIMAL(18,2) NOT NULL,
    updated_at   DATETIME NOT NULL
)
UNIQUE KEY(product_id, sku_id)
DISTRIBUTED BY HASH(product_id) BUCKETS 1
PROPERTIES ("replication_num" = "1");

CREATE TABLE IF NOT EXISTS internal.retail_ods.stg_category (
    category_id        BIGINT NOT NULL,
    parent_category_id BIGINT,
    category_level     INT NOT NULL,
    category_name      VARCHAR(64) NOT NULL,
    updated_at         DATETIME NOT NULL
)
UNIQUE KEY(category_id)
DISTRIBUTED BY HASH(category_id) BUCKETS 1
PROPERTIES ("replication_num" = "1");

CREATE TABLE IF NOT EXISTS internal.retail_ods.stg_store (
    store_id      BIGINT NOT NULL,
    store_name    VARCHAR(128) NOT NULL,
    store_type    VARCHAR(16) NOT NULL,        -- DIRECT / FRANCHISE
    region_id     BIGINT NOT NULL,
    province      VARCHAR(32) NOT NULL,
    city          VARCHAR(32) NOT NULL,
    open_date     DATE NOT NULL,
    updated_at    DATETIME NOT NULL
)
UNIQUE KEY(store_id)
DISTRIBUTED BY HASH(store_id) BUCKETS 1
PROPERTIES ("replication_num" = "1");

CREATE TABLE IF NOT EXISTS internal.retail_ods.stg_region (
    region_id    BIGINT NOT NULL,
    region_name  VARCHAR(64) NOT NULL,
    province     VARCHAR(32) NOT NULL,
    city         VARCHAR(32) NOT NULL,
    city_tier    VARCHAR(16) NOT NULL,
    updated_at   DATETIME NOT NULL
)
UNIQUE KEY(region_id)
DISTRIBUTED BY HASH(region_id) BUCKETS 1
PROPERTIES ("replication_num" = "1");

-- DW dimensions
CREATE TABLE IF NOT EXISTS internal.retail_dw.dim_channel (
    channel_id    VARCHAR(64) NOT NULL,
    channel_type  VARCHAR(16) NOT NULL,
    channel_name  VARCHAR(32) NOT NULL,
    is_online     TINYINT NOT NULL,
    updated_at    DATETIME NOT NULL
)
UNIQUE KEY(channel_id)
DISTRIBUTED BY HASH(channel_id) BUCKETS 1
PROPERTIES ("replication_num" = "1");

CREATE TABLE IF NOT EXISTS internal.retail_dw.dim_store (
    store_id     BIGINT NOT NULL,
    store_name   VARCHAR(128) NOT NULL,
    store_type   VARCHAR(16) NOT NULL,
    region_id    BIGINT NOT NULL,
    province     VARCHAR(32) NOT NULL,
    city         VARCHAR(32) NOT NULL,
    city_tier    VARCHAR(16) NOT NULL,
    open_date    DATE NOT NULL,
    updated_at   DATETIME NOT NULL
)
UNIQUE KEY(store_id)
DISTRIBUTED BY HASH(store_id) BUCKETS 1
PROPERTIES ("replication_num" = "1");

CREATE TABLE IF NOT EXISTS internal.retail_dw.dim_product (
    product_id     BIGINT NOT NULL,
    sku_id         BIGINT NOT NULL,
    product_name   VARCHAR(128) NOT NULL,
    brand_name     VARCHAR(64) NOT NULL,
    category_id    BIGINT NOT NULL,
    category_name  VARCHAR(64) NOT NULL,
    list_price     DECIMAL(18,2) NOT NULL,
    cost_price     DECIMAL(18,2) NOT NULL,
    updated_at     DATETIME NOT NULL
)
UNIQUE KEY(product_id, sku_id)
DISTRIBUTED BY HASH(product_id) BUCKETS 1
PROPERTIES ("replication_num" = "1");

-- DW facts and summaries
CREATE TABLE IF NOT EXISTS internal.retail_dw.dwd_order_detail (
    order_id        BIGINT NOT NULL,
    order_item_id   BIGINT NOT NULL,
    order_date      DATE NOT NULL,
    order_time      DATETIME NOT NULL,
    channel_id      VARCHAR(64) NOT NULL,
    channel_type    VARCHAR(16) NOT NULL,
    channel_name    VARCHAR(32) NOT NULL,
    store_id        BIGINT,
    customer_id     BIGINT NOT NULL,
    product_id      BIGINT NOT NULL,
    sku_id          BIGINT NOT NULL,
    category_id     BIGINT NOT NULL,
    category_name   VARCHAR(64) NOT NULL,
    quantity        INT NOT NULL,
    gross_amount    DECIMAL(18,2) NOT NULL,
    discount_amount DECIMAL(18,2) NOT NULL,
    net_amount      DECIMAL(18,2) NOT NULL,
    cost_amount     DECIMAL(18,2) NOT NULL,
    profit_amount   DECIMAL(18,2) NOT NULL,
    province        VARCHAR(32),
    city            VARCHAR(32),
    updated_at      DATETIME NOT NULL
)
UNIQUE KEY(order_id, order_item_id)
DISTRIBUTED BY HASH(order_id) BUCKETS 1
PROPERTIES ("replication_num" = "1");

CREATE TABLE IF NOT EXISTS internal.retail_dw.dwd_logistics_detail (
    logistics_id     BIGINT NOT NULL,
    order_id         BIGINT NOT NULL,
    order_date       DATE NOT NULL,
    channel_id       VARCHAR(64) NOT NULL,
    carrier          VARCHAR(32) NOT NULL,
    warehouse_id     BIGINT NOT NULL,
    ship_time        DATETIME,
    signed_time      DATETIME,
    delivery_hours   DECIMAL(18,2),
    logistics_status VARCHAR(16) NOT NULL,
    freight_amount   DECIMAL(18,2) NOT NULL,
    updated_at       DATETIME NOT NULL
)
UNIQUE KEY(logistics_id)
DISTRIBUTED BY HASH(logistics_id) BUCKETS 1
PROPERTIES ("replication_num" = "1");

CREATE TABLE IF NOT EXISTS internal.retail_dw.dws_store_day_sales (
    biz_date      DATE NOT NULL,
    store_id      BIGINT NOT NULL,
    store_type    VARCHAR(16) NOT NULL,
    province      VARCHAR(32) NOT NULL,
    city          VARCHAR(32) NOT NULL,
    order_count   BIGINT NOT NULL,
    item_count    BIGINT NOT NULL,
    sale_qty      BIGINT NOT NULL,
    net_amount    DECIMAL(18,2) NOT NULL,
    profit_amount DECIMAL(18,2) NOT NULL,
    updated_at    DATETIME NOT NULL
)
UNIQUE KEY(biz_date, store_id)
DISTRIBUTED BY HASH(store_id) BUCKETS 1
PROPERTIES ("replication_num" = "1");

CREATE TABLE IF NOT EXISTS internal.retail_dw.dws_ecommerce_day_sales (
    biz_date      DATE NOT NULL,
    channel_id    VARCHAR(64) NOT NULL,
    channel_name  VARCHAR(32) NOT NULL,
    order_count   BIGINT NOT NULL,
    sale_qty      BIGINT NOT NULL,
    net_amount    DECIMAL(18,2) NOT NULL,
    profit_amount DECIMAL(18,2) NOT NULL,
    updated_at    DATETIME NOT NULL
)
UNIQUE KEY(biz_date, channel_id)
DISTRIBUTED BY HASH(channel_id) BUCKETS 1
PROPERTIES ("replication_num" = "1");

CREATE TABLE IF NOT EXISTS internal.retail_dw.dws_product_day_sales (
    biz_date      DATE NOT NULL,
    product_id    BIGINT NOT NULL,
    sku_id        BIGINT NOT NULL,
    category_id   BIGINT NOT NULL,
    category_name VARCHAR(64) NOT NULL,
    sale_qty      BIGINT NOT NULL,
    net_amount    DECIMAL(18,2) NOT NULL,
    profit_amount DECIMAL(18,2) NOT NULL,
    updated_at    DATETIME NOT NULL
)
UNIQUE KEY(biz_date, product_id, sku_id)
DISTRIBUTED BY HASH(product_id) BUCKETS 1
PROPERTIES ("replication_num" = "1");

CREATE TABLE IF NOT EXISTS internal.retail_dw.dws_region_day_sales (
    biz_date      DATE NOT NULL,
    region_id     BIGINT NOT NULL,
    region_name   VARCHAR(64) NOT NULL,
    province      VARCHAR(32) NOT NULL,
    city          VARCHAR(32) NOT NULL,
    city_tier     VARCHAR(16) NOT NULL,
    order_count   BIGINT NOT NULL,
    net_amount    DECIMAL(18,2) NOT NULL,
    profit_amount DECIMAL(18,2) NOT NULL,
    updated_at    DATETIME NOT NULL
)
UNIQUE KEY(biz_date, region_id)
DISTRIBUTED BY HASH(region_id) BUCKETS 1
PROPERTIES ("replication_num" = "1");

CREATE TABLE IF NOT EXISTS internal.retail_dw.dws_inventory_day_snapshot (
    snapshot_date DATE NOT NULL,
    store_id      BIGINT NOT NULL,
    product_id    BIGINT NOT NULL,
    sku_id        BIGINT NOT NULL,
    available_qty INT NOT NULL,
    safety_stock  INT NOT NULL,
    stock_status  VARCHAR(16) NOT NULL,
    updated_at    DATETIME NOT NULL
)
UNIQUE KEY(snapshot_date, store_id, product_id, sku_id)
DISTRIBUTED BY HASH(product_id) BUCKETS 1
PROPERTIES ("replication_num" = "1");

-- ADS layer
CREATE TABLE IF NOT EXISTS internal.retail_ads.ads_channel_sales_rank (
    biz_date       DATE NOT NULL,
    channel_id     VARCHAR(64) NOT NULL,
    channel_name   VARCHAR(32) NOT NULL,
    net_amount     DECIMAL(18,2) NOT NULL,
    profit_amount  DECIMAL(18,2) NOT NULL,
    sales_rank     BIGINT NOT NULL,
    updated_at     DATETIME NOT NULL
)
UNIQUE KEY(biz_date, channel_id)
DISTRIBUTED BY HASH(channel_id) BUCKETS 1
PROPERTIES ("replication_num" = "1");

CREATE TABLE IF NOT EXISTS internal.retail_ads.ads_store_franchise_compare (
    biz_date          DATE NOT NULL,
    store_type        VARCHAR(16) NOT NULL,
    store_count       BIGINT NOT NULL,
    order_count       BIGINT NOT NULL,
    net_amount        DECIMAL(18,2) NOT NULL,
    avg_store_amount  DECIMAL(18,2) NOT NULL,
    updated_at        DATETIME NOT NULL
)
UNIQUE KEY(biz_date, store_type)
DISTRIBUTED BY HASH(store_type) BUCKETS 1
PROPERTIES ("replication_num" = "1");

CREATE TABLE IF NOT EXISTS internal.retail_ads.ads_logistics_delay_monitor (
    biz_date          DATE NOT NULL,
    carrier           VARCHAR(32) NOT NULL,
    delayed_orders    BIGINT NOT NULL,
    avg_delivery_hours DECIMAL(18,2) NOT NULL,
    freight_amount    DECIMAL(18,2) NOT NULL,
    updated_at        DATETIME NOT NULL
)
UNIQUE KEY(biz_date, carrier)
DISTRIBUTED BY HASH(carrier) BUCKETS 1
PROPERTIES ("replication_num" = "1");

CREATE TABLE IF NOT EXISTS internal.retail_ads.ads_inventory_replenishment_suggestion (
    snapshot_date   DATE NOT NULL,
    store_id        BIGINT NOT NULL,
    product_id      BIGINT NOT NULL,
    sku_id          BIGINT NOT NULL,
    available_qty   INT NOT NULL,
    seven_day_qty   BIGINT NOT NULL,
    suggest_qty     BIGINT NOT NULL,
    updated_at      DATETIME NOT NULL
)
UNIQUE KEY(snapshot_date, store_id, product_id, sku_id)
DISTRIBUTED BY HASH(product_id) BUCKETS 1
PROPERTIES ("replication_num" = "1");

CREATE TABLE IF NOT EXISTS internal.retail_ads.ads_category_profit_dashboard (
    biz_date        DATE NOT NULL,
    category_id     BIGINT NOT NULL,
    category_name   VARCHAR(64) NOT NULL,
    net_amount      DECIMAL(18,2) NOT NULL,
    profit_amount   DECIMAL(18,2) NOT NULL,
    profit_rate     DECIMAL(18,4) NOT NULL,
    updated_at      DATETIME NOT NULL
)
UNIQUE KEY(biz_date, category_id)
DISTRIBUTED BY HASH(category_id) BUCKETS 1
PROPERTIES ("replication_num" = "1");

CREATE TABLE IF NOT EXISTS internal.retail_ads.ads_region_omni_channel_dashboard (
    biz_date       DATE NOT NULL,
    region_key     VARCHAR(128) NOT NULL,
    channel_group  VARCHAR(16) NOT NULL,
    order_count    BIGINT NOT NULL,
    net_amount     DECIMAL(18,2) NOT NULL,
    profit_amount  DECIMAL(18,2) NOT NULL,
    updated_at     DATETIME NOT NULL
)
UNIQUE KEY(biz_date, region_key, channel_group)
DISTRIBUTED BY HASH(region_key) BUCKETS 1
PROPERTIES ("replication_num" = "1");

-- Minimal seed data
INSERT INTO internal.retail_ods.stg_category VALUES
(10, NULL, 1, '食品饮料', '2026-05-01 00:00:00'),
(11, 10, 2, '咖啡茶饮', '2026-05-01 00:00:00'),
(20, NULL, 1, '个护清洁', '2026-05-01 00:00:00');

INSERT INTO internal.retail_ods.stg_product VALUES
(1001, 100101, '冷萃咖啡', 'NorthCafe', 11, 19.90, 8.50, '2026-05-01 00:00:00'),
(1002, 100201, '挂耳咖啡', 'NorthCafe', 11, 49.90, 21.00, '2026-05-01 00:00:00'),
(2001, 200101, '洗手液', 'CleanPro', 20, 29.90, 10.00, '2026-05-01 00:00:00');

INSERT INTO internal.retail_ods.stg_region VALUES
(1, '华东一区', '上海', '上海', 'T1', '2026-05-01 00:00:00'),
(2, '华北一区', '北京', '北京', 'T1', '2026-05-01 00:00:00'),
(3, '华南一区', '广东', '广州', 'T1', '2026-05-01 00:00:00');

INSERT INTO internal.retail_ods.stg_store VALUES
(101, '上海南京东路直营店', 'DIRECT', 1, '上海', '上海', '2024-01-01', '2026-05-01 00:00:00'),
(102, '北京朝阳加盟店', 'FRANCHISE', 2, '北京', '北京', '2024-03-01', '2026-05-01 00:00:00'),
(103, '广州天河直营店', 'DIRECT', 3, '广东', '广州', '2024-05-01', '2026-05-01 00:00:00');

INSERT INTO internal.retail_ods.stg_channel_order VALUES
(900001, 1, '2026-05-11 10:00:00', 'STORE', 'DIRECT', 101, NULL, 5001, 1001, 100101, 2, 19.90, 0.00, 39.80, 'PAID', '上海', '上海', '2026-05-11 10:05:00'),
(900002, 1, '2026-05-11 11:00:00', 'STORE', 'FRANCHISE', 102, NULL, 5002, 2001, 200101, 1, 29.90, 5.00, 24.90, 'PAID', '北京', '北京', '2026-05-11 11:05:00'),
(900003, 1, '2026-05-11 12:00:00', 'ECOM', 'TAOBAO', NULL, 'tb_north_01', 5003, 1002, 100201, 1, 49.90, 10.00, 39.90, 'PAID', '广东', '广州', '2026-05-11 12:05:00'),
(900004, 1, '2026-05-11 13:00:00', 'ECOM', 'JD', NULL, 'jd_north_01', 5004, 1001, 100101, 3, 19.90, 3.00, 56.70, 'PAID', '上海', '上海', '2026-05-11 13:05:00'),
(900005, 1, '2026-05-11 14:00:00', 'ECOM', 'DOUYIN', NULL, 'dy_north_01', 5005, 2001, 200101, 2, 29.90, 0.00, 59.80, 'PAID', '北京', '北京', '2026-05-11 14:05:00');

INSERT INTO internal.retail_ods.stg_logistics_event VALUES
(700001, 900001, 'SF', 301, '2026-05-11 16:00:00', '2026-05-12 09:00:00', 'SIGNED', 8.00, '2026-05-12 09:05:00'),
(700002, 900003, 'YTO', 302, '2026-05-11 18:00:00', '2026-05-13 18:00:00', 'SIGNED', 6.00, '2026-05-13 18:05:00'),
(700003, 900004, 'JD', 303, '2026-05-11 18:30:00', NULL, 'SHIPPING', 5.00, '2026-05-12 10:00:00');

INSERT INTO internal.retail_ods.stg_inventory_snapshot VALUES
('2026-05-11', 301, 101, 1001, 100101, 80, 5, 10, 30, '2026-05-11 23:00:00'),
('2026-05-11', 302, 102, 2001, 200101, 15, 2, 5, 20, '2026-05-11 23:00:00'),
('2026-05-11', 303, 103, 1002, 100201, 10, 1, 3, 15, '2026-05-11 23:00:00');

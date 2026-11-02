CREATE OR REPLACE MATERIALIZED VIEW gold.mv_daily_sales
SCHEDULE EVERY 5 MINUTES
AS
SELECT order_date, store_id, sum(amount) AS revenue, rand() AS sample_key
FROM silver.orders
GROUP BY order_date, store_id;

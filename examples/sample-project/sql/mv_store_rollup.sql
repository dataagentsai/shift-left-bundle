CREATE OR REPLACE MATERIALIZED VIEW gold.mv_store_rollup AS
SELECT store_id, sum(revenue) AS revenue FROM gold.mv_daily_sales GROUP BY store_id;

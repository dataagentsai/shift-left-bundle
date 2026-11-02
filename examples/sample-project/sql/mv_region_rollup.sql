CREATE OR REPLACE MATERIALIZED VIEW gold.mv_region_rollup AS
SELECT s.region, sum(r.revenue) AS revenue
FROM gold.mv_store_rollup r JOIN silver.stores s ON r.store_id = s.store_id
GROUP BY s.region;

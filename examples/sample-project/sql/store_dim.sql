-- Small, explicit dimension: three columns, used by the stores page
WITH s AS (
    SELECT store_id, store_name, region FROM silver.stores WHERE is_active
)
SELECT * FROM s;

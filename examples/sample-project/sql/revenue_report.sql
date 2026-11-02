-- Revenue by store and month for the finance pack
SELECT *
FROM silver.orders o
JOIN silver.stores s ON o.store_id = s.store_id
WHERE year(o.order_date) = 2026
  AND o.customer_id NOT IN (SELECT customer_id FROM silver.test_customers)
UNION
SELECT *
FROM silver.orders_archive a
JOIN silver.stores s ON a.store_id = s.store_id
WHERE year(a.order_date) = 2025
ORDER BY 1;

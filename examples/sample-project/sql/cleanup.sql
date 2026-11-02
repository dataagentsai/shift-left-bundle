-- Remove test orders before the month-end close
DELETE FROM silver.orders;

-- Keep only 400 days of raw events
DELETE FROM bronze.events WHERE event_date < date_sub(current_date(), 400);

GRANT ALL PRIVILEGES ON SCHEMA gold TO `account users`;

CREATE OR REPLACE VIEW gold.finance_metrics
WITH METRICS
LANGUAGE YAML
AS $$
version: 1.1
source: silver.orders
dimensions:
  - name: Order Month
    expr: date_trunc('MONTH', order_date)
    comment: Calendar month of the order
measures:
  - name: Revenue
    expr: SUM(amount) FILTER (WHERE status <> 'cancelled')
    comment: Net order value in INR, cancelled orders excluded
  - name: Margin
    expr: SUM(profit) / SUM(amount)
    comment: Profit over revenue, computed on totals
$$;

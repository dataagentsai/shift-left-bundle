CREATE OR REPLACE VIEW gold.sales_metrics
WITH METRICS
LANGUAGE YAML
AS $$
version: 1.1
source: silver.orders
joins:
  - name: lines
    source: silver.order_lines
    on: source.order_id = lines.order_id
dimensions:
  - name: Order Month
    expr: date_trunc('MONTH', order_date)
  - name: Store
    expr: store_id
measures:
  - name: Revenue
    expr: SUM(amount)
    comment: Gross order value in INR, including cancelled orders
  - name: Margin
    expr: AVG(profit / amount)
  - name: Shipping Revenue
    expr: SUM(shipping_fee)
  - name: Order Status
    expr: status
$$;

select
    order_id,
    customer_id,
    store_id,
    cast(amount as decimal(12, 2)) as amount,
    order_date
from {{ source('bronze', 'orders') }}

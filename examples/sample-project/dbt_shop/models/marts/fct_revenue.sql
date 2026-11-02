select
    o.order_date,
    c.city,
    sum(o.amount) as revenue,
    case
        when dayofweek(o.order_date) in (1, 7) then 'weekend'
        else 'weekday'
    end as day_type
from {{ source('bronze', 'orders') }} o
join {{ ref('stg_customers') }} c on o.customer_id = c.customer_id
group by 1, 2, 4

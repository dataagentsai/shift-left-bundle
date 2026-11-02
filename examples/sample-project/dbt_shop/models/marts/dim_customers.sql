select customer_id, name, city
from {{ ref('stg_customers') }}

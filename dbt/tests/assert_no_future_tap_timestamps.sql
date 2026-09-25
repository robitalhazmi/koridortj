-- Custom test: Ensures no tap timestamps are in the future relative to current execution time.
-- Returns failing records (if any).
select
    tap_id,
    trans_id,
    tap_timestamp
from {{ ref('fact_taps') }}
where tap_timestamp > now()

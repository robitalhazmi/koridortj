-- Custom test: Ensures every stop_id in fact_taps exists in dim_stops.
-- Returns failing records (if any).
select
    f.tap_id,
    f.stop_id
from {{ ref('fact_taps') }} f
left join {{ ref('dim_stops') }} s on f.stop_id = s.stop_id
where s.stop_id is null

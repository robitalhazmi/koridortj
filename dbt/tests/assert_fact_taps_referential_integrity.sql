-- Custom test: Ensures every stop_id in fact_taps exists in dim_stops and every route_id exists in dim_routes.
-- Returns failing records (if any).
select
    f.tap_id,
    f.stop_id,
    f.route_id
from {{ ref('fact_taps') }} f
left join {{ ref('dim_stops') }} s on f.stop_id = s.stop_id
left join {{ ref('dim_routes') }} r on f.route_id = r.route_id
where s.stop_id is null or r.route_id is null

with corridors_from_taps as (
    select
        corridor_code,
        coalesce(nullif(max(corridor_name), ''), corridor_code) as corridor_name,
        min(direction) as direction
    from {{ ref('stg_taps') }}
    where corridor_code is not null and corridor_code != ''
    group by corridor_code
),

corridors_from_routes as (
    select
        route_id as corridor_code,
        coalesce(nullif(max(route_long_name), ''), max(route_short_name), route_id) as corridor_name,
        0 as direction
    from {{ ref('stg_routes') }}
    where route_id not in (select corridor_code from corridors_from_taps)
    group by route_id
),

unknown_corridor as (
    select
        'UNKNOWN' as corridor_code,
        'Unknown Corridor' as corridor_name,
        0 as direction
    where not exists (
        select 1 from corridors_from_taps where corridor_code = 'UNKNOWN'
    )
    and not exists (
        select 1 from corridors_from_routes where corridor_code = 'UNKNOWN'
    )
),

unioned as (
    select * from corridors_from_taps
    union all
    select * from corridors_from_routes
    union all
    select * from unknown_corridor
)

select
    corridor_code,
    corridor_name,
    direction
from unioned

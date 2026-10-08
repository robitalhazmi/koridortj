with gtfs_routes as (
    select
        route_id,
        route_short_name,
        route_long_name,
        coalesce(nullif(route_long_name, ''), route_short_name, route_id) as route_name,
        route_desc,
        route_type,
        route_color,
        route_text_color,
        route_id as corridor_code,
        _ingested_at
    from {{ ref('stg_routes') }}
),

all_taps as (
    select route_id, corridor_name, corridor_code, _ingested_at from {{ ref('stg_taps') }}
    union all
    select route_id, corridor_name, corridor_code, _ingested_at from {{ ref('stg_streaming_taps') }}
),

tap_routes as (
    select
        route_id,
        route_id as route_short_name,
        max(corridor_name) as route_long_name,
        coalesce(nullif(max(corridor_name), ''), route_id) as route_name,
        'Simulated Corridor' as route_desc,
        3 as route_type,
        '#003399' as route_color,
        '#FFFFFF' as route_text_color,
        max(corridor_code) as corridor_code,
        min(_ingested_at) as _ingested_at
    from all_taps
    where route_id not in (select gtfs_routes.route_id from gtfs_routes)
    group by route_id
),

unknown_route as (
    select
        'UNKNOWN' as route_id,
        'UNKNOWN' as route_short_name,
        'Unknown Route' as route_long_name,
        'Unknown Route' as route_name,
        'Unassigned / Missing in source data' as route_desc,
        3 as route_type,
        '#999999' as route_color,
        '#FFFFFF' as route_text_color,
        'UNKNOWN' as corridor_code,
        now() as _ingested_at
    where
        not exists (
            select 1
            from gtfs_routes
            where gtfs_routes.route_id = 'UNKNOWN'
        )
        and not exists (
            select 1
            from tap_routes
            where tap_routes.route_id = 'UNKNOWN'
        )
),

unioned as (
    select * from gtfs_routes
    union all
    select * from tap_routes
    union all
    select * from unknown_route
)

select * from unioned

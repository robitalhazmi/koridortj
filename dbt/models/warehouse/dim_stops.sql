with gtfs_stops as (
    select
        stop_id,
        stop_code,
        stop_name,
        stop_desc,
        latitude,
        longitude,
        location_type,
        wheelchair_boarding,
        _ingested_at
    from {{ ref('stg_stops') }}
),

tap_stops as (
    select
        stop_id,
        stop_id as stop_code,
        stop_name,
        'Simulated Stop' as stop_desc,
        avg(latitude) as latitude,
        avg(longitude) as longitude,
        0 as location_type,
        0 as wheelchair_boarding,
        min(_ingested_at) as _ingested_at
    from {{ ref('stg_taps') }}
    where stop_id not in (select stop_id from gtfs_stops)
    group by stop_id, stop_name
),

unioned as (
    select * from gtfs_stops
    union all
    select * from tap_stops
)

select * from unioned

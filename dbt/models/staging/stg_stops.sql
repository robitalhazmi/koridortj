with source as (
    select * from {{ source('raw', 'gtfs_stops') }}
),

cleaned as (
    select
        trim(stop_id) as stop_id,
        trim(stop_code) as stop_code,
        trim(stop_name) as stop_name,
        trim(stop_desc) as stop_desc,
        stop_lat as latitude,
        stop_lon as longitude,
        trim(zone_id) as zone_id,
        coalesce(location_type, 0) as location_type,
        trim(parent_station) as parent_station,
        coalesce(wheelchair_boarding, 0) as wheelchair_boarding,
        trim(platform_code) as platform_code,
        _ingested_at,
        _source_url
    from source
)

select * from cleaned

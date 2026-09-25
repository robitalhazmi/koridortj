with source as (
    select * from {{ source('raw', 'gtfs_trips') }}
),

cleaned as (
    select
        trim(trip_id) as trip_id,
        trim(route_id) as route_id,
        trim(service_id) as service_id,
        trim(trip_headsign) as trip_headsign,
        trim(trip_short_name) as trip_short_name,
        coalesce(direction_id, 0) as direction_id,
        trim(block_id) as block_id,
        trim(shape_id) as shape_id,
        coalesce(wheelchair_accessible, 0) as wheelchair_accessible,
        coalesce(bikes_allowed, 0) as bikes_allowed,
        ticketing_trip_id,
        _ingested_at,
        _source_url
    from source
)

select * from cleaned

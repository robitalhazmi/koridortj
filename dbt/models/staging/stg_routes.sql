with source as (
    select * from {{ source('raw', 'gtfs_routes') }}
),

cleaned as (
    select
        trim(route_id) as route_id,
        trim(agency_id) as agency_id,
        trim(route_short_name) as route_short_name,
        trim(route_long_name) as route_long_name,
        trim(route_desc) as route_desc,
        coalesce(route_type, 3) as route_type,
        route_url,
        upper(trim(route_color)) as route_color,
        upper(trim(route_text_color)) as route_text_color,
        route_sort_order,
        ticketing_deep_link_id,
        _ingested_at,
        _source_url
    from source
)

select * from cleaned

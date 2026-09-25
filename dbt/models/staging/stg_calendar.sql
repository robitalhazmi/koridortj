with source as (
    select * from {{ source('raw', 'gtfs_calendar') }}
),

cleaned as (
    select
        trim(service_id) as service_id,
        monday,
        tuesday,
        wednesday,
        thursday,
        friday,
        saturday,
        sunday,
        to_date(start_date, 'YYYYMMDD') as start_date,
        to_date(end_date, 'YYYYMMDD') as end_date,
        _ingested_at,
        _source_url
    from source
)

select * from cleaned

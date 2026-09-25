with date_series as (
    select generate_series('2023-01-01'::date, '2027-12-31'::date, '1 day'::interval)::date as full_date
),

transformed as (
    select
        to_char(full_date, 'YYYYMMDD')::int as date_id,
        full_date,
        extract(isodow from full_date)::int as day_of_week,
        trim(to_char(full_date, 'Day')) as day_name,
        trim(to_char(full_date, 'Month')) as month_name,
        extract(year from full_date)::int as year,
        extract(quarter from full_date)::int as quarter,
        extract(month from full_date)::int as month,
        extract(day from full_date)::int as day_of_month,
        case when extract(isodow from full_date) in (6, 7) then true else false end as is_weekend,
        case when (extract(month from full_date) = 1 and extract(day from full_date) = 1)
                  or (extract(month from full_date) = 8 and extract(day from full_date) = 17)
                  or (extract(month from full_date) = 12 and extract(day from full_date) = 25)
             then true else false end as is_holiday
    from date_series
)

select * from transformed

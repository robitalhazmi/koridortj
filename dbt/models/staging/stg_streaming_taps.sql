with source as (
    select * from {{ source('raw', 'taps_stream') }}
),

tap_ins as (
    select
        trans_id || '_IN' as tap_id,
        trim(trans_id) as trans_id,
        trim(pay_card_id) as pay_card_id,
        trim(pay_card_bank) as pay_card_bank,
        trim(pay_card_name) as pay_card_name,
        upper(trim(pay_card_sex)) as pay_card_sex,
        pay_card_birth_date,
        coalesce(trim(corridor_id), 'UNKNOWN') as route_id,
        coalesce(trim(corridor_id), 'UNKNOWN') as corridor_code,
        coalesce(trim(corridor_name), 'Unknown Corridor') as corridor_name,
        coalesce(direction, 0) as direction,
        trim(tap_in_stops) as stop_id,
        trim(tap_in_stops_name) as stop_name,
        tap_in_stops_lat as latitude,
        tap_in_stops_lon as longitude,
        stop_start_seq as stop_sequence,
        'IN' as tap_type,
        tap_in_time as tap_timestamp,
        coalesce(pay_amount, 3500.00) as pay_amount,
        is_simulated,
        _ingested_at,
        _source_topic as _source_file
    from source
    where tap_in_time is not null and tap_in_stops is not null
),

tap_outs as (
    select
        trans_id || '_OUT' as tap_id,
        trim(trans_id) as trans_id,
        trim(pay_card_id) as pay_card_id,
        trim(pay_card_bank) as pay_card_bank,
        trim(pay_card_name) as pay_card_name,
        upper(trim(pay_card_sex)) as pay_card_sex,
        pay_card_birth_date,
        coalesce(trim(corridor_id), 'UNKNOWN') as route_id,
        coalesce(trim(corridor_id), 'UNKNOWN') as corridor_code,
        coalesce(trim(corridor_name), 'Unknown Corridor') as corridor_name,
        coalesce(direction, 0) as direction,
        trim(tap_out_stops) as stop_id,
        trim(tap_out_stops_name) as stop_name,
        tap_out_stops_lat as latitude,
        tap_out_stops_lon as longitude,
        stop_end_seq as stop_sequence,
        'OUT' as tap_type,
        tap_out_time as tap_timestamp,
        0.00 as pay_amount,
        is_simulated,
        _ingested_at,
        _source_topic as _source_file
    from source
    where tap_out_time is not null and tap_out_stops is not null
),

unioned as (
    select * from tap_ins
    union all
    select * from tap_outs
)

select * from unioned

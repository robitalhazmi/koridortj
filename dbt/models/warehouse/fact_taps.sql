with batch_taps as (
    select
        tap_id,
        trans_id,
        pay_card_id,
        pay_card_bank,
        pay_card_name,
        pay_card_sex,
        pay_card_birth_date,
        route_id,
        stop_id,
        to_char(tap_timestamp, 'YYYYMMDD')::int as date_id,
        corridor_code,
        direction,
        tap_type,
        tap_timestamp,
        stop_sequence,
        pay_amount,
        is_simulated,
        _ingested_at
    from {{ ref('stg_taps') }}
),

streaming_taps as (
    select
        tap_id,
        trans_id,
        pay_card_id,
        pay_card_bank,
        pay_card_name,
        pay_card_sex,
        pay_card_birth_date,
        route_id,
        stop_id,
        to_char(tap_timestamp, 'YYYYMMDD')::int as date_id,
        corridor_code,
        direction,
        tap_type,
        tap_timestamp,
        stop_sequence,
        pay_amount,
        is_simulated,
        _ingested_at
    from {{ ref('stg_streaming_taps') }}
),

unioned as (
    select * from batch_taps
    union all
    select * from streaming_taps
),

deduped as (
    select distinct on (tap_id)
        tap_id,
        trans_id,
        pay_card_id,
        pay_card_bank,
        pay_card_name,
        pay_card_sex,
        pay_card_birth_date,
        route_id,
        stop_id,
        date_id,
        corridor_code,
        direction,
        tap_type,
        tap_timestamp,
        stop_sequence,
        pay_amount,
        is_simulated,
        _ingested_at
    from unioned
    order by tap_id, _ingested_at desc
)

select * from deduped


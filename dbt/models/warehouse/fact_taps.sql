with taps as (
    select * from {{ ref('stg_taps') }}
),

enriched as (
    select
        t.tap_id,
        t.trans_id,
        t.pay_card_id,
        t.pay_card_bank,
        t.pay_card_name,
        t.pay_card_sex,
        t.pay_card_birth_date,
        t.route_id,
        t.stop_id,
        to_char(t.tap_timestamp, 'YYYYMMDD')::int as date_id,
        t.corridor_code,
        t.direction,
        t.tap_type,
        t.tap_timestamp,
        t.stop_sequence,
        t.pay_amount,
        t.is_simulated,
        t._ingested_at
    from taps t
)

select * from enriched

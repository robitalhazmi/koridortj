-- Custom test: Ensures no transactions exist where tap-out timestamp is earlier than tap-in timestamp.
-- Evaluates both historical batch taps and real-time streaming taps.
-- Returns failing records (if any).
with historical as (
    select
        trans_id,
        tap_in_time,
        tap_out_time,
        'batch' as source_type
    from {{ source('raw', 'taps') }}
    where tap_out_time is not null and tap_in_time is not null
),

streaming as (
    select
        trans_id,
        tap_in_time,
        tap_out_time,
        'stream' as source_type
    from {{ source('raw', 'taps_stream') }}
    where tap_out_time is not null and tap_in_time is not null
),

combined as (
    select * from historical
    union all
    select * from streaming
)

select
    trans_id,
    source_type,
    tap_in_time,
    tap_out_time
from combined
where tap_out_time < tap_in_time

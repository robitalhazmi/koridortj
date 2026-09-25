-- Custom test: Ensures no transactions exist where tap-out timestamp is earlier than tap-in timestamp.
-- Returns failing records (if any).
select
    trans_id,
    tap_in_time,
    tap_out_time
from {{ source('raw', 'taps') }}
where tap_out_time is not null
  and tap_in_time is not null
  and tap_out_time < tap_in_time

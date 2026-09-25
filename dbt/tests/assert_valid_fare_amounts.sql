-- Custom test: Ensures all transactions in fact_taps adhere to valid Indonesian transit fare pricing rules.
-- Tap-in fares must be non-negative and <= Rp 50,000; Tap-out fares must be Rp 0.00.
-- Returns failing records (if any).
select
    tap_id,
    trans_id,
    tap_type,
    pay_amount
from {{ ref('fact_taps') }}
where pay_amount < 0.00
   or pay_amount > 50000.00
   or (tap_type = 'OUT' and pay_amount != 0.00)

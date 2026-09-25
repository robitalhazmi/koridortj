-- Custom test: Validates that all stop geographic coordinates in dim_stops fall within the greater Jakarta metropolitan region.
-- Bounding box: Latitude [-7.0, -5.5], Longitude [106.3, 107.5].
-- Returns failing records (if any).
select
    stop_id,
    stop_name,
    latitude,
    longitude
from {{ ref('dim_stops') }}
where latitude < -7.0
   or latitude > -5.5
   or longitude < 106.3
   or longitude > 107.5

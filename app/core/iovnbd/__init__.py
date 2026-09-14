"""IO-VNBD toolkit for the ISRO Intelligent Dead Reckoning challenge.

Sub-modules
-----------
paths        : dataset location + trip discovery
schema       : raw -> canonical column mapping for S (phone) and V (vehicle) files
loader       : robust CSV readers returning canonical numpy/pandas structures
geo          : lat/lon <-> local ENU helpers, haversine
eda          : per-trip summary statistics and quality checks
blackout     : synthetic GNSS-outage window generation
deadreckon   : baseline INS mechanisation + non-holonomic constraint
metrics      : drift metrics scored against the ISRO <10 % benchmark
harness      : end-to-end evaluation loop over many trips / scenarios
"""

from .paths import DATASET_ROOT, find_synced_trips, find_phone_only_trips
from .loader import load_trip, load_phone_csv, load_vehicle_csv
from .blackout import BlackoutSpec, make_blackouts
from .deadreckon import dead_reckon
from .metrics import drift_metrics

__all__ = [
    "DATASET_ROOT",
    "find_synced_trips",
    "find_phone_only_trips",
    "load_trip",
    "load_phone_csv",
    "load_vehicle_csv",
    "BlackoutSpec",
    "make_blackouts",
    "dead_reckon",
    "drift_metrics",
]

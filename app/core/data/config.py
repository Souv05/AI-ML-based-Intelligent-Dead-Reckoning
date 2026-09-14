"""Single source of truth for every tunable in the preparation pipeline.

Everything here is data-prep only. Nothing about model architecture or training.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]          # D:\SIH 2026

# Raw dataset location. The real CSVs live under dataset/IO-VNBD (git-lfs pulled).
# data/raw/ is a documented pointer only - we never copy or edit the raw tree.
RAW_DATASET_ROOT = Path(
    os.environ.get("IOVNBD_ROOT", PROJECT_ROOT / "dataset" / "IO-VNBD")
)

ARTIFACTS = PROJECT_ROOT / "artifacts"
PLOTS = ARTIFACTS / "plots"
DATA = PROJECT_ROOT / "data"
INTERIM = DATA / "interim"
PROCESSED = DATA / "processed"


# --------------------------------------------------------------------------- #
# canonical schema
# --------------------------------------------------------------------------- #
# Model INPUT features available during a GNSS outage (phone-only, no GNSS,
# no vehicle/reference data). Order is fixed and is the channel order in the
# generated windows.
INPUT_FEATURES: tuple[str, ...] = (
    "acc_x", "acc_y", "acc_z",
    "gyro_x", "gyro_y", "gyro_z",
    "mag_x", "mag_y", "mag_z",
    "roll", "pitch", "yaw",
)

# Canonical fields carried through the pipeline but NOT model inputs.
GNSS_FIELDS: tuple[str, ...] = (
    "latitude", "longitude", "gnss_speed", "gnss_heading", "altitude",
)
REFERENCE_FIELDS: tuple[str, ...] = (
    "reference_latitude", "reference_longitude",
    "reference_speed", "reference_heading",
    "reference_x", "reference_y",
)
BOOKKEEPING_FIELDS: tuple[str, ...] = (
    "timestamp", "sequence_id", "gnss_available", "native_gnss_valid",
)


@dataclass(frozen=True)
class PrepConfig:
    # ----- IO -----
    raw_root: Path = RAW_DATASET_ROOT
    artifacts: Path = ARTIFACTS
    plots: Path = PLOTS
    interim: Path = INTERIM
    processed: Path = PROCESSED

    # ----- master timeline -----
    master_clock: str = "imu"          # keep the IMU rate as the master timeline
    expected_hz: float = 10.0          # VERIFIED per file, never hard-applied
    max_gap_s: float = 0.6             # timestep above this = a logging gap

    # ----- reference trajectory -----
    reference_source: str = "vehicle_gnss_ins"   # V-file Latitude/Longitude/Velocity
    reference_speed_channel: str = "vel_kmh"

    # ----- GNSS blackout simulation (affects INPUTS only) -----
    blackout_warmup_s: float = 30.0
    blackout_duration_s: float = 30.0
    blackout_period_s: float = 120.0   # spacing for the recurring variant
    blackout_min_speed_ms: float = 3.0

    # ----- temporal windows -----
    window_seconds: float = 2.0
    window_stride_steps: int = 1
    target: str = "forward_speed"      # forward_speed | velocity_vector | displacement
    target_horizon_steps: int = 0      # 0 = nowcast speed at window end

    # ----- sequence-wise split -----
    split_fractions: tuple[float, float, float] = (0.70, 0.15, 0.15)  # train/val/test
    split_seed: int = 26168

    # ----- usability filter (which synced pairs enter the model-ready set) -----
    min_sequence_seconds: float = 60.0
    min_sequence_km: float = 0.3
    max_row_mismatch: int = 300

    def dirs(self) -> list[Path]:
        return [self.artifacts, self.plots, self.interim,
                self.processed / "train",
                self.processed / "validation",
                self.processed / "test"]


DEFAULT_CONFIG = PrepConfig()

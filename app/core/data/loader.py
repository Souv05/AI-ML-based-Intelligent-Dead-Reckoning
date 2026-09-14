"""Stage 1-2 support: load raw IO-VNBD CSVs and expose both the untouched raw
frame and a canonical view.

Raw data is opened read-only; nothing here writes to dataset/IO-VNBD.
The low-level header mapping (mojibake, two phone layouts, mislabelled units) is
reused from the already-validated `iovnbd` package.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

_SRC = Path(__file__).resolve().parents[1]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from iovnbd import loader as _iolo          # noqa: E402
from iovnbd.schema import build_rename, PHONE_MAP, VEHICLE_MAP  # noqa: E402

_ENC = "latin-1"

# canonical phone field  <-  iovnbd canonical name
_PHONE_CANON = {
    "acc_x": "acc_x", "acc_y": "acc_y", "acc_z": "acc_z",
    "gyro_x": "gyro_x", "gyro_y": "gyro_y", "gyro_z": "gyro_z",
    "mag_x": "mag_x", "mag_y": "mag_y", "mag_z": "mag_z",
    "roll": "ori_roll", "pitch": "ori_pitch", "yaw": "ori_yaw",
    "latitude": "lat", "longitude": "lon",
    "gnss_speed": "gps_speed_ms",         # header says Kmh, values are m/s (verified)
    "gnss_heading": "gps_course_deg",
    "altitude": "alt_m",
    "grav_x": "grav_x", "grav_y": "grav_y", "grav_z": "grav_z",
}
_VEHICLE_CANON = {
    "reference_latitude": "lat", "reference_longitude": "lon",
    "reference_speed_kmh": "vel_kmh", "reference_heading": "heading_deg",
    "yaw_rate_dps": "yaw_rate_dps",
    "ws_fl": "ws_fl", "ws_fr": "ws_fr", "ws_rl": "ws_rl", "ws_rr": "ws_rr",
    "ind_speed_kmh": "ind_speed_kmh",
}

REQUIRED_PHONE = ["acc_x", "acc_y", "acc_z", "gyro_x", "gyro_y", "gyro_z"]
REQUIRED_VEHICLE = ["reference_latitude", "reference_longitude", "reference_speed_kmh"]


class MissingColumns(RuntimeError):
    pass


@dataclass
class LoadedFile:
    path: Path
    kind: str                     # "phone" | "vehicle"
    raw: pd.DataFrame             # exactly as read, original column names
    canonical: pd.DataFrame      # canonical names + 't' seconds-from-start
    rename_map: dict              # raw column -> canonical (iovnbd) name
    layout: str | None = None    # phone only


def _raw_headers(path: Path, mp) -> tuple[list[str], dict]:
    cols = list(pd.read_csv(path, encoding=_ENC, nrows=0).columns)
    return cols, build_rename(cols, mp)


def load_phone_file(path: str | Path) -> LoadedFile:
    path = Path(path)
    raw = pd.read_csv(path, encoding=_ENC, low_memory=False)
    plog = _iolo.load_phone_csv(path)                 # canonical + parsed clock
    canon = pd.DataFrame({"t": plog.df["t"].to_numpy()})
    for out_name, io_name in _PHONE_CANON.items():
        canon[out_name] = plog.df[io_name].to_numpy() if io_name in plog.df else np.nan
    missing = [c for c in REQUIRED_PHONE if canon[c].notna().mean() < 0.5]
    if missing:
        raise MissingColumns(f"{path.name}: phone columns unusable: {missing}")
    _, rename = _raw_headers(path, PHONE_MAP)
    return LoadedFile(path, "phone", raw, canon, rename, layout=plog.source_layout)


def load_vehicle_file(path: str | Path) -> LoadedFile:
    path = Path(path)
    raw = pd.read_csv(path, encoding=_ENC, low_memory=False)
    vlog = _iolo.load_vehicle_csv(path)
    canon = pd.DataFrame({"t": vlog.df["t"].to_numpy()})
    for out_name, io_name in _VEHICLE_CANON.items():
        canon[out_name] = vlog.df[io_name].to_numpy() if io_name in vlog.df else np.nan
    canon["reference_speed"] = canon["reference_speed_kmh"] / 3.6      # m/s
    missing = [c for c in REQUIRED_VEHICLE if canon[c].notna().mean() < 0.5]
    if missing:
        raise MissingColumns(f"{path.name}: vehicle columns unusable: {missing}")
    _, rename = _raw_headers(path, VEHICLE_MAP)
    return LoadedFile(path, "vehicle", raw, canon, rename)


def load_any(path: str | Path) -> LoadedFile:
    name = Path(path).name.upper()
    if name.startswith("S-"):
        return load_phone_file(path)
    if name.startswith("V-"):
        return load_vehicle_file(path)
    raise ValueError(f"cannot tell phone/vehicle from name: {path}")

"""Robust readers that turn the raw IO-VNBD CSVs into canonical structures.

Public API
----------
load_phone_csv(path)    -> PhoneLog
load_vehicle_csv(path)  -> VehicleLog
load_trip(synced_trip)  -> Trip           (row-aligned phone + vehicle + ENU truth)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from . import geo
from .paths import SyncedTrip
from .schema import PHONE_MAP, VEHICLE_MAP, build_rename

_ENC = "latin-1"          # tolerates the mojibake bytes without raising
NOMINAL_HZ = 10.0
NOMINAL_DT = 1.0 / NOMINAL_HZ


# --------------------------------------------------------------------------- #
# containers
# --------------------------------------------------------------------------- #
@dataclass
class PhoneLog:
    df: pd.DataFrame                     # canonical columns, plus 't' (s from 0)
    path: Path
    source_layout: str                  # "yaw_pitch_roll" | "xyz"

    @property
    def t(self) -> np.ndarray:
        return self.df["t"].to_numpy()

    def acc(self) -> np.ndarray:
        return self.df[["acc_x", "acc_y", "acc_z"]].to_numpy()

    def gyro(self) -> np.ndarray:
        return self.df[["gyro_x", "gyro_y", "gyro_z"]].to_numpy()

    def gravity(self) -> np.ndarray:
        return self.df[["grav_x", "grav_y", "grav_z"]].to_numpy()


@dataclass
class VehicleLog:
    df: pd.DataFrame                     # canonical columns, plus 't' (s from 0)
    path: Path

    @property
    def t(self) -> np.ndarray:
        return self.df["t"].to_numpy()

    @property
    def speed_ms(self) -> np.ndarray:
        """Ground-truth speed in m/s (from the GNSS/INS 'Velocity' channel)."""
        return self.df["vel_kmh"].to_numpy() / 3.6


@dataclass
class Trip:
    key: str
    driver: str
    phone: PhoneLog
    vehicle: VehicleLog
    # row-aligned truth in a local ENU frame (origin = first vehicle fix)
    lat0: float
    lon0: float
    east_m: np.ndarray
    north_m: np.ndarray
    t: np.ndarray                        # common time base, seconds from 0
    dist_m: np.ndarray                   # cumulative ground-truth path length
    meta: dict = field(default_factory=dict)

    @property
    def n(self) -> int:
        return len(self.t)

    @property
    def duration_s(self) -> float:
        return float(self.t[-1] - self.t[0])

    @property
    def length_m(self) -> float:
        return float(self.dist_m[-1])


# --------------------------------------------------------------------------- #
# phone
# --------------------------------------------------------------------------- #
def _parse_phone_time(df: pd.DataFrame) -> np.ndarray:
    """Seconds from the first row. Prefer the wall-clock DATE column; the
    'TIME SINCE START (ms)' channel is unreliable on several trips."""
    if "date" in df.columns:
        s = (
            df["date"].astype(str).str.strip()
            .str.replace(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}):(\d+)$",
                         r"\1.\2", regex=True)
        )
        ts = pd.to_datetime(s, errors="coerce")
        if ts.notna().mean() > 0.9:
            t = (ts - ts.iloc[0]).dt.total_seconds().to_numpy()
            # a few NaT rows -> fill by nominal cadence
            if np.isnan(t).any():
                idx = np.arange(len(t))
                good = ~np.isnan(t)
                t = np.interp(idx, idx[good], t[good])
            return t
    if "t_ms" in df.columns:
        t = pd.to_numeric(df["t_ms"], errors="coerce").to_numpy() / 1000.0
        t = t - np.nanmin(t)
        idx = np.arange(len(t))
        good = np.isfinite(t)
        return np.interp(idx, idx[good], t[good])
    return np.arange(len(df)) * NOMINAL_DT


def _split_sats(series: pd.Series) -> pd.Series:
    # values like "18 / 19"  ->  18   (satellites used in range)
    return pd.to_numeric(
        series.astype(str).str.split("/").str[0].str.strip(), errors="coerce"
    )


def load_phone_csv(path: str | Path) -> PhoneLog:
    path = Path(path)
    raw = pd.read_csv(path, encoding=_ENC, low_memory=False)
    rename = build_rename(list(raw.columns), PHONE_MAP)
    df = raw.rename(columns=rename)
    layout = "yaw_pitch_roll" if any(
        "yaw" in c.lower() and "gyro" in c.lower() for c in rename
    ) else "xyz"

    keep = [c for c in PHONE_MAP if c in df.columns]
    df = df[keep].copy()
    if "gps_sats" in df.columns:
        df["gps_sats"] = _split_sats(df["gps_sats"])
    for c in df.columns:
        if c == "date":
            continue
        df[c] = pd.to_numeric(df[c], errors="coerce")

    df["t"] = _parse_phone_time(df)
    df = df.reset_index(drop=True)
    return PhoneLog(df=df, path=path, source_layout=layout)


# --------------------------------------------------------------------------- #
# vehicle
# --------------------------------------------------------------------------- #
def load_vehicle_csv(path: str | Path) -> VehicleLog:
    path = Path(path)
    raw = pd.read_csv(path, encoding=_ENC, low_memory=False)
    rename = build_rename(list(raw.columns), VEHICLE_MAP)
    df = raw.rename(columns=rename)
    keep = [c for c in VEHICLE_MAP if c in df.columns]
    df = df[keep].copy()
    for c in df.columns:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    if "t_sod_s" in df.columns and df["t_sod_s"].notna().mean() > 0.9:
        t = df["t_sod_s"].to_numpy(dtype=float)
        t = t - t[0]
    elif "dt_s" in df.columns:
        t = np.cumsum(np.r_[0.0, df["dt_s"].to_numpy(dtype=float)[1:]])
    else:
        t = np.arange(len(df)) * NOMINAL_DT
    df["t"] = t
    df = df.reset_index(drop=True)
    return VehicleLog(df=df, path=path)


# --------------------------------------------------------------------------- #
# synced trip
# --------------------------------------------------------------------------- #
def load_trip(st: SyncedTrip) -> Trip:
    phone = load_phone_csv(st.phone_csv)
    veh = load_vehicle_csv(st.vehicle_csv)

    n = min(len(phone.df), len(veh.df))
    phone.df = phone.df.iloc[:n].reset_index(drop=True)
    veh.df = veh.df.iloc[:n].reset_index(drop=True)

    # common time base: the synchronised pairs are sample-locked at 10 Hz, and
    # the vehicle clock is the trustworthy one.
    t = veh.df["t"].to_numpy(dtype=float)
    if not np.all(np.isfinite(t)) or np.any(np.diff(t) <= 0):
        t = np.arange(n) * NOMINAL_DT
    t = t - t[0]

    lat = veh.df["lat"].to_numpy(dtype=float)
    lon = veh.df["lon"].to_numpy(dtype=float)
    lat0, lon0 = float(lat[0]), float(lon[0])
    east, north = geo.latlon_to_enu(lat, lon, lat0, lon0)
    dist = geo.cumulative_path_length_m(lat, lon)

    return Trip(
        key=st.key,
        driver=st.driver,
        phone=phone,
        vehicle=veh,
        lat0=lat0,
        lon0=lon0,
        east_m=east,
        north_m=north,
        t=t,
        dist_m=dist,
        meta={
            "trip_id": st.trip_id,
            "phone_csv": str(st.phone_csv),
            "vehicle_csv": str(st.vehicle_csv),
            "phone_layout": phone.source_layout,
            "n_rows": n,
        },
    )

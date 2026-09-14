"""Geodesy helpers - all lightweight, numpy only.

Distances over a single IO-VNBD trip are at most a few tens of km, so a local
equirectangular (tangent-plane) projection about the trip's first fix is well
under 1 m of error and keeps everything in a simple Cartesian ENU frame.
"""

from __future__ import annotations

import numpy as np

_R_EARTH = 6_378_137.0  # WGS-84 equatorial radius [m]


def latlon_to_enu(lat_deg, lon_deg, lat0_deg=None, lon0_deg=None):
    """Return (east_m, north_m) relative to (lat0, lon0) (defaults to first sample)."""
    lat = np.asarray(lat_deg, dtype=float)
    lon = np.asarray(lon_deg, dtype=float)
    if lat0_deg is None:
        lat0_deg = float(lat[0])
    if lon0_deg is None:
        lon0_deg = float(lon[0])
    lat0 = np.radians(lat0_deg)
    east = np.radians(lon - lon0_deg) * _R_EARTH * np.cos(lat0)
    north = np.radians(lat - lat0_deg) * _R_EARTH
    return east, north


def enu_to_latlon(east_m, north_m, lat0_deg, lon0_deg):
    lat0 = np.radians(lat0_deg)
    lat = lat0_deg + np.degrees(np.asarray(north_m) / _R_EARTH)
    lon = lon0_deg + np.degrees(np.asarray(east_m) / (_R_EARTH * np.cos(lat0)))
    return lat, lon


def haversine_m(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    return 2 * _R_EARTH * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def cumulative_path_length_m(lat_deg, lon_deg):
    """Arc length along the polyline, same length as input (first element 0)."""
    lat = np.asarray(lat_deg, dtype=float)
    lon = np.asarray(lon_deg, dtype=float)
    step = haversine_m(lat[:-1], lon[:-1], lat[1:], lon[1:])
    return np.concatenate([[0.0], np.cumsum(step)])


def wrap_deg(a):
    """Wrap angle(s) to [-180, 180)."""
    return (np.asarray(a) + 180.0) % 360.0 - 180.0


def unwrap_deg(a):
    return np.degrees(np.unwrap(np.radians(np.asarray(a, dtype=float))))

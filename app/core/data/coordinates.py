"""Stage: GNSS latitude/longitude -> local metric (ENU) coordinates.

Method (documented in artifacts/reference_definition.md as well):

  origin      = first row with a finite, in-range (lat, lon)
  projection  = equirectangular / local-tangent-plane ENU
                  east  = R * cos(lat0) * (lon - lon0) in radians
                  north = R * (lat - lat0)             in radians
  R           = 6378137 m (WGS-84 equatorial radius)

For a single IO-VNBD drive (<= a few tens of km) the linearisation error is
well under 1 m, which is far below the GNSS noise floor (~2-6 m here).
"""

from __future__ import annotations

import numpy as np

R_EARTH = 6_378_137.0

LAT_RANGE = (-90.0, 90.0)
LON_RANGE = (-180.0, 180.0)


def first_valid_origin(lat, lon):
    lat = np.asarray(lat, float)
    lon = np.asarray(lon, float)
    ok = (
        np.isfinite(lat) & np.isfinite(lon)
        & (lat > LAT_RANGE[0]) & (lat < LAT_RANGE[1])
        & (lon > LON_RANGE[0]) & (lon < LON_RANGE[1])
        & ~((lat == 0.0) & (lon == 0.0))
    )
    if not ok.any():
        raise ValueError("no valid GNSS fix to use as ENU origin")
    i = int(np.argmax(ok))
    return i, float(lat[i]), float(lon[i])


def latlon_to_local_xy(lat, lon, lat0=None, lon0=None):
    """Return (x_east_m, y_north_m). Origin defaults to the first valid fix."""
    lat = np.asarray(lat, float)
    lon = np.asarray(lon, float)
    if lat0 is None or lon0 is None:
        _, lat0, lon0 = first_valid_origin(lat, lon)
    x = np.radians(lon - lon0) * R_EARTH * np.cos(np.radians(lat0))
    y = np.radians(lat - lat0) * R_EARTH
    return x, y, (lat0, lon0)


def haversine_m(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    d = (np.sin((lat2 - lat1) / 2) ** 2
         + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2)
    return 2 * R_EARTH * np.arcsin(np.sqrt(np.clip(d, 0, 1)))


def path_length_m(lat, lon):
    lat = np.asarray(lat, float)
    lon = np.asarray(lon, float)
    step = haversine_m(lat[:-1], lon[:-1], lat[1:], lon[1:])
    step = np.where(np.isfinite(step), step, 0.0)
    return float(np.sum(step))

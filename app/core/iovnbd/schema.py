"""Raw header -> canonical column mapping.

The IO-VNBD CSVs carry two annoyances:

1. Mojibake / stray whitespace in headers, e.g. ``ACCELEROMETER X (m/s�) `` where
   ``�`` is a mangled ``2`` (m/s^2), and a leading space on many names.
2. Two different phone layouts:
     * categorised trips  -> ``GYROSCOPE Yaw/Pitch/Roll``,  ``ORIENTATION (Yaw)``
     * uncategorised pool  -> ``GYROSCOPE X/Y/Z``,           ``ORIENTATION (Azimuth)``
   They contain the same physical signals in the same column order.

We therefore normalise on *position-independent* fuzzy keys: lowercase, drop any
parenthesised unit, collapse whitespace, then match on a keyword list.
"""

from __future__ import annotations

import re

# canonical name -> ordered list of keyword sets; first header whose cleaned
# form contains every keyword in any set wins.
PHONE_MAP: dict[str, list[list[str]]] = {
    "lat":            [["gps", "latitude"]],
    "lon":            [["gps", "longitude"]],
    "alt_m":          [["gps", "altitude"]],
    # NOTE: header says "(Kmh)" but the values are metres/second (verified against
    # the vehicle ground-truth speed on every synced trip, ratio ~1.00).
    "gps_speed_ms":   [["gps", "speed"]],
    "gps_acc_m":      [["gps", "accuracy"]],
    "gps_course_deg": [["gps", "orientation"]],
    "gps_sats":       [["gps", "satellites"]],
    "t_ms":           [["time", "since", "start"]],
    "date":           [["date"]],
    "acc_x":          [["accelerometer", "x"]],
    "acc_y":          [["accelerometer", "y"]],
    "acc_z":          [["accelerometer", "z"]],
    "grav_x":         [["gravity", "x"]],
    "grav_y":         [["gravity", "y"]],
    "grav_z":         [["gravity", "z"]],
    "gyro_x":         [["gyroscope", "x"], ["gyroscope", "roll"]],
    "gyro_y":         [["gyroscope", "y"], ["gyroscope", "pitch"]],
    "gyro_z":         [["gyroscope", "z"], ["gyroscope", "yaw"]],
    "mag_x":          [["magnetic", "x"]],
    "mag_y":          [["magnetic", "y"]],
    "mag_z":          [["magnetic", "z"]],
    "ori_yaw":        [["orientation", "yaw"], ["orientation", "azimuth"]],
    "ori_pitch":      [["orientation", "pitch"]],
    "ori_roll":       [["orientation", "roll"]],
}

VEHICLE_MAP: dict[str, list[list[str]]] = {
    "n_sats":         [["gps", "satellites"]],
    "t_sod_s":        [["time", "since", "start", "day"]],
    "lat":            [["latitude"]],
    "lon":            [["longitude"]],
    "vel_kmh":        [["velocity"]],            # OXTS/GNSS-INS ground-truth speed
    "heading_deg":    [["heading"]],
    "height_m":       [["height"]],             # header says km, values are m
    "vvel_kmh":       [["vertical", "velocity"]],
    "dt_s":           [["sample", "period"]],
    "steer_deg":      [["steering", "angle"]],
    "ws_fl":          [["wheel", "speed", "front", "left"]],
    "ws_fr":          [["wheel", "speed", "front", "right"]],
    "ws_rl":          [["wheel", "speed", "rear", "left"]],
    "ws_rr":          [["wheel", "speed", "rear", "right"]],
    "yaw_rate_dps":   [["yaw", "rate"]],
    "ind_speed_kmh":  [["indicated", "vehicle", "speed"]],
    "acc_long_g":     [["indicated", "longitudinal", "acceleration"]],
    "acc_lat_g":      [["indicated", "lateral", "acceleration"]],
    "handbrake":      [["handbrake"]],
    "gear_req":       [["gear", "requested"]],
    "gear":           [["gear"]],
    "engine_rpm":     [["engine", "speed"]],
    "coolant_c":      [["coolant", "temperature"]],
    "clutch":         [["clutch", "position"]],
    "brake_psi":      [["brake", "pressure"]],
    "brake_pos":      [["brake", "position"]],
    "battery_v":      [["battery", "voltage"]],
    "air_temp_c":     [["air", "temperature"]],
    "accel_pedal":    [["accelerator", "pedal"]],
}

_NONALNUM_RE = re.compile(r"[^0-9a-zA-Z]+")


def clean_header(h: str) -> str:
    """Lowercase keyword bag: keep letters/digits (unit text included), drop the
    rest.  We deliberately keep parenthesised content because the phone
    ORIENTATION columns encode their axis there, e.g. ``ORIENTATION (Yaw) (deg)``.
    """
    return _NONALNUM_RE.sub(" ", h).strip().lower()


def build_rename(raw_headers: list[str], mapping: dict[str, list[list[str]]]) -> dict[str, str]:
    """raw header -> canonical name (only for columns we recognise).

    Keywords are matched against whole *tokens* of the cleaned header, not as
    substrings - otherwise a single-letter axis key like ``"y"`` would match
    ``"gyroscope yaw"``.  On a tie the header with the fewest tokens wins
    (e.g. ``Velocity`` beats ``Vertical velocity`` for the ``velocity`` key).
    """
    cleaned = [clean_header(h) for h in raw_headers]
    tokens = [set(c.split()) for c in cleaned]
    used_raw: set[str] = set()
    rename: dict[str, str] = {}
    for canon, keyword_sets in mapping.items():
        for kws in keyword_sets:
            hit = None
            hit_ntok = 1 << 30
            for raw, cl, tk in zip(raw_headers, cleaned, tokens):
                if raw in used_raw:
                    continue
                if all(k in tk for k in kws):
                    if len(tk) < hit_ntok:
                        hit, hit_ntok = raw, len(tk)
            if hit is not None:
                rename[hit] = canon
                used_raw.add(hit)
                break
    return rename

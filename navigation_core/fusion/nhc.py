"""NHC is built into EKFFusion._apply_nhc().

This module documents the NHC design and exports a standalone helper
for testing the constraint in isolation.
"""

from __future__ import annotations

import math


def lateral_velocity(vE: float, vN: float, heading_rad: float) -> float:
    """Return the lateral (sideways) speed component.

    Should be ~0 for a ground vehicle.
    Positive = sliding right, negative = sliding left.
    """
    return vE * math.cos(heading_rad) - vN * math.sin(heading_rad)


def forward_velocity(vE: float, vN: float, heading_rad: float) -> float:
    """Return the forward speed component."""
    return vE * math.sin(heading_rad) + vN * math.cos(heading_rad)

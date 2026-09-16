"""Base class all sensor adapters must inherit from."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterator

from .standard_imu import StandardIMUSample


class IMUAdapter(ABC):
    """Convert raw sensor data → StandardIMUSample.

    Subclasses handle unit conversion, frame transformation, and bias
    calibration.  The navigation core never receives anything else.
    """

    @abstractmethod
    def convert(self, raw: dict) -> StandardIMUSample:
        """Convert one raw sensor packet to a StandardIMUSample."""

    def stream(self, packets: Iterator[dict]) -> Iterator[StandardIMUSample]:
        """Convenience: lazily convert an iterable of raw packets."""
        for pkt in packets:
            yield self.convert(pkt)

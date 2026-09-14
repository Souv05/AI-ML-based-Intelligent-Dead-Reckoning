"""IO-VNBD data-preparation pipeline (SIH 2026 / PS 26168, phase: DATA PREP ONLY).

Stage order (see scripts/prepare_dataset.py):

    inventory -> inspect -> visualize -> validate -> synchronize
    -> define reference -> define inputs/target -> blackout mask
    -> temporal windows -> sequence-wise split -> leakage check -> save processed

NO MODEL TRAINING happens anywhere in this package.
"""

from .config import PrepConfig, DEFAULT_CONFIG

__all__ = ["PrepConfig", "DEFAULT_CONFIG"]

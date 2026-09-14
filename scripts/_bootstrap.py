"""Put <project>/src on sys.path so `import iovnbd` works when scripts are run
directly (`python scripts/02_eda_report.py`)."""

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

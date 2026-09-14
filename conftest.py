"""Pytest bootstrap: put <repo>/src on sys.path so `import data` / `import iovnbd`
resolve without each test file doing its own path insert.

pytest auto-discovers this file at collection time; many editors/analyzers also
honour a root-level conftest.py for import resolution.
"""

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

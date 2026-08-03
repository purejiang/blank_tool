"""
Root-level pytest conftest.

Inserts the ``backend/`` package directory into ``sys.path`` so every test
suite under ``tests/`` (contracts, backend/unit, ...) can ``import app.*``
without repeating path setup per test file. Mirrors the sys.path pattern from
``tests/contracts/conftest.py``.
"""

import os
import sys

# Path to the backend/ package directory (one level up from tests/).
BACKEND_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "backend")
)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

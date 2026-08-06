"""
Root-level pytest conftest.

Inserts the ``cli/`` package directory into ``sys.path`` so every test
suite under ``tests/`` (contracts, cli/unit, ...) can ``import app.*``
without repeating path setup per test file. Mirrors the sys.path pattern from
``tests/contracts/conftest.py``.
"""

import os
import sys

# Path to the cli/ package directory (one level up from tests/).
CLI_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "cli")
)
if CLI_DIR not in sys.path:
    sys.path.insert(0, CLI_DIR)

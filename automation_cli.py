#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Launcher for the adb automation CLI — run automation WITHOUT the app.

    python automation_cli.py --steps steps.json [--device SERIAL] [--package PKG]

Standalone distribution: copy ``backend/app/`` + this file + an adb
binary; no pip dependencies (Python 3.10+ standard library only).
See backend/app/automation/cli.py for details.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend"))

from app.automation.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())

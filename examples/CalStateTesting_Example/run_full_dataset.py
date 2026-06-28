#!/usr/bin/env python3
"""
run_full_dataset.py
====================
Convenience wrapper around generate_calstate_testing.py for regenerating
this example's committed {PREFIX}_gv_node.csv/{PREFIX}_gv_tag.csv.

To change the year range, just edit START_YEAR / END_YEAR below and re-run
this file -- no command-line flags to remember. (Everything else --
grade, demographic groups, color palette, etc. -- still has its own flag
on generate_calstate_testing.py if you want to change those too; this
wrapper only fixes the two you'll touch most often.)
"""

START_YEAR = 2003
END_YEAR = 2012
GRADE = 8

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent

subprocess.run([
    sys.executable, str(HERE / "generate_calstate_testing.py"),
    "--source", "mysql",
    "--grade", str(GRADE),
    "--start-year", str(START_YEAR),
    "--end-year", str(END_YEAR),
], check=True)

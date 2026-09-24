from pathlib import Path
from typing import Optional

MAX_STACK_DEPTH = 16

# Enabled with --debug: performs the safety checks (which are excluded otherwise to avoid
# distorting the measured times) and stores the debug dumps in DEBUG_DIR
DEBUG = False
DEBUG_DIR: Optional[Path] = None

from pathlib import Path
from typing import Optional

MAX_STACK_DEPTH = 16

# Enabled with --thread-empty-blocks: every block whose emitted code is only its jump is skipped at emission (the
# jumps and return addresses that reach it go to its successor), not only grey's edge blocks
THREAD_EMPTY_BLOCKS = False

# Enabled with --debug: performs the safety checks (which are excluded otherwise to avoid
# distorting the measured times) and stores the debug dumps in DEBUG_DIR
DEBUG = False
DEBUG_DIR: Optional[Path] = None

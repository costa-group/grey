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

# Disabled with --no-push-dup: once the greedy has decided the code of a block, the PUSHes of values that are
# already in the stack are replaced by DUPs (fewer bytes, same number of instructions and gas)
PUSH_DUP = True

# Disabled with --no-fallthrough: the unconditional jumps to the block placed right after (PUSH [tag] t JUMP tag t)
# are removed, as solc's code generator does (it generates the target in place when it has not been generated yet)
FALLTHROUGH = True

# Set with --solc-cfg-fallback: solc executable used to generate the yulCFGJson when the main one (-solc) fails with an
# internal error (e.g. builds that also compute their own stack layouts, whose stack shuffler can throw "stack too
# deep"). The main solc is still used for the importer
SOLC_CFG_FALLBACK: Optional[str] = None

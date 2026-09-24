"""
Helpers for the --debug option. Safety checks and debug dumps are only performed when it is
enabled, so that the times measured in regular executions correspond only to the pipeline
"""
from pathlib import Path
import global_params.constants as constants


def debug_file(file_name: str) -> Path:
    """
    Returns the path in which a debug dump named file_name must be stored,
    creating the debug folder if needed
    """
    assert constants.DEBUG_DIR is not None, "The debug folder must be set before storing debug dumps"
    constants.DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    return constants.DEBUG_DIR.joinpath(file_name)

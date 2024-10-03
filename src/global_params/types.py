"""
Module that contains the declaration of common types used throughout the project
"""
from typing import Dict, Union, Any

ASM_bytecode_T = Dict[str, Union[int, str]]

# SMS refers to the JSON representation of a block, with the initial and final stacks and the operations
SMS_T = Dict[str, Any]

Yul_CFG_T = Dict[str, Any]
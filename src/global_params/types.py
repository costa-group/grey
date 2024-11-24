"""
Module that contains the declaration of common types used throughout the project.
While most of the types correspond to basic types, it is useful to read the project
"""
from typing import Dict, Union, Any, List, Tuple

# Constants in the yul format are hexadecimal
constant_T = str

# Type for the stack variables that are introduced in the stack as args of other expressions
var_id_T = str

# An expression consists of either a variable, a constant or an op and their subexpressions
# Its grammar:
# exp -> int_val | input_var | (op, [exp1, ..., expn])
expression_T = Union[int, var_id_T, Tuple[str, List['expression_T']]]

# Representation of an interval formed by an expression and an offset
memory_instr_interval_T = Tuple[expression_T, expression_T]

# Type for the id of instructions in the SMS
instr_id_T = str

# Id for block ids
block_id_T = str

# Name of a function
function_name_T = str

# Object type
cfg_object_T = str

# A component correspond to the name of either a object or function in the CFG
component_name_T = Union[cfg_object_T, function_name_T]

# The type of a block list id corresponds to its associated component
block_list_id_T = component_name_T

# How dependencies among instructions are represented
dependencies_T = List[List[instr_id_T]]

# How instructions are represented in the SFS
instr_JSON_T = Dict[str, Any]

ASM_bytecode_T = Dict[str, Union[int, str]]

# SMS refers to the JSON representation of a block, with the initial and final stacks and the operations
SMS_T = Dict[str, Any]

Yul_CFG_T = Dict[str, Any]

ASM_contract_T = Dict[str, Any]

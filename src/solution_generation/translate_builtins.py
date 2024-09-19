"""
Module to translate the special builtins in Yul to the corresponding assembly JSON.
See "https://notes.ethereum.org/znem65ljTKaoL11xOWv-Ew" for an explanation on the different translations
"""

from parser.cfg_instruction import CFGInstruction
from global_params.types import ASM_bytecode_T


def assert_translation_name(expected_name: str, instr_name: str):
    assert instr_name == expected_name, f"Translating {instr_name} as {expected_name}"


def translate_linkersymbol(instr: CFGInstruction) -> ASM_bytecode_T:
    assert_translation_name("linkersymbol", instr.op)


def translate_memoryguard(instr: CFGInstruction) -> ASM_bytecode_T:
    assert_translation_name("memoryguard", instr.op)
    pass


def translate_datasize(instr: CFGInstruction) -> ASM_bytecode_T:
    assert_translation_name("datasize", instr.op)


def translate_dataoffset(instr: CFGInstruction) -> ASM_bytecode_T:
    assert_translation_name("dataoffset", instr.op)


def translate_datacopy(instr: CFGInstruction) -> ASM_bytecode_T:
    assert_translation_name("datacopy", instr.op)


def translate_setimmutable(instr: CFGInstruction) -> ASM_bytecode_T:
    assert_translation_name("setimmutable", instr.op)


def translate_loadimmutable(instr: CFGInstruction) -> ASM_bytecode_T:
    assert_translation_name("loadimmutable", instr.op)

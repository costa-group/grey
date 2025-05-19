"""
Module that translates the opcodes into assembly
"""
from typing import Dict, Any, List
import json


def build_assembly_instruction(name: str, value: int = None) -> Dict[str, Any]:
    """
    Given an instruction, generates it assembly representation
    """
    opcode = {"name": name, "begin": -1, "end": -1, "source": -1}

    if value is not None:
        opcode["value"] = str(value)
    return opcode


def bytecode2asm(opcodes: List[str]) -> List[Dict[str, Any]]:
    pc = 0
    tag_number = 0
    byte2jumpdest = dict()
    i = 0
    while i < len(opcodes):
        opcode = opcodes[i]

        if opcode.startswith("PUSH") and opcode != "PUSH0":
            i += 1
            bytecode_size = int(opcode[4:])
            pc += bytecode_size
        elif opcode.startswith("JUMPDEST"):
            byte2jumpdest[pc] = tag_number
            tag_number += 1

        pc += 1
        i += 1

    pc = 0
    operations = []
    i = 0

    while i < len(opcodes):
        opcode = opcodes[i]

        if opcode.startswith("PUSH") and opcode != "PUSH0":
            bytecode_size = int(opcode[4:])
            pc += bytecode_size
            value = int(opcodes[i+1], 16)
            i += 1
            if value in byte2jumpdest:
                operations.append(build_assembly_instruction("PUSH [tag]", byte2jumpdest[value]))
            else:
                operations.append(build_assembly_instruction("PUSH", value))
        elif opcode.startswith("JUMPDEST"):
            operations.append(build_assembly_instruction("tag", byte2jumpdest[pc]))
            operations.append(build_assembly_instruction("JUMPDEST"))
        else:
            operations.append(build_assembly_instruction(opcode))

        i += 1
        pc += 1

    with open("operations.json", 'w') as f:
        json.dump(operations, f, indent=4)
    return operations


def asm_from_opcodes(opcodes: str) -> Dict[str, Any]:
    asm_json = dict()

    opcodes_per_region = [chunk.strip().split(" ")
                          for chunk in opcodes.split("INVALID")]

    assert len(opcodes_per_region) in [2, 3], \
        f"Expected two or three regions. Got: {len(opcodes_per_region)}"

    init_code = bytecode2asm(opcodes_per_region[0])

    asm_json[".code"] = init_code
    asm_json["sourceList"] = []

    asm_json[".data"] = dict()
    asm_json[".data"]["0"] = {".code": bytecode2asm(opcodes_per_region[1])}

    return asm_json

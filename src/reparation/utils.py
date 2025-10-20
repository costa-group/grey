"""
Utils module
"""


def extract_value_from_pseudo_instr(instruction: str) -> str:
    if instruction.startswith("VGET"):
        return instruction[5:-1]
    elif instruction.startswith("VSET"):
        return instruction[5:-1]
    elif instruction.startswith("DUP-VSET"):
        return instruction[9:-1].split(",")[0]
    return None


def extract_dup_pos_from_dup_vset(instruction: str) -> int:
    assert instruction.startswith("DUP-VSET"), f"Instruction {instruction} must be DUP-VSET"
    return int(instruction[9:-1].split(",")[1])

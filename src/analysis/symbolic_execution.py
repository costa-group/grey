"""
Symbolic execution
"""
from typing import List
from global_params.types import var_id_T, instr_id_T, instr_JSON_T
import re

get_re = re.compile('VGET\((.*)\)')
set_re = re.compile('VSET\((.*)\)')


def extract_idx_from_id(instr_id: str) -> int:
    return int(instr_id.split('_')[-1])


def execute_instr_id(instr_id: str, cstack: List[var_id_T], user_instr: List[instr_JSON_T]):
    """
    Executes the instr id according to user_instr
    """
    # POP: Pop the value
    if instr_id == 'POP':
        cstack.pop(0)

    # SWAPx: swaps elements at positions 0 and x
    elif 'SWAP' in instr_id:
        idx = int(instr_id[4:])
        assert 0 <= idx < len(cstack), f"Swapping with index {idx} a stack of {len(cstack)} elements: {cstack}"
        cstack[0], cstack[idx] = cstack[idx], cstack[0]

    # DUPx: duplicates the value at position x-1
    elif 'DUP' in instr_id:
        idx = int(instr_id[3:]) - 1
        assert 0 <= idx < len(cstack), f"Duplicating index {idx} in a stack in {len(cstack)} elements: {cstack}"
        cstack.insert(0, cstack[idx])

    # GET x: just inserts the corresponding element in the memory
    elif (get_match := get_re.match(instr_id)) is not None:
        cstack.insert(0, get_match.group(1))

    # SET x: just pops the element from the stack (as if it was stored in memory)
    elif (set_match := set_re.match(instr_id)) is not None:
        stack_var = set_match.group(1)
        popped_var = cstack.pop(0)
        assert stack_var == popped_var, "Attempting to store an unexpected variable in memory"

    # Otherwise, the remaining uninterpreted instructions
    else:
        instr = [instr for instr in user_instr if instr['id'] == instr_id][0]

        if instr["commutative"]:
            input_vars = instr['inpt_sk']
            assert len(input_vars) == 2, 'Commutative instructions with #args != 2'
            # We consume the elements
            s0, s1 = cstack.pop(0), cstack.pop(0)
            assert (s0 == input_vars[0] and s1 == input_vars[1]) or (s0 == input_vars[1] and s1 == input_vars[0]), \
                f"Args don't match in commutative instr {instr_id}"

        else:
            # We consume the elements
            for input_var in instr['inpt_sk']:
                assert cstack[0] == input_var, f"Args don't match in non-commutative instr {instr_id}"
                cstack.pop(0)

        # We introduce the new elements
        for output_var in reversed(instr['outpt_sk']):
            cstack.insert(0, output_var)

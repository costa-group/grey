"""
Module that includes the necessary methods for a lightweight verification of the output from a synthesizer,
given a SFS. It is less powerful than Forves, but it provides readable insights for most common errors
"""
import collections
import json
from typing import List, Dict, Tuple
import sys
from global_params.types import var_id_T, instr_id_T, instr_JSON_T
import re

DEBUG_MODE = False

get_re = re.compile('GET\((.*)\)')
set_re = re.compile('SET\((.*)\)')


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


def check_deps(instr_ids: List[instr_id_T], dependencies: List[Tuple[instr_id_T, instr_id_T]]) -> bool:
    """
    Check the ids from the final instructions satisfy the dependencies
    """
    pos_by_id = collections.defaultdict(lambda: [])
    for i, instr in enumerate(instr_ids):
        pos_by_id[instr].append(i)
    if DEBUG_MODE:
        for dep in dependencies:
            print(dep, max(pos_by_id[dep[0]]) < min(pos_by_id[dep[1]]))
    return all(max(pos_by_id[dep[0]]) < min(pos_by_id[dep[1]]) for dep in dependencies)


def ensure_ids_are_unique(user_instr: List[instr_JSON_T]) -> bool:
    accesses = set()
    for instr in user_instr:
        instr_id = instr['id']
        if instr_id in accesses:
            return False
        else:
            accesses.add(instr_id)
    return True


def ensure_stack_vars_are_unique(user_instr: List[instr_JSON_T]) -> bool:
    accesses = set()
    for instr in user_instr:
        stack_vars = instr['outpt_sk']
        for stack_var in stack_vars:
            if stack_var in accesses:
                return False
            else:
                accesses.add(stack_var)
    return True


def print_state(instr_id, stack):
    max_list_len = 70 # - sum(len(elem) for elem in stack) - 2*len(stack) - 2*(len(stack)- 1)

    # Calculate the maximum length of the string part
    max_str_len = 40

    # Print each tuple with aligned formatting
    print(f"{instr_id:<{max_str_len}} {str(stack):>{max_list_len}}")


def check_execution_from_ids(sfs: Dict, instr_ids: List[instr_id_T]) -> bool:
    """
    Given a SFS and a sequence of ids, checks the ids indeed represent a valid solution
    """
    user_instr: List[instr_JSON_T] = sfs['user_instrs']
    dependencies: List[Tuple[instr_id_T, instr_id_T]] = sfs['dependencies']

    cstack, fstack = sfs['src_ws'].copy(), sfs['tgt_ws']

    for instr_id in instr_ids:
        print_state(instr_id, cstack)
        execute_instr_id(instr_id, cstack, user_instr)

    assert cstack == fstack, f"""
                             Ids - Stack do not match. 
                             Cstack {cstack}
                             Fstack {fstack}
                             """

    assert check_deps(instr_ids, dependencies), 'Dependencies are not coherent'
    for instr in user_instr:
        if any(instr_name in instr["disasm"] for instr_name in ["STORE"]):
            assert instr_ids.count(instr["id"]) == 1, "Mem operation used more than once"

    return True


if __name__ == "__main__":
    with open(sys.argv[1], 'r') as f:
        loaded_sfs = json.load(f)

"""
Module that includes the necessary methods for a lightweight verification of the output from a synthesizer,
given a SFS. It is less powerful than Forves, but it provides readable insights for most common errors
"""
import collections
import json
from typing import List, Dict, Tuple
import sys
from global_params.types import var_id_T, instr_id_T, instr_JSON_T
from analysis.symbolic_execution import execute_instr_id

DEBUG_MODE = False


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
        # If there is a function that must be computed at most once
        if instr["storage"]:
            assert instr_ids.count(instr["id"]) == 1, "Mem operation used more than once"

    return True


if __name__ == "__main__":
    with open(sys.argv[1], 'r') as f:
        loaded_sfs = json.load(f)

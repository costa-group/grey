import collections
import sys
import json
from typing import Dict, List, Tuple, Set, Union, Optional, Generator
from block_generation import greedy_from_json, var_T, id_T
from enum import Enum, unique

max_depth = 16


# Situations we might encounter for stack too deep errors
@unique
class StackTooDeepSituation(Enum):
    # We just need to retrieve the corresponding value
    dup = 0

    # Swap done to bring to the front an element that must be consumed
    swap_compute = 1

    # Swap to place an element in its corresponding position
    swap_place = 2


class VarInformation:

    def __init__(self, stack_var: var_T):
        self.stack_var: var_T = stack_var
        self.positions_top: Set[int] = set()
        self.positions_consumed: Set[int] = set()
        self.inaccessible_positions: List[Tuple[StackTooDeepSituation, int]] = []

    def add_position_top(self, pos: int):
        """
        Adds a position to the set of possible positions in which the term appears as the topmost element
        """
        self.positions_top.add(pos)

    def add_position_consumed(self, pos: int):
        """
        Adds a position to the set of positions in which the term is being used (either consumed as a subterm
        or placed in their final position)
        """
        self.positions_consumed.add(pos)

    def add_inaccessible_position(self, stack_situation: StackTooDeepSituation, pos: int):
        """
        Adds the set of corresponding positions in which the stack var is accessed a too deep SWAPx or DUPx
        """
        self.inaccessible_positions.append((stack_situation, pos))

    def when_to_store(self) -> Tuple[str, int]:
        """
        Determines in which step we must have stored the corresponding stack element according to the different
        accesses and whether it must be done using a GETx or a TEEx instruction
        """
        pass

class StackVarsInformation:
    """
    Stores the information from the greedy algorithm and decides which terms must be stored
    """

    def __init__(self):
        self._stack_var_info: Dict[var_T, VarInformation] = dict()

    def store_topmost(self, stack_var: var_T, step: int):
        current_info = self._stack_var_info.get(stack_var, None)
        if current_info is None:
            current_info = VarInformation(stack_var)
            self._stack_var_info[stack_var] = current_info

        current_info.add_position_top(step)

    def store_consumed(self, stack_var: var_T, step: int):
        current_info = self._stack_var_info.get(stack_var, None)
        if current_info is None:
            current_info = VarInformation(stack_var)
            self._stack_var_info[stack_var] = current_info

        current_info.add_position_consumed(step)

    def store_inaccessible(self, stack_var: var_T, stack_situation: StackTooDeepSituation, step: int):
        current_info = self._stack_var_info.get(stack_var, None)
        if current_info is None:
            current_info = VarInformation(stack_var)
            self._stack_var_info[stack_var] = current_info

        current_info.add_inaccessible_position(stack_situation, step)

    def elements_to_store(self) -> List[Tuple[str, int]]:
        """
        Given the information stored so far, returns the instructions that must be performed and the position in which
        they should be applied
        """
        for stack_var, var_info in self._stack_var_info.items():
            # If there are inaccessible positions, we must store the corresponding stack element
            # when it reaches the top of the stack (last instruction). Also, we must determine whether to do it
            # with a GETx or a TEEx instruction, depending on whether it is used afterwards
            # There are some inaccessible positions
            # Detect if there are innaccessible positions
            if len(var_info.inaccessible_positions) > 0:
                pass



def execute_instr_id(instr_id: str, cstack: List[var_T], user_instr: List[Dict]) -> Tuple[Optional[var_T], List[var_T]]:
    """
    Executes the instr id according to user_instr. Returns the element that is being accessed if it is too deep and the
    list of variables that are consumed (if any)
    """
    affected_element = None
    consumed_elements = []

    # Drop the value
    if instr_id == 'POP':
        cstack.pop(0)

    elif 'DUP' in instr_id:
        idx = int(instr_id[3:])

        if idx > max_depth:
            affected_element = cstack[idx-1]
        cstack.insert(0, cstack[idx-1])

    elif 'SWAP' in instr_id:
        idx = int(instr_id[4:])

        if idx > max_depth:
            affected_element = cstack[idx]

        cstack[0], cstack[idx] = cstack[idx], cstack[0]

    # SET instructions: pseudoinstructions to represent storing in registers
    elif 'SET' in instr_id:
        # Ensure the topmost element is the element we are setting
        topmost = cstack.pop(0)

    # GET instructions pseudoinstructions to represent loading from registers
    elif 'GET' in instr_id:
        cstack.insert(0, instr_id.split(" ")[1])

    # TEE instructions pseudoinstructions to represent storing in a register while keeping the stack variable inside
    # Useful when need to keep a copy that does not need to be loaded
    elif 'TEE' in instr_id:
        pass

    else:
        instr = [instr for instr in user_instr if instr['id'] == instr_id][0]

        if instr["commutative"]:
            input_vars = instr['inpt_sk']
            assert len(input_vars) == 2, 'Commutative instructions with #args != 2'
            # We consume the elements
            s0, s1 = cstack.pop(0), cstack.pop(0)
            consumed_elements.append(s0)
            consumed_elements.append(s1)
            assert (s0 == input_vars[0] and s1 == input_vars[1]) or (s0 == input_vars[1] and s1 == input_vars[0]), \
                f"Args don't match in commutative instr {instr_id}"

        else:
            # We consume the elements
            for input_var in instr['inpt_sk']:
                assert cstack[0] == input_var, f"Args don't match in non-commutative instr {instr_id}." \
                                               f"\nTopmost elements in stack: {cstack[:len(instr['inpt_sk'])]}" \
                                               f"\nArgs in instr: {instr['inpt_sk']}"
                consumed_elements.append(cstack.pop(0))

        # We introduce the new elements
        for output_var in reversed(instr['outpt_sk']):
            cstack.insert(0, output_var)

    return affected_element


def elements_to_store_in_regs(sfs: Dict, instr_ids: List[id_T]) -> StackVarsInformation:
    """
    Given the sfs and the instr ids in the corresponding sequences, generates two lists. The first list contains
    each stack variable, the position it was introduced first and the positions in which it is needed
    """
    user_instr: List[Dict] = sfs['user_instrs']
    cstack, fstack = sfs['src_ws'].copy(), sfs['tgt_ws']

    var2varinfo: StackVarsInformation = StackVarsInformation()

    if len(cstack) > 0:
        # Annotate the initial stack element
        var2varinfo.store_topmost(cstack[0], -1)

    for i, instr_id in enumerate(instr_ids):
        print(i, instr_id, cstack)
        affected, consumed_stack_vars = execute_instr_id(instr_id, cstack, user_instr)

        # Store the positions in which the element is being used
        for consumed_stack_var in consumed_stack_vars:
            var2varinfo.store_consumed(consumed_stack_var, i)

        if affected is not None:
            if "DUP" in instr_id:
                stack_situation = StackTooDeepSituation.dup

            # Check if it moves an element to its corresponding position in the final stack
            else:
                # Check if it moves an element to its corresponding position in the final stack
                swap_idx = int(instr_id[4:])

                # Element has been placed in its corresponding position in the final stack
                if cstack[swap_idx] == fstack[len(fstack) + swap_idx - len(cstack)]:
                    stack_situation = StackTooDeepSituation.swap_place
                else:
                    # We are using the moved stack element to compute a new term
                    stack_situation = StackTooDeepSituation.swap_compute

            var2varinfo.store_inaccessible(affected, stack_situation, i)

        if len(cstack) > 0:
            var2varinfo.store_topmost(cstack[0], i)

    return var2varinfo


def combine_same_stack_var(elements_to_store: List[Tuple[var_T, StackTooDeepSituation, int, int]]) -> Dict[var_T, Tuple[int, List[Tuple[StackTooDeepSituation, int]]]]:
    var2positions = dict()
    for variable, stack_situation, initial_position, final_position in elements_to_store:
        var_positions = var2positions.get(variable, None)
        if var_positions is None:
            var2positions[variable] = (initial_position, [(stack_situation, final_position)])
        # It has already appeared, so we just update the final position and include the new one
        else:
            var2positions[variable] = (min(initial_position, var_positions[0]), [*var_positions[1],
                                                                                 (stack_situation, final_position)])
    return var2positions


def decide_vars_to_store(step2top: List[var_T], conflicting_elements: List[Tuple[var_T, int, int]]) -> Set[var_T]:
    # Given the list of variables that have been the topmost element, decide which ones are going to be stored
    # (number "elements_to_store")
    # TODO: refine so that once an element is stored, the next one is also a possibility

    # Naive approach: store the first elements in step2top
    for element in step2top:
        pass
        #elements_to_store.add(element)
        #if len(elements_to_store) == n_elements_to_store:
        #    return elements_to_store

def update_affected_interval(shift, affected_intervals: List[int]) -> List[int]:
    # We have to update the interval information, as new elements are not affected. Moreover,
    # if an interval is less than 0, then we remove it (as it no longer contains elements that are affected)
    # TODO inneficient!:
    new_affected_intervals = []
    for interval_ini in affected_intervals:
        new_interval_ini = interval_ini + shift
        if new_interval_ini >= 0:
            new_affected_intervals.append(new_interval_ini)
    return new_affected_intervals


def find_interval(idx: int, affected_intervals: List[int]):
    # TODO inneficient!!: Binary search
    for i, element in enumerate(affected_intervals):
        if idx >= element:
            return -i - 1
    return 0


def decide_get_or_tee():
    pass


def substitute_positions(seq_id: List[id_T], user_instrs: Dict, var2info: StackVarsInformation) -> List[id_T]:
    # We sort the dictionary according to the corresponding position. We introduce a SETx and GETx instruction
    # for each initial and final position
    operations2introduce = []

    for var, (initial_position, final_positions) in var2info.items():

        # If the corresponding variable is accessed in between with other instruction,
        # we apply a TEEx instead of a GETx
        operations2introduce.append([initial_position, f"TEE {var}"])
        for stack_situation, final_position in final_positions:

            # If it is a DUP or a SWAP that reuses an element,
            # then we need to include a GET instruction to retrieve the element
            if stack_situation == StackTooDeepSituation.dup or stack_situation == StackTooDeepSituation.swap_compute:
                operations2introduce.append([final_position, f"GET {var}"])

            # Otherwise, we need to remove some elements to apply a SWAP operation
            # to the corresponding position. We mark those instruction as "ACCESS swap_idx"
            else:
                operations2introduce.append([final_position, f"ACCESS {sw}"])


def introduce_operations(seq_id: List[id_T], user_instrs: Dict, operations2introduce: List[Tuple[int, str]]):
    # First we introduce the SETx and GETx "instructions"
    operations2introduce_ordered = sorted(operations2introduce)
    new_seq_id = seq_id.copy()

    ops_introduced = 0
    # Introduce the instruction, replacing the corresponding instruction that was previously used instead
    for position, instruction in operations2introduce_ordered:
        # SET and TEE instructions must be introduced in the moment when the corresponding element is in the top
        if "SET" in instruction or "TEE" in instruction:
            new_seq_id.insert(position + ops_introduced + 1, instruction)
            ops_introduced += 1
        # Otherwise, we just replace the corresponding instruction (shifting the previous index according to the
        # previous SET operations)
        else:
            new_seq_id[position + ops_introduced] = instruction

    # Intervals of positions in the stack that are affected with the changes. We only represent the first element
    # in the interval, as all the elements in between are affected. See below for more explanations
    affected_intervals = []

    # Then we update the intermediate SWAPx and DUPx instructions by substracting the elements that no longer exist
    final_seq_id = []

    # We need to consider only the elements that are active
    for instr_id in new_seq_id:
        new_instr = instr_id
        if "SET" in instr_id:
            shift = -1

        elif "GET" in instr_id:
            shift = 1

        elif "TEE" in instr_id:
            # Tee keeps the shift
            shift = 0

        elif "SWAP" in instr_id:
            idx = int(instr_id[4:])
            swap_shift = find_interval(idx, affected_intervals)
            new_instr = f"SWAP{idx+swap_shift}"
            shift = 0

        elif "DUP" in instr_id:
            idx = int(instr_id[3:])
            dup_shift = find_interval(idx, affected_intervals)
            shift = 1

            new_instr = f"DUP{idx+dup_shift}"
        elif "POP" in instr_id:
            # Remove an element
            shift = -1
        else:
            instr = [instr for instr in user_instrs if instr['id'] == instr_id][0]
            shift = len(instr["outpt_sk"]) - len(instr["inpt_sk"])

        # First we update the intervals
        affected_intervals = update_affected_interval(shift, affected_intervals)

        # Then we add the new interval or remove it
        if "SET" in instr_id:
            # Each time we do a SET instruction, we need to consider that stack elements from then on are affected
            # when swapped an element (as an element has been removed). As multiple set can go together, we need
            # to set multiple intervals
            affected_intervals.append(0)

        elif "GET" in instr_id:
            # We POP the latest interval, as it no longer affects the results
            if len(affected_intervals) > 0:
                affected_intervals.pop(0)

        final_seq_id.append(new_instr)

    return final_seq_id


def symbolic_exec_from_ids(sfs, seq_ids: List[id_T]):
    user_instr: List[Dict] = sfs['user_instrs']
    cstack, fstack = sfs['src_ws'].copy(), sfs['tgt_ws']
    for i, instr_id in enumerate(seq_ids):
        print(i, instr_id, cstack)
        affected = execute_instr_id(instr_id, cstack, user_instr)
        # There are no affected elements
        assert affected is None

    assert cstack == fstack


def substitute_operations(sfs: Dict, seq_ids: List[id_T]):
    var2info = elements_to_store_in_regs(sfs, seq_ids)
    # vars_to_store = decide_vars_to_store(step2top, conflicting_elements)
    # var2position = combine_same_stack_var(conflicting_elements)
    substituted_ids = substitute_positions(seq_ids, sfs["user_instrs"], var2info)
    symbolic_exec_from_ids(sfs, substituted_ids)


if __name__ == "__main__":
    json_file = sys.argv[1]
    with open(json_file, 'r') as f:
        sfs = json.load(f)
    _, _, _, resids, _ = greedy_from_json(sfs)
    substitute_operations(sfs, resids)
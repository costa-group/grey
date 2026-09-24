"""
Module that validates the memory slots used to access stack-too-deep values (--debug only).
After the reparation, every VGET/VSET/DUP-VSET has been replaced by concrete memory accesses
(PUSH c; MLOAD / PUSH c; MSTORE / DUPk; PUSH c; MSTORE) and phi values are moved between slots by
the copies emitted at the end of the predecessors. This module checks that every load reads the
value that the following instructions expect, considering all the paths in the CFG.

It performs a forward must-analysis over the blocks of a block list:
  - The state maps each memory slot to the set of variable names it is known to hold. Several
    names are possible because a phi value and its argument are the same value along an edge.
  - Joins keep only the slots (and names) that agree in every predecessor.
  - The state is propagated by executing symbolically the final ids of every block, starting from
    the input stack of its specification. Loads push the set of names held by the slot.
The fixpoint is computed first without asserting anything (loads of unknown slots are allowed, as
back edges might not have been processed yet) and then a final pass checks every instruction.
"""
from dataclasses import dataclass
from typing import Dict, FrozenSet, List, Optional, Set, Tuple, Union

from global_params.types import block_id_T, var_id_T, instr_id_T, instr_JSON_T
from parser.cfg_block_list import CFGBlockList
from parser.cfg_block import CFGBlock

slot_T = str
memory_state_T = Dict[slot_T, FrozenSet[var_id_T]]


@dataclass(frozen=True)
class LoadedValue:
    """
    Value loaded from a memory slot: the set of names it is known to hold (empty if unknown)
    """
    slot: slot_T
    names: FrozenSet[var_id_T]


# A stack element is either a variable name or a memory token: a slot address pushed to perform a
# memory access or a value loaded from a slot
stack_element_T = Union[var_id_T, Tuple[str, slot_T], LoadedValue]


class MemorySlotError(AssertionError):
    def __init__(self, message: str, block_id: block_id_T = None, slot: Optional[slot_T] = None):
        super().__init__(message)
        self.block_id = block_id
        self.slot = slot


def _matches(stack_element: stack_element_T, expected_var: var_id_T) -> bool:
    """
    Checks whether the stack element corresponds to the expected variable
    """
    if isinstance(stack_element, LoadedValue):
        return expected_var in stack_element.names
    return stack_element == expected_var


def _names(stack_element: stack_element_T) -> FrozenSet[var_id_T]:
    """
    Set of variable names represented by a stack element (used when storing it in memory)
    """
    if isinstance(stack_element, LoadedValue):
        return stack_element.names
    if isinstance(stack_element, tuple):
        # Storing a slot address in memory does not happen in the emitted code
        return frozenset()
    return frozenset([stack_element])


def _describe(stack_element: stack_element_T) -> str:
    if isinstance(stack_element, LoadedValue):
        return f"slot {stack_element.slot} holding {set(stack_element.names) if stack_element.names else '(unknown)'}"
    return str(stack_element)


def execute_block(block: CFGBlock, memory: memory_state_T, strict: bool) -> memory_state_T:
    """
    Executes symbolically the final ids of the block, starting from the given memory state, and returns the
    memory state at the end of the block. In strict mode, every mismatch raises a MemorySlotError
    """
    spec = block.spec
    user_instrs: Dict[instr_id_T, instr_JSON_T] = {instr["id"]: instr for instr in spec["user_instrs"]}
    stack: List[stack_element_T] = list(spec["src_ws"])
    memory = dict(memory)

    def fail(position: int, instr_id: str, reason: str, elements: List[stack_element_T] = ()):
        if strict:
            # The first loaded value that does not match is used to explain the error afterwards
            slot = next((element.slot for element in elements if isinstance(element, LoadedValue)), None)
            raise MemorySlotError(f"Block {block.block_id}, position {position} ({instr_id}): {reason}",
                                  block.block_id, slot)

    for position, instr_id in enumerate(block.greedy_ids):
        if instr_id == "NOP":
            continue

        if instr_id == "POP":
            stack.pop(0)

        elif instr_id.startswith("SWAP"):
            idx = int(instr_id[4:])
            stack[0], stack[idx] = stack[idx], stack[0]

        elif instr_id.startswith("DUP"):
            stack.insert(0, stack[int(instr_id[3:]) - 1])

        # Slot addresses introduced by the reparation ("PUSH <hex>", not an instruction of the spec)
        elif instr_id.startswith("PUSH ") and instr_id not in user_instrs:
            stack.insert(0, ("slot", instr_id.split(" ")[1]))

        elif instr_id == "MSTORE":
            slot, value = stack.pop(0), stack.pop(0)
            if not isinstance(slot, tuple):
                fail(position, instr_id, f"the address is not a slot: {_describe(slot)}")
                continue
            memory[slot[1]] = _names(value)

        elif instr_id == "MLOAD":
            slot = stack.pop(0)
            if not isinstance(slot, tuple):
                fail(position, instr_id, f"the address is not a slot: {_describe(slot)}")
                stack.insert(0, LoadedValue("?", frozenset()))
                continue
            stack.insert(0, LoadedValue(slot[1], memory.get(slot[1], frozenset())))

        else:
            instr = user_instrs.get(instr_id)
            if instr is None:
                fail(position, instr_id, "unknown instruction id")
                continue

            input_vars = instr["inpt_sk"]
            consumed = [stack.pop(0) for _ in input_vars]
            if instr["commutative"] and len(input_vars) == 2:
                correct = (_matches(consumed[0], input_vars[0]) and _matches(consumed[1], input_vars[1])) or \
                          (_matches(consumed[0], input_vars[1]) and _matches(consumed[1], input_vars[0]))
            else:
                correct = all(_matches(element, var) for element, var in zip(consumed, input_vars))
            if not correct:
                fail(position, instr_id, f"expected {input_vars}, found {[_describe(e) for e in consumed]}",
                     consumed)

            for output_var in reversed(instr["outpt_sk"]):
                stack.insert(0, output_var)

    # The final stack must match the target stack (junk might remain below if admitted)
    target_stack = spec["tgt_ws"]
    stack_to_compare = stack[:len(target_stack)] if spec.get("admits_junk", False) else stack
    if len(stack_to_compare) != len(target_stack) or \
            not all(_matches(element, var) for element, var in zip(stack_to_compare, target_stack)):
        mismatching = [element for element, var in zip(stack_to_compare, target_stack) if not _matches(element, var)]
        fail(len(block.greedy_ids), "end", f"final stack {[_describe(e) for e in stack_to_compare]} "
                                           f"does not match {target_stack}", mismatching)
    return memory


def _edge_state(block_list: CFGBlockList, predecessor_id: block_id_T, successor_id: block_id_T,
                out_state: memory_state_T) -> memory_state_T:
    """
    Memory state along the edge predecessor -> successor. The phi values that are handled in memory
    hold the same value as their argument for this edge, so the name of the phi def is added to the
    slots that hold the argument
    """
    successor = block_list.get_block(successor_id)
    if not successor.entries:
        return out_state
    entry_idx = successor.entries.index(predecessor_id)
    renaming: Dict[var_id_T, Set[var_id_T]] = {}
    for phi_instr in successor.phi_instructions():
        phi_def = phi_instr.out_args[0]
        if phi_def in successor.greedy_info.phi_defs_to_solve:
            renaming.setdefault(phi_instr.in_args[entry_idx], set()).add(phi_def)
    if not renaming:
        return out_state
    return {slot: names.union(*(renaming.get(name, set()) for name in names))
            for slot, names in out_state.items()}


def _meet(states: List[memory_state_T]) -> memory_state_T:
    """
    Keeps the slots whose names agree in every state
    """
    common_slots = set(states[0]).intersection(*states[1:])
    met = {}
    for slot in sorted(common_slots):
        names = frozenset.intersection(*(state[slot] for state in states))
        if names:
            met[slot] = names
    return met


def validate_memory_slots(block_list: CFGBlockList) -> None:
    """
    Checks that every memory access introduced by the reparation reads the expected value in all paths
    of the block list. Raises a MemorySlotError describing the first mismatch found
    """
    # None represents a block not reached yet: it does not restrict the state of its successors
    # (optimistic initialization, needed to preserve the values stored before entering a loop)
    out_states: Dict[block_id_T, Optional[memory_state_T]] = {block_id: None for block_id in block_list.blocks}

    def in_state(block_id: block_id_T) -> memory_state_T:
        block = block_list.get_block(block_id)
        incoming = [_edge_state(block_list, predecessor, block_id, out_states[predecessor])
                    for predecessor in block.get_comes_from()
                    if out_states.get(predecessor) is not None]
        if block_id == block_list.start_block or not incoming:
            return {}
        return _meet(incoming)

    # Fixpoint: worklist starting from the entry. A block is only (re)computed once some predecessor has been
    # reached, and its successors are revisited whenever its output state changes. States only decrease
    pending = [block_list.start_block]
    while pending:
        block_id = pending.pop(0)
        new_out = execute_block(block_list.get_block(block_id), in_state(block_id), strict=False)
        if new_out != out_states[block_id]:
            out_states[block_id] = new_out
            for successor in block_list.get_block(block_id).successors:
                if successor in out_states and successor not in pending:
                    pending.append(successor)

    # Final pass: every access must be valid with the stable states. Blocks unreachable from the entry
    # are dead code and are not checked
    for block_id in block_list.blocks:
        if out_states[block_id] is None:
            continue
        try:
            execute_block(block_list.get_block(block_id), in_state(block_id), strict=True)
        except MemorySlotError as error:
            raise MemorySlotError(f"{error}\n{_explain_slot(block_list, block_id, error.slot, out_states)}",
                                  error.block_id, error.slot) from None


def _explain_slot(block_list: CFGBlockList, block_id: block_id_T, slot: Optional[slot_T],
                  out_states: Dict[block_id_T, Optional[memory_state_T]]) -> str:
    """
    Describes the contents of the slot at the end of every predecessor of the failing block, together with
    the blocks that write the slot, to locate the path in which the value is lost
    """
    if slot is None:
        return ""
    lines = [f"Slot {slot} in the block list {block_list.name}:"]
    for predecessor in block_list.get_block(block_id).get_comes_from():
        state = out_states.get(predecessor)
        contents = "not computed" if state is None else set(state.get(slot, frozenset())) or "unknown"
        lines.append(f"  at the end of predecessor {predecessor}: {contents}")
    writers = [other_id for other_id, other in block_list.blocks.items()
               if any(instr_id == f"PUSH {slot}" and position + 1 < len(other.greedy_ids)
                      and other.greedy_ids[position + 1] == "MSTORE"
                      for position, instr_id in enumerate(other.greedy_ids))]
    lines.append(f"  blocks storing into it: {writers}")
    return "\n".join(lines)

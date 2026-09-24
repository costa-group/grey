"""
Liveness of the values stored in memory, needed to decide where the colour (memory slot) of each
value is released in the tree scan. It follows the path exploration of "SSA-based Compiler Design"
(Algorithms 9.9 and 9.10): for each value, the liveness is propagated backwards from its uses along
the CFG predecessors until its (unique) definition is reached. Every value must have a single
definition (see reparation.memory_values).

Phi-functions follow the multiplexing mode (Definition 21.1): the phi defs handled in memory are
defined at the entry of their block (live-in), and the arguments that are copied from memory by the
parallel copies at the end of the predecessors are used at the exit of those predecessors (live-out).

The results are stored in the GreedyInfo of each block:
  - memory_live_in / memory_live_out: the values live at the entry and the exit of the block.
  - last_use: positions in the greedy ids after which a value is no longer live (so its colour can
    be released within the block).
"""
from typing import Dict, List, Set, Tuple

from global_params.types import block_id_T, var_id_T
from parser.cfg_block_list import CFGBlockList
from reparation.utils import extract_value_from_pseudo_instr


def _is_memory_def(instr_id: str) -> bool:
    return instr_id.startswith("VSET") or instr_id.startswith("DUP-VSET")


def phi_copies_from_memory(block_list: CFGBlockList, block_id: block_id_T,
                           memory_values: Set[var_id_T]) -> List[Tuple[block_id_T, var_id_T, var_id_T]]:
    """
    Returns the copies (successor, phi def, argument) performed at the end of the block for the phi defs of
    its successors handled in memory, whose argument is also stored in memory (i.e. read from its slot)
    """
    copies = []
    block = block_list.get_block(block_id)
    for successor_id in block.successors:
        successor = block_list.get_block(successor_id)
        if not successor.entries:
            continue
        entry_idx = successor.entries.index(block_id)
        for phi_instr in successor.phi_instructions():
            phi_def = phi_instr.out_args[0]
            if phi_def in successor.greedy_info.phi_defs_to_solve:
                argument = phi_instr.in_args[entry_idx]
                if argument in memory_values:
                    copies.append((successor_id, phi_def, argument))
    return copies


def compute_memory_liveness(block_list: CFGBlockList) -> None:
    """
    Computes the liveness of the memory values in the block list and stores the live-in, live-out
    and last-use information in the GreedyInfo of each block
    """
    blocks = block_list.blocks

    # Definitions (block of each value) and uses (blocks in which each value is loaded)
    definition_block: Dict[var_id_T, block_id_T] = {}
    phi_defs: Dict[block_id_T, Set[var_id_T]] = {}
    uses: Dict[var_id_T, List[block_id_T]] = {}
    for block_id, block in blocks.items():
        greedy_info = block.greedy_info
        phi_defs[block_id] = set(greedy_info.phi_defs_to_solve)
        for phi_def in greedy_info.phi_defs_to_solve:
            definition_block[phi_def] = block_id
        for instr_id in greedy_info.greedy_ids:
            if _is_memory_def(instr_id):
                definition_block[extract_value_from_pseudo_instr(instr_id)] = block_id
            elif instr_id.startswith("VGET"):
                uses.setdefault(extract_value_from_pseudo_instr(instr_id), []).append(block_id)

    memory_values = set(definition_block)
    live_in: Dict[block_id_T, Set[var_id_T]] = {block_id: set() for block_id in blocks}
    live_out: Dict[block_id_T, Set[var_id_T]] = {block_id: set() for block_id in blocks}

    def up_and_mark(use_block_id: block_id_T, value: var_id_T) -> None:
        """
        Algorithm 9.10 (iterative version, to avoid the recursion limit): propagates the liveness of value
        backwards from the entry of use_block_id until its definition is reached
        """
        pending = [use_block_id]
        while pending:
            block_id = pending.pop()
            # Killed in the block: the definition is reached (the uses in the definition block come after it)
            if definition_block.get(value) == block_id and value not in phi_defs[block_id]:
                continue
            # Propagation already done
            if value in live_in[block_id]:
                continue
            live_in[block_id].add(value)
            # Do not propagate phi definitions
            if value in phi_defs[block_id]:
                continue
            for predecessor_id in blocks[block_id].get_comes_from():
                if value not in live_out[predecessor_id]:
                    live_out[predecessor_id].add(value)
                    pending.append(predecessor_id)

    # Algorithm 9.9: values processed one by one (sorted, to be deterministic)
    phi_uses: Dict[block_id_T, Set[var_id_T]] = {block_id: set() for block_id in blocks}
    for block_id in blocks:
        for _, _, argument in phi_copies_from_memory(block_list, block_id, memory_values):
            phi_uses[block_id].add(argument)

    for value in sorted(memory_values):
        for block_id in dict.fromkeys(uses.get(value, [])):
            up_and_mark(block_id, value)
        for block_id in blocks:
            if value in phi_uses[block_id] and value not in live_out[block_id]:
                # Used in the phi of a direct successor: live-out of the block
                live_out[block_id].add(value)
                if definition_block.get(value) != block_id or value in phi_defs[block_id]:
                    up_and_mark(block_id, value)

    # Phi defs are always live-in of their block (Definition 21.1), even if they are not accessed later
    for block_id in blocks:
        live_in[block_id].update(phi_defs[block_id])

    # Last uses within each block: the last access (use or definition) to a value that is not live-out
    for block_id, block in blocks.items():
        greedy_info = block.greedy_info
        greedy_info.memory_live_in = live_in[block_id]
        greedy_info.memory_live_out = live_out[block_id]
        greedy_info.last_use = set()
        last_access: Dict[var_id_T, int] = {}
        for position, instr_id in enumerate(greedy_info.greedy_ids):
            if _is_memory_def(instr_id) or instr_id.startswith("VGET"):
                last_access[extract_value_from_pseudo_instr(instr_id)] = position
        for value, position in last_access.items():
            if value not in live_out[block_id]:
                greedy_info.last_use.add(position)


def validate_memory_liveness(block_list: CFGBlockList) -> None:
    """
    Debug check: compares the liveness sets computed by path exploration with the classical iterative
    data-flow equations (Sect. 9.2) over the same definitions and uses
    """
    blocks = block_list.blocks
    memory_values = {value for block in blocks.values() for value in block.greedy_info.phi_defs_to_solve}
    for block in blocks.values():
        for instr_id in block.greedy_info.greedy_ids:
            if _is_memory_def(instr_id):
                memory_values.add(extract_value_from_pseudo_instr(instr_id))

    defs, upward_exposed, phi_defs, phi_uses = {}, {}, {}, {}
    for block_id, block in blocks.items():
        greedy_info = block.greedy_info
        defs[block_id], upward_exposed[block_id] = set(), set()
        for instr_id in greedy_info.greedy_ids:
            value = extract_value_from_pseudo_instr(instr_id)
            if _is_memory_def(instr_id):
                defs[block_id].add(value)
            elif instr_id.startswith("VGET") and value not in defs[block_id]:
                upward_exposed[block_id].add(value)
        phi_defs[block_id] = set(greedy_info.phi_defs_to_solve)
        phi_uses[block_id] = {argument for _, _, argument in
                              phi_copies_from_memory(block_list, block_id, memory_values)}

    live_in = {block_id: set() for block_id in blocks}
    live_out = {block_id: set() for block_id in blocks}
    changed = True
    while changed:
        changed = False
        for block_id, block in blocks.items():
            new_live_out = set(phi_uses[block_id])
            for successor_id in block.successors:
                new_live_out |= live_in[successor_id] - phi_defs[successor_id]
            new_live_in = phi_defs[block_id] | upward_exposed[block_id] | (new_live_out - defs[block_id])
            if new_live_out != live_out[block_id] or new_live_in != live_in[block_id]:
                live_out[block_id], live_in[block_id] = new_live_out, new_live_in
                changed = True

    for block_id, block in blocks.items():
        # Only the values live at some point are considered by the path exploration
        assert block.greedy_info.memory_live_in == live_in[block_id], \
            f"Live-in of {block_id} differs: {block.greedy_info.memory_live_in} vs {live_in[block_id]}"
        assert block.greedy_info.memory_live_out == live_out[block_id], \
            f"Live-out of {block_id} differs: {block.greedy_info.memory_live_out} vs {live_out[block_id]}"

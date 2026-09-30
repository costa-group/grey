"""
Function-level passes run before grey's inliner, mirroring the ones solc runs before its own inliner.

solc's Yul optimiser always runs the EquivalentFunctionCombiner (`v`) right before the FullInliner (`i`), and prunes
unused parameters (`p`) before both. grey adds one more inlining step (every function called from a single place is
inlined, see function_inlining), but the Yul CFG it receives comes after the last `v`: functions that became
equivalent later (or that only differ in an unused parameter, which `p` did not remove) are still separate. solc
keeps them as functions and its block deduplicator merges their identical code, whereas grey would inline each copy
into a different caller, where the copies can no longer be merged. These passes do what `p` and `v` do, on grey's CFG:

- prune_unused_arguments_cfg: removes the arguments that a function never uses from the function and from all its
  calls (the value computed by the caller is simply not passed);
- combine_equivalent_functions_cfg: functions whose bodies are equal up to the renaming of their variables are
  combined: the calls are redirected to one of them and the others are removed. As in solc, the calls inside the
  bodies are compared by the name of the callee, so callers of combined functions may become equivalent afterwards:
  the pass is repeated until nothing changes (solc stops after the 4 occurrences of `v` in its sequence).

Both run after the variables are renamed and before the inliner, when the calls only carry their real arguments
(no return labels nor tags yet).
"""
import logging
from typing import Dict, List, Optional, Set, Tuple

from global_params.types import block_id_T, var_id_T, function_name_T
from parser.cfg import CFG
from parser.cfg_block_list import CFGBlockList
from parser.cfg_function import CFGFunction
from parser.cfg_object import CFGObject


def _traversal_order(block_list: CFGBlockList) -> List[block_id_T]:
    """
    Blocks reachable from the start block in depth-first preorder, visiting the successors in their order
    (jumps to, falls to), so that equivalent functions list corresponding blocks in the same positions
    """
    order, visited, stack = [], set(), [block_list.start_block]
    while stack:
        block_id = stack.pop()
        if block_id in visited:
            continue
        visited.add(block_id)
        order.append(block_id)
        # Reversed, so that the first successor is visited first
        stack.extend(reversed(block_list.get_block(block_id).successors))
    return order


def function_key(cfg_function: CFGFunction) -> Optional[Tuple]:
    """
    Representation of the body of a function up to the renaming of its variables and blocks: blocks are numbered by
    traversal order, the arguments by position, the values defined in the function by definition order (in traversal
    order), and constants are kept. Each block contributes its jump type, its successors, its phi-functions (with the
    number of the predecessor of each argument), its instructions (operation, literal arguments, builtin, inputs and
    outputs; calls by the name of the callee), its condition and the values it returns. Two functions with the same
    key are equivalent. Returns None if the function uses a value that is neither an argument nor defined in it
    """
    block_list = cfg_function.blocks
    order = _traversal_order(block_list)
    block_number = {block_id: position for position, block_id in enumerate(order)}

    # Definitions first: phi-functions of loop headers use values defined in blocks visited later
    value_number: Dict[var_id_T, Tuple[str, int]] = {argument: ("a", position)
                                                     for position, argument in enumerate(cfg_function.arguments)}
    for block_id in order:
        for instruction in block_list.get_block(block_id).get_instructions():
            for out_arg in instruction.get_out_args():
                value_number.setdefault(out_arg, ("l", len(value_number)))

    def use(value: var_id_T):
        if value.startswith("0x"):
            return "c", value
        if value not in value_number:
            raise KeyError(value)
        return value_number[value]

    try:
        blocks_key = []
        for block_id in order:
            block = block_list.get_block(block_id)
            phis = tuple((use(phi.get_out_args()[0]),
                          tuple((block_number.get(entry, -1), use(argument))
                                for entry, argument in zip(block.entries, phi.get_in_args())))
                         for phi in block.phi_instructions())
            instructions = tuple((instruction.get_op_name(),
                                  tuple(instruction.get_literal_args() or ()),
                                  instruction.get_builtin_op(),
                                  tuple(use(in_arg) for in_arg in instruction.get_in_args()),
                                  tuple(use(out_arg) for out_arg in instruction.get_out_args()))
                                 for instruction in block.instructions_without_phi_functions())
            condition = use(block.get_condition()) if block.get_condition() is not None else None
            blocks_key.append((block.get_jump_type(), tuple(block_number.get(successor, -1)
                                                            for successor in block.successors),
                               phis, instructions, condition))
    except KeyError:
        return None
    return len(cfg_function.arguments), tuple(blocks_key)


def _block_lists(cfg_object: CFGObject) -> List[CFGBlockList]:
    return [cfg_object.blocks] + [cfg_object.functions[name].blocks for name in sorted(cfg_object.functions)]


def _redirect_calls(cfg_object: CFGObject, replacements: Dict[function_name_T, function_name_T]) -> None:
    """
    Replaces the calls to the keys of replacements by calls to their values, in every block list of the object
    """
    for block_list in _block_lists(cfg_object):
        for block in block_list.blocks.values():
            for instruction in block.get_instructions():
                if instruction.get_op_name() in replacements:
                    instruction.op = replacements[instruction.get_op_name()]
            if block.function_calls & replacements.keys():
                block.function_calls = {replacements.get(name, name) for name in block.function_calls}


def combine_equivalent_functions_object(cfg_object: CFGObject) -> int:
    """
    Combines the equivalent functions of the object (see the module docstring). Returns the number of functions removed
    """
    removed = 0
    while True:
        representatives: Dict[Tuple, function_name_T] = dict()
        replacements: Dict[function_name_T, function_name_T] = dict()
        # Sorted, so that the representative (the first name) does not depend on the order of the dict
        for name in sorted(cfg_object.functions):
            key = function_key(cfg_object.functions[name])
            if key is None:
                continue
            if key in representatives:
                replacements[name] = representatives[key]
            else:
                representatives[key] = name
        if not replacements:
            return removed
        _redirect_calls(cfg_object, replacements)
        for name in sorted(replacements):
            logging.info(f"Combining function {name} with {replacements[name]}")
            cfg_object.functions.pop(name)
        removed += len(replacements)


def _used_values(cfg_function: CFGFunction) -> Set[var_id_T]:
    used = set()
    for block in cfg_function.blocks.blocks.values():
        for instruction in block.get_instructions():
            used.update(instruction.get_in_args())
        if block.get_condition() is not None:
            used.add(block.get_condition())
    return used


def prune_unused_arguments_object(cfg_object: CFGObject) -> int:
    """
    Removes the arguments that each function of the object never uses, from the function and from its calls. The
    arguments are stored in reverse order with respect to the inputs of the call instructions (argument k is input
    len - 1 - k of the call, see InlineFunction). Returns the number of arguments removed
    """
    removed = 0
    unused_positions: Dict[function_name_T, List[int]] = dict()
    for name in sorted(cfg_object.functions):
        cfg_function = cfg_object.functions[name]
        used = _used_values(cfg_function)
        positions = [position for position, argument in enumerate(cfg_function.arguments) if argument not in used]
        if positions:
            unused_positions[name] = positions
            cfg_function.arguments = [argument for position, argument in enumerate(cfg_function.arguments)
                                      if position not in positions]
            removed += len(positions)
            logging.info(f"Pruning {len(positions)} unused arguments of {name}")

    if unused_positions:
        for block_list in _block_lists(cfg_object):
            for block in block_list.blocks.values():
                for instruction in block.get_instructions():
                    positions = unused_positions.get(instruction.get_op_name())
                    if positions is None:
                        continue
                    num_inputs = len(instruction.in_args)
                    removed_inputs = {num_inputs - 1 - position for position in positions}
                    instruction.in_args = [in_arg for index, in_arg in enumerate(instruction.in_args)
                                           if index not in removed_inputs]
    return removed


def _apply_to_objects(cfg: CFG, method) -> int:
    total = 0
    for cfg_object in cfg.objectCFG.values():
        total += method(cfg_object)
        sub_object = cfg_object.get_subobject()
        if sub_object is not None:
            total += _apply_to_objects(sub_object, method)
    return total


def prune_unused_arguments_cfg(cfg: CFG) -> int:
    return _apply_to_objects(cfg, prune_unused_arguments_object)


def combine_equivalent_functions_cfg(cfg: CFG) -> int:
    return _apply_to_objects(cfg, combine_equivalent_functions_object)

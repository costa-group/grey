"""
Per-function calling convention (--call-convention). By default (fixed), a call jumps with [jd, arg1, ..., argn, rd]
on top of the stack (jd: tag of the function, rd: return label) and a function returns with [rd, ret1, ..., retm],
following the order of the Yul arguments and return values, as solc does (QUESTIONS Q21).

As all the callers of a function are known, the order of its arguments and return values can be chosen from the
code of the callee instead (h1 of the paper, Def. 3.4), and the callers adapt to it:
- args: the arguments are ordered by their next use in the callee, the ones used sooner closer to the top;
- orders: besides, the return values are ordered by their definition point in the callee, the ones introduced
  earlier deeper, as they are produced before the others.
The return label stays below the arguments, as in the fixed convention.

The convention is applied after the liveness analysis (which is set-based, and hence not affected by the order) and
before generating the layouts, by permuting the arguments of the function, the in_args/out_args of every call and
the in_args of every functionReturn.
"""
import math
from collections import deque
from typing import Dict, List, Optional, Tuple

from global_params.types import var_id_T, block_id_T, component_name_T
from parser.cfg_object import CFGObject
from parser.cfg_block_list import CFGBlockList
from parser.cfg_instruction import CFGInstruction
from liveness.liveness_analysis import LivenessAnalysisInfoSSA


class FunctionConvention:
    """
    Calling convention of a function: positions are top-first and refer to the Yul order of the arguments (as in the
    in_args of the calls, without jd and rd) and of the return values (as in the in_args of functionReturn without rd
    and in the out_args of the calls)
    """

    def __init__(self, function_name: str, argument_permutation: List[int], return_permutation: List[int]):
        self.function_name = function_name
        # New position i holds the argument with Yul position argument_permutation[i]
        self.argument_permutation = argument_permutation
        # New position k holds the return value with Yul position return_permutation[k]
        self.return_permutation = return_permutation

    def arguments(self, values: List[var_id_T]) -> List[var_id_T]:
        return [values[position] for position in self.argument_permutation]

    def returned_values(self, values: List[var_id_T]) -> List[var_id_T]:
        return [values[position] for position in self.return_permutation]

    def __repr__(self):
        return f"FunctionConvention({self.function_name}, args={self.argument_permutation}, " \
               f"returns={self.return_permutation})"


def block_order(block_list: CFGBlockList) -> Dict[block_id_T, Tuple[int, int]]:
    """
    Breadth-first traversal from the start block: for each reachable block, its distance in blocks from the start and
    the order in which it was discovered
    """
    start_block = block_list.start_block
    order = {start_block: (0, 0)}
    pending = deque([start_block])
    while pending:
        block_id = pending.popleft()
        distance = order[block_id][0]
        for successor in block_list.get_block(block_id).successors:
            if successor not in order and successor in block_list.blocks:
                order[successor] = (distance + 1, len(order))
                pending.append(successor)
    return order


def first_uses(block_list: CFGBlockList, order: Dict[block_id_T, Tuple[int, int]]) \
        -> Dict[var_id_T, Tuple[int, int, int]]:
    """
    For each variable, its closest use from the start: (distance of the block, instruction index, argument index).
    The blocks are visited in breadth-first order (the insertion order of the dict), so the first use found is the
    closest one
    """
    uses = dict()
    for block_id, (distance, _) in order.items():
        for instruction_idx, instruction in enumerate(block_list.get_block(block_id).get_instructions()):
            for argument_idx, in_arg in enumerate(instruction.get_in_args()):
                if in_arg not in uses:
                    uses[in_arg] = (distance, instruction_idx, argument_idx)
    return uses


def definition_points(block_list: CFGBlockList, order: Dict[block_id_T, Tuple[int, int]],
                      arguments_bottom_first: List[var_id_T]) -> Dict[var_id_T, Tuple]:
    """
    Definition point of each variable of the function, comparable as tuples (the smaller, the earlier):
    - the arguments, (-1, 0, 0, height in the entry stack): the deeper the argument, the earlier;
    - the other variables, (distance of the block, discovery order of the block, instruction index,
      -position in the outputs): the deeper the output, the earlier
    """
    points = {argument: (-1, 0, 0, height) for height, argument in enumerate(arguments_bottom_first)}
    for block_id, (distance, discovery) in order.items():
        for instruction_idx, instruction in enumerate(block_list.get_block(block_id).get_instructions()):
            for output_idx, out_arg in enumerate(instruction.get_out_args()):
                points[out_arg] = (distance, discovery, instruction_idx, -output_idx)
    return points


def argument_order(arguments: List[var_id_T], live_in: set, uses: Dict[var_id_T, Tuple[int, int, int]]) -> List[int]:
    """
    Order (top-first) of the arguments, given in Yul order, as the list of their Yul positions. The arguments that are
    not live at the entry are placed on top (they are popped first); the rest are ordered by their closest use
    (distance in blocks, instruction, argument position). Ties keep the Yul order
    """
    def key(position: int) -> Tuple:
        argument = arguments[position]
        if argument not in live_in:
            return -1, 0, 0, position
        return uses.get(argument, (math.inf, 0, 0)) + (position,)

    return sorted(range(len(arguments)), key=key)


def return_order(returned_per_block: List[List[var_id_T]], points: Dict[var_id_T, Tuple]) -> List[int]:
    """
    Order (top-first) of the return values, as the list of their Yul positions. In each return block, the values are
    ranked by their definition point (the earliest one gets rank 0). The ranks are added over the return blocks, and
    the values with the highest total are placed on top (the latest introduced), so the earliest introduced ones end
    up at the bottom. Constants (and unknown values) are considered the latest, as they are pushed at the end. Ties
    keep the Yul order
    """
    num_returns = len(returned_per_block[0]) if returned_per_block else 0
    rank_sum = [0] * num_returns
    latest = (math.inf, 0, 0, 0)
    for returned_values in returned_per_block:
        # Ties in the definition point keep the Yul order: the value with the lowest position is placed on top,
        # i.e. it gets the highest rank
        bottom_first = sorted(range(num_returns),
                              key=lambda position: (points.get(returned_values[position], latest), -position))
        for rank, position in enumerate(bottom_first):
            rank_sum[position] += rank
    bottom_first = sorted(range(num_returns), key=lambda position: (rank_sum[position], -position))
    return list(reversed(bottom_first))


def _return_instruction(block) -> CFGInstruction:
    return_instruction = block.get_instructions()[-1]
    assert return_instruction.get_op_name() == "functionReturn", \
        f"Last instruction of the return block {block.block_id} is not a functionReturn"
    return return_instruction


def compute_function_convention(function_name: str, cfg_function, live_in: set, mode: str) -> FunctionConvention:
    """
    Computes the convention ("args" or "orders") of a function from its code. The arguments of the function
    (cfg_function.arguments) are stored bottom-first, with rd as the first element if the function returns (see
    jump_insertion)
    """
    block_list = cfg_function.blocks
    return_blocks = block_list.function_return_blocks
    yul_arguments = list(reversed(cfg_function.arguments))
    if return_blocks:
        yul_arguments.pop()
    returned_per_block = [_return_instruction(block_list.get_block(block_id)).get_in_args()[1:]
                          for block_id in return_blocks]
    num_returns = len(returned_per_block[0]) if returned_per_block else 0

    order = block_order(block_list)
    argument_permutation = argument_order(yul_arguments, live_in, first_uses(block_list, order))
    convention = FunctionConvention(function_name, argument_permutation, list(range(num_returns)))

    if mode == "orders" and num_returns > 1:
        # The definition points of the arguments refer to their position in the new entry stack
        new_arguments_bottom_first = list(reversed(convention.arguments(yul_arguments)))
        points = definition_points(block_list, order, new_arguments_bottom_first)
        convention.return_permutation = return_order(returned_per_block, points)
    return convention


def apply_function_convention(convention: FunctionConvention, cfg_function, call_sites: List[CFGInstruction]) -> None:
    """
    Permutes the arguments of the function, the in_args of its functionReturn instructions and the in_args/out_args
    of the calls according to the convention
    """
    block_list = cfg_function.blocks
    yul_arguments = list(reversed(cfg_function.arguments))
    return_label = [yul_arguments.pop()] if block_list.function_return_blocks else []
    num_arguments = len(yul_arguments)

    cfg_function.arguments = list(reversed(convention.arguments(yul_arguments) + return_label))

    for block_id in block_list.function_return_blocks:
        return_instruction = _return_instruction(block_list.get_block(block_id))
        in_args = return_instruction.get_in_args()
        return_instruction.in_args = [in_args[0]] + convention.returned_values(in_args[1:])

    for call in call_sites:
        # [jd, arg1, ..., argn] + [rd] if the call returns (see sub_block_generation.modify_block_list_split)
        in_args = call.get_in_args()
        assert len(in_args) in [num_arguments + 1, num_arguments + 2], \
            f"Unexpected number of arguments in the call {call}"
        call.in_args = [in_args[0]] + convention.arguments(in_args[1:num_arguments + 1]) + in_args[num_arguments + 1:]
        call.out_args = convention.returned_values(call.get_out_args())


def _call_sites(cfg_object: CFGObject) -> Dict[str, List[CFGInstruction]]:
    """
    Calls to each function of the object (they are the split instructions of the blocks that perform them)
    """
    call_sites = {function_name: [] for function_name in cfg_object.functions}
    block_lists = [cfg_object.blocks] + [cfg_function.blocks for cfg_function in cfg_object.functions.values()]
    for block_list in block_lists:
        for block in block_list.blocks.values():
            split_instruction = block.split_instruction
            if split_instruction is not None and split_instruction.get_op_name() in call_sites:
                call_sites[split_instruction.get_op_name()].append(split_instruction)
    return call_sites


def apply_calling_conventions(cfg_object: CFGObject,
                              liveness_per_component: Dict[component_name_T, Dict[block_id_T, LivenessAnalysisInfoSSA]],
                              mode: str, selected: Optional[set] = None) -> Dict[str, FunctionConvention]:
    """
    Computes and applies the convention ("args" or "orders") of every function in the object. All the conventions
    are computed before applying any of them, so that they only depend on the original code
    """
    conventions = dict()
    for function_name, cfg_function in cfg_object.functions.items():
        # With a selection (--call-convention best), the other functions keep the Yul order
        if selected is not None and function_name not in selected:
            continue
        start_block = cfg_function.blocks.start_block
        live_in = liveness_per_component[function_name][start_block].in_state.live_vars
        conventions[function_name] = compute_function_convention(function_name, cfg_function, live_in, mode)
    call_sites = _call_sites(cfg_object)
    for function_name, convention in conventions.items():
        apply_function_convention(convention, cfg_object.functions[function_name], call_sites[function_name])
    return conventions


def _matches(spec_stack: List[var_id_T], expected: List[var_id_T], allow_forgotten: bool,
             defined_in_block: Optional[set] = None) -> bool:
    """
    Whether the stack of a specification starts with the expected elements. The constants (and "bottom") of the
    expected stack are replaced by an alias in the specification, and so are the values computed in the block by
    equivalent instructions (see CFGBlock.build_spec), so their positions are not compared (the greedy validation
    checks them). If allow_forgotten is set, the specification may contain only a prefix of the expected elements:
    the dead elements at the bottom are forgotten in blocks that admit junk (see forget_values)
    """
    defined_in_block = defined_in_block if defined_in_block is not None else set()
    if allow_forgotten:
        expected = expected[:len(spec_stack)]
    if len(spec_stack) < len(expected):
        return False
    return all(expected_element.startswith("0x") or expected_element == "bottom" or
               expected_element in defined_in_block or spec_element == expected_element
               for spec_element, expected_element in zip(spec_stack, expected))


def _defined_in_block(block) -> set:
    return {out_arg for instruction in block.get_instructions() for out_arg in instruction.get_out_args()}


def validate_calling_conventions(cfg_object: CFGObject) -> None:
    """
    Checks that the specifications of the callers and the callees agree on the stacks at the calls and returns:
    the entry block of a function starts with its arguments, every return block ends with the in_args of its
    functionReturn, every block that calls a function ends with the in_args of the call on top and its continuation
    starts with the out_args of the call on top. Applies to every convention (it only uses the instructions)
    """
    for function_name, cfg_function in cfg_object.functions.items():
        block_list = cfg_function.blocks
        entry_stack = list(reversed(cfg_function.arguments))
        start_spec = block_list.get_block(block_list.start_block).spec
        assert _matches(start_spec["src_ws"], entry_stack, True) and \
               len(start_spec["src_ws"]) <= len(entry_stack), \
            f"Entry of {function_name}: {start_spec['src_ws']} does not match the arguments {entry_stack}"

        for block_id in block_list.function_return_blocks:
            block = block_list.get_block(block_id)
            in_args = _return_instruction(block).get_in_args()
            assert _matches(block.spec["tgt_ws"], in_args, False, _defined_in_block(block)) and \
                   len(block.spec["tgt_ws"]) == len(in_args), \
                f"Return block {block_id} of {function_name}: {block.spec['tgt_ws']} does not match {in_args}"

    call_sites = _call_sites(cfg_object)
    block_lists = [cfg_object.blocks] + [cfg_function.blocks for cfg_function in cfg_object.functions.values()]
    for block_list in block_lists:
        for block in block_list.blocks.values():
            call = block.split_instruction
            if call is None or call.get_op_name() not in call_sites:
                continue
            callee = cfg_object.functions[call.get_op_name()]
            in_args = call.get_in_args()
            assert len(in_args) == len(callee.arguments) + 1 or \
                   (len(in_args) == len(callee.arguments) and len(callee.blocks.function_return_blocks) > 0), \
                f"Call {call} in {block.block_id} does not match the arguments of {call.get_op_name()}"
            assert _matches(block.spec["tgt_ws"], in_args, False, _defined_in_block(block)), \
                f"Call block {block.block_id}: {block.spec['tgt_ws']} does not start with {in_args}"
            out_args = call.get_out_args()
            for successor_id in block.successors:
                successor_spec = block_list.get_block(successor_id).spec
                assert _matches(successor_spec["src_ws"], out_args, True), \
                    f"Continuation {successor_id} of {block.block_id}: {successor_spec['src_ws']} " \
                    f"does not start with {out_args}"


def candidate_functions(cfg_object: CFGObject,
                        liveness_per_component: Dict[component_name_T, Dict[block_id_T, LivenessAnalysisInfoSSA]],
                        mode: str) -> set:
    """
    Functions whose convention in the given mode differs from the Yul order (the only ones it can change)
    """
    candidates = set()
    for function_name, cfg_function in cfg_object.functions.items():
        start_block = cfg_function.blocks.start_block
        live_in = liveness_per_component[function_name][start_block].in_state.live_vars
        convention = compute_function_convention(function_name, cfg_function, live_in, mode)
        if convention.argument_permutation != list(range(len(convention.argument_permutation))) or \
                convention.return_permutation != list(range(len(convention.return_permutation))):
            candidates.add(function_name)
    return candidates


def undo_calling_conventions(cfg_object: CFGObject, conventions: Dict[str, FunctionConvention]) -> None:
    """
    Undoes the conventions applied to the functions of the object (applies the inverse permutations)
    """
    def inverse(permutation: List[int]) -> List[int]:
        result = [0] * len(permutation)
        for new_position, old_position in enumerate(permutation):
            result[old_position] = new_position
        return result

    call_sites = _call_sites(cfg_object)
    for function_name, convention in conventions.items():
        inverse_convention = FunctionConvention(function_name, inverse(convention.argument_permutation),
                                                inverse(convention.return_permutation))
        apply_function_convention(inverse_convention, cfg_object.functions[function_name], call_sites[function_name])

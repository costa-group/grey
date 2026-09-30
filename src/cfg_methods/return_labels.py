"""
Hoists the PUSH [tag] of the return labels of function calls. After splitting the blocks (see
sub_block_generation.split_blocks_cfg), the return label of a call is pushed in the sub-block that performs the call,
so every copy of a piece of code that ends up calling a function contains a different constant, and solc cannot
deduplicate the copies. solc instead treats the return label as a stack slot that is pushed where all the paths
towards the call are shared. We do the same: the push is moved to the highest dominator of the call block from which
every path reaches the call (the call post-dominates it), within the same loop. The label then becomes a variable
defined in that block and used in the call, handled by the layout generation and the greedy as any other one.
"""
import collections
import logging
from typing import Dict, List, Optional, Set, Tuple
import networkx as nx
from global_params.types import block_id_T, var_id_T
from parser.cfg import CFG
from parser.cfg_block import CFGBlock
from parser.cfg_block_list import CFGBlockList
import global_params.constants as constants
from liveness.liveness_analysis import construct_analysis_info_from_cfgblocklist, liveness_analysis_from_vertices

VIRTUAL_EXIT = "__virtual_exit__"

# Room left for the computations when checking the stack pressure of a hoisted label
PRESSURE_MARGIN = 2


def hoist_return_labels_cfg(cfg: CFG, strategy: str = "shared") -> int:
    """
    Hoists the return labels in every block list of the CFG (objects, functions and subobjects).
    Returns the number of labels hoisted
    """
    num_hoisted = 0
    for cfg_object in cfg.objectCFG.values():
        # Calls to functions that solc's inliner will inline keep their return label: once the body is inlined at
        # the call site, CSE only turns its return jump into a direct jump if the label is pushed in the same block
        inlined = inline_candidates({function_name: cfg_function.blocks
                                     for function_name, cfg_function in cfg_object.functions.items()})
        function_names = {function_name for function_name in cfg_object.functions if function_name not in inlined}
        block_lists = [cfg_object.blocks] + [cfg_function.blocks for cfg_function in cfg_object.functions.values()]
        # solc deduplicates the whole assembly of an object, so the copies are searched in all its block lists
        shared = shared_blocks(block_lists, function_names) if strategy == "shared" else set()
        for block_list in block_lists:
            num_hoisted += hoist_return_labels_block_list(block_list, function_names, strategy, shared)

        sub_object = cfg_object.get_subobject()
        if sub_object is not None:
            num_hoisted += hoist_return_labels_cfg(sub_object, strategy)
    return num_hoisted


def inline_candidates(functions: Dict[str, CFGBlockList]) -> Set[str]:
    """
    Functions that solc's legacy inliner can inline at their call sites: the body is a single straight-line block
    that ends by returning to the caller. The inliner is applied repeatedly, so a function whose body is a chain of
    blocks (no branches) split only at calls to inline candidates becomes a single block once they are inlined,
    and is a candidate as well (computed as a fixpoint)
    """
    def straight_chain_calls(block_list: CFGBlockList) -> Optional[Set[str]]:
        # The callees of a straight chain ending in the function return, or None if it is not such a chain
        callees, current, visited = set(), block_list.get_block(block_list.start_block), set()
        while current.get_jump_type() != "FunctionReturn":
            if current.block_id in visited or len(current.successors) != 1:
                return None
            visited.add(current.block_id)
            split_instruction = current.split_instruction
            if split_instruction is None or split_instruction.get_op_name() not in functions:
                return None
            callees.add(split_instruction.get_op_name())
            current = block_list.get_block(current.successors[0])
        # Every block of the function must be in the chain
        return callees if len(visited) + 1 == len(block_list.blocks) else None

    chain_callees = {function_name: straight_chain_calls(block_list) for function_name, block_list in functions.items()}
    candidates = set()
    changed = True
    while changed:
        changed = False
        for function_name, callees in chain_callees.items():
            if function_name not in candidates and callees is not None and callees <= candidates:
                candidates.add(function_name)
                changed = True
    return candidates


def _canonical_instructions(block: CFGBlock) -> Tuple:
    """
    Instructions of the block (without phi-functions and PUSH [tag]s) with the arguments canonicalised: constants
    are kept, tags are abstracted, values defined in the block are numbered by definition order and the remaining
    ones by first use
    """
    local_vars: Dict[var_id_T, int] = dict()
    input_vars: Dict[var_id_T, int] = dict()
    tag_vars = {instruction.get_out_args()[0] for instruction in block.get_instructions()
                if instruction.get_op_name() == "PUSH [tag]"}

    def canonical(argument: var_id_T) -> Tuple:
        if argument.startswith("0x"):
            return "c", argument
        if argument in tag_vars or argument.isdigit():
            return ("tag",)
        if argument in local_vars:
            return "l", local_vars[argument]
        return "i", input_vars.setdefault(argument, len(input_vars))

    instructions = []
    for instruction in block.get_instructions():
        if instruction.get_op_name() in ("PhiFunction", "PUSH [tag]"):
            continue
        arguments = tuple(canonical(argument) for argument in instruction.get_in_args())
        for out_arg in instruction.get_out_args():
            local_vars[out_arg] = len(local_vars)
        literal_args = tuple(instruction.get_literal_args()) if instruction.get_literal_args() is not None else ()
        instructions.append((instruction.get_op_name(), literal_args, arguments, len(instruction.get_out_args())))
    return tuple(instructions)


def shared_blocks(block_lists: List[CFGBlockList], function_names: Set[str]) -> Set[Tuple[str, block_id_T]]:
    """
    Blocks (identified by block list name and id) whose structural key appears at least twice among the block lists.
    The key contains the jump type, the canonical instructions and the keys of the successors (recursively), except
    for the continuation of a call with a return label: once the label is hoisted, the call no longer refers to it.
    Blocks sharing a key can be deduplicated by solc if they get the same stack layouts
    """
    # Keys are interned: each distinct key gets an integer id, and the successors are referenced by their ids.
    # Otherwise the keys would be nested tuples whose hashing unfolds the CFG, exponential with many joins
    keys: Dict[Tuple[str, block_id_T], int] = dict()
    key_ids: Dict[Tuple, int] = dict()
    for block_list in block_lists:
        blocks = block_list.blocks

        def successors_of(block_id):
            block = blocks[block_id]
            return [] if return_label(block, function_names) is not None else list(block.successors)

        # Iterative post-order, so that long chains do not exceed the recursion limit. Blocks reached again while
        # in progress (cycles) get a placeholder key (-1)
        in_progress = set()
        for root in blocks:
            if (block_list.name, root) in keys:
                continue
            stack = [(root, False)]
            while stack:
                block_id, expanded = stack.pop()
                node = (block_list.name, block_id)
                if node in keys:
                    continue
                if expanded:
                    in_progress.discard(block_id)
                    successor_keys = tuple(keys.get((block_list.name, successor), -1)
                                           for successor in successors_of(block_id))
                    key = (blocks[block_id].get_jump_type(), _canonical_instructions(blocks[block_id]),
                           successor_keys)
                    keys[node] = key_ids.setdefault(key, len(key_ids))
                    continue
                if block_id in in_progress:
                    continue
                in_progress.add(block_id)
                stack.append((block_id, True))
                for successor in successors_of(block_id):
                    if (block_list.name, successor) not in keys and successor not in in_progress:
                        stack.append((successor, False))

    counts = collections.Counter(keys.values())
    return {node for node, key in keys.items() if counts[key] > 1}


def return_label(block: CFGBlock, function_names: Set[str]) -> Optional[Tuple[int, var_id_T]]:
    """
    If the block ends with a call to a function whose return label is pushed in the block, returns the index of
    the PUSH [tag] instruction and the label. The return label is the last argument of the call (the callee tag
    is the first one)
    """
    split_instruction = block.split_instruction
    if split_instruction is None or split_instruction.get_op_name() not in function_names:
        return None
    in_args = split_instruction.get_in_args()
    if len(in_args) < 2:
        return None
    label = in_args[-1]
    for idx, instruction in enumerate(block.get_instructions()):
        if instruction.get_op_name() == "PUSH [tag]" and instruction.get_out_args() == [label]:
            return idx, label
    return None


def _innermost_loops(loop_nesting_forest: nx.DiGraph) -> Dict[block_id_T, block_id_T]:
    """
    Innermost loop (identified by its header) of every block inside a loop. A header belongs to its own loop
    """
    innermost = dict()
    for block_id in loop_nesting_forest.nodes:
        if loop_nesting_forest.out_degree(block_id) > 0:
            innermost[block_id] = block_id
        else:
            predecessors = list(loop_nesting_forest.predecessors(block_id))
            innermost[block_id] = predecessors[0] if predecessors else block_id
    return innermost


def _liveness_sizes(block_list: CFGBlockList) -> Tuple[Dict[block_id_T, int], Dict[block_id_T, int]]:
    """
    Number of live variables at the entry and at the exit of each block (liveness analysis of the block list)
    """
    info = construct_analysis_info_from_cfgblocklist(block_list)
    results = liveness_analysis_from_vertices(info["block_info"], info["terminal_blocks"]).get_analysis_results()
    return ({block_id: len(result.in_state.live_vars) for block_id, result in results.items()},
            {block_id: len(result.out_state.live_vars) for block_id, result in results.items()})


def _dominated_blocks(immediate_dominators: Dict[block_id_T, block_id_T], start_block: block_id_T) \
        -> Dict[block_id_T, List[block_id_T]]:
    """
    Blocks dominated by each block (including itself), from the immediate dominators
    """
    children = collections.defaultdict(list)
    for block_id, dominator in immediate_dominators.items():
        if block_id != start_block:
            children[dominator].append(block_id)
    dominated = dict()

    def collect(block_id):
        result, pending = [], [block_id]
        while pending:
            current = pending.pop()
            result.append(current)
            pending.extend(children[current])
        return result

    for block_id in immediate_dominators:
        dominated[block_id] = collect(block_id)
    return dominated


def _immediate_post_dominators(graph: nx.DiGraph) -> Dict[block_id_T, block_id_T]:
    """
    Immediate post-dominators, computed as the dominators of the reversed graph from a virtual exit connected to
    every block without successors
    """
    reversed_graph = graph.reverse(copy=True)
    reversed_graph.add_node(VIRTUAL_EXIT)
    for block_id in graph.nodes:
        if graph.out_degree(block_id) == 0:
            reversed_graph.add_edge(VIRTUAL_EXIT, block_id)
    return nx.immediate_dominators(reversed_graph, VIRTUAL_EXIT)


def _shared_target(call_block_id: block_id_T, start_block: block_id_T, immediate_dominators: Dict,
                   post_dominates, innermost: Dict, is_shared) -> List[block_id_T]:
    """
    Candidate targets of the "shared" strategy, from the preferred one to the lowest: climbing the dominator tree
    from the call block while the dominators are shared (and post-dominated by the call, in the same loop), the first
    non-shared dominator is preferred. If the climb stops before (post-dominance, loop or start block), the highest
    shared block reached. The following candidates are the blocks crossed, downwards (used when the preferred one
    would exceed the stack pressure). If the call block is not shared, there is no candidate
    """
    if not is_shared(call_block_id):
        return []
    path, current = [], call_block_id
    while current != start_block:
        candidate = immediate_dominators[current]
        if not post_dominates(call_block_id, candidate) or innermost.get(candidate) != innermost.get(call_block_id):
            break
        path.append(candidate)
        if not is_shared(candidate):
            break
        current = candidate
    return list(reversed(path))


def hoist_return_labels_block_list(block_list: CFGBlockList, function_names: Set[str], strategy: str = "shared",
                                   shared: Optional[Set[Tuple[str, block_id_T]]] = None) -> int:
    """
    Moves the PUSH [tag] of the return label of each call to a dominator D of the call block C such that C
    post-dominates D and both have the same innermost loop. With the "branch" strategy, D is the nearest such
    dominator that is a branch point (several successors): the paths from it that reach the call become independent
    of the call site. If there is none, the label is not moved. With the "max" strategy, D is the highest such
    dominator (the label can then live for long, increasing the stack pressure). With the "shared" strategy (the
    default), D is the lowest non-shared block above the shared blocks that lead to the call (see shared_blocks):
    the shared part becomes independent of the call site, and the label only lives across it. Returns the number of
    labels hoisted
    """
    shared = shared if shared is not None else set()

    def is_shared(block_id: block_id_T) -> bool:
        return (block_list.name, block_id) in shared

    block_list.graph = None
    block_list._dominant_tree = None
    block_list._loop_nesting_forest = None
    graph = block_list.to_graph()
    immediate_dominators = nx.immediate_dominators(graph, block_list.start_block)
    immediate_post_dominators = _immediate_post_dominators(graph)
    innermost = _innermost_loops(block_list.loop_nesting_forest)

    def post_dominates(post_dominator: block_id_T, block_id: block_id_T) -> bool:
        current = block_id
        while current != post_dominator:
            following = immediate_post_dominators.get(current)
            if following is None or following == current:
                return False
            current = following
        return True

    # Stack pressure: a hoisted label is live in the blocks between its target and the call (dominated by the target
    # and post-dominated by the call). It is only hoisted if, in all of them, the live-in variables plus the labels
    # already hoisted across them plus this one leave room for the computations within the reachable part of the stack
    live_in_sizes, live_out_sizes = _liveness_sizes(block_list) if strategy == "shared" else ({}, {})
    pending_labels = collections.Counter()
    dominated = _dominated_blocks(immediate_dominators, block_list.start_block) if strategy == "shared" else {}
    limit = constants.MAX_STACK_DEPTH - PRESSURE_MARGIN

    def fits(target_id: block_id_T, region: List[block_id_T]) -> bool:
        if live_out_sizes.get(target_id, 0) + pending_labels[target_id] + 1 > limit:
            return False
        return all(live_in_sizes.get(block_id, 0) + pending_labels[block_id] + 1 <= limit for block_id in region)

    moves: List[Tuple[block_id_T, int, block_id_T, int]] = []
    for call_block_id, call_block in block_list.blocks.items():
        label_info = return_label(call_block, function_names)
        if label_info is None or call_block_id not in immediate_dominators:
            continue
        if strategy == "shared":
            candidates = _shared_target(call_block_id, block_list.start_block, immediate_dominators,
                                        post_dominates, innermost, is_shared)
            # The highest candidate whose region does not exceed the stack pressure
            for crossed_idx, target_id in enumerate(candidates):
                region = [block_id for block_id in dominated[target_id] if block_id != target_id
                          and post_dominates(call_block_id, block_id)]
                if fits(target_id, region):
                    for block_id in region + [target_id]:
                        pending_labels[block_id] += 1
                    moves.append((call_block_id, label_info[0], target_id, len(candidates) - crossed_idx))
                    break
            continue

        target_id, crossed, current = call_block_id, 0, call_block_id
        while current != block_list.start_block:
            candidate = immediate_dominators[current]
            if not post_dominates(call_block_id, candidate) or \
                    innermost.get(candidate) != innermost.get(call_block_id):
                break
            crossed += 1
            current = candidate
            if strategy == "max":
                target_id = candidate
            elif len(block_list.get_block(candidate).successors) > 1:
                # "branch": the nearest branch point whose paths all reach the call, as solc does. Hoisting further
                # only makes the label live longer, as the code above is not shared by the paths towards the call
                target_id = candidate
                break
        if target_id != call_block_id:
            moves.append((call_block_id, label_info[0], target_id, crossed))

    # The push instructions are taken before moving any of them: a call block can also be the target of another
    # move, and inserting into it would shift the positions computed above
    push_instructions = [block_list.get_block(call_block_id).get_instructions()[push_idx]
                         for call_block_id, push_idx, _, _ in moves]
    for (call_block_id, _, target_id, _), push_instruction in zip(moves, push_instructions):
        call_instructions = block_list.get_block(call_block_id).get_instructions()
        call_instructions.pop(next(idx for idx, instruction in enumerate(call_instructions)
                                   if instruction is push_instruction))
        target_block = block_list.get_block(target_id)
        target_instructions = target_block.get_instructions()
        # Before the split instruction of the target block (the last one), after its phi-functions
        position = len(target_instructions) - 1 if target_block.split_instruction is not None and target_instructions \
            and target_instructions[-1] is target_block.split_instruction else len(target_instructions)
        while position < len(target_instructions) and target_instructions[position].get_op_name() == "PhiFunction":
            position += 1
        target_block.insert_instruction(position, push_instruction)

    if moves:
        logging.info(f"Hoisted {len(moves)} return labels in {block_list.name} "
                     f"(on average {sum(m[3] for m in moves) / len(moves):.1f} dominators up)")
    return len(moves)

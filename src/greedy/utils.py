from collections import Counter
import warnings
from typing import Tuple, List, Dict, Any
import networkx as nx
import global_params.constants as constants
from global_params.types import var_id_T
from parser.cfg_block_list import CFGBlockList


def compute_max_n_elements(node: str, instr_graph: nx.DiGraph()) -> Tuple[int, bool]:
    """
    Computes the maximum number of elements that can be used to fix a position
    """
    if instr_graph.out_degree(node) == 0:
        return 1, True

    # Commutative case
    if instr_graph.nodes[node]["commutative"]:
        edges = list(instr_graph.edges(node))
        first_arg_nodes, first_args_inserting = compute_max_n_elements(edges[0][1], instr_graph)
        second_arg_nodes, second_args_inserting = compute_max_n_elements(edges[1][1], instr_graph)

        # If one of them can insert elements
        # Ensure every path can be computed
        # TODO: improve strategy
        return min(first_arg_nodes, second_arg_nodes), False

    # Non-Commutative case
    else:
        n_elements = 0
        for edge in instr_graph.edges(node):
            target = edge[1]
            current_nodes, keep_on_inserting = compute_max_n_elements(target, instr_graph)
            n_elements += current_nodes
            if not keep_on_inserting:
                return n_elements, False

        return n_elements, False


def print_traces(cstate) -> None:
    """
    Prints the traces so far from the current state. Debug mode must be activated
    """
    if cstate.debug_mode:
        list_strings = [str(t[0]) for t in cstate.trace]
        max_list_len = max(len(ls) for ls in list_strings)

        # Calculate the maximum length of the string part
        max_str_len = max(len(t[1]) for t in cstate.trace)

        # Print each tuple with aligned formatting
        for (lst, string), list_str in zip(cstate.trace, list_strings):
            print(f"{string:<{max_str_len}} {list_str:>{max_list_len}}")


def detect_blocks_with_multiple_insertion(cfg_block_list: CFGBlockList) -> Dict[var_id_T, int]:
    """
    Detects which blocks correspond to a sub block in which the splitting instruction
    of the previous returns too many things in the stack to have it reachable at some point.
    Also for the start block if the arguments are too many
    """
    blocks_inaccessible_elements = dict()

    # First check start block
    start_block = cfg_block_list.get_block(cfg_block_list.start_block)
    if len(start_block.spec["src_ws"]) > constants.MAX_STACK_DEPTH:
        blocks_inaccessible_elements[cfg_block_list.start_block] = len(start_block.spec["src_ws"]) - constants.MAX_STACK_DEPTH

    for block_name, block in cfg_block_list.blocks.items():
        if "StakingPool" in block_name:
            print("HOLA")
        if (block.get_jump_type() == "sub_block" and block.split_instruction is not None
                and len(block.split_instruction.out_args) > constants.MAX_STACK_DEPTH):
            assert len(block.successors) == 1, f"Sub_block {block_name} should only have one successor"
            blocks_inaccessible_elements[block.successors[0]] = len(block.split_instruction.out_args) - constants.MAX_STACK_DEPTH

    return blocks_inaccessible_elements


def count_elements(sfs: Dict[str, Any]) -> Counter[var_id_T]:
    counter = Counter()
    for element in sfs["src_ws"]:
        counter[element] -= 1
    for element in sfs["tgt_ws"]:
        counter[element] += 1
    for instr in sfs["user_instrs"]:
        for in_var in instr['inpt_sk']:
            counter[in_var] += 1
    return counter


def pseudo_instr(var_: var_id_T):
    """
    Pseudo instruction to represent a variable can be loaded from memory
    """
    return {
            "id": f"VGET({var_})",
            "opcode": "01",
            "disasm": "CALLVALUE",
            "inpt_sk": [
            ],
            "outpt_sk": [
                var_
            ],
            "gas": 3,
            "commutative": False,
            "push": False,
            "storage": False,
            "size": 5
        }


def move_elements_to_make_reachable(sfs: Dict[str, Any], num_elements: int):
    current_stack: List[var_id_T] = sfs["src_ws"]
    operands = []
    counter = count_elements(sfs)
    
    current_index = 0
    # First try to pop elements
    while num_elements > 0 and current_index < num_elements:
        # Can be removed
        if counter[current_stack[current_index]] == -1:
            # Swap current one and put in their position
            if current_index > 0:
                operands.append(f"SWAP{current_index}")
                current_stack[0], current_stack[current_index] = current_stack[current_index], current_stack[0]

            operands.append("POP")
            current_stack.pop(0)
            num_elements -= 1

        else:
            current_index += 1

    # Second: perform VSETs
    while num_elements > 0:
        current_element = current_stack.pop(0)
        operands.append(f"VSET({current_element})")
        sfs["user_instrs"].append(pseudo_instr(current_element))
        num_elements -= 1

    sfs["src_ws"] = current_stack
    return operands

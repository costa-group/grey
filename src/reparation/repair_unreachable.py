"""
Main methods to repairing the stack-too-deep placeholders
"""
from typing import List, Dict, Tuple, Set, Optional, Iterable
from pathlib import Path
import networkx as nx
from collections import Counter

from parser.parser import CFGBlockList, CFGBlock, CFGObject, CFG
from greedy.greedy_info import GreedyInfo
from global_params.types import var_id_T, block_id_T, constant_T
from reparation.reachability import construct_reachability
from reparation.insert_placeholders import repair_unreachable, PhiWebs
from reparation.tree_scan import TreeScan, ColourAssignment
from reparation.utils import extract_value_from_pseudo_instr
from graphs.algorithms import information_on_graph


def repair_cfg(cfg: CFG, path_to_files: Optional[Path]):
    """
    Repairs all the block lists in a CFG
    """
    csv_dicts = []
    for cfg_object in cfg.get_objects().values():
        csv_dicts.extend(repair_cfg_objects(cfg_object, path_to_files))
        sub_object = cfg_object.subObject
        if sub_object is not None:
            csv_dicts.extend(repair_cfg(sub_object, path_to_files))
    return csv_dicts


def repair_cfg_objects(cfg: CFGObject, path_to_files: Path):
    """
    Repairs all block list in an object
    """
    csvs_dicts, original_max = [], get_first_constant(cfg.blocks)
    max_constant = original_max

    for cfg_function in cfg.functions.values():
        if cfg_function.blocks.needs_repair:
            csv_dicts_block_list, max_constant = repair_unreachable_blocklist(cfg_function.blocks, cfg.blocks.to_fix,
                                                                              path_to_files.joinpath(cfg.name) if path_to_files is not None else None,
                                                                              max_constant)
            max_constant = hex(int(max_constant, 16) + 32)[2:]
            csvs_dicts.append(csv_dicts_block_list)

    if cfg.blocks.needs_repair:
        csv_dicts_block_list, max_constant = repair_unreachable_blocklist(cfg.blocks, cfg.blocks.to_fix,
                                                                          path_to_files.joinpath(cfg.name) if path_to_files is not None else None,
                                                                          max_constant)
        max_constant = hex(int(max_constant, 16) + 32)[2:]

        csvs_dicts.append(csv_dicts_block_list)

    if original_max != max_constant:
        # Finally, change the first instruction
        set_first_constant(cfg.blocks, max_constant)

    return csvs_dicts

def repair_unreachable_blocklist(cfg_blocklist: CFGBlockList,
                                 elements_to_fix: Counter[var_id_T],
                                 path_to_files: Optional[Path],
                                 forbidden_constants: List[str]):
    """
    Assumes the blocks in the cfg contain the information of the
    greedy algorithm according to greedy algorithm
    """
    # TODO: store the dominant tree somewhere it makes sense
    construct_reachability(cfg_blocklist, cfg_blocklist.dominant_tree)
    prepass_fixing_constants(cfg_blocklist, elements_to_fix)

    # Visual debugging information
    if path_to_files is not None:
        reachability_path = path_to_files.joinpath("reachability")
        reachability_path.mkdir(exist_ok=True, parents=True)
        _debug_cfg_reachability(cfg_blocklist, reachability_path)

        vget_annotated = path_to_files.joinpath("annotated_vget")
        vget_annotated.mkdir(exist_ok=True, parents=True)
        _debug_reparation(cfg_blocklist, vget_annotated)

    phi_webs, num_vals = repair_unreachable(cfg_blocklist, set(elements_to_fix.keys()))

    if path_to_files is not None:
        repaired = path_to_files.joinpath("repaired_vget")
        repaired.mkdir(exist_ok=True, parents=True)
        _debug_reparation(cfg_blocklist, repaired)

    color_assignment, used_constants = TreeScan(cfg_blocklist, phi_webs, num_vals, forbidden_constants).executable_from_code()
    return extract_statistics(cfg_blocklist.name, phi_webs, color_assignment), used_constants


def get_first_constant(cfg_blocklist: CFGBlockList):
    first_block = cfg_blocklist.get_block(cfg_blocklist.start_block)
    first_instruction = first_block.instructions_to_synthesize[0]

    # print(first_instruction)
    if first_instruction.op == "memoryguard":
        # print("GUARD", first_instruction)
        return hex(int(first_instruction.literal_args[0]))[2:]
    elif first_instruction.op == "push":
        # print("PUSH", first_instruction)
        return first_instruction.literal_args[0][2:]
    elif first_instruction.op == "mstore":
        return first_instruction.in_args[1]


def set_first_constant(cfg_blocklist: CFGBlockList, new_constant: constant_T):
    first_block = cfg_blocklist.get_block(cfg_blocklist.start_block)
    first_instruction = first_block.instructions_to_synthesize[0]
    constant_with_preffix = "0x" + new_constant

    if first_instruction.op == "memoryguard":
        # print("GUARD", first_instruction)
        first_instruction.literal_args[0] = constant_with_preffix
    elif first_instruction.op == "push":
        # print("PUSH", first_instruction)
        first_instruction.literal_args[0] = constant_with_preffix
    elif first_instruction.op == "mstore":
        first_instruction.in_args[1] = constant_with_preffix

    greedy_ids = cfg_blocklist.blocks[cfg_blocklist.start_block].greedy_ids
    first_push = greedy_ids[0]
    assert "PUSH" in first_push, "First instruction is not a PUSH"

    cfg_blocklist.blocks[cfg_blocklist.start_block].greedy_ids = [f"PUSH {new_constant}"
                                                                  if element == first_push else element
                                                                  for element in greedy_ids]

def prepass_fixing_constants(cfg_blocklist: CFGBlockList,
                             elements_to_fix: Counter[var_id_T]):
    """
    We first detect if some of the too-deep computations
    correspond to constants, in which case we can just
    compute them directly in the code without the previous process.
    """
    first_block = cfg_blocklist.get_block(cfg_blocklist.start_block)
    first_instruction = first_block.instructions_to_synthesize[0]

    if first_instruction.op == "memoryguard":
        # print("GUARD", first_instruction)
        cfg_blocklist.assigment_dict[first_instruction.get_out_args()[0]] = hex(int(first_instruction.literal_args[0]))
    elif first_instruction.op == "push":
        # print("PUSH", first_instruction)
        cfg_blocklist.assigment_dict[first_instruction.get_out_args()[0]] = first_instruction.literal_args[0]        
        
    get_with_constants = _detect_replace_constants(elements_to_fix,
                                                   cfg_blocklist.assigment_dict)

    # Traverse all the blocks
    for block_name, block in cfg_blocklist.blocks.items():
        greedy_info = block.greedy_info

        # Values in the intersection
        if len(greedy_info.elements_to_fix) > 0:
            new_ids = []
            for instr in greedy_info.greedy_ids:
                if instr.startswith("VGET"):
                    var = extract_value_from_pseudo_instr(instr)
                    # First case: a variable that has been propagated
                    if var in get_with_constants:
                        constant = cfg_blocklist.assigment_dict[var]
                        new_ids.append(f"PUSH {constant[2:]}")
                    elif (push_instr := greedy_info.var2push.get(var)) is not None:
                        new_ids.append(f"PUSH {hex(push_instr['value'][0])[2:]}")
                    else:
                        # If no PUSH instruction can be replaced, then we just add the new instruction
                        new_ids.append(instr)
                else:
                    new_ids.append(instr)

            # We update the greedy ids
            greedy_info.set_greedy_ids(new_ids)


def _detect_replace_constants(elements_to_fix: Counter[var_id_T],
                              assignment_dict: Dict[var_id_T, constant_T]) -> Set[var_id_T]:
    """
    Determines which constants are pushed directly instead of fixed
    """
    constants_to_replace = set()
    for var_, num_uses in elements_to_fix.items():
        # We ignore the variables that are not constants
        if var_ not in assignment_dict:
            continue

        constant = assignment_dict[var_]
        size = (len(constant) - 2) // 2

        # Same heuristic as in the constant propagation
        # uses*size >= #uses + size + 2 for fixing
        if num_uses * size < num_uses + size + 2:
            constants_to_replace.add(var_)

    return constants_to_replace


def _represent_reachability_info(block: CFGBlock, num_elements: int = 5):
    msg = [block.block_id, "Reachable:"]
    greedy_info = block.greedy_info

    # Represent the reachable elements
    current_msg = ["{"]
    for element in greedy_info.reachable:
        if len(current_msg) > num_elements:
            msg.append(' '.join(current_msg))
            current_msg = []
        current_msg.append(element)
    current_msg.append("}")
    msg.append(' '.join(current_msg))
    msg.append("Unreachable:")

    # Represent the unreachable elements
    current_msg = ["{"]
    for element in greedy_info.unreachable:
        if len(current_msg) > num_elements:
            msg.append(' '.join(current_msg))
            current_msg = []
        current_msg.append(element)
    current_msg.append("}")
    msg.append(' '.join(current_msg))

    return '\n'.join(msg)


def _debug_cfg_reachability(cfg_blocklist: CFGBlockList, path_to_files: Path):
    dominant_tree = cfg_blocklist.dominant_tree
    renamed_graph = information_on_graph(dominant_tree,
                                         {block_name: _represent_reachability_info(block)
                                          for block_name, block in cfg_blocklist.blocks.items()})

    nx.nx_agraph.write_dot(renamed_graph, path_to_files.joinpath(f"{cfg_blocklist.name}.dot"))


def _debug_reparation(cfg_blocklist: CFGBlockList, path_to_files: Path):
    cfg_graph = cfg_blocklist.to_graph()
    renamed_graph = information_on_graph(cfg_graph,
                                         {block_name: _represent_greedy_info(block_name, block.greedy_info)
                                          for block_name, block in cfg_blocklist.blocks.items()})

    nx.nx_agraph.write_dot(renamed_graph, path_to_files.joinpath(f"{cfg_blocklist.name}.dot"))


def _represent_greedy_info(block_name: block_id_T, greedy_info: GreedyInfo) -> str:
    return block_name + '\n' + '\n'.join(greedy_info.greedy_ids)


def extract_statistics(name: str, phi_web: PhiWebs, color_assignment: ColourAssignment):
    return {"name": name, "num_phi": phi_web.num_elements,
            "num_assigned": color_assignment.num_assigned,
            "num_colors": color_assignment.num_regs}

"""
Module that handles the generation of the ids from the greedy algorithm.
"""
import copy
from pathlib import Path
from typing import Tuple, List, Dict, Optional, Set, Iterable, Any
from collections import Counter

import pandas as pd

from global_params.types import instr_id_T, var_id_T
from parser.cfg_block import CFGBlock
from parser.cfg_block_list import CFGBlockList
from parser.cfg_object import CFGObject
from parser.cfg import CFG
import greedy.greedy_previous_param as previous
from greedy.utils import detect_blocks_with_multiple_insertion, move_elements_to_make_reachable
from solution_generation.statistics import generate_statistics_info
from greedy.greedy_info import GreedyInfo
import greedy.greedy_new_version as alternative
import numpy as np
from reparation.repair_unreachable import repair_unreachable_blocklist
from analysis.greedy_validation import check_execution_from_ids
import global_params.constants as constants
from reparation.utils import PUSH_CONSTANT

def _length_or_zero(l, outcome):
    return len(l) if l is not None and outcome != "error" else 10000


def push_to_dup(greedy_ids: List[instr_id_T], initial_stack: List[var_id_T],
                instr_map: Dict[instr_id_T, Dict[str, Any]]) -> List[instr_id_T]:
    """
    Replaces the PUSHes (except PUSH0) of values that are already in the stack within the reach of DUP by the
    corresponding DUP: same number of instructions and gas, fewer bytes. The stack is simulated from the initial
    stack of the block, tracking the values pushed; the simulation stops at an unknown id.
    It runs once on the final ids of the block (after the reparation, see cfg_push_to_dup), so besides the ids of the
    greedy it understands the code emitted by the reparation: the memory slots ("PUSH a0" + MLOAD/MSTORE) and the
    constants of the phi copies ("PUSH-CONSTANT 0x20")
    """
    new_ids = list(greedy_ids)
    stack = [("initial", var) for var in initial_stack]    # top at position 0
    for i, instr_id in enumerate(greedy_ids):
        pushed_value = None
        if instr_id.startswith("DUP") and instr_id[3:].isdigit():
            depth = int(instr_id[3:])
            if depth > len(stack):
                break
            stack.insert(0, stack[depth - 1])
        elif instr_id.startswith("SWAP") and instr_id[4:].isdigit():
            depth = int(instr_id[4:])
            if depth >= len(stack):
                break
            stack[0], stack[depth] = stack[depth], stack[0]
        elif instr_id == "POP":
            if not stack:
                break
            stack.pop(0)
        elif instr_id == "NOP":
            continue
        elif instr_id in ["MLOAD", "MSTORE"]:
            # Memory accesses of the reparation: the loaded value is unknown
            num_inputs = 1 if instr_id == "MLOAD" else 2
            if num_inputs > len(stack):
                break
            del stack[:num_inputs]
            if instr_id == "MLOAD":
                stack.insert(0, ("computed", f"MLOAD@{i}"))
        elif instr_id.startswith(PUSH_CONSTANT):
            # Constant of a phi copy ("PUSH-CONSTANT 0x20")
            pushed_value = int(instr_id.split(" ")[1], 16)
        elif instr_id.startswith("PUSH") and " 0x" in instr_id:
            # Constant pushed directly by the greedy (e.g. "PUSH2 0x100")
            pushed_value = int(instr_id.split(" 0x")[1], 16)
        elif instr_id.startswith("PUSH ") and all(c in "0123456789abcdefABCDEF" for c in instr_id[5:]) \
                and len(instr_id) > 5:
            # Address of a memory slot or rewritten memoryguard, emitted by the reparation ("PUSH a0")
            pushed_value = int(instr_id[5:], 16)
        elif instr_id in instr_map:
            instr = instr_map[instr_id]
            if instr.get("push", False) and instr["disasm"] != "PUSH0" and "value" in instr:
                key = ("value", instr["disasm"], str(instr["value"]))
                if key in stack[:constants.MAX_STACK_DEPTH] and instr.get("size", 2) > 1:
                    new_ids[i] = "DUP" + str(stack.index(key) + 1)
                stack.insert(0, key)
            else:
                num_inputs = len(instr["inpt_sk"])
                if num_inputs > len(stack):
                    break
                del stack[:num_inputs]
                for out in instr["outpt_sk"]:
                    stack.insert(0, ("computed", out))
        else:
            break

        if pushed_value is not None:
            key = ("value", "PUSH", str([pushed_value]))
            if pushed_value != 0 and key in stack[:constants.MAX_STACK_DEPTH]:
                new_ids[i] = "DUP" + str(stack.index(key) + 1)
            stack.insert(0, key)
    return new_ids


def cfg_block_spec_ids(cfg_block: CFGBlock, elements_to_move: int = 0) -> Tuple[str, float, List[instr_id_T], Counter[var_id_T]]:
    cfg_block.get_liveness()
    # Retrieve the information from each of the executions
    sfs = copy.deepcopy(cfg_block._spec)
    admits_junk = sfs["admits_junk"]

    # TODO: better integration
    if elements_to_move > 0:
        extra_operands = move_elements_to_make_reachable(sfs, elements_to_move)
    else:
        extra_operands = []

    outcome1, time1, greedy_ids1 = previous.greedy_standalone(sfs, admits_junk, constants.MAX_STACK_DEPTH)

    # Append the preprocessing variables
    greedy_ids1 = extra_operands + greedy_ids1

    greedy_info = GreedyInfo.from_old_version(greedy_ids1, outcome1, time1, cfg_block.spec["user_instrs"])
    greedy_ids1 = greedy_info.greedy_ids

    # greedy_info3 = alternative.greedy_standalone(cfg_block.spec)
    # outcome3, time3, greedy_ids3 = greedy_info3.outcome, greedy_info3.execution_time, greedy_info3.greedy_ids

    lengths = [_length_or_zero(greedy_ids1, outcome1),
               # _length_or_zero(greedy_ids3, outcome3)
               ]

    chosen_idx = np.argmin(lengths)

    outcome = outcome1 # [outcome1, outcome3][chosen_idx]
    time = time1 #  [time1, time3][chosen_idx]
    greedy_ids = greedy_ids1 # [greedy_ids1, greedy_ids3][chosen_idx]

    # Safety check: only performed in debug mode, as it is not part of the pipeline
    if constants.DEBUG:
        assert check_execution_from_ids(copy.deepcopy(cfg_block.spec), greedy_ids, admits_junk), \
            f"Fails in block: {cfg_block.block_id}"

    cfg_block.greedy_ids = greedy_ids if greedy_ids is not None else []
    cfg_block.greedy_info = greedy_info
    return outcome, time, greedy_ids, greedy_info.elements_to_fix


def cfg_block_list_spec_ids(cfg_blocklist: CFGBlockList, visualize: bool) -> Tuple[bool, List[Dict]]:
    """
    Generates the assembly code of all the blocks in a block list and returns the statistics
    """
    csv_dicts = []
    to_fix = Counter()
    has_vget = False

    blocks_to_move_elements = detect_blocks_with_multiple_insertion(cfg_blocklist)
    for block_name, block in cfg_blocklist.blocks.items():
        outcome, time, greedy_ids, to_fix_block = cfg_block_spec_ids(block, blocks_to_move_elements.get(block_name, 0))
        to_fix += to_fix_block
        has_vget = has_vget or block.greedy_info.has_vget

        if visualize:
            csv_dicts.append(generate_statistics_info(block_name, greedy_ids, time, block.spec))

    cfg_blocklist.needs_repair = has_vget
    cfg_blocklist.to_fix = to_fix
    return has_vget, csv_dicts


def cfg_object_spec_ids(cfg: CFGObject, visualize: bool) -> Tuple[bool, List[Dict]]:
    """
    Generates the assembly code for a
    """
    needs_repair, csv_dicts = cfg_block_list_spec_ids(cfg.blocks, visualize)
    for cfg_function in cfg.functions.values():
        repair_func, csv_rows = cfg_block_list_spec_ids(cfg_function.blocks, visualize)
        csv_dicts.extend(csv_rows)
        needs_repair = needs_repair or repair_func
    return needs_repair, csv_dicts


def recursive_cfg_spec_ids(cfg: CFG, visualize: bool) -> Tuple[bool, List[Dict]]:
    """
    Generates the assembly for all the blocks inside the CFG, excluding the sub objects.
    """
    csv_dicts = []
    needs_repair = False
    for cfg_object in cfg.get_objects().values():
        repair_obj, csv_rows = cfg_object_spec_ids(cfg_object, visualize)
        csv_dicts.extend(csv_rows)
        needs_repair = needs_repair or repair_obj
        sub_object = cfg_object.subObject
        if sub_object is not None:
            repair_obj, csv_rows = recursive_cfg_spec_ids(sub_object, visualize)
            needs_repair = needs_repair or repair_obj
            csv_dicts.extend(csv_rows)
    return needs_repair, csv_dicts


def cfg_block_list_push_to_dup(cfg_blocklist: CFGBlockList) -> None:
    for block in cfg_blocklist.blocks.values():
        if block.greedy_ids:
            block.greedy_ids = push_to_dup(block.greedy_ids, block.spec["src_ws"],
                                           {instr["id"]: instr for instr in block.spec["user_instrs"]})


def cfg_push_to_dup(cfg: CFG) -> None:
    """
    Replaces the PUSHes of values already in the stack by DUPs in the final ids of every block (block.greedy_ids),
    including the functions and the sub objects. It runs once, after the reparation: the checks (greedy validation,
    memory slots) compare variables, not values, and the reparation works on greedy_info.greedy_ids and rebuilds
    block.greedy_ids of every block of a repaired block list. The statistics CSV keeps the ids before this pass
    """
    for cfg_object in cfg.get_objects().values():
        cfg_block_list_push_to_dup(cfg_object.blocks)
        for cfg_function in cfg_object.functions.values():
            cfg_block_list_push_to_dup(cfg_function.blocks)
        if cfg_object.subObject is not None:
            cfg_push_to_dup(cfg_object.subObject)


def cfg_spec_ids(cfg: CFG, csv_file: Optional[Path], visualize: bool) -> bool:
    """
    Generates the greedy ids from the specification inside the cfg and stores in the field "greedy_ids" inside
    each block. Stores the information from the greedy generation in a csv file
    """
    needs_repair, csv_dicts = recursive_cfg_spec_ids(cfg, visualize)
    if visualize:
        pd.DataFrame(csv_dicts).to_csv(csv_file)
    return needs_repair, csv_dicts if visualize else []

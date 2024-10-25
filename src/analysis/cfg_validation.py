"""
Module that includes methods for checking that the CFG is coherent
"""
from collections import Counter, defaultdict
from typing import Dict, Set, Tuple, Optional
from global_params.types import block_id_T
from parser.cfg_block import CFGBlock
from parser.cfg_block_list import CFGBlockList


def validate_block(cfg_block: CFGBlock, comes_from_id: Optional[block_id_T], reached_comes_from: Dict[block_id_T, Set[block_id_T]],
                   cfg_block_list: CFGBlockList) -> Tuple[bool, str]:
    """
    Validates the block and returns the reason why the validation fails (if any)
    """
    block_id = cfg_block.block_id
    already_traversed = block_id in reached_comes_from

    # Skip the initial case (as there is no comes from)
    if comes_from_id is not None:
        if comes_from_id not in cfg_block.get_comes_from():
            return False, f"Block {cfg_block.block_id} does not contain {comes_from_id} as part of the list of comes from" \
                          f"blocks {cfg_block.get_comes_from()}"

        reached_comes_from[block_id].add(comes_from_id)

        # For blocks that we have already traversed, we just need to validate the comes
        # from block does appear in the list
        if already_traversed:
            return True, ""

    for successor in cfg_block.successors:
        successor_is_validated, successor_error_message = validate_block(cfg_block_list.blocks[successor], block_id,
                                                                         reached_comes_from, cfg_block_list)
        if not successor_is_validated:
            return False, successor_error_message

    return True, ""


def validate_comes_from(reached_comes_from: Dict[block_id_T, Set[block_id_T]],
                        cfg_block_list: CFGBlockList) -> Tuple[bool, str]:
    """
    Validates that all the comes from reached from the original cfg correspond to the ones stored in the blocks
    """
    for block_id, comes_from in reached_comes_from.items():
        cfg_block = cfg_block_list.blocks[block_id]
        if Counter(cfg_block.get_comes_from()) != Counter(comes_from):
            return False, f"The expected 'comes_from' of {block_id} does not match the expected." \
                          f"From the traversal: {Counter(comes_from)}. In the CFG: {Counter(cfg_block.get_comes_from())} "
    return True, ""


def validate_block_list_comes_from(cfg_block_list: CFGBlockList) -> Tuple[bool, str]:
    """
    Validates that the comes from and jumps to/falls to
    """
    reached_comes_from = defaultdict(lambda: set())
    failed_validation, reason = validate_block(cfg_block_list.blocks[cfg_block_list.start_block], None, reached_comes_from, cfg_block_list)
    if not failed_validation:
        return failed_validation, reason
    else:
        second_verification, reason = validate_comes_from(reached_comes_from, cfg_block_list)
        return second_verification, reason

"""
Stores the information for the greedy algorithm following the SFS format
"""
import copy
import json
from pathlib import Path
from typing import List
from parser.cfg_block import CFGBlock
from parser.cfg_block_list import CFGBlockList
from parser.cfg_object import CFGObject
from parser.cfg import CFG
from analysis.greedy_validation import store_sfs_params_from_greedy

def cfg_block_spec_ids(cfg_block: CFGBlock, target_file: Path):
    # Retrieve the information from each of the executions
    sfs = copy.deepcopy(cfg_block._spec)

    # We need to detect whether the block finishes with revert
    # TODO: extend to the notion of garbage in GASOL
    store_sfs_params_from_greedy(sfs, cfg_block.greedy_info.greedy_ids,
                                 cfg_block.split_instruction.get_op_name().lower() == "revert")

    with open(target_file, 'w') as f:
        json.dump(sfs, f, indent=4)


def sfs_from_cfg_blocklist(cfg_blocklist: CFGBlockList, final_folder: Path):

    for block_name, block in cfg_blocklist.blocks.items():
        cfg_block_spec_ids(block, final_folder.joinpath(f"sfs_{block_name}.json"))


def sfs_from_cfg_object(cfg: CFGObject, final_folder: Path) -> None:
    final_folder.mkdir(parents=True, exist_ok=True)
    sfs_from_cfg_blocklist(cfg.blocks, final_folder)
    for cfg_function in cfg.functions.values():
        sfs_from_cfg_blocklist(cfg_function.blocks, final_folder)


def sfs_from_cfg_recursive(cfg: CFG, final_folder: Path, positions: List[str] = None) -> None:
    if positions is None:
        positions = ["0"]

    for i, (object_id, cfg_object) in enumerate(cfg.get_objects().items()):
        sfs_from_cfg_object(cfg_object, final_folder.joinpath('_'.join([str(position) for position in positions])).joinpath("sfs_gasol"))
        sub_object = cfg_object.subObject
        if sub_object is not None:
            sfs_from_cfg_recursive(sub_object, final_folder, positions + [str(i)])


def sfs_from_cfg(cfg: CFG, final_folder: Path, ) -> None:
    sfs_from_cfg_recursive(cfg, final_folder.joinpath("stack_layouts").joinpath())

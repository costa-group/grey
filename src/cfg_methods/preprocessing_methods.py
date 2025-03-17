"""
Preprocess the graph by performing inlining and splitting of blocks
"""
from typing import Dict
from pathlib import Path
from liveness.liveness_analysis import dot_from_analysis
from parser.cfg import CFG
from cfg_methods.function_inlining import inline_functions
from cfg_methods.sub_block_generation import combine_remove_blocks_cfg, split_blocks_cfg
from cfg_methods.jump_insertion import insert_jumps_tags_cfg
from cfg_methods.variable_renaming import rename_variables_cfg
from cfg_methods.constants_insertion import insert_variables_for_constants


def preprocess_cfg(cfg: CFG, dot_file_dir: Path, visualization: bool) -> Dict[str, Dict[str, int]]:
    if visualization:
        liveness_info = dot_from_analysis(cfg, dot_file_dir.joinpath("initial"))

    # Assign distinct names for all the variables in the CFG among different functions and blocks
    # TODO: in the future, we could do the renaming just in the inliner when two block lists are merged
    rename_variables_cfg(cfg)

    if visualization:
        liveness_info = dot_from_analysis(cfg, dot_file_dir.joinpath("renamed"))

    # We inline the functions
    inline_functions(cfg)
    if visualization:
        liveness_info = dot_from_analysis(cfg, dot_file_dir.joinpath("inlined"))

    # We combine and remove the blocks from the CFG
    # Must be the latest step because we might have split blocks after insert jumps and tags
    combine_remove_blocks_cfg(cfg)
    if visualization:
        liveness_info = dot_from_analysis(cfg, dot_file_dir.joinpath("combined"))

    # We introduce the jumps, tags and the stack requirements for each block
    tag_dict = insert_jumps_tags_cfg(cfg)
    if visualization:
        liveness_info = dot_from_analysis(cfg, dot_file_dir.joinpath("jumps"))

    # Then we split by sub blocks
    split_blocks_cfg(cfg, tag_dict)
    if visualization:
        liveness_info = dot_from_analysis(cfg, dot_file_dir.joinpath("split"))

    # We replace variables for constants
    insert_variables_for_constants(cfg)
    if visualization:
        liveness_info = dot_from_analysis(cfg, dot_file_dir.joinpath("constants"))

    return tag_dict

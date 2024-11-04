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


def preprocess_cfg(cfg: CFG, dot_file_dir: Path) -> Dict[str, Dict[str, int]]:
    dot_file_dir.joinpath("initial").mkdir(exist_ok=True, parents=True)
    liveness_info = dot_from_analysis(cfg, dot_file_dir.joinpath("initial"))

    # Assign distinct names for all the variables in the CFG among different functions and blocks
    # TODO: in the future, we could do the renaming just in the inliner when two block lists are merged
    rename_variables_cfg(cfg)
    dot_file_dir.joinpath("renamed").mkdir(exist_ok=True, parents=True)
    liveness_info = dot_from_analysis(cfg, dot_file_dir.joinpath("renamed"))

    # We inline the functions
    inline_functions(cfg)
    dot_file_dir.joinpath("inlined").mkdir(exist_ok=True, parents=True)
    liveness_info = dot_from_analysis(cfg, dot_file_dir.joinpath("inlined"))

    # Then we split by sub blocks
    split_blocks_cfg(cfg)
    dot_file_dir.joinpath("split").mkdir(exist_ok=True, parents=True)
    liveness_info = dot_from_analysis(cfg, dot_file_dir.joinpath("split"))

    # Then we combine and remove the blocks from the CFG
    combine_remove_blocks_cfg(cfg)
    dot_file_dir.joinpath("combined").mkdir(exist_ok=True, parents=True)
    liveness_info = dot_from_analysis(cfg, dot_file_dir.joinpath("combined"))

    # Finally, we introduce the jumps, tags and the stack requirements for each block
    # Then we combine and remove the blocks from the CFG
    tag_dict = insert_jumps_tags_cfg(cfg)
    dot_file_dir.joinpath("jumps").mkdir(exist_ok=True, parents=True)
    liveness_info = dot_from_analysis(cfg, dot_file_dir.joinpath("jumps"))
    return tag_dict

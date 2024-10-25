"""
Preprocess the graph by performing inlining and splitting of blocks
"""
from liveness.liveness_analysis import dot_from_analysis
from parser.cfg import CFG
from cfg_methods.function_inlining import inline_functions
from cfg_methods.sub_block_generation import combine_remove_blocks_cfg, split_blocks_cfg


def preprocess_cfg(cfg: CFG, dot_file_dir):
    # First we inline the functions
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

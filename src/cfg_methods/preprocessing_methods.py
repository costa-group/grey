"""
Preprocess the graph by performing inlining and splitting of blocks
"""
import json
from typing import Dict
from pathlib import Path
from argparse import Namespace
from liveness.liveness_analysis import dot_from_analysis
from analysis.validate_liveness import validate_liveness
from parser.cfg import CFG
from cfg_methods.function_inlining import inline_functions
from cfg_methods.sub_block_generation import combine_remove_blocks_cfg, split_blocks_cfg
from cfg_methods.jump_insertion import insert_jumps_tags_cfg
from cfg_methods.variable_renaming import rename_variables_cfg
from cfg_methods.constants_insertion import insert_variables_for_constants
from cfg_methods.minimizing_constants_insertion import insert_variables_for_constants_propagated
from cfg_methods.return_labels import hoist_return_labels_cfg
from cfg_methods.equivalent_blocks_merging import merge_equivalent_blocks_cfg
from cfg_methods.critical_edges import split_critical_edges_cfg, split_call_join_edges_cfg
from cfg_methods.cse_rules import apply_cse_rules_cfg


def preprocess_cfg(cfg: CFG, dot_file_dir: Path, args: Namespace) -> Dict[str, Dict[str, int]]:
    if args.visualize:
        dot_from_analysis(cfg, dot_file_dir.joinpath("initial"))

    # Assign distinct names for all the variables in the CFG among different functions and blocks
    # TODO: in the future, we could do the renaming just in the inliner when two block lists are merged
    rename_variables_cfg(cfg)

    if args.visualize:
        dot_from_analysis(cfg, dot_file_dir.joinpath("renamed"))

    if args.cse:
        # Simplifications that solc's optimizer does not apply to grey's code (e.g. return(literal, 0) -> stop())
        apply_cse_rules_cfg(cfg)
        if args.visualize:
            dot_from_analysis(cfg, dot_file_dir.joinpath("cse"))

    if args.inline:
        # We inline the functions
        inline_functions(cfg)
        if args.visualize:
            dot_from_analysis(cfg, dot_file_dir.joinpath("inlined"))

    # We combine and remove the blocks from the CFG
    # Must be the latest step because we might have split blocks after insert jumps and tags
    combine_remove_blocks_cfg(cfg)
    if args.visualize:
        dot_from_analysis(cfg, dot_file_dir.joinpath("combined"))

    if getattr(args, "merge_equivalent", True):
        # We merge the equivalent blocks in the acyclic tails of the CFG. It must be done before
        # introducing the jumps and tags, as the removed blocks would need no tag
        merge_equivalent_blocks_cfg(cfg, getattr(args, "solc_deduplicates", True))
        if args.visualize:
            dot_from_analysis(cfg, dot_file_dir.joinpath("merged_equivalent"))

    if getattr(args, "split_critical_edges", False):
        # No critical edges: the predecessors of a join have a single successor. It must be done before
        # introducing the jumps and tags, so that the edge blocks get their jump
        split_critical_edges_cfg(cfg)
        if args.visualize:
            dot_from_analysis(cfg, dot_file_dir.joinpath("no_critical_edges"))

    # A function call cannot return directly into a join (see split_call_join_edges_cfg)
    split_call_join_edges_cfg(cfg)

    # We introduce the jumps, tags and the stack requirements for each block
    tag_dict = insert_jumps_tags_cfg(cfg)
    if args.visualize:
        dot_from_analysis(cfg, dot_file_dir.joinpath("jumps"))
        # To validate liveness for Moritz cases
        # validate_liveness(cfg)

    # Then we split by sub blocks
    split_blocks_cfg(cfg, tag_dict)
    if args.visualize:
        dot_from_analysis(cfg, dot_file_dir.joinpath("split"))

    if getattr(args, "hoist_return_labels", None) is not None:
        # The return labels are pushed where all the paths towards the call are shared, as solc does, so that solc's
        # block deduplicator merges the shared paths afterwards
        hoist_return_labels_cfg(cfg, args.hoist_return_labels)
        if args.visualize:
            dot_from_analysis(cfg, dot_file_dir.joinpath("return_labels"))

    if args.constants:
        # We replace variables for constants
        # insert_variables_for_constants(cfg)
        insert_variables_for_constants_propagated(cfg)
        if args.visualize:
            dot_from_analysis(cfg, dot_file_dir.joinpath("constants"))

    return tag_dict

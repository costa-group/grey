import copy
import logging
import networkx as nx
from typing import Dict, List, Union, Any
from pathlib import Path

from analysis.fixpoint_analysis import BlockAnalysisInfo, BackwardsAnalysis, state_T
from analysis.abstract_state import digraph_from_block_info
from liveness.liveness_state import LivenessState, LivenessBlockInfo, LivenessBlockInfoSSA
from graphs.algorithms import condense_to_dag
from parser.utils_parser import shorten_name
from parser.cfg_block_list import CFGBlockList
from parser.cfg import CFG

# The information from the CFG consists of a dict with two keys:
# "block_info": a dictionary that contains for each block id a LivenessBlockInfo object
# "terminal_blocks: the list of terminal block ids, in order to start the analysis
cfg_info_T = Dict[str, Union[Dict[str, LivenessBlockInfo], List[str]]]

i = 0

class LivenessAnalysisInfo(BlockAnalysisInfo):
    """
    Assumes self.input_stack and self.block_info are updated accordingly
    """

    def __init__(self, block_info: LivenessBlockInfo, input_state: LivenessState) -> None:
        # We need to copy the input state given, as it corresponds to the output state of a given previous state
        super().__init__(block_info, copy.deepcopy(input_state))

    def propagate_information(self) -> None:
        # If the output state is None, we need to propagate the information from the block and the input state
        if self.in_state is None:
            output_state = LivenessState()
            output_state.live_vars = self.block_info.uses.union(
                self.out_state.live_vars.difference(self.block_info.defines))
            self.in_state = output_state

        # Otherwise, the information from the block is already propagated
        else:
            self.in_state.live_vars = self.block_info.uses.union(
                self.out_state.live_vars.difference(self.block_info.defines))

    def propagate_state(self, current_state: LivenessState) -> None:
        self.out_state.lub(current_state)

    def dot_repr(self) -> str:
        instr_repr = '\n'.join([instr.dot_repr() for instr in self.block_info._instructions])
        assignment_repr = '\n'.join([f"{out_value} = {in_value}"
                                     for out_value, in_value in self.block_info._assignment_dict.items()])

        combined_repr = '\n'.join(repr_ for repr_ in [assignment_repr, instr_repr] if repr_ != "") \
            if assignment_repr != "" or instr_repr != "" else "[]"

        text_repr_list = [f"{self.block_info.block_id}:", f"{self.in_state}", combined_repr, f"{self.out_state}"]
        return '\n'.join(text_repr_list)

    def __repr__(self) -> str:
        text_repr_list = [f"In state: {self.out_state}", f"Out state: {self.in_state}",
                          f"Block info: {self.block_info}"]
        return '\n'.join(text_repr_list)


class LivenessAnalysisInfoSSA(BlockAnalysisInfo):
    """
    Liveness analysis using the SSA representation
    """

    def __init__(self, block_info: LivenessBlockInfoSSA, input_state: LivenessState) -> None:
        # We need to copy the input state given, as it corresponds to the output state of a given previous state
        super().__init__(block_info, copy.deepcopy(input_state))

    def propagate_information(self) -> None:
        # If the output state is None, we need to propagate the information from the block and the input state
        if self.in_state is None:
            output_state = LivenessState()
            self.in_state = output_state

        # Live in variables: remove from the out variables those that are defined (either as part of a
        # normal function or a phi function) and add the ones that are used with no preceding definition
        # 0TODO: check if it is correct (differs slightly from the book)
        self.in_state.live_vars = self.block_info.upward_exposed.union(
            self.out_state.live_vars.difference(self.block_info.defs.union(self.block_info.phi_defs)))

    def propagate_state(self, current_state: LivenessState) -> None:        # Live out variables: the live in variables + those selected from the phi functions
        self.out_state.live_vars = set().union(self.out_state.live_vars,
                                               self.block_info.phi_uses,
                                               current_state.live_vars)

    def dot_repr(self) -> str:
        instr_repr = '\n'.join([instr.dot_repr() for instr in self.block_info._instructions])

        combined_repr = instr_repr if instr_repr != "" else "[]"

        text_repr_list = [f"{self.block_info.block_id}:", f"{self.in_state}", combined_repr, f"{self.out_state}",
                          f"{self.block_info._entries}"]
        # "Phi uses", f"{self.block_info.phi_uses}", "Phi defines:", f"{self.block_info.phi_defs}",
        # "Upward:", f"{self.block_info.upward_exposed}", f"{self.block_info._entries}"
        return '\n'.join(text_repr_list)

    def __repr__(self) -> str:
        text_repr_list = [f"In state: {self.out_state}", f"Out state: {self.in_state}",
                          f"Block info: {self.block_info}"]
        return '\n'.join(text_repr_list)


def construct_analysis_info_from_cfgblocklist(block_list: CFGBlockList) -> cfg_info_T:
    """
    Constructs the info needed for the liveness analysis from a given set of blocks.
    This information consists of a dict with two entries: "block_info", that contains the information needed per
    block and "terminal_blocks", which contain the list of terminal block ids
    """
    # TODO: better initialization without requiring to pass block list for each construction
    block_info = {block_id: LivenessBlockInfoSSA(block, block_list.get_blocks_dict())
                  for block_id, block in block_list.get_blocks_dict().items()}
    # if any(block_id.startswith("extract_byte_array_length") for block_id in block_info.keys()):
    #     print("HERE")
    terminal_blocks = block_list.terminal_blocks.copy()
    return {"block_info": block_info, "terminal_blocks": terminal_blocks}


def construct_analysis_info(cfg: CFG) -> Dict[str, cfg_info_T]:
    """
    Constructs the info needed for the liveness analysis for all the code in a CFG: the main blocks and the functions
    inside (excludes the CFG stored in the subObject field). The dictionary contains an item for each structure
    """
    cfg_info = dict()

    # Construct the cfg information for the blocks in the objects
    for object_id, cfg_object in cfg.objectCFG.items():
        block_list = cfg_object.blocks
        cfg_info[object_id] = construct_analysis_info_from_cfgblocklist(block_list)

        # We also consider the information per function
        for function_name, cfg_function in cfg_object.functions.items():
            cfg_info[function_name] = construct_analysis_info_from_cfgblocklist(cfg_function.blocks)

    return cfg_info


def liveness_analysis_from_vertices(vertices: Dict[str, LivenessBlockInfo],
                                    initial_blocks: List[str]) -> BackwardsAnalysis:
    """
    Performs the liveness analysis and returns a BackwardsAnalysis object with the corresponding info
    """
    liveness_analysis = BackwardsAnalysis(vertices, initial_blocks, LivenessState(), LivenessAnalysisInfoSSA)
    liveness_analysis.analyze()
    return liveness_analysis


def perform_liveness_analysis_from_cfg_info(cfg_info: Dict[str, cfg_info_T]) -> Dict[
    str, Dict[str, LivenessAnalysisInfo]]:
    """
    Returns the information from the liveness analysis for each structure stored in the cfg info
    """
    results = dict()

    for cfg_object_name, cfg_object in cfg_info.items():
        logging.debug(f"Start analysis for {cfg_object_name}...")
        liveness_analysis = liveness_analysis_from_vertices(cfg_object["block_info"],
                                                            cfg_object["terminal_blocks"])
        logging.debug(f"End analysis for {cfg_object_name}...")
        results[cfg_object_name] = liveness_analysis.get_analysis_results()
    logging.debug("RESULTS" + str(results))
    return results


def perform_liveness_analysis(cfg: CFG) -> Dict[str, Dict[str, LivenessAnalysisInfo]]:
    """
    Returns the information from the liveness analysis
    """
    cfg_info = construct_analysis_info(cfg)
    return perform_liveness_analysis_from_cfg_info(cfg_info)


def dot_from_analysis_cfg(cfg: CFG, final_dir: Path = Path(".")) -> Dict[str, Dict[str, LivenessAnalysisInfo]]:
    """
    Returns the information from the liveness analysis and also stores a dot file for each analyzed structure
    in "final_dir"
    """
    cfg_info = construct_analysis_info(cfg)
    results = perform_liveness_analysis_from_cfg_info(cfg_info)
    for component_name, liveness in results.items():
        cfg_info_suboject = cfg_info[component_name]["block_info"]
        digraph = digraph_from_block_info(cfg_info_suboject.values())

        renaming_dict = dict()
        for block_live, live_vars in liveness.items():
            renaming_dict[block_live] = live_vars.dot_repr()
        renamed_digraph = nx.relabel_nodes(digraph, renaming_dict)

        short_component_name = shorten_name(component_name)
        try:
            nx.nx_agraph.write_dot(renamed_digraph, final_dir.joinpath(f"{short_component_name}.dot"))
        except:

            global i

            nx.nx_agraph.write_dot(renamed_digraph, final_dir.joinpath(f"too_long_name_{i}.dot"))
            i += 1

    return results


def dot_from_analysis(cfg: CFG, final_dir: Path = Path("."), position: int = 0) -> Dict[str, Dict[str, LivenessAnalysisInfo]]:
    """
    Returns the information from the liveness analysis and also stores a dot file for each analyzed structure
    in "final_dir"
    """
    sub_cfg = final_dir.joinpath(f"{position}")
    sub_cfg.mkdir(exist_ok=True, parents=True)
    analysis_cfg = dot_from_analysis_cfg(cfg, sub_cfg)
    if cfg.subObjects is not None:
        analysis_cfg.update(dot_from_analysis(cfg.subObjects, final_dir, position + 1))
    return analysis_cfg

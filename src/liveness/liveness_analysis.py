import copy
import logging
from typing import Dict, List, Union, Any
from pathlib import Path

from analysis.fixpoint_analysis import BlockAnalysisInfo, BackwardsAnalysis
from analysis.abstract_state import digraph_from_block_info
from liveness.liveness_state import LivenessState, LivenessBlockInfo
from parser.cfg_block_list import CFGBlockList
from parser.cfg import CFG


# The information from the CFG consists of a dict with two keys:
# "block_info": a dictionary that contains for each block id a LivenessBlockInfo object
# "terminal_blocks: the list of terminal block ids, in order to start the analysis
cfg_info_T = Dict[str, Union[Dict[str, LivenessBlockInfo], List[str]]]


class LivenessAnalysisInfo(BlockAnalysisInfo):
    """
    Assumes self.input_stack and self.block_info are updated accordingly
    """

    def __init__(self, block_info: LivenessBlockInfo, input_state: LivenessState) -> None:
        # We need to copy the input state given, as it corresponds to the output state of a given previous state
        super().__init__(block_info,  copy.deepcopy(input_state))

    def propagate_information(self) -> None:
        # If the output state is None, we need to propagate the information from the block and the input state
        if self.output_state is None:
            output_state = LivenessState()
            output_state.live_vars = self.block_info.uses.union(
                self.input_state.live_vars.difference(self.block_info.defines))
            self.output_state = output_state

        # Otherwise, the information from the block is already propagated
        else:
            self.output_state.live_vars = self.block_info.uses.union(self.input_state.live_vars.difference(self.block_info.defines))

    def dot_repr(self) -> str:
        instr_repr = '\n'.join([instr.dot_repr() for instr in self.block_info._instructions]) \
            if len(self.block_info._instructions) > 0 else "[]"
        text_repr_list = [f"{self.block_info.block_id}:", f"{self.output_state}", instr_repr, f"{self.input_state}"]
        return '\n'.join(text_repr_list)

    def __repr__(self) -> str:
        text_repr_list = [f"Input state: {self.input_state}", f"Output state: {self.output_state}",
                          f"Block info: {self.block_info}"]
        return '\n'.join(text_repr_list)


def construct_analysis_info_from_cfgblocklist(block_list: CFGBlockList) -> cfg_info_T:
    """
    Constructs the info needed for the liveness analysis from a given set of blocks.
    This information consists of a dict with two entries: "block_info", that contains the information needed per
    block and "terminal_blocks", which contain the list of terminal block ids
    """
    block_info = {block_id: LivenessBlockInfo(block) for block_id, block in block_list.get_block_dict().items()}
    terminal_blocks = block_list.get_terminal_blocks()
    return {"block_info": block_info, "terminal_blocks": terminal_blocks}


def construct_analysis_info(cfg: CFG) -> Dict[str, cfg_info_T]:
    """
    Constructs the info needed for the liveness analysis for all the code in a CFG: the main blocks, the functions
    inside and the CFG stored in the subObject field. The dictionary contains an item for each structure
    """
    cfg_info = dict()

    # Construct the cfg information for the blocks in the objects
    for object_id, cfg_object in cfg.objectCFG.items():
        block_list = cfg_object.blocks
        cfg_info[object_id] = construct_analysis_info_from_cfgblocklist(block_list)

        # We also consider the information per function
        for function_name, cfg_function in cfg_object.functions.items():
            cfg_info[function_name] = construct_analysis_info_from_cfgblocklist(cfg_function.blocks)

        subobject = cfg.get_subobject()

        if subobject is not None:
            subobject_cfg_info = construct_analysis_info(subobject)
            cfg_info.update(subobject_cfg_info)

    return cfg_info


def liveness_analysis_from_vertices(vertices: Dict[str, LivenessBlockInfo],
                                    initial_blocks: List[str]) -> BackwardsAnalysis:
    """
    Performs the liveness analysis and returns a BackwardsAnalysis object with the corresponding info
    """
    liveness_analysis = BackwardsAnalysis(vertices, initial_blocks, LivenessState(), LivenessAnalysisInfo)
    liveness_analysis.analyze()
    return liveness_analysis


def perform_liveness_analysis_from_cfg_info(cfg_info: Dict[str, cfg_info_T]) -> Dict[str, Dict[str, LivenessAnalysisInfo]]:
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


def dot_from_analysis(cfg: CFG, final_dir: Path = Path(".")) -> Dict[str, Dict[str, LivenessAnalysisInfo]]:
    """
    Returns the information from the liveness analysis and also stores a dot file for each analyzed structure
    in "final_dir"
    """
    cfg_info = construct_analysis_info(cfg)
    results = perform_liveness_analysis_from_cfg_info(cfg_info)
    for component_name, liveness in results.items():
        cfg_info_suboject = cfg_info[component_name]["block_info"]
        pgv_graph = digraph_from_block_info(cfg_info_suboject.values())

        for block_live, live_vars in liveness.items():
            n = pgv_graph.get_node(block_live)
            n.attr["label"] = live_vars.dot_repr()

        pgv_graph.write(final_dir.joinpath(f"{component_name}.dot"))
    return results

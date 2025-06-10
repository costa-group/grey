import copy
import logging
import networkx as nx
from typing import Dict, List, Union, Any, Tuple
from pathlib import Path
from collections import defaultdict

from global_params.types import cfg_object_T, component_name_T
from analysis.fixpoint_analysis import BlockAnalysisInfo, BackwardsAnalysis, state_T
from analysis.abstract_state import digraph_from_block_info
from liveness.liveness_state import LivenessState, LivenessBlockInfoSSA
from graphs.algorithms import condense_to_dag
from parser.utils_parser import shorten_name
from parser.cfg_block_list import CFGBlockList
from parser.cfg import CFG

# The information from the CFG consists of a dict with two keys:
# "block_info": a dictionary that contains for each block id a LivenessBlockInfo object
# "terminal_blocks: the list of terminal block ids, in order to start the analysis
cfg_info_T = Dict[str, Union[Dict[str, LivenessBlockInfoSSA], List[str]]]

i = 0


class LivenessAnalysisInfoSSA(BlockAnalysisInfo):
    """
    Liveness analysis using the SSA representation
    """

    def __init__(self, block_info: LivenessBlockInfoSSA, input_state: LivenessState) -> None:
        # We need to copy the input state given, as it corresponds to the output state of a given previous state
        super().__init__(block_info, LivenessState())

    def propagate_information(self) -> None:
        # If the output state is None, we need to propagate the information from the block and the input state
        if self.in_state is None:
            output_state = LivenessState()
            self.in_state = output_state

        # Live in variables: remove from the out variables those that are defined (either as part of a
        # normal function or a phi function) and add the ones that are used with no preceding definition
        # TODO: check if it is correct (differs slightly from the book)
        self.in_state.live_vars = self.block_info.upward_exposed.union(self.block_info.phi_defs,
                                                                       self.out_state.live_vars.difference(self.block_info.defs))

    def propagate_state(self, current_state: LivenessState) -> None:        # Live out variables: the live in variables + those selected from the phi functions
        self.out_state.live_vars = set().union(self.out_state.live_vars,
                                               self.block_info.phi_uses,
                                               current_state.live_vars.difference(self.block_info.pred_phi_defs))

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


def construct_analysis_info(cfg: CFG) -> Dict[cfg_object_T, Dict[component_name_T, cfg_info_T]]:
    """
    Constructs the info needed for the liveness analysis for all the code in a CFG: the main blocks and the functions
    inside (excludes the CFG stored in the subObject field). The dictionary contains an item for each structure
    """
    cfg_info = defaultdict(lambda: dict())

    # Construct the cfg information for the blocks in the objects
    for object_id, cfg_object in cfg.objectCFG.items():
        block_list = cfg_object.blocks
        cfg_info[object_id][object_id] = construct_analysis_info_from_cfgblocklist(block_list)

        # We also consider the information per function
        for function_name, cfg_function in cfg_object.functions.items():
            cfg_info[object_id][function_name] = construct_analysis_info_from_cfgblocklist(cfg_function.blocks)

    return cfg_info


def liveness_analysis_from_vertices(vertices: Dict[str, LivenessBlockInfoSSA],
                                    initial_blocks: List[str]) -> BackwardsAnalysis:
    """
    Performs the liveness analysis and returns a BackwardsAnalysis object with the corresponding info
    """
    liveness_analysis = BackwardsAnalysis(vertices, initial_blocks, LivenessState(), LivenessAnalysisInfoSSA)
    liveness_analysis.analyze()
    return liveness_analysis


def perform_liveness_analysis_from_cfg_info(cfg_info: Dict[cfg_object_T, Dict[component_name_T, Dict[str, cfg_info_T]]]) \
        -> Dict[cfg_object_T, Dict[component_name_T, Dict[str, LivenessAnalysisInfoSSA]]]:
    """
    Returns the information from the liveness analysis for each structure stored in the cfg info
    """
    results = defaultdict(lambda: {})

    for cfg_object_name, cfg_object_info in cfg_info.items():
        for cfg_component_name, cfg_component_info in cfg_object_info.items():
            logging.debug(f"Start analysis for {cfg_object_name}...")
            liveness_analysis = liveness_analysis_from_vertices(cfg_component_info["block_info"],
                                                                cfg_component_info["terminal_blocks"])
            logging.debug(f"End analysis for {cfg_object_name}...")
            results[cfg_object_name][cfg_component_name] = liveness_analysis.get_analysis_results()
    logging.debug("RESULTS" + str(results))
    return results


def perform_liveness_analysis(cfg: CFG) -> Dict[cfg_object_T, Dict[cfg_object_T, Dict[str, LivenessAnalysisInfoSSA]]]:
    """
    Returns the information from the liveness analysis for each object and each component in that object
    """
    cfg_info = construct_analysis_info(cfg)
    liveness_info = perform_liveness_analysis_from_cfg_info(cfg_info)

    for object_id, object_dict in liveness_info.items():
        cfg_object = cfg.get_object(object_id)
        for block_list_id, block_list_dict in object_dict.items():
            cfg_blocklist = cfg_object.get_block_list(block_list_id)
            for block_id, block_info in block_list_dict.items():
                generated_liveness = liveness2json(block_info)
                current_block = cfg_blocklist.get_block(block_id)
                json_liveness = cfg_blocklist.get_block(block_id).liveness
                generated_liveness = {key: sorted([element for element in v if not element.startswith("out")]) for key, v in generated_liveness.items()}
                json_liveness = {key: sorted(v) for key, v in json_liveness.items()}

                if current_block.split_instruction is not None and current_block.split_instruction.op == "functionReturn":
                    json_liveness["out"] = list(sorted(set(json_liveness["out"]).difference(current_block.split_instruction.in_args)))

                assert generated_liveness == json_liveness, \
                    f"Do not match {object_id} {block_list_id} {block_id}: Ours {generated_liveness} Theirs {json_liveness}"

def dot_from_analysis_cfg(cfg: CFG, final_dir: Path = Path(".")) -> Dict[cfg_object_T, Dict[component_name_T, Dict[str, LivenessAnalysisInfoSSA]]]:
    """
    Returns the information from the liveness analysis and also stores a dot file for each analyzed structure
    in "final_dir"
    """
    cfg_info = construct_analysis_info(cfg)
    results = perform_liveness_analysis_from_cfg_info(cfg_info)
    for cfg_object_name, object_liveness in results.items():
        for component_name, liveness in object_liveness.items():
            cfg_info_suboject = cfg_info[cfg_object_name][component_name]["block_info"]
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


def dot_from_analysis(cfg: CFG, final_dir: Path = Path("."), positions: List[str] = None) -> Dict[Tuple[str, str], Dict[str, LivenessAnalysisInfoSSA]]:
    """
    Returns the information from the liveness analysis and also stores a dot file for each analyzed structure
    in "final_dir"
    """
    if positions is None:
        positions = ["0"]

    sub_cfg = final_dir.joinpath(f"{'_'.join(positions)}")
    sub_cfg.mkdir(exist_ok=True, parents=True)
    # It only analyzes the code from one CFG level
    analysis_cfg = dot_from_analysis_cfg(cfg, sub_cfg)
    for idx, cfg_object in enumerate(cfg.objectCFG.values()):
        if cfg_object.subObject is not None:
            analysis_cfg.update(dot_from_analysis(cfg_object.subObject, final_dir, positions + [str(i)]))
    return analysis_cfg


def liveness2json(liveness: LivenessAnalysisInfoSSA) -> Dict[str, Any]:
    return {"in": list(liveness.in_state.live_vars), "out": list(liveness.out_state.live_vars)}


def cfg_dict2json_dict(cfg_dict: Dict[str, Dict[str, Dict[str, LivenessAnalysisInfoSSA]]]) -> Dict[str, Dict[str, Dict[str, Any]]]:
    solution = dict()
    for cfg_name, block_list_dict in cfg_dict.items():
        current_cfg = dict()
        for block_list_name, liveness_info_dict in block_list_dict.items():
            print(block_list_name)
            current_block_list = dict()
            for block, liveness_info in liveness_info_dict.items():
                current_block_list[block] = liveness2json(liveness_info)
            current_cfg[block_list_name] = dict(sorted(current_block_list.items()))
        solution[cfg_name] = dict(sorted(current_cfg.items()))
    return solution


def validate_liveness(cfg: CFG) -> Dict[str, Dict[str, LivenessAnalysisInfoSSA]]:
    """
    Returns the information from the liveness analysis and also stores a dot file for each analyzed structure
    in "final_dir"
    """
    # It only analyzes the code from one CFG level
    perform_liveness_analysis(cfg)
    for idx, cfg_object in enumerate(cfg.objectCFG.values()):
        if cfg_object.subObject is not None:
            perform_liveness_analysis(cfg_object.subObject)

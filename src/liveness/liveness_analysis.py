import logging
from typing import Dict, List, Any

from analysis.fixpoint_analysis import BlockAnalysisInfo, BackwardsAnalysis
from liveness.liveness_state import LivenessState, LivenessBlockInfo
from parser.cfg import CFG
from parser.parser import parser_CFG_from_JSON
import networkx


class LivenessAnalysisInfo(BlockAnalysisInfo):
    """
    Assumes self.input_stack and self.block_info are updated accordingly
    """

    def __init__(self, block_info: LivenessBlockInfo, input_state: LivenessState):
        super().__init__(block_info, input_state)

    def propagate_information(self):
        # If the output state is None, we need to propagate the information from the block and the input state
        if self.output_state is None:
            output_state = LivenessState()
            output_state.live_vars = self.input_state.live_vars.union(self.block_info.propagated_variables)
            self.output_state = output_state

        # Otherwise, the information from the block is already propagated
        else:
            self.output_state.lub(self.input_state)

    def __repr__(self):
        text_repr_list = [f"Input state: {self.input_state}", f"Output state: {self.output_state}", f"Block info: {self.block_info}"]
        return '\n'.join(text_repr_list)


def construct_analysis_info(cfg: CFG):
    # TODO: decide how to construct the vertices for each subobject
    cfg_info = dict()
    for object_id, subobject in cfg.objectCFG.items():
        block_list = subobject.blocks
        block_info = {block_id: LivenessBlockInfo(block) for block_id, block in block_list.get_block_dict()}
        terminal_blocks = block_list.get_terminal_blocks()
        cfg_info[subobject.name] = {"block_info": block_info, "terminal_blocks": terminal_blocks}
    logging.debug("Suboject" + str(cfg_info))
    return cfg_info


def liveness_analysis_from_vertices(vertices: Dict[str, LivenessBlockInfo], initial_blocks: List[str]) -> BackwardsAnalysis:
    liveness_analysis = BackwardsAnalysis(vertices, initial_blocks, LivenessState(), LivenessAnalysisInfo)
    liveness_analysis.analyze()
    return liveness_analysis


def perform_liveness_analysis_from_cfg_info(cfg_info: Dict[str, Any]):
    results = dict()

    for cfg_object_name, cfg_object in cfg_info.items():
        logging.debug(f"Start analysis for {cfg_object_name}...")
        liveness_analysis = liveness_analysis_from_vertices(cfg_object["block_info"],
                                                            cfg_object["terminal_blocks"])
        logging.debug(f"End analysis for {cfg_object_name}...")
        results[cfg_object_name] = liveness_analysis.get_analysis_results()
        logging.debug(liveness_analysis.print_analysis_results())
    logging.debug("RESULTS" + str(results))
    return results


def perform_liveness_analysis(cfg: CFG):
    cfg_info = construct_analysis_info(cfg)
    logging.debug("CFG Info" + str(cfg_info))
    return perform_liveness_analysis_from_cfg_info(cfg_info)


def dot_from_analysis(cfg: CFG):
    cfg_info = construct_analysis_info(cfg)
    results = perform_liveness_analysis_from_cfg_info(cfg_info)
    for component_name, liveness in results.items():
        cfg_info_suboject = cfg_info[component_name]
        print("CFG info", cfg_info)
        print("Liveness", liveness)


if __name__ == "__main__":
    if_json = {"object": {"blocks": [{"exit": "Block0Exit", "id": "Block0",
                                      "instructions": [{"in": ["0x0101", "0x01"], "op": "sstore", "out": []},
                                                       {"in": ["0x00"], "op": "calldataload", "out": ["_27"]}],
                                      "type": "BuiltinCall"},
                                     {"cond": ["_27"], "exit": ["Block1", "Block2"], "id": "Block0Exit",
                                      "instructions": [],
                                      "type": "ConditionalJump"},
                                     {"exit": "Block1Exit", "id": "Block1", "instructions": [
                                         {"in": ["0x03", "0x03"], "op": "sstore", "out": []}],
                                      "type": "BuiltinCall"},
                                     {"exit": ["Block1"], "id": "Block1Exit", "instructions": [],
                                      "type": "MainExit"},
                                     {"exit": "Block2Exit", "id": "Block2",
                                      "instructions": [{"in": ["0x0202", "0x02"], "op": "sstore", "out": []}],
                                      "type": "BuiltinCall"},
                                     {"exit": ["Block1"], "id": "Block2Exit", "instructions": [], "type": "Jump"}],
                          "functions": {}}, "subObjects": {}, "type": "Object"}
    if_cfg = parser_CFG_from_JSON(if_json)
    dot_from_analysis(if_cfg)

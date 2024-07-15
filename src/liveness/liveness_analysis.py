import logging
from typing import Dict
from analysis.fixpoint_analysis import BlockAnalysisInfo, Analysis
from liveness.liveness_state import LivenessState, LivenessBlockInfo
from parser.cfg import CFG


class LivenessAnalysisInfo(BlockAnalysisInfo):
    """
    Assumes self.input_stack and self.block_info are updated accordingly
    """

    def propagate_information(self):
        # If the output state is None, we need to propagate the information from the block and the input state
        if self.output_state is None:
            output_state = LivenessState()
            output_state.live_vars = self.input_state.live_vars.union(self.block_info.propagated_variables)
            self.output_state = output_state

        # Otherwise, the information from the block is already propagated
        else:
            self.output_state.lub(self.input_state)


def construct_vertices(cfg: CFG):
    # TODO: decide how to construct the vertices for each subobject
    for object_id, subobject in cfg.objectCFG.items():
        return {block_id: LivenessBlockInfo(block) for block_id, block in subobject.blocks.items()}


def liveness_analysis_from_vertices(vertices: Dict[str, LivenessBlockInfo], initial_block: str) -> Analysis:
    liveness_analysis = Analysis(vertices, initial_block, LivenessState(), LivenessAnalysisInfo)
    liveness_analysis.analyze()
    return liveness_analysis


def perform_liveness_analysis(cfg: CFG):
    logging.debug("Start analysis...")
    vertices = construct_vertices(cfg)
    logging.debug("Start analysis...")
    liveness_analysis = liveness_analysis_from_vertices(vertices, "Block0")
    return liveness_analysis.get_analysis_results()

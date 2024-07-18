"""
Original Author: gromandiez

Module that serves as the skeleton for fixpoint-based analysis. Used for implementing the liveness analysis to detect
which variables must be reused. Adapted from
https://github.com/costa-group/EthIR/blob/fea70e305801258c3ec50b47e1251237063d3fcd/ethir/analysis/fixpoint_analysis.py
"""

import logging
from analysis.abstract_state import AbstractState, AbstractBlockInfo
from typing import Dict, List, Any, Optional, Type
from abc import ABC, abstractmethod
from parser.cfg_block import CFGBlock

# Relevant types to consider in the algorithm
block_T = AbstractBlockInfo
block_id_T = str
var_T = str
state_T = AbstractState


class BlockAnalysisInfo(ABC):
    """
    Class that contains the information needed to manage and propagate the information
    for a block in a given analysis. A concrete class has to implement the method
    of propagation
    """

    # Creates an initial abstract state with the received information
    def __init__(self, block_info: block_T, input_state: state_T):
        self.block_info: block_T = block_info
        self.input_state: state_T = input_state
        self.output_state: Optional[state_T] = None

    def get_input_state(self) -> state_T:
        return self.input_state

    def get_output_state(self) -> state_T:
        return self.output_state  

    def revisit_block(self, current_state: state_T):
        """
        Evaluates if a block need to be revisited or not
        """
        logging.debug("Comparing...")
        logging.debug("Stored state: " + str(self))
        logging.debug("Current state: " + str(current_state))

        # If the state being considered is leq than the one
        # currently stored, then we return False
        leq = current_state.leq(self.input_state)
        logging.debug("Result: " + str(leq))

        if leq:
            return False

        self.input_state.lub(current_state)
        return True

    @abstractmethod
    def propagate_information(self):
        """
        For a more efficient implementation, we consider propagate information as an abstract
        method. This way, we don't need to create and destroy an output state each time it is updated
        """
        raise NotImplementedError

    def process_block(self):
        # We start with the initial state of the block
        current_state = self.input_state
        id_block = self.block_info.block_id

        logging.debug("Processing " + str(id_block) + " :: " + str(current_state))
        self.propagate_information()
        logging.debug("Resulting state " + str(id_block) + " :: " + str(self.output_state))

    def __repr__(self):
        textual_repr = str(self.block_info.block_id) + "." + "Input State: " + str(self.input_state) + \
                       ". Output State: " + str(self.output_state) + "."
        return textual_repr


class BackwardsAnalysis:

    def __init__(self, vertices: Dict[block_id_T, block_T], initial_blocks: List[block_id_T], initial_state: state_T,
                 analysis_info_constructor):
        self.vertices = vertices
        self.pending = initial_blocks
        self.constructor = analysis_info_constructor

        logging.debug("Vertices" + str(self.vertices))
        logging.debug("Pending" + str(self.pending))

        # Info from the analysis for each block
        self.blocks_info: Dict[block_id_T, BlockAnalysisInfo] = \
            {block: analysis_info_constructor(vertices[block], initial_state) for block in initial_blocks}

    def analyze(self):
        while len(self.pending) > 0:
            block_id = self.pending.pop()

            # Process the block
            block_info = self.blocks_info[block_id]

            block_info.process_block()

            # Returns the output state of the corresponding block
            output_state = block_info.get_output_state()

            # Propagates the information
            self.process_jumps(block_id, output_state)

    def process_jumps(self, block_id: block_id_T, input_state: state_T):
        """
        Propagates the information according to the blocks and the input state considering all blocks in comes from
        """
        logging.debug("Process JUMPS")
        logging.debug("Input State: " + str(input_state))
        basic_block = self.vertices[block_id]
        logging.debug("COMES " + str(basic_block.comes_from))
        for previous_block in basic_block.comes_from:
            logging.debug(f"Comes from {previous_block}")

            if self.blocks_info.get(previous_block) is None:
                self.pending.append(previous_block)
                # print("************")
                # print(block_id)
                # print(jump_target)
                # print(self.vertices[block_id].display())
                self.blocks_info[previous_block] = self.constructor(self.vertices[previous_block], input_state)

            elif self.blocks_info.get(previous_block).revisit_block(input_state):
                #print("REVISITING BLOCK!!! " + str(jump_target))
                self.pending.append(previous_block)

    def get_analysis_results(self):
        return self.blocks_info

    def print_analysis_results(self):
        text_repr = []
        for block_id, block in self.blocks_info.items():
            text_repr.append("Block id " + block_id)
            text_repr.append(str(block))
        return '\n'.join(text_repr)

    def get_block_results(self, block_id):
        if str(block_id).find("_") == -1:
            block_id = int(block_id)
        return self.blocks_info[block_id]

    def __repr__(self): 
        for id_ in self.blocks_info:
            print(str(self.blocks_info[id_]))
        return ""

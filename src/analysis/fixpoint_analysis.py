"""
Original Author: gromandiez

Module that serves as the skeleton for fixpoint-based analysis. Used for implementing the liveness analysis to detect
which variables must be reused. Adapted from
https://github.com/costa-group/EthIR/blob/fea70e305801258c3ec50b47e1251237063d3fcd/ethir/analysis/fixpoint_analysis.py
"""

import logging
from analysis.abstract_state import AbstractState, AbstractBlockInfo
from typing import Dict, List, Any, Optional
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

    def revisit_block(self, input_state: state_T):
        """
        Evaluates if a block need to be revisited or not
        """
        logging.debug("Comparing...")
        logging.debug("Current input state: " + str(self))
        logging.debug("Compared state: " + str(input_state))
        leq = input_state.leq(self.input_state)
        logging.debug("Result: " + str(leq))

        if leq:
            return False

        self.input_state.lub(input_state)
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


class Analysis:

    def __init__(self, vertices: Dict[block_id_T, block_T], initial_block: block_id_T, initial_state: state_T,
                 analysis_info_constructor):
        self.vertices = vertices
        self.pending = [initial_block]
        self.constructor = analysis_info_constructor

        # Info from the analysis for each block
        self.blocks_info: Dict[block_id_T, BlockAnalysisInfo] = {initial_block: analysis_info_constructor(vertices[initial_block], initial_state)}

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
        Propagates the information according to the blocks and the input state
        """
        logging.debug("Process JUMPS")
        logging.debug("Input State: " + str(input_state))
        basic_block = self.vertices[block_id]

        if basic_block.block_type == "terminal" or basic_block.block_type == "mainExit":
            return 

        jump_target = basic_block.jumps_to

        if jump_target != 0 and jump_target != -1:
            if self.blocks_info.get(jump_target) is None:
                self.pending.append(jump_target)
                # print("************")
                # print(block_id)
                # print(jump_target)
                # print(self.vertices[block_id].display())
                self.blocks_info[jump_target] = self.constructor(self.vertices[jump_target], input_state)

            elif self.blocks_info.get(jump_target).revisit_block(input_state):
                #print("REVISITING BLOCK!!! " + str(jump_target))
                self.pending.append(jump_target)

        jump_target = basic_block.falls_to

        if jump_target is not None:
            if self.blocks_info.get(jump_target) is None:
                self.pending.append(jump_target)
                self.blocks_info[jump_target] = self.constructor(self.vertices[jump_target], input_state)

            elif self.blocks_info.get(jump_target).revisit_block(input_state):
                self.pending.append(jump_target)

    def get_analysis_results(self):
        return self.blocks_info

    def get_block_results(self, block_id):
        if str(block_id).find("_") == -1:
            block_id = int(block_id)
        return self.blocks_info[block_id]

    def __repr__(self): 
        for id_ in self.blocks_info:
            print(str(self.blocks_info[id_]))
        return ""
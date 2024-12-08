"""
Original Author: gromandiez

Module that serves as the skeleton for fixpoint-based analysis. Used for implementing the liveness analysis to detect
which variables must be reused. Adapted from
https://github.com/costa-group/EthIR/blob/fea70e305801258c3ec50b47e1251237063d3fcd/ethir/analysis/fixpoint_analysis.py
"""

import logging
from global_params.types import block_id_T
from analysis.abstract_state import AbstractState, AbstractBlockInfo
from typing import Dict, List, Any, Optional, Type
from abc import ABC, abstractmethod

# Relevant types to consider in the algorithm
block_T = AbstractBlockInfo
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
        self._out: state_T = input_state
        self._in: Optional[state_T] = None

    @property
    def out_state(self) -> state_T:
        return self._out

    @out_state.setter
    def out_state(self, value: state_T) -> None:
        self._out = value

    @property
    def in_state(self) -> state_T:
        return self._in

    @in_state.setter
    def in_state(self, value: state_T) -> None:
        self._in = value

    def revisit_block(self, current_state: state_T) -> bool:
        """
        Evaluates if a block need to be revisited or not
        """
        logging.debug("Comparing...")
        logging.debug(f"Block name: {self.block_info.block_id}")
        logging.debug("Stored state: " + str(self.out_state))
        logging.debug("Current state: " + str(current_state))
        
        
        #Giulia
        #print(f"Comparing...")
        #print(f"Block name: {self.block_info.block_id}")
        #print(f"Stored state: " + str(self.out_state))
        #print(f"Current state: " + str(current_state))
        #Giulia

        # If the state being considered is leq than the one
        # currently stored, then we return False
        leq = current_state.leq(self.out_state)
        logging.debug("Result: " + str(leq))
        
        #Giulia
        #print(f"Result: " + str(leq))
        #Giulia

        return not leq

    @abstractmethod
    def propagate_state(self, current_state: state_T) -> None:
        """
        The state propagation backwards is also declared as an abstract method
        """
        raise NotImplementedError

    @abstractmethod
    def propagate_information(self) -> None:
        """
        For a more efficient implementation, we consider propagate information as an abstract
        method. This way, we don't need to create and destroy an output state each time it is updated
        """
        raise NotImplementedError

    def process_block(self) -> None:
        # We start with the initial state of the block
        current_state = self.out_state
        id_block = self.block_info.block_id

        logging.debug("Processing " + str(id_block) + " :: " + str(current_state))
        
        #Giulia
        #print(f"Processing " + str(id_block) + " :: " + str(current_state))
        #Giulia
        
        self.propagate_information()
        logging.debug("Resulting state " + str(id_block) + " :: " + str(self._in))
        
        #Giulia
        #print(f"Resulting state " + str(id_block) + " :: " + str(self._in))
        #Giulia

    def __repr__(self):
        textual_repr = str(self.block_info.block_id) + "." + "Input State: " + str(self._out) + \
                       ". Output State: " + str(self._in) + "."
                                            
        #Giulia
        #print(textual_repr)
        #Giulia  
                     
        return textual_repr


class BackwardsAnalysis:
    """
    Modification of the traditional Backward propagation analysis to consider phi functions. See Page 110 of
    "SSA-based Compiler Design (2022)". The change comes in the propagation, as we have to consider which value from
    the phi function corresponds to the block
    """

    def __init__(self, vertices: Dict[block_id_T, block_T], initial_blocks: List[block_id_T], initial_state: state_T,
                 analysis_info_constructor):
        self.vertices = vertices
        self.pending = initial_blocks
        self.constructor = analysis_info_constructor

        # Info from the analysis for each block
        self.blocks_info: Dict[block_id_T, BlockAnalysisInfo] = \
            {block: analysis_info_constructor(vertices[block], initial_state) for block in initial_blocks}

    def analyze(self) -> None:
        while len(self.pending) > 0:
            block_id = self.pending.pop()
            logging.debug(f"Processing {block_id}")
            
            #Giulia
            #print(f"\n BackWordsAnalysys \n Processing {block_id}")
            #Giulia

            # Process the block
            block_info = self.blocks_info[block_id]

            block_info.process_block()

            # Returns the in state of the corresponding block
            in_state = block_info.in_state
            
            #Giulia
            #print(f"\n Returns the in state of the corresponding block {block_id}: {in_state}")
            #Giulia

            # Propagates the information
            self.process_jumps(block_id, in_state)

    def process_jumps(self, block_id: block_id_T, input_state: state_T) -> None:
        """
        Propagates the information according to the blocks and the input state considering all blocks in comes from
        """
        logging.debug("Process JUMPS")
        logging.debug("Input State: " + str(input_state))
        
        #Giulia
        #print(f"\n Process JUMPS")
        #print(f"\n Input State: " + str(input_state))
        #Giulia
        
        basic_block = self.vertices[block_id]
        logging.debug("COMES " + str(basic_block.comes_from))
        
        #Giulia
        #print(f"COMES " + str(basic_block.comes_from))
        #Giulia        
        
        for previous_block in basic_block.comes_from:
            logging.debug(f"Comes from {previous_block}")
            
            #Giulia
            #print(f"\n Comes from {previous_block}")
            #Giulia
            
            previous_block_info = self.blocks_info.get(previous_block)

            # We create the corresponding information
            if previous_block_info is None:
                self.pending.append(previous_block)
                self.blocks_info[previous_block] = self.constructor(self.vertices[previous_block], input_state)

            # If we decide to revisit the block, we propagate the state and
            # then include it as part of the pending blocks
            elif previous_block_info.revisit_block(input_state):
                previous_block_info.propagate_state(input_state)
                self.pending.append(previous_block)

    def get_analysis_results(self) -> Dict[block_id_T, BlockAnalysisInfo]:
        return self.blocks_info

    def print_analysis_results(self) -> str:
        text_repr = []
        for block_id, block in self.blocks_info.items():
            text_repr.append("Block id " + block_id)
            text_repr.append(str(block))
        return '\n'.join(text_repr)

    def __repr__(self): 
        for id_ in self.blocks_info:
            print(str(self.blocks_info[id_]))
        return ""

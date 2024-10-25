"""
Module that contains the necessary methods for a set of blocks that correspond to the same subobject
(either for cfg objects or functions)
"""

from typing import List, Dict, Any, Tuple
import logging
import networkx
from global_params.types import block_id_T
from parser.cfg_block import CFGBlock, include_function_call_tags
from parser.constants import split_block


class CFGBlockList:
    """
    Object that manages a list of blocks that are connected through an object or function
    """

    def __init__(self, name: block_id_T):
        self.name: block_id_T = name
        self.blocks: Dict[block_id_T, CFGBlock] = {}
        self.graph = None
        self.start_block = None
        self.terminal_blocks: List[block_id_T] = []
        self.block_tags_dict = {}
        self.entry_dict: Dict[str, Tuple[str, str]] = dict()

    def add_block(self, block: CFGBlock) -> None:
        block_id = block.get_block_id()

        # Assuming the first block corresponds to the entry point
        if not self.blocks:
            self.start_block = block_id

        # The blocks that return in the CFG correspond to function returns and main exits
        if block.get_jump_type() in ["FunctionReturn", "mainExit"]:
            self.terminal_blocks.append(block_id)

        if block_id in self.blocks:
            logging.warning("You are overwritting an existing block")

        self.graph = None
        self.blocks[block_id] = block

    def get_block(self, block_id: block_id_T) -> CFGBlock:
        return self.blocks[block_id]

    def remove_block(self, block_id: block_id_T) -> None:
        if block_id not in self.blocks:
            raise ValueError(f"{block_id} does not appear in the block list {self.name}")
        if block_id == self.start_block:
            raise ValueError(f"Attempting to remove start block {block_id} in block list {self.name}")
        self.blocks.pop(block_id)
        self.terminal_blocks = [terminal_block for terminal_block in self.terminal_blocks if terminal_block == block_id]

    def get_blocks_dict(self):
        return self.blocks

    def build_spec(self, block_tag_idx, return_function_element = 0):
        """
        Build specs from blocks
        """
        list_spec = {}

        valid_blocks =  self.blocks
        
        for b in valid_blocks:
            block = self.blocks[b]
            spec, out_idx, block_tag_idx  = block.build_spec(self.block_tags_dict, block_tag_idx)

            if b.get_jump_type() == "sub_block":
                split_block = self.blocks[b.get_falls_to()]

                split_instr = split_block.get_instructions()[0]
                #It only has one instruction

                if split_instr.get_op() not in split_block:
                    #It is a call to a function
                    spec, out_idx = include_function_call_tags(split_instr, out_idx, spec)
            
            list_spec[b.get_block_id()] = spec

        return list_spec, block_tag_idx

    def to_graph(self) -> networkx.DiGraph:
        """
        Creates a networkx.DiGraph from the blocks information
        """
        if self.graph is None:
            graph = networkx.DiGraph()
            graph.add_nodes_from(self.blocks.keys())
            for block_id, block in self.blocks.items():
                for successor in [block.get_jump_to(), block.get_falls_to()]:
                    if successor is not None:
                        graph.add_edge(block_id, successor)
            return graph
        return self.graph

    def to_graph_comes_from(self) -> networkx.DiGraph:
        """
        Creates a networkx.DiGraph from the comes_from
        """
        if self.graph is None:
            graph = networkx.DiGraph()
            graph.add_nodes_from(self.blocks.keys())
            for block_id, block in self.blocks.items():
                for predecessor in block.get_comes_from():
                    graph.add_edge(predecessor, block_id)
            return graph
        return self.graph


    def to_json(self) -> List[Dict[str, Any]]:
        """
        List of dicts for each block
        """
        json_blocks = []
        for block in self.blocks.values():
            json_block, json_jump_block = block.get_as_json()
            json_blocks.append(json_block)
            json_blocks.append(json_jump_block)

        return json_blocks

    def __repr__(self):
        text_repr = []
        for block_id, block in self.blocks.items():
            text_repr.append(' '.join([str(block_id), str(block.get_instructions())]))
        return '\n'.join(text_repr)

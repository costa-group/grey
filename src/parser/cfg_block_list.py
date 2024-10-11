"""
Module that contains the necessary methods for a set of blocks that correspond to the same subobject
(either for cfg objects or functions)
"""

from typing import List, Dict, Any, Tuple
import networkx
from parser.cfg_block import CFGBlock, include_function_call_tags
from parser.constants import split_block


class CFGBlockList:
    """
    Object that manages a list of blocks that connected
    """

    def __init__(self):
        self.blocks: Dict[str, CFGBlock] = {}
        self.graph = None
        self.start_block = None
        self.block_tags_dict = {}
        self.entry_dict: Dict[str, Tuple[str, str]] = dict()

    def add_block(self, block: CFGBlock) -> None:
        block_id = block.get_block_id()

        # Assuming the first block corresponds to the entry point
        if not self.blocks:
            self.start_block = block_id

        if block_id in self.blocks:
            if block_id in self.blocks:
                print("WARNING: You are overwritting an existing block")
        self.graph = None
        self.blocks[block_id] = block

    def get_block(self, block_id: str):
        return self.blocks[block_id]

    def get_blocks_dict(self):
        return self.blocks

    def get_terminal_blocks(self) -> List[str]:
        """
        Terminal blocks are either mainExit and terminal blocks
        """
        return [block.block_id for block in self.blocks.values() if block.get_jump_type() in
                ["mainExit", "terminal", "FunctionReturn"]]

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
            graph = networkx.DiGraph(self.blocks)
            for block_id, block in self.blocks.items():
                for successor in [block.get_jump_to(), block.get_falls_to()]:
                    if successor is not None:
                        graph.add_edge(block_id, successor)
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

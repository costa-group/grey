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
from graphs.cfg import compute_loop_nesting_forest_graph
from graphs.algorithms import compute_dominance_tree


class CFGBlockList:
    """
    Object that manages a list of blocks that are connected through an object or function
    """
    
    def __init__(self, name: block_id_T):
        self.name: block_id_T = name
        self.blocks: Dict[block_id_T, CFGBlock] = {}
        self.graph = None
        self.start_block = None
        self._terminal_blocks: List[block_id_T] = []
        self._function_return_blocks: List[block_id_T] = []
        self.block_tags_dict = {}
        self.assigment_dict = {}

        # Graph forms for the following data structures
        self._dominant_tree = None
        self._loop_nesting_forest = None
        
    @property
    def terminal_blocks(self) -> List[block_id_T]:
        return self._terminal_blocks

    @property
    def function_return_blocks(self) -> List[block_id_T]:
        return self._function_return_blocks

    def add_block(self, block: CFGBlock, is_start_block: bool = False) -> None:
        """
        Adds a block to the block list, updating the corresponding internal attributes accordingly.
        The flag 'is_start_block' indicates whether the new added block corresponds to the start block,
        assuming no start block is already assigned.
        """
        block_id = block.get_block_id()

        # Assuming the first block corresponds to the entry point
        if not self.blocks or is_start_block:
            assert self.start_block is None, f"Trying to set the start block of block list {self.name} to {block_id} " \
                                             f"when already assigned to {self.start_block}"
            self.start_block = block_id

        # The blocks that return in the CFG correspond to function returns and main exits
        if block.get_jump_type() in ["FunctionReturn", "mainExit", "terminal"]:
            self._terminal_blocks.append(block_id)

            if block.get_jump_type() in ["FunctionReturn"]:
                self._function_return_blocks.append(block_id)

        if block_id in self.blocks:
            logging.warning(f"You are overwritting an existing block: {block_id}")

        self.graph = None
        self.blocks[block_id] = block

    def get_block(self, block_id: block_id_T) -> CFGBlock:
        return self.blocks[block_id]

    def remove_block(self, block_id: block_id_T) -> None:
        if block_id not in self.blocks:
            raise ValueError(f"{block_id} does not appear in the block list {self.name}")

        if block_id == self.start_block:
            self.start_block = None

        self.blocks.pop(block_id)

        # Remove the corresponding terminal block
        self._terminal_blocks = [terminal_block for terminal_block in self._terminal_blocks
                                 if terminal_block != block_id]

        # Same for function return
        self._function_return_blocks = [return_block for return_block in self._function_return_blocks
                                        if return_block != block_id]

    def rename_blocks(self, renaming_dict: Dict[block_id_T, block_id_T]):
        new_block_dict = dict()
        for old_block_id, block in self.blocks.items():
            new_block_id = renaming_dict.get(old_block_id, old_block_id)
            block.set_block_id(new_block_id)
            block.rename_cfg(renaming_dict)
            new_block_dict[new_block_id] = block

        self.blocks = new_block_dict

        self._terminal_blocks = [renaming_dict.get(terminal_block, terminal_block)
                                 for terminal_block in self._terminal_blocks]

        self._function_return_blocks = [renaming_dict.get(return_block, return_block)
                                        for return_block in self._function_return_blocks]

        self.start_block = renaming_dict.get(self.start_block, self.start_block)

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

    
    def add_assigment(self, in_value:str, out_var: str) -> None:
        self.assigment_dict[out_var] = in_value


    def set_assigment(self, assigment_dict: Dict[str,str]) -> None:
        self.assigment_dict = assigment_dict

    def get_assigment_dict(self) -> Dict[str,str]:
        return self.assigment_dict
        
        
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
            self.graph = graph
        return self.graph

    @property
    def dominant_tree(self):
        if self._dominant_tree is None:
            self._dominant_tree = compute_dominance_tree(self.to_graph(), self.start_block)
        return self._dominant_tree

    @property
    def loop_nesting_forest(self):
        if self._loop_nesting_forest is None:
            self._loop_nesting_forest = compute_loop_nesting_forest_graph(self.to_graph())
        return self._loop_nesting_forest

    def to_graph_info(self) -> networkx.DiGraph:
        """
        Creates a networkx.DiGraph from the blocks information. Useful for debugging
        """
        graph = networkx.DiGraph()
        graph.add_nodes_from(self.blocks.keys())
        for block_id, block in self.blocks.items():
            for successor in [block.get_jump_to(), block.get_falls_to()]:
                if successor is not None:
                    graph.add_edge(block_id, successor)

        relabel_dict = {block_name: '\n'.join([block.get_block_id(), *[instr.dot_repr() for instr in block.get_instructions()]])
                        for block_name, block in self.blocks.items()}
        renamed_digraph = networkx.relabel_nodes(graph, relabel_dict)

        return renamed_digraph


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


    def get_stats(self):
        total_blocks = len(self.blocks.values())
        total_instructions = 0
        
        for _block_name, block_object in self.blocks.items():
            instructions = block_object.get_stats()
            total_instructions+= instructions
            
        return total_blocks, total_instructions


    def dfs(self):
        visited = set()
        stack = [self.name+"_"+"Block0"]
        order = []

        while stack:
            node = stack.pop()
            if node not in visited:
                visited.add(node)
                order.append(node)
                
                block_node = self.blocks.get(node, None)
                if block_node == None:
                    print(node)
                    print(self.name)
                    print(self.blocks.keys())
                    raise Exception ("ERROR in DFS")
                succs = block_node.successors
                stack.extend(reversed(succs))
    
        return order


    def translate_opcodes(self,objects_keys):
        block_list_dfs = self.dfs()
        
        next_idx = 0
        subobjects_idx = {}

        for block_id in block_list_dfs[::-1]:
            block = self.blocks[block_id]
            next_idx = block.translate_opcodes(objects_keys,next_idx,self.name,subobjects_idx)
    
    def __repr__(self):
        text_repr = []
        for block_id, block in self.blocks.items():
            text_repr.append(' '.join([str(block_id), str(block.get_instructions())]))
        return '\n'.join(text_repr)

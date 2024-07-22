from typing import Dict
from parser.cfg_block_list import CFGBlockList


class CFGFunction:
    def __init__(self, name, args, ret, entry, blocks: CFGBlockList):
        self.name = name
        self.blocks: CFGBlockList = blocks
        self.arguments = args
        self.returns = ret
        self.entry = entry
        self.exits = []

    def get_block(self, block_id):
        return self.blocks.get_block(block_id)

    def get_name(self):
        return self.name

    def get_arguments(self):
        return self.arguments

    def get_blocks_dict(self):
        return self.blocks.get_block_dict()
    
    def get_exit_points(self):
        return self.exits

    def get_entry_point(self):
        return self.entry

    def get_return_arguments(self):
        return self.returns

    def add_exit_point(self, block_id):
        if block_id not in self.exits:
            self.exits.append(block_id)

    def build_spec(self):
        return self.blocks.build_spec()

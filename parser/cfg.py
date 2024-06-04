from parser.cfg_block import CFGBlock


class CFG:
    def __init__(self, contract_name: str):
        self.contract_name = contract_name
        self.blocks = {}


    def add_block(self, block: CFGBlock)-> None:
        block_id = block.block_id()

        if block_id in self.blocks:
            print("WARNING: You are overwritting an existing block")

        self.blocks[block_id] = block

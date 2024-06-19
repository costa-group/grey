from parser.cfg_block import CFGBlock


class CFG:
    def __init__(self, file_name: str, nodeType : str):
        self.file_name = file_name
        self.nodeType = nodeType
        self.objectCFG = {}
        self.blocks = {}
        self.objectCFG["blocks"] = self.blocks
        self.subObjects = {}

    def add_block(self, block: CFGBlock)-> None:
        block_id = block.get_block_id()

        if block_id in self.blocks:
            print("WARNING: You are overwritting an existing block")

        self.blocks[block_id] = block

    def add_object_name(self, name: str) -> None:
        self.objectCFG["name"] = name


    def add_subobjects(self, subobjects):
        self.subObjects = subobjects

    def get_block(self, block_id):
        return self.blocks[block_id]

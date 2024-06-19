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



    def get_as_json(self):
        json_cfg = {}
        json_cfg["nodeType"] = self.nodeType

        json_blocks = []
        for block in self.blocks:
            json_block, json_jump_block = block.get_as_json()
            json_blocks.append(json_block)
            json_blocks.append(json_jump_block)

        json_obj = {}
        json_obj["blocks"] = json_blocks
        json_obj["name"] = self.objectCFG["name"] 
        
        json_cfg["object"] = json_obj
        json_cfg["subObjects"] = self.subObjects

        return json_cfg

    def __str__(self):
        return self.get_as_json()

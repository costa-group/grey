from parser.cfg_block import CFGBlock

class CFGFunction:
    def __init__(self,name, args, ret, entry):
        self.name = name
        self.blocks : Dict[str, CFGBlock] = {}
        self.arguments = args
        self.returns = ret
        self.entry = entry
        self.exits = []


    def add_block(self, block:CFGBlock) -> None:
        block_id = block.get_block_id()

        if block_id in self.blocks:
            if block_id in self.blocks:
                print("WARNING: You are overwritting an existing block")

        self.blocks[block_id] = block

    def get_block(self, block_id):
        return self.blocks[block_id]

    def get_name(self):
        return self.name

    def get_arguments(self):
        return self.arguments

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
        list_spec = []
        for b in self.blocks:
            block = self.blocks[b]
            spec = block.build_spec()
            list_spec.append(spec)
            
        return list_spec


from parser.cfg_instruction import CFGInstruction


class CFGBlock:
    """
    Class for representing a cfg block
    """
    
    def __init__(self, cname : str, identifier : str, name : str):
        self.contract_name = cname
        self.block_id = identifier
        self.block_name = name
        self._instructions = []
        # minimum size of the source stack
        self.source_stack = 0
        self._jump_type = None
        self._jump_to = None
        self._falls_to = None
        
    @property
    def contract_name(self) -> str:
        return self.contract_name

    @property
    def block_id(self) -> str:
        return self.block_id


    @property
    def block_name(self) -> str:
        return self.block_name

    @property
    def instructions(self) -> [CFGInstruction]:
        return self.contract_name

    @property
    def source_stack(self) -> int:
        return self.source_stack

    @property
    def jump_type(self) -> str:
        return self._jump_type

    @property
    def jump_to(self) -> str:
        return self._jump_to

    @property
    def falls_to(self) -> str:
        return self._falls_to




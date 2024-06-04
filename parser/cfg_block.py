from parser.cfg_instruction import CFGInstruction
from typing import List

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

        
    def get_contract_name(self) -> str:
        return self.contract_name

    @property
    def block_id(self) -> int:
        return self.block_id


    @property
    def block_name(self) -> str:
        return self.block_name

    @property
    def instructions(self) -> List[CFGInstruction]:
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


    @instructions.setter
    def instructions(self, new_instructions: List[CFGInstruction]) -> None:
        self._instructions = new_instructions

        # Then we update the source stack size
        # TODO
        #self.source_stack = utils.compute_stack_size(map(lambda x: x.disasm, self.instructions_to_optimize_bytecode()))

    def add_instruction(self, new_instr: CFGInstruction) -> None:
        self._instructions.add(new_instr)
        # TODO
        #self.source_stack = utils.compute_stack_size(map(lambda x: x.disasm, self.instructions_to_optimize_bytecode()))

    @jump_type.setter
    def jump_type(self, t : str) -> None:
        if t not in ["conditional","unconditional","terminal", "falls_to"]:
            raise Exception("Wrong jump type")
        else:
            self._jump_type = t
    
    @jump_to.setter
    def jump_to(self, blockId : str) -> None:
        self._jump_to = blockId

    @falls_to.setter
    def falls_to(self, blockId :str) -> None:
        self._falls_to = blockId

    @property
    def length(self) -> int:
        return len(self._instructions)

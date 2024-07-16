"""
Module that implements the state needed to perform the liveness analysis
"""

from analysis.abstract_state import AbstractState, AbstractBlockInfo
from parser.cfg_block import CFGBlock, CFGInstruction
from typing import Dict, List, Tuple, Set, Any

var_T = str


def _uses_defines_from_instructions(instructions: List[CFGInstruction]) -> Tuple[Set[var_T], Set[var_T]]:
    """
    Generates uses and defines sets with the variables that are used and defined in the set of instructions, resp.
    """
    uses, defines = set(), set()
    for instruction in instructions:
        uses.update(instruction.in_args)
        defines.update(instruction.out_args)
    return uses, defines


class LivenessBlockInfo(AbstractBlockInfo):

    def __init__(self, basic_block: CFGBlock):
        super().__init__()
        self._id = basic_block.block_id
        self._successors = [possible_successor for possible_successor
                            in [basic_block.get_jump_to(), basic_block.get_falls_to()]
                            if possible_successor is not None]
        print(self._id, basic_block.get_jump_to(), basic_block.get_falls_to())
        self._block_type = basic_block.get_jump_type()
        self._comes_from = basic_block.get_comes_from()
        self.uses, self.defines = _uses_defines_from_instructions(basic_block.get_instructions())

        # Variables that need to be propagated
        self.propagated_variables = self.uses.difference(self.defines)

    @property
    def block_id(self) -> Any:
        return self._id

    @property
    def successors(self) -> Any:
        return self._successors

    @property
    def block_type(self) -> Any:
        return self._block_type

    @property
    def comes_from(self) -> Any:
        return self._comes_from

    def __repr__(self):
        text_repr = [f"Block id: {self._id}", f"Block type: {self.block_type}", f"Successors: {self.successors}",
                     f"Propagated variables: {self.propagated_variables}"]
        return '\n'.join(text_repr)


class LivenessState(AbstractState):
    """
    Records the liveness state from a given block
    """

    def __init__(self):
        super().__init__()
        self.live_vars = set()

    def lub(self, state: 'LivenessState') -> None:
        self.live_vars.union(state.live_vars)

    def leq(self, state: 'LivenessState') -> bool:
        return self.live_vars.issubset(state.live_vars)

    def __repr__(self):
        return str(self.live_vars)

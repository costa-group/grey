"""
Module that implements the state needed to perform the liveness analysis
"""
from global_params.types import var_id_T, block_id_T
from analysis.abstract_state import AbstractState, AbstractBlockInfo
from parser.cfg_block import CFGBlock, CFGInstruction
from typing import Dict, List, Tuple, Set, Any


def _uses_defines_from_instructions(instructions: List[CFGInstruction],
                                    assignment_dict: Dict[str, str]) -> Tuple[Set[var_id_T], Set[var_id_T]]:
    """
    Generates uses and defines sets with the variables that are used and defined in the set of instructions, resp.
    """
    uses, defines = set(), set()
    for instruction in instructions:
        # For computing the uses, we cannot include variables that have been defined in the same block
        uses.update([element for element in instruction.in_args if not element.startswith("0x")
                     and element not in defines])
        defines.update(instruction.out_args)

    # We also need to consider the assignment dict
    for out_arg, in_arg in assignment_dict.items():
        if not in_arg.startswith("0x"):
            uses.add(in_arg)
        defines.add(out_arg)

    return uses, defines


class LivenessBlockInfo(AbstractBlockInfo):

    def __init__(self, basic_block: CFGBlock):
        super().__init__()
        self._id = basic_block.block_id
        self._successors = basic_block.successors

        self._block_type = basic_block.get_jump_type()
        self._comes_from = basic_block.get_comes_from()
        self.uses, self.defines = _uses_defines_from_instructions(basic_block.get_instructions(),
                                                                  basic_block.assignment_dict)
        self._instructions = basic_block.get_instructions()
        self._assignment_dict = basic_block.assignment_dict

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

# State for liveness analysis


class LivenessState(AbstractState):
    """
    Records the liveness state from a given block
    """

    def __init__(self):
        super().__init__()
        self.live_vars = set()

    def lub(self, state: 'LivenessState') -> None:
        self.live_vars.update(state.live_vars)

    def leq(self, state: 'LivenessState') -> bool:
        return self.live_vars.issubset(state.live_vars)

    def __repr__(self):
        return str(self.live_vars)


# Methods for classic backwards analysis using phi-functions

def _ssa_liveness_definitions(instructions: List[CFGInstruction]) -> Dict[str, Set[var_id_T]]:
    """
    Generates five different sets: Defs, Uses, UpwardExposed, PhiDefs (see Page 110 of
    "SSA-based Compiler Design (2022)"). In order to avoid using 4 different sets, we store them in a dictionary
    using the previously referred keys
    """
    combined_liveness_sets = dict()
    uses, defines, upward, phi_defs = set(), set(), set(), set()
    for instruction in instructions:

        # The phi instruction case must be handled differently: phi_uses and phi_defs
        if instruction.op == "PhiFunction":
            phi_defs.update(instruction.out_args)

        else:
            # For computing the uses, we cannot include variables that have been defined in the same block
            uses.update([element for element in instruction.in_args if not element.startswith("0x")])

            # The updward set must consider variables with no preceding definition in B
            upward.update([element for element in instruction.in_args if not element.startswith("0x") and
                           element not in defines.union(phi_defs)])

            defines.update(instruction.out_args)

    # TODO: check if the assignment dict is needed or not (it shouldn't)

    combined_liveness_sets["Uses"] = uses
    combined_liveness_sets["Defs"] = defines
    combined_liveness_sets["UpwardExposed"] = upward
    combined_liveness_sets["PhiDefs"] = phi_defs
    return combined_liveness_sets


def _block_id_to_uses_defs(instructions: List[CFGInstruction], entries_list: List[block_id_T]) -> Dict[block_id_T, Set[var_id_T]]:
    """
    Generates a dict that links each predecessor block with the corresponding variables that are used
    in the phi-functions for that block
    """
    # First we retrieve the arguments for every phi function
    i = 0
    arguments_per_index = [set() for _ in entries_list]
    while i < len(instructions) and instructions[i].get_op_name() == "PhiFunction":
        for j, input_elem in enumerate(instructions[i].get_in_args()):
            arguments_per_index[j].add(input_elem)
        i += 1

    # Then we store the corresponding the variables for the corresponding entry
    return {entry: arguments for entry, arguments in zip(entries_list, arguments_per_index)}


def _block_id_to_phi_uses(block_id: block_id_T, successor_instructions: List[CFGInstruction],
                          successor_entry_list: List[block_id_T]) -> Tuple[Set[var_id_T], Set[var_id_T]]:
    """
    Given the instructions from one of the successors of block_id, generates the corresponding PhiUses and PhiDefs sets
    """
    # First we retrieve the arguments for every phi function
    i = 0
    if block_id == "extract_byte_array_length_Block1_copy_0":
        print("HOLA")

    corresponding_arg = successor_entry_list.index(block_id)
    phi_uses, phi_defs = set(), set()
    while i < len(successor_instructions) and successor_instructions[i].get_op_name() == "PhiFunction":
        arg = successor_instructions[i].get_in_args()[corresponding_arg]
        if not arg.startswith("0x"):
            phi_uses.add(arg)
        phi_defs.update(successor_instructions[i].get_out_args())
        i += 1

    return phi_uses, phi_defs


class LivenessBlockInfoSSA(AbstractBlockInfo):
    """
    Same as LivenessBlockInfo, but storing the information needed to perform the analysis for a SSA
    """
    def __init__(self, basic_block: CFGBlock, block_dict: Dict[block_id_T, CFGBlock]):
        super().__init__()
        self._id = basic_block.block_id
        self._successors = basic_block.successors

        self._block_type = basic_block.get_jump_type()
        self._comes_from = basic_block.get_comes_from()
        self.liveness_sets = _ssa_liveness_definitions(basic_block.get_instructions())
        self._instructions = basic_block.get_instructions()
        self._assignment_dict = basic_block.assignment_dict
        self._entries = basic_block.entries

        self._phi_uses = set()
        for successor in self._successors:
            successor_block = block_dict[successor]
            if len(successor_block.entries) > 0:
                phi_uses, _ = _block_id_to_phi_uses(basic_block.block_id, successor_block.get_instructions(),
                                                    successor_block.entries)
                self._phi_uses.update(phi_uses)

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

    def _liveness_set(self, name: str) -> Set[var_id_T]:
        return self.liveness_sets[name]

    @property
    def uses(self) -> Set[var_id_T]:
        return self._liveness_set("Uses")

    @property
    def defs(self) -> Set[var_id_T]:
        return self._liveness_set("Defs")

    @property
    def upward_exposed(self) -> Set[var_id_T]:
        return self._liveness_set("UpwardExposed")

    @property
    def phi_defs(self) -> Set[var_id_T]:
        return self._liveness_set("PhiDefs")

    @property
    def phi_uses(self) -> Set[var_id_T]:
        return self._phi_uses

    def __repr__(self):
        text_repr = [f"Block id: {self._id}", f"Block type: {self.block_type}", f"Successors: {self.successors}"]
        return '\n'.join(text_repr)

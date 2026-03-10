"""
Methods to compute the solc layouts
"""
from typing import List
from parser.cfg_block_list import CFGBlockList
from global_params.types import var_id_T


def combine_layouts(combined_layout: List[var_id_T], next_out_stack: List[var_id_T]):
    """
    As the successors may convert into JUNK elements depending
    on the predecessor, we just combine the information
    """
    assert len(combined_layout) == len(next_out_stack), "Different stack sizes"
    combined_stack = []
    for combined_elem, next_elem in zip(combined_layout, next_out_stack):
        if combined_elem == "JUNK":
            combined_stack.append(next_elem)
        elif next_elem == "JUNK":
            combined_stack.append(combined_elem)
        else:
            assert combined_elem == next_elem, "Elements that are unified must match"
            combined_stack.append(combined_elem)
    return combined_stack



def compute_out_layouts(block_list: CFGBlockList):
    """
    Computes the out stack layouts from the in stacks
    """
    for block_id, block in block_list.blocks.items():

        generated_out_stack = None
        # Traverse the successors
        for successor_id in block.successors:
            successor_block = block_list.get_block(successor_id)
            in_stack = successor_block.get_in_layout_solc()

            if len(successor_block.phi_instructions()):
                # The entry id refers to the phi-def corresponding to current block
                entry_id = successor_block.entries.index(block_id)
                phi_use2def = {phi_instr.out_args[0]: phi_instr.in_args[entry_id] for phi_instr in successor_block.phi_instructions()}
            else:
                phi_use2def = dict()

            # The out stack corresponds to the in stack after replacing phi defs
            out_stack = [phi_use2def.get(var, var) for var in in_stack]

            # We check the consistency of the stack
            if generated_out_stack is not None:
                try:
                    generated_out_stack = combine_layouts(generated_out_stack, out_stack)
                except Exception as e:
                    raise ValueError(f"Error in block {block_id} with successors {block.successors}: {e}")
            else:
                generated_out_stack = out_stack

        block.set_out_layout_solc(generated_out_stack)

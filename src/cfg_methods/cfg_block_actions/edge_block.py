"""
Insertion of edge blocks: empty blocks with an unconditional jump that split an edge of the CFG (e.g. a
critical edge, from a block with several successors to a block with several predecessors)
"""
from cfg_methods.cfg_block_actions.utils import modify_comes_from, modify_successors
from global_params.types import block_id_T
from parser.cfg_block import CFGBlock
from parser.cfg_block_list import CFGBlockList


def edge_block_id(pred_block_id: block_id_T, successor_id: block_id_T) -> block_id_T:
    return f"{pred_block_id}_to_{successor_id}"


def insert_edge_block(block_list: CFGBlockList, pred_block_id: block_id_T, successor_id: block_id_T) -> CFGBlock:
    """
    Inserts an empty block with an unconditional jump in the edge from pred_block_id to successor_id. The phi
    entries of the successor are updated, so the phi arguments for that edge now come from the edge block.
    The block is marked as an edge block, as it is transparent for the stack (its output is its input)
    """
    new_block_id = edge_block_id(pred_block_id, successor_id)
    assert new_block_id not in block_list.blocks, f"Block {new_block_id} already exists"
    pred_block = block_list.get_block(pred_block_id)
    edge_block = CFGBlock(new_block_id, [], "unconditional", pred_block.assignment_dict)
    edge_block.is_edge_block = True
    edge_block.set_comes_from([pred_block_id])
    edge_block.set_jump_to(successor_id)
    block_list.add_block(edge_block)

    modify_successors(pred_block_id, successor_id, new_block_id, block_list)
    modify_comes_from(successor_id, pred_block_id, new_block_id, block_list)
    return edge_block

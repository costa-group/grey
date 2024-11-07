from typing import Optional
from global_params.types import block_id_T
from parser.cfg_block_list import CFGBlockList


def modify_comes_from(block_to_modify: block_id_T, previous_pred_id: Optional[block_id_T],
                      new_pred_id: Optional[block_id_T], cfg_block_list: CFGBlockList) -> None:
    """
    Modifies the comes from the block id to replace the id of the initial block with the new one in the block list
    """
    block = cfg_block_list.blocks[block_to_modify]
    found_previous = False
    comes_from = block.get_comes_from()
    new_comes_from = []
    for pred_block in comes_from:
        if pred_block == previous_pred_id:
            found_previous = True
            new_comes_from.append(new_pred_id)
        else:
            new_comes_from.append(pred_block)

    # None case for "previous_pred_id" means that there is no substitution to perform.
    # Hence, we just add the new id to the list of comes from
    if previous_pred_id is None:
        found_previous = True
        new_comes_from.append(new_pred_id)

    block.set_comes_from(new_comes_from)
    block.entries = [entry if entry != previous_pred_id else new_pred_id for entry in block.entries]
    assert found_previous, f"Comes from list {comes_from} of {block_to_modify} does not contain {previous_pred_id}"


def modify_successors(block_to_modify: block_id_T, previous_successor_id: Optional[block_id_T],
                      new_successor_id: block_id_T, cfg_block_list: CFGBlockList):
    """
    Modifies the successor "previous_successor_id" from block "block_to_modify" so that it falls to or jumps to
    "new_successor_id" instead
    """
    pred_block = cfg_block_list.blocks[block_to_modify]

    # To avoid assigning the same successor id if the previous one was None,
    # we force the "jumps to" case not to be empty (same as unconditional jumps)
    if previous_successor_id is None or pred_block.get_jump_to() == previous_successor_id:
        pred_block.set_jump_to(new_successor_id)
    else:
        falls_to = pred_block.get_falls_to()
        assert falls_to == previous_successor_id, \
            f"Incoherent CFG: the predecessor block {block_to_modify} must reach block {previous_successor_id}"
        pred_block.set_falls_to(new_successor_id)

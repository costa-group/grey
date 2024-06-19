

def check_block_validity(block_id, block_instructions, block_exit, block_type):
    if block_id == -1:
        raise Exception("[ERROR]: Input block does not contain an identifier")

    if block_instructions == -1:
        raise Exception("[ERROR]: Input block does not contain instructions")

    if block_exit == -1:
        raise Exception("[ERROR]: Input block does not contain an exit")

    if block_type == -1:
        raise Exception("[ERROR]: Input block does not contain an identifier")


    
def check_instruction_validity(in_args, op, out_args):
    if in_args == -1:
        raise Exception("[ERROR]: Instruction does not contain in argument")

    if op == -1:
        raise Exception("[ERROR]: Instruction does not contain op argument")

    if out_args == -1:
        raise Exception("[ERROR]: instruction does not contain out argument")


    

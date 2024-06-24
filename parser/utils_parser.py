

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

def process_opcode(result):
    op_val = hex(int(result))[2:]

    if (int(op_val,16)<12):
        op_val = "0"+str(op_val)
    return op_val


# Number encoding size following the implementation in Solidity compiler:
# https://github.com/ethereum/solidity/blob/develop/libsolutil/Numeric.h
def number_encoding_size(number):
    i = 0
    
    if number < 0 :
        number = (2**256)+number


    while number != 0:
        i += 1
        number = number >> 8
    return i

# Number of bytes necessary to encode an int value
def get_num_bytes_int(val):
    return max(1, number_encoding_size(val))


# Number of bytes necessary to encode a hex value. Matches the x in PUSHx opcodes
def get_push_number_hex(val):
    return get_num_bytes_int(int(val, 16))


# Taken directly from https://github.com/ethereum/solidity/blob/develop/libevmasm/AssemblyItem.cpp
# Address length: maximum address a tag can appear. By default, 2 (check https://eips.ethereum.org/EIPS/eip-3860)
def get_ins_size(op_name, val = None, address_length = 2):
    if op_name == "ASSIGNIMMUTABLE":
        # Number of PushImmutable's with the same hash. Assume 1 (?)
        immutableOccurrences = 1

        # Just in case the behaviour is changed, following code corresponds to the byte size according to
        # immutable variable
        if immutableOccurrences == 0:
            return 2
        else:
            return (immutableOccurrences - 1) * (5 + 32) + (3 + 32)
    elif op_name == "PUSH0":
        return 1
    elif op_name == "PUSH":
        return 1 + get_num_bytes_int(val)
    elif op_name == "PUSH #[$]" or op_name == "PUSHSIZE":
        return 1 + 4
    elif op_name == "PUSH [tag]" or op_name == "PUSH data" or op_name == "PUSH [$]":
        return 1 + address_length
    elif op_name == "PUSHLIB" or op_name == "PUSHDEPLOYADDRESS":
        return 1 + 20
    elif op_name == "PUSHIMMUTABLE":
        return 1 + 32
    # JUMPDEST are already included in the json_solc file, so tags do not count either in size or gas
    elif op_name == "tag":
        return 0
    elif not op_name.startswith("PUSH"):
        return 1
    else:
        raise ValueError("Opcode not recognized", op_name)

def is_commutative(op):
    return op in ["ADD","MUL","EQ","AND","OR","XOR"]


def is_in_input_stack(var, instructions):
    if instructions == []:
        return True

    candidate = any(filter(lambda x: var not in x.get_out_args(),instructions))
    return candidate

def is_in_output_stack(var, instructions):
    if instructions == []:
        return True

    candidate = any(filter(lambda x: var in x.get_in_args(),instructions))
    return not candidate

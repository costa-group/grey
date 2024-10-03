from typing import List, Dict, Any
import json


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


def check_assignment_validity(in_args: List[str], assignments: List[str], out_args: List[str]):
    """
    Check that there is the same number of elements in fields in_args, assignments and out_args
    """
    if len(in_args) != len(assignments) or len(assignments) != len(out_args):
        raise Exception("[ERROR]: Assignment must contain the same number of elements for all its fields")


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
    elif op_name == "PUSH [TAG]" or op_name == "PUSH data" or op_name == "PUSH [$]":
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

    candidate = any(filter(lambda x: var in x.get_out_args(),instructions))
    return not candidate

def is_in_output_stack(var, instructions):
    if instructions == []:
        return True

    candidate = any(filter(lambda x: var in x.get_in_args(),instructions))
    return not candidate


def is_assigment_var_used(var, instructions):
    candidates = list(filter(lambda x: var in x["inpt_sk"],instructions))
    return len(candidates) != 0 #If it is !=0 means that the var generated in the assignment is used in the block


def get_empty_spec():
    spec = {}
    
    spec["original_instrs"] = ""
    spec["yul_expressions"] = ""
    spec["src_ws"] = []
    spec["tgt_ws"] = []
    spec["user_instrs"] = []
    spec["variables"] = []
    
    spec["memory_dependences"] = []
    spec["storage_dependences"] = []
    
    #They are not used in greedy algorithm
    spec["init_progr_len"] = 0
    spec["max_progr_len"] = 0
    spec["min_length_instrs"] = 0 
    spec["min_length_bounds"] = 0
    spec["min_length"] = 0
    spec["rules"] = ""

    return spec



def get_interval(opcode_name, input_args):
    if opcode_name in ["keccak256","log0","log1","log2","log3","log4"]:
        return [input_args[0], input_args[1]]
    elif opcode_name in ["codecopy","calldatacopy","returndatacopy","mcopy"]:
        return [input_args[0], input_args[2]]
    elif opcode_name in ["extcodecopy"]:
        return [input_args[1], input_args[3]]
    elif opcode_name in ["create","create2"]:
        return [input_args[1], input_args[2]]
    elif opcode_name in ["call","callcode"]:
        return [[input_args[3],input_args[4]],[input_args[5],input_args[6]]]
    elif opcode_name in ["delegatecall","staticcall"]:
        return [[input_args[2],input_args[3]],[input_args[4],input_args[5]]]


#It returns the expression that a instruction takes as argument
#It returns a expression of the form:
# op -> opcode_name
# exp -> [int_val] | [input_var] | [op, [exp]]

def get_expression(var, instructions):
    if var.startswith("0x"):
        return [var]

    candidates = list(filter(lambda x: var in x.get_out_args(), instructions))
    if len(candidates) == 0:
        return [var]

    assert len(candidates) == 1, "[ERROR]: A variable cannot be generated by more than one instruction"
    
    new_instruction = candidates[0]

    sub_expression = []
    for v in new_instruction.get_in_args():
        new_subexp = get_expression(v,instructions)
        sub_expression.append(new_subexp)
    
    return [new_instruction.get_op_name(),sub_expression]


def is_member_recursive(val, exp):
    if len(exp) == 1:
        return val in exp

    else:
        result = False
        for x in exp[1]:
            result = result or is_member_recursive(val, x)
        result = result and x[0] in ["add","mul","sub","div"]
        return result

def are_dependent_accesses(exp1, exp2):
    val1 = exp1[0]
    val2 = exp2[0]

    print(exp1)
    print(exp2)
    
    if val1 == "inf" or val2 == "inf":
        return True
    elif val1.startswith("0x") and val2.startswith("0x"): #constants
        return val1==val2
    elif len(val1) == len(val2) and len(val1) == 1: #variables
        print("Check with ssa")
        return True #val1 == val2
    elif len(val1) == 1 and len(val2) >1 : #One expression is contained in the other
        return not is_member_recursive(val1, val2)
    elif len(val1) > 1 and len(val2) == 1:
        return not is_member_recursive(val2, val1)
    else:
        return True

def are_dependent_interval(exp1, exp2):
    val1 = exp1[0]
    offset1 = exp1[1]

    val2 = exp2[0]
    offset2 = exp2[1]

    if val1.startswith("0x") and offset1.startswith("0x") and val2.startswith("0x") and offset2.startswith("0x"): #all are constants
        return overlap(int(val1,16), int(offset1,16), int(val2,16), int(offset2,16))

    else:
        return True


def overlap(idx1, offset1, idx2, offset2):
    return idx1 <= idx2 < idx1 + offset1 or idx2 <= idx1 < idx2 + offset2


def replace_pos_instrsid(dependences, map_positions_instructions):
    deps = []
    for (i,j) in dependences:
        assert (i in map_positions_instructions) and (j in map_positions_instructions), \
            "[ERROR]: position not found in map of instructions when genereting the dependences"
        deps.append((map_positions_instructions[i], map_positions_instructions[j]))

    return deps

def generate_dep(t_ins1, t_ins2):
    if t_ins1 == "write":
        return True
    elif t_ins1 == "read" and t_ins2 == "write":
        return True
    else:
        return False
    

def split_json(input_file: str) -> Dict[str, Any]:
    """
    It returns all the jsons stored in one file as separate dictionaries
    """
    with open(input_file, 'r') as f:
        lines = f.read()

    json_structs = {}
    ini = 0
    level = 0

    for i, char in enumerate(lines):
        # Ignore continue lines
        if any(char == line_skip for line_skip in ["null", ""]):
            continue

        if char == '{':
            if level == 0:
                ini = i  # Init of new JSON
            level += 1
        elif char == '}':
            level-= 1
            if level == 0:
                # New JSON found
                content = lines[ini:i+1]
                content = content.replace("'", '"')
                try:
                    json_st = json.loads(content)
                    json_structs[str(i)] = json_st
                except json.JSONDecodeError:
                    print(f"Error when decoding: {content}")

    return json_structs

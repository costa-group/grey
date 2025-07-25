import sys
import os
import re
import json as js
from typing import Dict, List


# Diccionario de las instrucciones EVM
instructions = {
    0x00: "STOP", 0x01: "ADD", 0x02: "MUL", 0x03: "SUB",
    0x04: "DIV", 0x05: "SDIV", 0x06: "MOD", 0x07: "SMOD",
    0x08: "ADDMOD", 0x09: "MULMOD", 0x0a: "EXP", 0x0b: "SIGNEXTEND",
    0x10: "LT", 0x11: "GT", 0x12: "SLT", 0x13: "SGT",
    0x14: "EQ", 0x15: "ISZERO", 0x16: "AND", 0x17: "OR", 0x18: "XOR", 0x19: "NOT", 0x1a: "BYTE", 0x1b: "SHL",
    0x1c: "SHR", 0x1d: "SAR",
    0x20: "SHA3",
    0x30: "ADDRESS", 0x31: "BALANCE", 0x32: "ORIGIN", 0x33: "CALLER",
    0x34: "CALLVALUE", 0x35: "CALLDATALOAD", 0x36: "CALLDATASIZE", 0x37: "CALLDATACOPY",
    0x38: "CODESIZE", 0x39: "CODECOPY", 0x3a: "GASPRICE", 0x3b: "EXTCODESIZE",
    0x3c: "EXTCODECOPY", 0x3d: "RETURNDATASIZE", 0x3e: "RETURNDATACOPY",
    0x3f: "EXTCODEHASH",
    0x40: "BLOCKHASH", 0x41: "COINBASE", 0x42: "TIMESTAMP", 0x43: "NUMBER",
    0x44: "DIFFICULTY", 0x45: "GASLIMIT", 0x46: "CHAINID", 0x47: "SELFBALANCE", 0x48: "BASEFEE", 0x49: "BLOBHASH",
    0x4a: "BLOBBASEFEE",
    0x50: "POP", 0x51: "MLOAD", 0x52: "MSTORE", 0x53: "MSTORE8",
    0x54: "SLOAD", 0x55: "SSTORE", 0x56: "JUMP", 0x57: "JUMPI",
    0x58: "PC", 0x59: "MSIZE", 0x5a: "GAS", 0x5b: "JUMPDEST", 0x5c: "TLOAD", 0x5d: "TSTORE", 0x5e: "MCOPY",
    0x5f: "PUSH0",  # EIP-3855: PUSH0 (no datos adicionales)
    0x60: "PUSH1", 0x61: "PUSH2", 0x62: "PUSH3", 0x63: "PUSH4", 0x64: "PUSH5", 0x65: "PUSH6",
    0x66: "PUSH7", 0x67: "PUSH8", 0x68: "PUSH9", 0x69: "PUSH10", 0x6a: "PUSH11", 0x6b: "PUSH12",
    0x6c: "PUSH13", 0x6d: "PUSH14", 0x6e: "PUSH15", 0x6f: "PUSH16", 0x70: "PUSH17", 0x71: "PUSH18",
    0x72: "PUSH19", 0x73: "PUSH20", 0x74: "PUSH21", 0x75: "PUSH22", 0x76: "PUSH23", 0x77: "PUSH24",
    0x78: "PUSH25", 0x79: "PUSH26", 0x7a: "PUSH27", 0x7b: "PUSH28", 0x7c: "PUSH29", 0x7d: "PUSH30",
    0x7e: "PUSH31", 0x7f: "PUSH32",
    0x80: "DUP1", 0x81: "DUP2", 0x82: "DUP3", 0x83: "DUP4", 0x84: "DUP5", 0x85: "DUP6", 0x86: "DUP7",
    0x87: "DUP8", 0x88: "DUP9", 0x89: "DUP10", 0x8a: "DUP11", 0x8b: "DUP12", 0x8c: "DUP13",
    0x8d: "DUP14", 0x8e: "DUP15", 0x8f: "DUP16",
    0x90: "SWAP1", 0x91: "SWAP2", 0x92: "SWAP3", 0x93: "SWAP4", 0x94: "SWAP5", 0x95: "SWAP6",
    0x96: "SWAP7", 0x97: "SWAP8", 0x98: "SWAP9", 0x99: "SWAP10", 0x9a: "SWAP11", 0x9b: "SWAP12",
    0x9c: "SWAP13", 0x9d: "SWAP14", 0x9e: "SWAP15", 0x9f: "SWAP16",
    0xa0: "LOG0", 0xa1: "LOG1", 0xa2: "LOG2", 0xa3: "LOG3", 0xa4: "LOG4",
    0xf0: "CREATE", 0xf1: "CALL", 0xf2: "CALLCODE", 0xf3: "RETURN", 0xf4: "DELEGATECALL",
    0xf5: "CREATE2", 0xfa: "STATICCALL", 0xfd: "REVERT", 0xfe: "INVALID", 0xff: "SELFDESTRUCT"
}


def get_evm_code(log_file):
    f = open(log_file, "r")
    all_lines = f.readlines()

    lines = list(filter(lambda x: x.find("Contract") != -1 and x.find("EVM") != -1, all_lines))

    res = {}
    
    for l in lines:
        elems = l.split("->")
        c_name = elems[0].split(":")[-1]
        evm_code = elems[-1].split(":")[-1]

        res[c_name] = evm_code

    #print(res)
        
    return res


def get_blocks(bytecode):

    i = 0
    count = 0

    blocks = []
    block = []

    num_ins = 0
    
    while i < len(bytecode):
        try:
            # Leer un byte (dos caracteres hexadecimales)
            opcode = int(bytecode[i:i+2], 16)
            count += 1  # Contar la instrucción
            opcode_name = instructions.get(opcode,"INVALID")
            
            num_ins+=1
            
            if opcode_name == "JUMPDEST":
                if block != []:
                    blocks.append(block)
                block = [opcode_name]
            elif opcode_name in ["JUMP","JUMPI","STOP","REVERT","INVALID","RETURN","SELFDESTRUCT"]:
                block.append(opcode_name)
                blocks.append(block)
                block = []

            else:
                block.append(opcode_name)

                
            # Manejar instrucciones PUSH (PUSH0 no requiere datos adicionales)
            if 0x60 <= opcode <= 0x7f:
                push_size = opcode - 0x60 + 1
                i += 2 + (push_size * 2)  # Saltar el tamaño de los datos incluidos

            elif instructions.get(opcode, "") == "INVALID":
                i += 2

            else:
                i += 2  # Avanzar 1 byte (2 caracteres hexadecimales)
        except ValueError:
            print(f"Error al leer el bytecode en posición {i}. Asegúrate de que sea válido.")
            break

    #print(blocks)
    return blocks, num_ins
    
def split_evm_instructions(bytecode: str) -> List[str]:
    """
    Separa en distintos

    :param bytecode: Bytecode hexadecimal como una cadena.
    :return: Número total de instrucciones.
    """
    i = 0
    count = 0
    split_init = 0
    partitions = []
    while i < len(bytecode):
        try:
            # Leer un byte (dos caracteres hexadecimales)
            opcode = int(bytecode[i:i+2], 16)
            count += 1  # Contar la instrucción

            
            # Manejar instrucciones PUSH (PUSH0 no requiere datos adicionales)
            if 0x60 <= opcode <= 0x7f:
                push_size = opcode - 0x60 + 1
                i += 2 + (push_size * 2)  # Saltar el tamaño de los datos incluidos

            elif instructions.get(opcode, "") == "INVALID":
                partitions.append(bytecode[split_init:i])
                split_init = i + 2
                i += 2

            else:
                i += 2  # Avanzar 1 byte (2 caracteres hexadecimales)
        except ValueError:
            print(f"Error al leer el bytecode en posición {i}. Asegúrate de que sea válido.")
            break

    if split_init < len(bytecode):
        partitions.append(bytecode[split_init:])
    return partitions

def remove_auxdata(evm: str):
    """
    Removes the .auxdata introduced by grey. It is always of the same form
    """
    return evm.replace("000000000000000000000000000000000000000000000000000000000000000000"
                       "000000000000000000000000000000000000000000000000000000000000000000"
                       "00000000000000000000000000000000000053", "")



def process_pops(block, num_pops):
    npops = list(filter(lambda x: x.find("POP")!=-1, block))
    num_pops.append(len(npops))


def is_terminal(block):
    bl_set = set(block)
    terminal = set(["RETURN","REVERT","INVALID","STOP","SELFDESTRUCT"])

    inter = bl_set.intersection(terminal)

    return len(inter)!=0
    
def process_terminal_blocks(blocks, num_pops):
    terminal_blocks = 0
    total_pops = []
    total_ins_terminal = 0
    
    for bl in blocks:
        process_pops(bl, total_pops)
        if is_terminal(bl):
            terminal_blocks+=1
            total_ins_terminal+=len(bl)
            process_pops(bl,num_pops)

    return terminal_blocks, sum(total_pops), total_ins_terminal

def count_instructions(blocks, ins):
    total_num_ins = 0

    for bl in blocks:
        num_ins = list(filter(lambda x: x.find(ins)!= -1, bl))
        total_num_ins += len(num_ins)

    return total_num_ins



def count_num_ins(evm: str):
    """
    Assumes the evm bytecode has no CBOR metadata appended
    """
    code_regions = split_evm_instructions(evm)
    #print(code_regions)
    num_pop = []
    terminal_blocks = 0
    total_pops = 0
    total_ins_terminal = 0
    total_blocks = 0

    num_ins = {}
    total_ins = 0
    for region in code_regions:
        blocks, num_ins_bytecode = get_blocks(remove_auxdata(region))
        num_tblocks, numtotal_pops, ins_terminal = process_terminal_blocks(blocks, num_pop)

        num_ins["SWAP"]=num_ins.get("SWAP",0)+count_instructions(blocks, "SWAP")
        num_ins["DUP"]=num_ins.get("DUP",0)+count_instructions(blocks, "DUP")
        num_ins["PUSH"]=num_ins.get("PUSH",0)+count_instructions(blocks, "PUSH")
        num_ins["PUSH0"]=num_ins.get("PUSH0",0)+count_instructions(blocks, "PUSH0")

        curr_jumpdest = count_instructions(blocks, "JUMPDEST")
        curr_jumpi = count_instructions(blocks, "JUMPI")
        curr_jump = count_instructions(blocks, "JUMP")

        num_ins["JUMPI"]=num_ins.get("JUMPI",0)+curr_jumpi
        num_ins["JUMPDEST"]=num_ins.get("JUMPDEST",0)+curr_jumpdest
        num_ins["JUMP"]=num_ins.get("JUMP",0)+(curr_jump - curr_jumpi - curr_jumpdest)

        num_ins["CALL"]=num_ins.get("CALL",0)+count_instructions(blocks, "CALL")
        
        terminal_blocks+=num_tblocks
        total_pops+=numtotal_pops
        total_ins_terminal+=ins_terminal
        total_blocks+=len(blocks)
        total_ins+=num_ins_bytecode
    #print("TERMINAL BLOCKS: " +str(terminal_blocks))
    #print("NUM_POPS: "+ str(sum(num_pop)))
    return (total_blocks, terminal_blocks, sum(num_pop), total_pops, total_ins_terminal, total_ins)


def execute_function(origin_file, log_opt_file):
    print("FILE: "+log_opt_file)
    f = open(origin_file, "r")

    evm_origin = f.read()

    evm_opt = get_evm_code(log_opt_file)

    total_terminal = 0
    total_pops = 0

    total_sol_terminal = 0
    total_sol_pops = 0

    all_pops_opt = 0
    all_pops_sol = 0

    total_ins_terminal_opt = 0
    total_ins_terminal_sol = 0

    total_blocks_solc = 0
    total_blocks_opt = 0

    total_ins_solc = 0
    total_ins_opt = 0
    
    for c in evm_opt:
        evm = evm_opt[c]

        opt = count_num_ins(evm.strip())

        total_blocks_opt+= opt[0]
        total_terminal+=opt[1]
        total_pops+=opt[2]
        all_pops_opt+=opt[3]
        total_ins_terminal_opt = opt[4]
        total_ins_opt+= opt[5]
        
        evm_dict = js.loads(evm_origin)
        contracts = evm_dict["contracts"]

        origin_ins = 0

        for cc in contracts:
            json = contracts[cc]

            if c.strip() in json:
                bytecode = json[c.strip()]["evm"]["bytecode"]["object"]
                # print("ORIGINAL")
                origin_ins =count_num_ins(bytecode.strip())

                total_blocks_solc+=origin_ins[0]
                total_sol_terminal+=origin_ins[1]
                total_sol_pops+=origin_ins[2]
                all_pops_sol+=origin_ins[3]
                total_ins_terminal_sol+=origin_ins[4]
                total_ins_solc+=origin_ins[5]
                
    return (total_terminal, total_pops, all_pops_opt, total_sol_terminal, total_sol_pops, all_pops_sol, total_ins_terminal_opt, total_ins_terminal_sol, total_blocks_solc, total_blocks_opt,total_ins_solc, total_ins_opt)

if __name__ == '__main__':
    origin_file = sys.argv[1]
    log_opt_file = sys.argv[2]

    total_terminal, total_pops, all_pops_opt, total_sol_terminal, total_sol_pops, all_pops_sol = execute_function(origin_file, log_opt_file)

    print("TOTAL TERMINAL OPT: "+str(total_terminal))
    print("TOTAL POPS TERMINAL OPT: "+str(total_pops))
    prin("TOTAL POPS OPT: "+str(all_pops_opt))

    print("TOTAL TERMINAL SOLC: "+str(total_sol_terminal))
    print("TOTAL POPS TERMINAL SOLC: "+str(total_sol_pops))
    print("TOTAL POPS SOLC: "+str(all_pops_sol))

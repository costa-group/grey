"""
Binary: can be split into chunks filtering by the separator 'fe'.
We have to be careful though because bytes after PUSHx instructions must
not be considered. There are two types of chunk we can find:
- Code: usually starts with '6080' o some PUSHx 20/40/80 value.
- Metadata: encoded in CBOR (see https://playground.sourcify.dev/)
  and usually starts with "a264" for some reason (when generating the binary
  from the compiler). The last two bytes of the
  metadata correspond to the size of the metadata file; it is usually 0053.
  There can be multiple metadata fields combined into the same chunk (they
  are not separated with fe)

- Strategy: filter the chunks and identify metada. Ignore metadata for counting
instructions
"""

import re
import sys
import json as js
from typing import Dict, List
from pathlib import Path

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


def split_basic_blocks(opcodes):
    """
    Dada una lista de instrucciones EVM (strings como 'PUSH1 0x02', 'JUMPI', 'JUMPDEST', 'STOP'),
    devuelve una lista de basic blocks (listas de instrucciones).

    Reglas:
    - Primera instrucción siempre es líder.
    - JUMPDEST siempre es líder.
    - La instrucción después de cualquier salto o terminador también es líder.
    """
    n = len(opcodes)
    leaders = set()

    # 1. Primera instrucción
    if n > 0:
        leaders.add(0)

    # 2. Detectar líderes
    print(opcodes)
    for i, op in enumerate(opcodes):
        if op.startswith("JUMPDEST"):
            leaders.add(i)
        elif op.startswith(("JUMP", "JUMPI", "STOP", "RETURN", "REVERT", "INVALID")):
            if i + 1 < n:
                leaders.add(i + 1)

    # 3. Dividir en bloques
    leaders = sorted(leaders)
    blocks = []
    for idx, start in enumerate(leaders):
        end = leaders[idx + 1] if idx + 1 < len(leaders) else n
        block = opcodes[start:end]
        blocks.append(block)

    return blocks


def extract_binary_from_solc_output(compiler_output: str) -> Dict[str, str]:

    # For now, we assume only the yul cfg option is enabled
    yul_cfg_regex = r"\n======= (.*?) =======\nBinary(.*?)\n(.*?)\n"

    contracts = re.findall(yul_cfg_regex, compiler_output)
    contracts = {contract[0]: contract[2] for contract in contracts if contract[1]}
    return contracts


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



import re

def split_evm_opcodes(code: str):
    """
    Separa un string de instrucciones EVM en una lista,
    manteniendo unidos los PUSHn con su argumento.
    """
    tokens = code.split()
    instructions = []
    i = 0

    while i < len(tokens):
        tok = tokens[i]
        # Detectar PUSHn
        if re.match(r'^PUSH\d+$', tok):
            if i + 1 < len(tokens) and tokens[i + 1].startswith("0x"):
                # Unir PUSHn con su argumento
                instructions.append(f"{tok} {tokens[i + 1]}")
                i += 2
                continue
            else:
                # PUSH sin argumento (caso raro o error)
                instructions.append(tok)
        else:
            instructions.append(tok)
        i += 1

    return instructions

def count_evm_instructions(bytecode: str) -> int:
    """
    Cuenta las instrucciones en el bytecode de un archivo EVM.

    :param bytecode: Bytecode hexadecimal como una cadena.
    :return: Número total de instrucciones.
    """
    i = 0
    count = 0
    while i < len(bytecode):
        try:
            # Leer un byte (dos caracteres hexadecimales)
            opcode = int(bytecode[i:i+2], 16)
            count += 1  # Contar la instrucción

            # Manejar instrucciones PUSH (PUSH0 no requiere datos adicionales)
            if 0x60 <= opcode <= 0x7f:
                push_size = opcode - 0x60 + 1
                i += 2 + (push_size * 2)  # Saltar el tamaño de los datos incluidos
            else:
                i += 2  # Avanzar 1 byte (2 caracteres hexadecimales)
        except ValueError:
            print(f"Error al leer el bytecode en posición {i}. Asegúrate de que sea válido.")
            break

    return count






def remove_auxdata(evm: str):
    """
    Removes the .auxdata introduced by grey. It is always of the same form
    """
    return evm.replace("000000000000000000000000000000000000000000000000000000000000000000"
                       "000000000000000000000000000000000000000000000000000000000000000000"
                       "00000000000000000000000000000000000053", "")


def generate_disasm(bytecode):
    code_regions = split_evm_instructions(bytecode)
    print("+*+*+*+*+*+*+*+*")
    print(code_regions)
    return (disasm_code(remove_auxdata(region)) for region in code_regions)


def disasm_code(bytecode):
    """
    Separa en distintos

    :param bytecode: Bytecode hexadecimal como una cadena.
    :return: Número total de instrucciones.
    """
    i = 0
    count = 0
    split_init = 0
    partitions = []
    op_list = []
    while i < len(bytecode):
        try:
            # Leer un byte (dos caracteres hexadecimales)
            opcode = int(bytecode[i:i+2], 16)
            count += 1  # Contar la instrucción
            
            print(bytecode[i:i+2])
            
            op_name = instructions.get(opcode, None)
            if op_name == None:
                print("[WARNING]: Error in name of opcode")
                op_list.append("INVALID")
                i+=2
                # raise Exception("Error in name of opcode")

            
            # Manejar instrucciones PUSH (PUSH0 no requiere datos adicionales)
            if 0x60 <= opcode <= 0x7f:
                push_size = opcode - 0x60 + 1
                i += 2 + (push_size * 2)  # Saltar el tamaño de los datos incluidos
                push_val= bytecode[i+2:i+2+(push_size*2)]
                op_name+= " 0x"+push_val

                op_list.append(op_name)
              
                
            elif instructions.get(opcode, "") == "INVALID":
                partitions.append(list(op_list))
                op_list = []
                split_init = i + 2
                i += 2

            else:
                op_list.append(op_name)
              
                i += 2  # Avanzar 1 byte (2 caracteres hexadecimales)
        except ValueError:
            print(f"Error al leer el bytecode en posición {i}. Asegúrate de que sea válido.")
            break

    if len(partitions)> 1 and partitions[-1] != op_list:
        partitions.append(op_list)
    elif len(partitions) == 0 and op_list != []:
        partitions.append(op_list)
    return partitions


def execute_script():
    solx_file = sys.argv[1]
    dir_blocks = sys.argv[2]
    name = solx_file.split("/")[-1].split(".")[0].strip()
    solx_block_dir = sys.argv[2]
    
    f_solx = open(solx_file, "r")
    
    evm_solx = f_solx.read()
    
    evm_dict_solx = js.loads(evm_solx)
    contracts_solx = evm_dict_solx["contracts"]

    
    for c in contracts_solx:
        json_solx = contracts_solx.get(c, [])
        for cc in json_solx.keys():
            # bytecode = json_solx[cc.strip()]["evm"]["bytecode"]["object"]
            bytecode = json_solx[cc.strip()]["evm"]["bytecode"]["opcodes"]
            opcodes = split_evm_opcodes(bytecode)
            print(opcodes)
            blocks = split_basic_blocks(opcodes)
            # print(bytecode)
            # result = generate_disasm(bytecode)
            # idx = 0
            # for r in result:
            #     for sequence in r:
            #         blocks = split_basic_blocks(sequence)
            idx = 0
            for i, block in enumerate(blocks):
                print(f"Block {i}: {block}")
                block_as_str = " ".join(block)
                f = open(dir_blocks+"/"+name+"_block_"+str(idx),"w")
                f.write(block_as_str)
                f.close()
                idx+=1
                    

if __name__ == '__main__':
    execute_script()

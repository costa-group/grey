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
from opcodes import get_ins_cost

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
        
    return res


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
    gas = 0
    while i < len(bytecode):
        try:
            # Leer un byte (dos caracteres hexadecimales)
            opcode = int(bytecode[i:i+2], 16)
            count += 1  # Contar la instrucción

            
            ins_op = instructions.get(opcode, "")
            if ins_op != "":
                opcode_gas = get_ins_cost(instructions.get(opcode))
                gas+=opcode_gas

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

    return partitions, gas


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


def count_bytes(bytecode:str) -> int:
    """
    Cuenta el numero de bytes en el bytecode de un archivo EVM.

    :param bytecode: Bytecode hexadecimal como una cadena.
    :return: Número total de bytes.
    """
    i = len(bytecode)

    assert(i%2 == 0) #It should have an odd number of elements
    
    count = i//2
    
    return count



def remove_auxdata(evm: str):
    """
    Removes the .auxdata introduced by grey. It is always of the same form
    """
    return evm.replace("000000000000000000000000000000000000000000000000000000000000000000"
                       "000000000000000000000000000000000000000000000000000000000000000000"
                       "00000000000000000000000000000000000053", "")

def count_num_ins(evm: str):
    """
    Assumes the evm bytecode has no CBOR metadata appended
    """
    code_regions, gas = split_evm_instructions(evm)
    return sum(count_evm_instructions(remove_auxdata(region)) for region in code_regions), gas

def count_num_bytes(evm: str):
    """
    Assumes the evm bytecode has no CBOR metadata appended
    """
    code_regions, _ = split_evm_instructions(evm)
    return sum(count_bytes(remove_auxdata(region)) for region in code_regions)


def execute_script():
    origin_file = sys.argv[1]
    log_opt_file = sys.argv[2]

    f = open(origin_file, "r")

    evm_origin = f.read()

    evm_opt = get_evm_code(log_opt_file)
    
    for c in evm_opt:
        evm = evm_opt[c]

        opt, gas_opt = count_num_ins(evm.strip())
        opt_bytes = count_num_bytes(evm.strip())

        
        evm_dict = js.loads(evm_origin)
        contracts = evm_dict["contracts"]

        origin_ins = 0
        origin_bytes = 0

        gas_origin = 0
        
        for cc in contracts:
            json = contracts[cc]

            if c.strip() in json:
                bytecode = json[c.strip()]["evm"]["bytecode"]["object"]
                origin_num_ins, origin_gas = count_num_ins(bytecode.strip())
                origin_ins += origin_num_ins
                gas_origin += origin_num_ins
                origin_bytes += count_num_bytes(bytecode.strip())
                
    if origin_ins != 0:
        print(log_opt_file + " ORIGIN NUM INS: " + str(origin_ins))
        print(log_opt_file + " OPT NUM INS: " + str(opt))

        print(log_opt_file + " ORIGIN NUM BYTES: " + str(origin_bytes))
        print(log_opt_file + " OPT NUM BYTES: " + str(opt_bytes))


def execute_script_solx():
    origin_file = sys.argv[1]
    log_opt_file = sys.argv[2]
    solx_file = sys.argv[3]
    
    f = open(origin_file, "r")
    f_solx = open(solx_file, "r")
    
    evm_origin = f.read()
    evm_solx = f_solx.read()
    
    evm_opt = get_evm_code(log_opt_file)

    for c in evm_opt:
        evm = evm_opt[c]

        opt, opt_gas = count_num_ins(evm.strip())
        opt_bytes = count_num_bytes(evm.strip())

        
        evm_dict = js.loads(evm_origin)

        contracts = evm_dict["contracts"]

        try:
            evm_dict_solx = js.loads(evm_solx)
            contracts_solx = evm_dict_solx["contracts"]
        except:
            contracts_solx = {}
            
        origin_ins = 0
        origin_bytes = 0
        origin_gas = 0
        
        origin_ins_solx = 0
        origin_bytes_solx = 0
        origin_gas_solx = 0
        
        for cc in contracts:
            json = contracts[cc]
            
            if c.strip() in json:
                bytecode = json[c.strip()]["evm"]["bytecode"]["object"]

                origin_ins_aux, gas = count_num_ins(bytecode.strip()) 
                origin_ins += origin_ins_aux
                origin_gas += gas
                origin_bytes += count_num_bytes(bytecode.strip())


            json_solx = contracts_solx.get(cc, [])
            
            if c.strip() in json_solx:
                bytecode = json_solx[c.strip()]["evm"]["bytecode"]["object"]
                origin_solx, gas_solx = count_num_ins(bytecode.strip())
                origin_ins_solx +=origin_solx
                origin_gas_solx += gas_solx
                
                origin_bytes_solx += count_num_bytes(bytecode.strip())
                
        if origin_ins != 0:
            print(log_opt_file + " ORIGIN NUM INS: " + str(origin_ins))
            print(log_opt_file + " ORIGIN NUM INS SOLX: " + str(origin_ins_solx))
            print(log_opt_file + " OPT NUM INS: " + str(opt))

            print(log_opt_file + " ORIGIN NUM BYTES: " + str(origin_bytes))
            print(log_opt_file + " ORIGIN NUM BYTES SOLX: " + str(origin_bytes_solx))
            print(log_opt_file + " OPT NUM BYTES: " + str(opt_bytes))

            print(log_opt_file + " ORIGIN OWN COSTAG: " + str(origin_gas))
            print(log_opt_file + " ORIGIN OWN COSTAG SOLX: " + str(origin_gas_solx))
            print(log_opt_file + " OPT OWN COSTAG: " + str(opt_gas))

            

def instrs_from_opcodes(origin_file, log_opt_file):
    with open(origin_file, 'r') as f:
        evm_origin = f.read()

    evm_opt = get_evm_code(log_opt_file)

    instrs_list = []
    for c in evm_opt:
        evm = evm_opt[c]

        opt = count_num_ins(evm.strip())
        opt_bytes = count_num_bytes(evm.strip())

        evm_dict = js.loads(evm_origin)
        contracts = evm_dict["contracts"]

        origin_ins, origin_bytes = 0, 0

        for cc in contracts:
            json = contracts[cc]

            if c.strip() in json:
                bytecode = json[c.strip()]["evm"]["bytecode"]["object"]
                origin_ins += count_num_ins(bytecode.strip())
                origin_bytes += count_num_bytes(bytecode.strip())

        instrs_list.append({"file": origin_file, "name": c,
                            "n_instrs_original": origin_ins, "n_instrs_grey": opt,
                            "bytes_original": origin_bytes, "bytes_grey": opt_bytes})
        
    return instrs_list

def measure_from_evm(evm_file) -> int:
    with open(evm_file, 'r') as f:
        evm = f.read().strip()
        return count_num_ins(evm)
    raise ValueError("Error opening file")

if __name__ == '__main__':
    if len(sys.argv) == 3:
        execute_script()
    elif len(sys.argv) == 4:
        execute_script_solx()
    # measure_from_evm(sys.argv[1])
    # print(instrs_from_opcodes(sys.argv[1], sys.argv[2]))

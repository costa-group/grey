import sys
import subprocess
import json as js
import os
import shlex

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

    print(res)
        
    return res

def count_evm_instructions(bytecode):
    """
    Cuenta las instrucciones en el bytecode de un archivo EVM.

    :param bytecode: Bytecode hexadecimal como una cadena.
    :return: Número total de instrucciones.
    """
    # Diccionario de las instrucciones EVM
    instructions = {
        0x00: "STOP", 0x01: "ADD", 0x02: "MUL", 0x03: "SUB",
        0x04: "DIV", 0x05: "SDIV", 0x06: "MOD", 0x07: "SMOD",
        0x08: "ADDMOD", 0x09: "MULMOD", 0x0a: "EXP", 0x0b: "SIGNEXTEND",
        0x10: "LT", 0x11: "GT", 0x12: "SLT", 0x13: "SGT",
        0x14: "EQ", 0x15: "ISZERO", 0x16: "AND", 0x17: "OR", 0x18: "XOR", 0x19: "NOT", 0x1a: "BYTE", 0x1b: "SHL", 0x1c: "SHR", 0x1d: "SAR",
        0x20: "SHA3",
        0x30: "ADDRESS", 0x31: "BALANCE", 0x32: "ORIGIN", 0x33: "CALLER",
        0x34: "CALLVALUE", 0x35: "CALLDATALOAD", 0x36: "CALLDATASIZE", 0x37: "CALLDATACOPY",
        0x38: "CODESIZE", 0x39: "CODECOPY", 0x3a: "GASPRICE", 0x3b: "EXTCODESIZE",
        0x3c: "EXTCODECOPY", 0x3d: "RETURNDATASIZE", 0x3e: "RETURNDATACOPY",
        0x3f: "EXTCODEHASH",
        0x40: "BLOCKHASH", 0x41: "COINBASE", 0x42: "TIMESTAMP", 0x43: "NUMBER",
        0x44: "DIFFICULTY", 0x45: "GASLIMIT", 0x46: "CHAINID", 0x47: "SELFBALANCE", 0x48: "BASEFEE",
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

    i = 0
    count = 0
    num_invalid = 0
    while i < len(bytecode):
        try:
            # Leer un byte (dos caracteres hexadecimales)
            opcode = int(bytecode[i:i+2], 16)
            count += 1  # Contar la instrucción
            
            if instructions[opcode] == "INVALID":
                num_invalid+=1
                if num_invalid == 2:
                    break
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


def count_num_ins(evm):
    pos_invalid = evm.find("fe")
    if pos_invalid != -1:
        second_invalid = evm.find("fe",pos_invalid+1)
        if(second_invalid != -1):
            real_evm = evm[:second_invalid]

            num_ins = count_evm_instructions(real_evm)

        else:
            real_evm = evm[:pos_invalid]
            num_ins = count_evm_instructions(real_evm)

        return num_ins
    else:
        return 0

if __name__ == '__main__':
    
    origin_file = sys.argv[1]
    log_opt_file = sys.argv[2]

    f = open(origin_file,"r")
    
    evm_origin = f.read()
    
    evm_opt = get_evm_code(log_opt_file)
    
    for c in evm_opt:
        evm = evm_opt[c]
    
        opt = count_evm_instructions(evm.strip())

        evm_dict = js.loads(evm_origin)
        contracts = evm_dict["contracts"]

        origin_ins = 0
        
        for cc in contracts:
            json = contracts[cc]

            if c.strip() in json:
                bytecode = json[c.strip()]["evm"]["bytecode"]["object"]
                origin_ins = count_evm_instructions(bytecode.strip())
                
    if origin_ins != 0:
        print(log_opt_file+" ORIGIN NUM INS: "+str(origin_ins))
        print(log_opt_file+" OPT NUM INS: "+str(opt))
    





        608060405263cafecafe5f5f6101000a81548173ffffffffffffffffffffffffffffffffffffffff021916908373ffffffffffffffffffffffffffffffffffffffff1602179055505b5b604d565b6105808061005a5f395ff3fe608060405234801561000f575f5ffd5b506004361061002d575f3560e01c8063b3de648b146100315761002d565b5f5ffd5b61004b600480360381019061004691906103e2565b610061565b60405161005891906103fd565b60405180910390f35b5f5f8214156100e9575f5f9054906101000a900473ffffffffffffffffffffffffffffffffffffffff1673ffffffffffffffffffffffffffffffffffffffff16630dbe671f6040518163ffffffff1660e01b81526004015f6040518083038186803b1580156100ce575f5ffd5b505afa1580156100e0573d5f5f3e3d5ffd5b505050506103c5565b6001821415610172575f5f9054906101000a900473ffffffffffffffffffffffffffffffffffffffff1673ffffffffffffffffffffffffffffffffffffffff16634df7e3d06040518163ffffffff1660e01b81526004015f604051808303815f87803b158015610157575f5ffd5b505af1158015610169573d5f5f3e3d5ffd5b505050506103c4565b60028214156101fb575f5f9054906101000a900473ffffffffffffffffffffffffffffffffffffffff1673ffffffffffffffffffffffffffffffffffffffff1663c3da42b86040518163ffffffff1660e01b81526004015f604051808303815f87803b1580156101e0575f5ffd5b505af11580156101f2573d5f5f3e3d5ffd5b505050506103c3565b6003821415610287575f5f9054906101000a900473ffffffffffffffffffffffffffffffffffffffff1673ffffffffffffffffffffffffffffffffffffffff1663c3da42b860016040518263ffffffff1660e01b81526004015f604051808303818588803b15801561026b575f5ffd5b505af115801561027d573d5f5f3e3d5ffd5b50505050506103c2565b6004821415610324575f5f9054906101000a900473ffffffffffffffffffffffffffffffffffffffff1673ffffffffffffffffffffffffffffffffffffffff16630c55699c6040518163ffffffff1660e01b81526004016020604051808303815f875af11580156102fa573d5f5f3e3d5ffd5b505050506040513d601f19601f8201168201806040525081019061031e919061040e565b506103c1565b60058214156103c0575f5f9054906101000a900473ffffffffffffffffffffffffffffffffffffffff1673ffffffffffffffffffffffffffffffffffffffff1663a56dfe4a6040518163ffffffff1660e01b81526004015f604051808303815f875af1158015610396573d5f5f3e3d5ffd5b505050506040513d5f823e3d601f19601f820116820180604052508101906103be919061043f565b505b5b5b5b5b5b8160016103d291906104fe565b90506103d9565b91905056610527565b5f602082840312156103f2575f5ffd5b813590505b92915050565b5f6020820190508282525b92915050565b5f6020828403121561041e575f5ffd5b815190505b92915050565b634e487b7160e01b5f52604160045260245ffd5b565b5f6020828403121561044f575f5ffd5b815167ffffffffffffffff811115610465575f5ffd5b808301905083601f820112151561047a575f5ffd5b805167ffffffffffffffff81111561049557610494610429565b5b604051601f19603f601f19601f8501160116810181811067ffffffffffffffff821117156104c6576104c5610429565b5b80604052508181528560208385010111156104df575f5ffd5b8160208401602083015e5f602083830101528093505050505b92915050565b5f82820190508082111561052057634e487b7160e01b5f52601160045260245ffd5b5b92915050565bfea2646970667358221220220dba573a37b473138fea59e5ef2bd3d1cc36e0e6e7e38acdb216c41d9d445364736f6c637824302e382e32392d63692e323032342e31302e33312b636f6d6d69742e35646162363763610055

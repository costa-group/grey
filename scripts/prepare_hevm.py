import re
import sys
import json as js
from typing import Dict, List
from pathlib import Path


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

def remove_auxdata(evm: str):
    """
    Removes the .auxdata introduced by grey. It is always of the same form
    """
    return evm.replace("000000000000000000000000000000000000000000000000000000000000000000"
                       "000000000000000000000000000000000000000000000000000000000000000000"
                       "00000000000000000000000000000000000053", "")


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

            # Manejar instrucciones PUSH (PUSH0 no requiere datos adicionales)
            if 0x60 <= opcode <= 0x7f:
                push_size = opcode - 0x60 + 1
                i += 2 + (push_size * 2)  # Saltar el tamaño de los datos incluidos

            elif opcode == 0xfe: #INVALID
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




def prepare_evm(evm: str):
    """
    Assumes the evm bytecode has no CBOR metadata appended
    """
    code_regions = split_evm_instructions(evm)
    return code_regions



def build_files(dir_file, contract_name, opt_regions, solc_regions):
    if len(opt_regions) == len(solc_regions):
        opt_regions.pop(0) #constructor
        solc_regions.pop(0) #constructor
           
        for i in range(len(opt_regions)):
            f_opt = open(dir_file+"/"+contract_name+str(i)+".grey","w")
            f.write(opt_regions[i])
            f_opt.close()

            f_solc = open(dir_file+"/"+contract_name+str(i)+".solc","w")
            f.write(solc_regions[i])
            f_opt.close()
            
    elif len(opt_regions) == len(solc_regions)-1:
        opt_regions.pop(0) #constructor
        solc_regions.pop(0) #constructor

        solc_regions.pop() # metadata
        assert(len(opt_regions) == len(solc_regions))

        for i in range(len(opt_regions)):
            f_opt = open(dir_file+"/"+contract_name+str(i)+".grey","w")
            f.write(opt_regions[i])
            f_opt.close()

            f_solc = open(dir_file+"/"+contract_name+str(i)+".solc","w")
            f.write(solc_regions[i])
            f_opt.close()

        
def execute_script():
    origin_file = sys.argv[1]
    log_opt_file = sys.argv[2]


    path_file = log_opt_file.split("/")
    path_file.pop()
    new_path = "/".join(path_file)

    print(new_path)
    
    f = open(origin_file, "r")

    evm_origin = f.read()

    evm_opt = get_evm_code(log_opt_file)
    
    for c in evm_opt:
        evm = evm_opt[c]
        opt_regions = prepare_evm(evm.strip())


        evm_dict = js.loads(evm_origin)
        contracts = evm_dict["contracts"]

        for cc in contracts:
            json = contracts[cc]
            
            if c.strip() in json:
                bytecode = json[c.strip()]["evm"]["bytecode"]["object"]
                bytecode_regions = prepare_evm(bytecode.strip()) 


    print("****************************")
    

if __name__ == '__main__':
    execute_script()

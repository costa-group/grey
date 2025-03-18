import json
import sys

def update_bytecode(json_file_path, contract_name, new_bytecode):
    """
    Lee un archivo JSON, sustituye el valor de la clave 'bytecode' y guarda el archivo actualizado.

    :param json_file_path: Fichero con el JSON de entrada.
    :param  contract_name: Nombre del contrato cuyo bytecode se va a sustituir.
    :param new_bytecode: Nuevo valor para la clave 'bytecode'.
    """
    
    for c in json_file_path:
 
        json_contract = json_file_path[c]

        if contract_name == json_contract["contract"].strip(":"):
             # Verificar si 'bytecode' está en el JSON
            json_contract["bytecode"] = new_bytecode             

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


if __name__ == '__main__':
    
    # Uso del script
    # Sustituye 'ruta/del/archivo.json' con la ruta de tu archivo JSON y 'nuevo_valor' con el valor deseado.
    test_file = sys.argv[1]
    log_file = sys.argv[2]

    evm_codes = get_evm_code(log_file)

    path_to_test = test_file.split("/")[:-1]

    result_file = "/".join(path_to_test)+"/test_grey"


    try:
        # Leer el archivo JSON
        with open(test_file, 'r') as file:
            data = json.load(file)

        for c in evm_codes:
            evm = evm_codes[c]

            update_bytecode(data, c.strip(), evm.strip())

        # Guardar el archivo JSON actualizado

        with open(result_file, 'w') as file:
            json.dump(data, file, indent=4)
            
    except:
        print("NO TEST: "+test_file)


    

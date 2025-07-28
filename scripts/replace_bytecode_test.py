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


    if len(sys.argv) == 3: #opt
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

        except:
            print("NO TEST: "+test_file)
        
    elif len(sys.argv) == 4: #Init test We have to replace the initial code in the test
        result_file = test_file
        
        with open(test_file, 'r') as file:
            data = json.load(file)
            
            origin_file = sys.argv[2]
            f = open(origin_file, "r")
            evm_origin = f.read()

            evm_dict = json.loads(evm_origin)
            contracts = evm_dict["contracts"]

            for cc in contracts:
                json_data = contracts[cc]
                contracts_names = json_data.keys()
                for c in contracts_names:
                    bytecode = json_data[c.strip()]["evm"]["bytecode"]["object"]

                    update_bytecode(data, c.strip(),bytecode.strip())
                            
    else:
        raise Exception("ERROR IN ARGS")


    # Guardar el archivo JSON actualizado
    with open(result_file, 'w') as file:
        json.dump(data, file, indent=4)



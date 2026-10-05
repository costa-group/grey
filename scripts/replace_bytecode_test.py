import json
import sys

def update_bytecode(json_file_path, contract_name, new_bytecode, source_file=None):
    """
    Lee un archivo JSON, sustituye el valor de la clave 'bytecode' y guarda el archivo actualizado.

    :param json_file_path: Fichero con el JSON de entrada.
    :param  contract_name: Nombre del contrato cuyo bytecode se va a sustituir.
    :param new_bytecode: Nuevo valor para la clave 'bytecode'.
    :param source_file: Fichero fuente del contrato (None si no se conoce).
    """
    
    for c in json_file_path:
 
        json_contract = json_file_path[c]

        # El campo 'contract' del test es "<fichero>:<contrato>" o ":<contrato>" (un único fichero)
        test_file, _, test_name = json_contract["contract"].rpartition(":")

        if contract_name == test_name and (test_file == "" or source_file is None or test_file == source_file):
        
             # Verificar si 'bytecode' está en el JSON
            json_contract["bytecode"] = new_bytecode             

def get_contract_sources(log_file):
    """
    Correspondencia entre los identificadores que usa grey para los contratos cuyo nombre aparece en varios ficheros
    fuente y su fichero y nombre ("Contract source: <id> -> <fichero>:<contrato>")
    """
    sources = {}
    with open(log_file, "r") as f:
        for line in f:
            if line.startswith("Contract source:"):
                key, target = line[len("Contract source:"):].split("->")
                filename, contract = target.strip().rsplit(":", 1)
                sources[key.strip()] = (filename, contract)
    return sources

def get_evm_code(log_file):

    f = open(log_file, "r")
    all_lines = f.readlines()

    # Solo las líneas con el código de un contrato ("Contract: <nombre> -> EVM Code: <código>")
    lines = list(filter(lambda x: x.startswith("Contract: ") and "-> EVM Code:" in x, all_lines))

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
        contract_sources = get_contract_sources(log_file)

        path_to_test = test_file.split("/")[:-1]

        result_file = "/".join(path_to_test)+"/test_grey"

        try:
            # Leer el archivo JSON
            with open(test_file, 'r') as file:
                data = json.load(file)
                for c in evm_codes:
                    evm = evm_codes[c]
                    source_file, contract_name = contract_sources.get(c.strip(), (None, c.strip()))
                    update_bytecode(data, contract_name, evm.strip(), source_file)

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

                    # Los contratos abstractos e interfaces no tienen bytecode
                    if bytecode.strip():
                        update_bytecode(data, c.strip(), bytecode.strip(), cc)
                            
    else:
        raise Exception("ERROR IN ARGS")


    # Guardar el archivo JSON actualizado
    with open(result_file, 'w') as file:
        json.dump(data, file, indent=4)



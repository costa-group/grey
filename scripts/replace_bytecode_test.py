import json
import sys

def update_bytecode(json_file_path, contract_name, new_bytecode, output_file_path=None):
    """
    Lee un archivo JSON, sustituye el valor de la clave 'bytecode' y guarda el archivo actualizado.

    :param json_file_path: Ruta del archivo JSON de entrada.
    :param new_bytecode: Nuevo valor para la clave 'bytecode'.
    :param output_file_path: Ruta del archivo JSON de salida. Si no se proporciona, se sobrescribe el original.
    """
    try:
        # Leer el archivo JSON
        with open(json_file_path, 'r') as file:
            data = json.load(file)
        
        # Verificar si 'bytecode' está en el JSON
        if "bytecode" in data:
            data["bytecode"] = new_bytecode
            print(f"Clave 'bytecode' actualizada a: {new_bytecode}")
        else:
            print("La clave 'bytecode' no existe en el JSON. Será añadida.")
            data["bytecode"] = new_bytecode

        # Determinar la ruta de salida
        if output_file_path is None:
            output_file_path = json_file_path
        
        # Guardar el archivo JSON actualizado
        with open(output_file_path, 'w') as file:
            json.dump(data, file, indent=4)
        
        print(f"Archivo JSON actualizado guardado en: {output_file_path}")
    except FileNotFoundError:
        print(f"El archivo {json_file_path} no fue encontrado.")
    except json.JSONDecodeError:
        print("Error al decodificar el archivo JSON. Asegúrate de que tenga un formato válido.")
    except Exception as e:
        print(f"Ocurrió un error: {e}")



if __name__ == '__main__':
    
    # Uso del script
    # Sustituye 'ruta/del/archivo.json' con la ruta de tu archivo JSON y 'nuevo_valor' con el valor deseado.
    test_file = sys.argv[1]
    log_file = sys.argv[2]

    evm_codes = get_evm_code(log_file)

    path_to_test = test_file.split("/")[::-2]

    result_file = "/".join(path_to_test)+"/test_grey"
    
    update_bytecode(test_file, contract_name, evm_codes, result_file)

import os
import json

def generate_standard_json_input(directory):
    # Estructura base del JSON input
    standard_json_input = {
        "language": "Solidity",
        "sources": {},
        "settings": {
            "optimizer": {
                "enabled": True,
                "runs": 200
            },
            "outputSelection": {
                "*": {
                    "*": [
                        "abi",
                        "metadata",
                        "evm.bytecode",
                        "evm.deployedBytecode",
                        "evm.methodIdentifiers"
                    ]
                }
            }
        }
    }
    
    # Iterar sobre los archivos .sol en el directorio especificado
    for filename in os.listdir(directory):
        if filename.endswith(".sol"):
            file_path = os.path.join(directory, filename)
            with open(file_path, "r", encoding="utf-8") as file:
                # Leer el contenido de cada archivo .sol
                solidity_code = file.read()
                # Añadir el contenido al JSON input
                standard_json_input["sources"][filename] = {
                    "content": solidity_code
                }
    
    # Guardar el JSON input en un archivo
    output_file = os.path.join(directory, "standard_input.json")
    with open(output_file, "w", encoding="utf-8") as json_file:
        json.dump(standard_json_input, json_file, indent=4)
    
    print(f"Archivo JSON de entrada generado en: {output_file}")

# Especifica el directorio que contiene los archivos Solidity
# Ejemplo de uso: "./contracts"
directory = "./"
generate_standard_json_input(directory)

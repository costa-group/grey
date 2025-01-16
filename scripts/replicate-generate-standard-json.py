import os
import json
import shutil


def parse_multisection_solidity(file_path):
    # Diccionario para almacenar las secciones
    sources = {}

    # Leer el archivo Solidity
    with open(file_path, 'r') as file:
        content = file.read()

    # Buscar las secciones con el patrón "==== Source: X ===="
    sections = re.split(r"==== Source: (.*?) ====", content)

    # Procesar las secciones
    for i in range(1, len(sections), 2):
        section_name = sections[i].strip()  # Nombre de la sección
        section_content = sections[i + 1].strip()  # Contenido de la sección
        sources[section_name] = {"content": section_content}

    return sources


def parse_single_solidity(file_path):

def generate_standard_json_input(directory, out_dir):
    """
    Genera un archivo JSON estándar por cada archivo .sol en el directorio especificado.
    Crea subdirectorios para cada archivo .sol y copia los archivos .sol junto con el JSON generado.
    """
    # Estructura base del JSON input
    standard_json_input = {
        "language": "Yul",
        "sources": {},
        "settings": {
            "optimizer": {
                "enabled": True,
                "runs": 200,
                "details": {
                    "peephole": False,
                    "inliner": False,
                    "jumpdestRemover": False,
                    "orderLiterals": False,
                    "deduplicate": False,
                    "cse": False,
                    "constantOptimizer": False
                }

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
        if filename.endswith(".yul"):
            standard_json_input["sources"]= {}
            file_path = os.path.join(directory, filename)

            f = open(file_path, "r")
            file_content = f.read()
            f.close()
            
            if (file_content.find("====") != -1 and file_content.find("Source: ") !=-1 ):
                source = parse_multisection_solidity(file_path)
                standard_json_input["sources"] = source

            else:

                with open(file_path, "r", encoding="utf-8") as file:
                    # Leer el contenido de cada archivo .sol
                    solidity_code = file.read()
                    # Añadir el contenido al JSON input
                    standard_json_input["sources"][filename] = {
                        "content": solidity_code
                    }
            
            # Crear subdirectorio con el nombre del archivo sin extensión
            outdir_name = os.path.join(out_dir, filename.split(".yul")[0])
            os.makedirs(outdir_name, exist_ok=True)

            # Copiar el archivo .sol al subdirectorio
            shutil.copy(file_path, os.path.join(outdir_name, filename))
            
            # Generar el archivo JSON en el subdirectorio
            output_file = os.path.join(outdir_name, f"{filename.split('.yul')[0]}_standard_input.json")
            with open(output_file, "w", encoding="utf-8") as json_file:
                json.dump(standard_json_input, json_file, indent=4)
    
            print(f"Archivo JSON de entrada generado en: {output_file}")

def replicar_estructura_y_procesar(origen, destino):
    """
    Replica la estructura de directorios desde 'origen' hasta 'destino'
    y ejecuta el procesamiento de archivos .sol en cada directorio.
    """
    for root, dirs, _ in os.walk(origen):
        # Obtiene la ruta relativa del directorio actual con respecto al origen
        ruta_relativa = os.path.relpath(root, origen)
        
        # Crea la ruta correspondiente en el directorio de salida
        destino_actual = os.path.join(destino, ruta_relativa)
        os.makedirs(destino_actual, exist_ok=True)
        
        print(f"Directorio replicado: {destino_actual}")
        
        # Ejecutar el procesamiento de archivos .sol en el directorio actual
        generate_standard_json_input(root, destino_actual)

if __name__ == "__main__":
    # Solicita los directorios de entrada y salida al usuario
    directorio_origen = input("Ingresa la ruta del directorio de entrada: ")
    directorio_destino = input("Ingresa la ruta del directorio de salida: ")

    if not os.path.exists(directorio_origen):
        print("El directorio de entrada no existe.")
    else:
        replicar_estructura_y_procesar(directorio_origen, directorio_destino)
        print("Estructura replicada y procesamiento completado.")

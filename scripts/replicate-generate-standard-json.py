import os
import json
import shutil

def generate_standard_json_input(directory, out_dir):
    """
    Genera un archivo JSON estándar por cada archivo .sol en el directorio especificado.
    Crea subdirectorios para cada archivo .sol y copia los archivos .sol junto con el JSON generado.
    """
    # Estructura base del JSON input
    standard_json_input = {
        "language": "Solidity",
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
        if filename.endswith(".sol"):
            file_path = os.path.join(directory, filename)
            with open(file_path, "r", encoding="utf-8") as file:
                # Leer el contenido de cada archivo .sol
                solidity_code = file.read()
                # Añadir el contenido al JSON input
                standard_json_input["sources"][filename] = {
                    "content": solidity_code
                }
            
            # Crear subdirectorio con el nombre del archivo sin extensión
            outdir_name = os.path.join(out_dir, filename.split(".sol")[0])
            os.makedirs(outdir_name, exist_ok=True)

            # Copiar el archivo .sol al subdirectorio
            shutil.copy(file_path, os.path.join(outdir_name, filename))
            
            # Generar el archivo JSON en el subdirectorio
            output_file = os.path.join(outdir_name, f"{filename.split('.sol')[0]}_standard_input.json")
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

import re
import json
import sys

def procesar_fichero(input_path):
    # Leer el archivo completo
    with open(input_path, 'r') as file:
        contenido = file.read()
    
    # Expresión regular para encontrar cada bloque de contrato
    contratos = re.split(r"=======\s(.*?)\s=======", contenido)
    
    # Procesar los bloques
    for i in range(1, len(contratos), 2):  # Itera sobre pares: nombre, contenido
        nombre_contrato = contratos[i].split(":")[-1]
        contenido_contrato = contratos[i + 1]
        
        # Eliminar la línea "EVM assembly:"
        contenido_contrato = re.sub(r"EVM assembly:\n", "", contenido_contrato)
        
        # Crear el archivo JSON
        nombre_archivo = f"{nombre_contrato.replace(':', '_')}-asm-solc.json"
        with open(nombre_archivo, 'w') as output_file:
            json.dump({"data": contenido_contrato.strip()}, output_file, indent=4)
        
        print(f"Archivo creado: {nombre_archivo}")


if __name__ == "__main__":
    
    # Ruta del archivo de entrada
    input_path = sys.argv[1]
    procesar_fichero(input_path)

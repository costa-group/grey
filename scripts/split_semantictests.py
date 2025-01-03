import json
import os

def split_json(input_file, output_dir):
    # Leer el archivo JSON principal
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Verificar si la carpeta de salida existe; si no, crearla
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # Iterar sobre cada clave y valor en el JSON
    for key, value in data.items():
        # Crear el nombre del archivo para cada clave
        name = "test_"+key.split("/")[-1].strip(".sol")
        output_file = os.path.join(output_dir, f"{name}.json")

        # Guardar cada objeto JSON en un archivo separado
        with open(output_file, 'w', encoding='utf-8') as out_f:
            json.dump(value, out_f, ensure_ascii=False, indent=4)

        print(f"Archivo creado: {output_file}")

if __name__ == "__main__":
    # Ruta del archivo JSON principal
    input_file = "testtrace"  # Cambia este nombre al de tu archivo JSON

    # Carpeta donde se guardarán los archivos resultantes
    output_dir = "salida_json"

    # Llamar a la función para separar los JSON
    split_json(input_file, output_dir)

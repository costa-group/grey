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
        real_key = key.split("/")[1::]
        name = ("_".join(real_key)).strip(".sol")
        print(name)
        
        #name = "test_"+key.split("/")[-1].strip(".sol")
        if not os.path.exists(output_dir+"/"+name):
            os.makedirs(output_dir+"/"+name)
        
        # Guardar cada objeto JSON en un archivo separado
        with open(output_dir+"/"+name+"/test", 'w', encoding='utf-8') as out_f:
            new_val = {}
            new_val[key] = value
            json.dump(new_val, out_f, ensure_ascii=False, indent=4)

        print(f"Archivo creado en : "+output_dir+"/"+name)

if __name__ == "__main__":
    # Ruta del archivo JSON principal
    input_file = "testtrace"  # Cambia este nombre al de tu archivo JSON

    # Carpeta donde se guardarán los archivos resultantes
    output_dir = "/Users/pablo/Repositorios/ethereum/grey/examples/test/semanticTests"

    # Llamar a la función para separar los JSON
    split_json(input_file, output_dir)

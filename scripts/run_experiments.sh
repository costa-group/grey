#!/bin/bash

# Directorio base (cambiar por la ruta deseada o pasar como argumento)
DIRECTORIO_BASE=/Users/pablo/Repositorios/ethereum/grey/scripts/prueba

# Comprobar si el directorio existe
if [ ! -d "$DIRECTORIO_BASE" ]; then
    echo "El directorio $DIRECTORIO_BASE no existe."
    exit 1
fi

# Recorrer todos los subdirectorios y buscar archivos .yul
find "$DIRECTORIO_BASE" -type f -name "*.yul" | while read -r yul_file; do
    # Obtener el directorio y el nombre base del archivo

    yul_dir=$(dirname "$yul_file")
    yul_base=$(basename "$yul_file" .yul)

    echo "Procesando archivo: $yul_file"

    /Users/pablo/Repositorios/ethereum/grey/examples/solc "$yul_file" --optimize --strict-assembly --yul-cfg-json --pretty-json &> "$yul_dir/$yul_base.cfg"

    /Users/pablo/Repositorios/ethereum/grey/examples/solc "$yul_file" --optimize --strict-assembly --pretty-json --asm-json &> "$yul_dir/$yul_base-asm-solc.json"

    sed -i '' '/^======= .* (EVM) =======$/d;/^EVM assembly:$/d' $yul_dir/$yul_base-asm-solc.json
    
    python3 /Users/pablo/Repositorios/ethereum/grey/src/grey_main.py -s "$yul_dir/$yul_base.cfg" -g -v -if yul-cfg -solc examples/solc -o "/tmp/$yul_base" &> "$yul_dir/yul_base.log"

    cp "/tmp/$yul_base"/*/*_asm.json "$yul_dir/"

    python3 extract_info.py "$yul_dir"

    JSON_FILES=`ls $yul_dir/*_asm.json`

    for JSON in $JSON_FILES; do

        echo "Executing import of $JSON"
        /Users/pablo/Repositorios/ethereum/grey/examples/solc --import-asm-json "$JSON" --asm-json --optimize &> "$yul_dir/$yul_base-asm-json-importer.json"
        
    done

    echo "*************************************"
    
done

echo "Procesamiento completado."

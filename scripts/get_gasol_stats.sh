#!/bin/bash

# Directorio base (cambiar por la ruta deseada o pasar como argumento)
DIRECTORIO_BASE=/Users/pablo/Repositorios/ethereum/grey/scripts/test/

# Comprobar si el directorio existe
if [ ! -d "$DIRECTORIO_BASE" ]; then
    echo "El directorio $DIRECTORIO_BASE no existe."
    exit 1
fi

# Recorrer todos los subdirectorios y buscar archivos .yul
# find "$DIRECTORIO_BASE" -type f -name "*.sol" | while read -r yul_file; do

# start=$(date +%s.%N)

# find "$DIRECTORIO_BASE" -type f -name "*standard_input.json" |  grep '/externalContract[^/]*/' | while read -r yul_file; do

find "$DIRECTORIO_BASE" -type f -name "*.output" | while read -r yul_file; do

    # Obtener el directorio y el nombre base del archivo

    yul_dir=$(dirname "$yul_file")
    yul_base=$(basename "$yul_file" .output)

    # test_dir_name=$(basename "$yul_dir")

    # solx_test_file="$test_dir_name/${yul_base}_standard_input.json"
    
    echo "Ejecuto: $yul_dir/solc_blocks"

    python3 compute_gasol_gains.py $yul_dir/solc_blocks
    echo "python3 compute_gasol_gains.py $yul_dir/solc_blocks"
    # python3 $GASOL_PATH/gasol_asm.py -s "$block_file" -bl -greedy &> "$yul_dir/solx_blocks/$block_file.log"
    
    
    echo "*************************************"

    
done

# end=$(date +%s.%N)
# elapsed=$(echo "$end - $start" | bc)
echo "Procesamiento completado."
# echo "Time passed: $elapsed seconds."

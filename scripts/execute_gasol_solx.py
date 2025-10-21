#!/bin/bash

# Directorio base (cambiar por la ruta deseada o pasar como argumento)
DIRECTORIO_BASE=/Users/pablo/Repositorios/ethereum/grey/scripts/test

GASOL_PATH=/Users/pablo/Repositorios/ethereum/gasol-optimizer/

# Comprobar si el directorio existe
if [ ! -d "$DIRECTORIO_BASE" ]; then
    echo "El directorio $DIRECTORIO_BASE no existe."
    exit 1
fi

# Recorrer todos los subdirectorios y buscar archivos .yul
# find "$DIRECTORIO_BASE" -type f -name "*.sol" | while read -r yul_file; do

# start=$(date +%s.%N)

# find "$DIRECTORIO_BASE" -type f -name "*standard_input.json" |  grep '/externalContract[^/]*/' | while read -r yul_file; do

find "$DIRECTORIO_BASE" -type f -name "*.solx_output" | while read -r yul_file; do

    # Obtener el directorio y el nombre base del archivo

    yul_dir=$(dirname "$yul_file")
    yul_base=$(basename "$yul_file" .solx_output)

    # test_dir_name=$(basename "$yul_dir")

    # solx_test_file="$test_dir_name/${yul_base}_standard_input.json"
    pushd $yul_dir
    echo "Procesando archivo: $yul_file"
    rm -rf solx_blocks
    mkdir solx_blocks
        
    # python3 $GASOL_PATH/gasol_asm.py -s "$block_file" -bl -greedy &> "$yul_dir/solx_blocks/$block_file.log"

    popd
    python3 generate_blocks_solx.py "$yul_dir/$yul_base.solx_output" "$yul_dir/solx_blocks"
    
    pushd $yul_dir/solx_blocks

    find "$yul_dir/solx_blocks" -type f -name "*" | while read -r block_file; do

        block_dir=$(dirname "$block_file")
        block_base=$(basename "$block_file")
        echo "$block_file"
        python3 $GASOL_PATH/gasol_asm.py "$block_file" -bl -greedy &> "$yul_dir/solx_blocks/$block_base.log"
        echo "python3 $GASOL_PATH/gasol_asm.py $block_file -bl -greedy &> $yul_dir/solx_blocks/$block_base.log"

    done
    popd
    
    
    echo "*************************************"

    
done

# end=$(date +%s.%N)
# elapsed=$(echo "$end - $start" | bc)
echo "Procesamiento completado."
# echo "Time passed: $elapsed seconds."

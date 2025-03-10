#!/bin/bash

# Directorio base (cambiar por la ruta deseada o pasar como argumento)
DIRECTORIO_BASE=/Users/pablo/Repositorios/ethereum/grey/scripts/test

GREY_PATH=/Users/pablo/Repositorios/ethereum/grey/src/grey_main.py
SOLC_PATH=/Users/pablo/Repositorios/ethereum/grey/examples/solc
TESTRUNNER_PATH=/Users/pablo/Repositorios/ethereum/solidity/build/test/tools/testrunner
EVMONE_LIB=/Users/pablo/Repositorios/ethereum/evmone/build/lib/libevmone.dylib

# Comprobar si el directorio existe
if [ ! -d "$DIRECTORIO_BASE" ]; then
    echo "El directorio $DIRECTORIO_BASE no existe."
    exit 1
fi

# Recorrer todos los subdirectorios y buscar archivos .yul
# find "$DIRECTORIO_BASE" -type f -name "*.sol" | while read -r yul_file; do

start=$(date +%s.%N)

find "$DIRECTORIO_BASE" -type f -name "*standard_input.json" | while read -r yul_file; do

    # Obtener el directorio y el nombre base del archivo

    yul_dir=$(dirname "$yul_file")
    yul_base=$(basename "$yul_file" _standard_input.json)

    echo "Procesando archivo: $yul_file"

    $SOLC_PATH "$yul_file" --standard-json &> "$yul_dir/$yul_base.output"

    echo "$SOLC_PATH $yul_file --standard-json &> $yul_dir/$yul_base.output"
    
    python3 $GREY_PATH -s "$yul_file" -g -v -if standard-json -solc $SOLC_PATH -o "/tmp/$yul_base" &> "$yul_dir/$yul_base.log"

    echo "python3 $GREY_PATH -s $yul_file -g -v -if standard-json -solc $SOLC_PATH -o /tmp/$yul_base"

    cp "/tmp/$yul_base"/*/*_asm.json "$yul_dir/"

    # python3 extract_info.py "$yul_dir"


    if [ -f "$yul_dir/test" ]; then
    
        python3 replace_bytecode_test.py "$yul_dir/test" "$yul_dir/$yul_base.log"

        echo "python3 replace_bytecode_test.py $yul_dir/test $yul_dir/$yul_base.log"

        $TESTRUNNER_PATH  $EVMONE_LIB $yul_dir/test $yul_dir/resultOriginal.json

        $TESTRUNNER_PATH  $EVMONE_LIB $yul_dir/test_grey $yul_dir/resultGrey.json

        python3 compare_outputs.py $yul_dir/resultOriginal.json $yul_dir/resultGrey.json > /dev/null;
        RES=$?
        # if diff $yul_dir/resultOriginal.json $yul_dir/resultGrey.json > /dev/null; then
        if [ $RES -eq 0 ]; then
            echo "[RES]: Test passed."
            echo "python3 count_num_ins.py $yul_dir/$yul_base.output $yul_dir/$yul_base.log"
            python3 count_num_ins.py "$yul_dir/$yul_base.output" "$yul_dir/$yul_base.log"
            
        else
            echo "[RES]: Test failed."
        fi

    else
        echo "Test not found: $yul_dir/"

    fi
    
    echo "*************************************"

    
done

end=$(date +%s.%N)
elapsed=$(echo "$end - $start" | bc)
echo "Procesamiento completado."
echo "Time passed: $elapsed seconds."

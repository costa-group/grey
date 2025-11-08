#!/bin/bash

# Directorio base (cambiar por la ruta deseada o pasar como argumento)
DIRECTORIO_BASE=/home/pablo/Repositorios/ethereum/grey/scripts/test

GREY_PATH=/home/pablo/Repositorios/ethereum/grey/src/grey_main.py
SOLC_PATH=/home/pablo/Repositorios/ethereum/grey/solc-latest
TESTRUNNER_PATH=/home/pablo/Repositorios/ethereum/solidity/build/test/tools/testrunner
SOLX_PATH=/hoome/pablo/Repositorios/ethereum/solx/solx-macosx-profiling
TEST_SOLX_PATH=/home/pablo/Repositorios/ethereum/grey/scripts/test_solx

EVMONE_LIB=/home/pablo/Repositorios/ethereum/evmone/build/lib/libevmone.so

# Comprobar si el directorio existe
if [ ! -d "$DIRECTORIO_BASE" ]; then
    echo "El directorio $DIRECTORIO_BASE no existe."
    exit 1
fi

# Recorrer todos los subdirectorios y buscar archivos .yul
# find "$DIRECTORIO_BASE" -type f -name "*.sol" | while read -r yul_file; do

# start=$(date +%s.%N)

# find "$DIRECTORIO_BASE" -type f -name "*standard_input.json" |  grep '/externalContract[^/]*/' | while read -r yul_file; do

find "$DIRECTORIO_BASE" -type f -name "*standard_input.json" | while read -r yul_file; do

    
    # Obtener el directorio y el nombre base del archivo

    yul_dir=$(dirname "$yul_file")
    yul_base=$(basename "$yul_file" _standard_input.json)

    test_dir_name=$(basename "$yul_dir")

    solx_test_file="$test_dir_name/${yul_base}_standard_input.json"
    
    echo "Procesando archivo: $yul_file"

    pushd $yul_dir
    start_solc=$(date +%s.%N)
    $SOLC_PATH "$yul_file" --standard-json &> "$yul_dir/$yul_base.output"
    end_solc=$(date +%s.%N)
    echo "$start_solc"
    echo "$end_solc"
    elapsed_solc=$(echo "$end_solc - $start_solc" | bc)
    echo "TIME SOLC $yul_file : $elapsed_solc"
    
    echo "$SOLC_PATH $yul_file --standard-json &> $yul_dir/$yul_base.output"

    #SOLX EXECUTION
    start_solx=$(date +%s.%N)
    $SOLX_PATH --standard-json "$TEST_SOLX_PATH/$solx_test_file" &> "$yul_dir/$yul_base.solx_output"
    end_solx=$(date +%s.%N)
    echo "$start_solx"
    echo "$end_solx"
    elapsed_solx=$(echo "$end_solx - $start_solx" | bc)
    echo "TIME SOLX $yul_file : $elapsed_solx"
    
    echo "$SOLX_PATH --standard-json $TEST_SOLX_PATH/$solx_test_file   &> $yul_dir/$yul_base.solx_output"
    

    start=$(date +%s.%N)
    python3 $GREY_PATH -s "$yul_file" -g -j -if standard-json -solc $SOLC_PATH -o "/tmp/$yul_base" &> "$yul_dir/$yul_base.log"
    end=$(date +%s.%N)
    popd
    elapsed=$(echo "$end - $start" | bc)
    echo "TIME GREY $yul_file : $elapsed"
    echo "TIME SOLC $yul_file : $elapsed_solc" >> "$yul_dir/$yul_base.log"
    
    echo "python3 $GREY_PATH -s $yul_file -g -v -if standard-json -solc $SOLC_PATH -o /tmp/$yul_base &> $yul_dir/$yul_base.log"

    cp "/tmp/$yul_base"/*/*_asm.json "$yul_dir/"

    # python3 extract_info.py "$yul_dir"


    if [ -f "$yul_dir/test" ]; then
    
        python3 replace_bytecode_test.py "$yul_dir/test" "$yul_dir/$yul_base.log"

        python3 replace_bytecode_test.py "$yul_dir/test" "$yul_dir/$yul_base.output" init
        
        echo "python3 replace_bytecode_test.py $yul_dir/test $yul_dir/$yul_base.log"

        echo "python3 replace_bytecode_test.py $yul_dir/test $yul_dir/$yul_base.output init"

        
        $TESTRUNNER_PATH  $EVMONE_LIB $yul_dir/test $yul_dir/resultOriginal.json

        $TESTRUNNER_PATH  $EVMONE_LIB $yul_dir/test_grey $yul_dir/resultGrey.json

        # python3 compare_outputs.py $yul_dir/resultOriginal.json $yul_dir/resultGrey.json $yul_file
        python3 compare_outputs.py $yul_dir/resultOriginal.json $yul_dir/test $yul_dir/resultGrey.json $yul_dir/test_grey $yul_file
        echo "python3 compare_outputs.py $yul_dir/resultOriginal.json $yul_dir/test $yul_dir/resultGrey.json $yul_dir/test_grey $yul_file"
        RES=$?
        # if diff $yul_dir/resultOriginal.json $yul_dir/resultGrey.json > /dev/null; then
        if [ $RES -eq 0 ]; then
            echo "[RES]: Test passed."
            echo "python3 count_num_ins.py $yul_dir/$yul_base.output $yul_dir/$yul_base.log"
            python3 count_num_ins.py "$yul_dir/$yul_base.output" "$yul_dir/$yul_base.log" "$yul_dir/$yul_base.solx_output"


            echo "python3 prepare_hevm.py $yul_dir/$yul_base.output $yul_dir/$yul_base.log"
            python3 prepare_hevm.py "$yul_dir/$yul_base.output" "$yul_dir/$yul_base.log"

            echo "python3 compare_solx.py $yul_dir/$yul_base.log $yul_dir/$yul_base.solx_output $yul_dir/intermediate.json"
            python3 compare_solx.py "$yul_dir/$yul_base.log" "$yul_dir/$yul_base.solx_output" "$yul_dir/intermediate.json"
            
        else
            echo "[RES]: Test failed."
        fi

    else
        echo "Test not found: $yul_dir/"

    fi
    
    echo "*************************************"
    
done

# end=$(date +%s.%N)
# elapsed=$(echo "$end - $start" | bc)
echo "Procesamiento completado."
# echo "Time passed: $elapsed seconds."

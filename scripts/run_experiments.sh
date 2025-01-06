#!/bin/bash

# Directorio base (cambiar por la ruta deseada o pasar como argumento)
DIRECTORIO_BASE=/Users/pablo/Repositorios/ethereum/grey/scripts/test

# Comprobar si el directorio existe
if [ ! -d "$DIRECTORIO_BASE" ]; then
    echo "El directorio $DIRECTORIO_BASE no existe."
    exit 1
fi

# Recorrer todos los subdirectorios y buscar archivos .yul
# find "$DIRECTORIO_BASE" -type f -name "*.sol" | while read -r yul_file; do
find "$DIRECTORIO_BASE" -type f -name "*standard_input.json" | while read -r yul_file; do

    # Obtener el directorio y el nombre base del archivo

    yul_dir=$(dirname "$yul_file")
    yul_base=$(basename "$yul_file" _standard_input.json)

    echo "Procesando archivo: $yul_file"

    # /Users/pablo/Repositorios/ethereum/grey/examples/solc "$yul_file" --optimize --yul-cfg-json --pretty-json &> "$yul_dir/$yul_base.cfg"

    # /Users/pablo/Repositorios/ethereum/grey/examples/solc "$yul_file" --optimize --strict-assembly --pretty-json --asm-json &> "$yul_dir/$yul_base-asm-solc.json"

    # /Users/pablo/Repositorios/ethereum/grey/examples/solc "$yul_file" --optimize --pretty-json --asm-json &> "$yul_dir/$yul_base-asm-solc.json"

    # sed -i '' '/^======= .* (EVM) =======$/d;/^EVM assembly:$/d' $yul_dir/$yul_base-asm-solc.json
    
    # python3 /Users/pablo/Repositorios/ethereum/grey/src/grey_main.py -s "$yul_dir/$yul_base.cfg" -g -v -if yul-cfg -solc examples/solc -o "/tmp/$yul_base" &> "$yul_dir/yul_base.log"
    
    python3 /Users/pablo/Repositorios/ethereum/grey/src/grey_main.py -s "$yul_file" -g -v -if standard-json -solc /Users/pablo/Repositorios/ethereum/grey/examples/solc -o "/tmp/$yul_base" &> "$yul_dir/$yul_base.log"

    echo "python3 /Users/pablo/Repositorios/ethereum/grey/src/grey_main.py -s $yul_file -g -v -if standard-json -solc /Users/pablo/Repositorios/ethereum/grey/examples/solc -o /tmp/$yul_base"

    cp "/tmp/$yul_base"/*/*_asm.json "$yul_dir/"

    # python3 extract_info.py "$yul_dir"

    python3 replace_bytecode_test.py "$yul_dir/test" "$yul_dir/$yul_base.log"

    echo "python3 replace_bytecode_test.py $yul_dir/test $yul_dir/$yul_base.log"

    /Users/pablo/Repositorios/ethereum/solidity/build/test/tools/testrunner  /Users/pablo/Repositorios/ethereum/evmone/build/lib/libevmone.dylib $yul_dir/test $yul_dir/resultOriginal.json

    /Users/pablo/Repositorios/ethereum/solidity/build/test/tools/testrunner  /Users/pablo/Repositorios/ethereum/evmone/build/lib/libevmone.dylib $yul_dir/test_grey $yul_dir/resultGrey.json

    if diff $yul_dir/resultOriginal.json $yul_dir/resultGrey.json > /dev/null; then
    echo "[RES]: Test passed."
else
    echo "[RES]: Test failed."
fi
    
    
    echo "*************************************"

    
done

echo "Procesamiento completado."

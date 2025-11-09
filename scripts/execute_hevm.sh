#!/bin/bash

# Directorio base (cambiar por la ruta deseada o pasar como argumento)
DIRECTORIO_BASE=/Users/pablo/Repositorios/ethereum/grey/scripts/test

HEVM_PATH=/Users/pablo/Repositorios/ethereum/grey/examples/hevm-arm64-macos

# Comprobar si el directorio existe
if [ ! -d "$DIRECTORIO_BASE" ]; then
    echo "El directorio $DIRECTORIO_BASE no existe."
    exit 1
fi

find "$DIRECTORIO_BASE" -type f -name "*.solc" | while read -r yul_file; do
    # Obtener el directorio y el nombre base del archivo

    yul_dir=$(dirname "$yul_file")
    yul_base=$(basename "$yul_file" .solc)

    echo "Procesando hevm para: $yul_file"
    echo "$HEVM_PATH equivalence --code-a \"\$(<${yul_file})\" --code-b \"\$(<${yul_dir}/${yul_base}.grey)\""


    timeout 180s $HEVM_PATH equivalence --code-a "$(<$yul_file)" --code-b "$(<$yul_dir/$yul_base.grey)"

    RES=$?
    echo "$RES"
    
    if [ $RES -eq 0 ]; then
        echo "HEVM passed"
        
    elif [ $RES -eq 1 ]; then
        echo "HEVM failed"

    elif [ $RES -eq 124 ]; then
        echo "HEVM timeout"

    else
        echo "Other"
    fi
done


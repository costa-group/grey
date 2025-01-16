#!/bin/bash

# Comprobar argumentos
if [ $# -ne 1 ]; then
    echo "Uso: $0 <directorio_raiz>"
    exit 1
fi

DIRECTORIO_RAIZ=$1

# Verificar si el directorio raíz existe
if [ ! -d "$DIRECTORIO_RAIZ" ]; then
    echo "Error: El directorio $DIRECTORIO_RAIZ no existe o no es un directorio."
    exit 1
fi

# Función para mover subdirectorios al primer nivel
mover_subdirectorios() {
    local dir_actual="$1"
    local ruta_base="$2"

    for item in "$dir_actual"/*; do
        if [ -d "$item" ]; then
            local nombre_dir=$(basename "$item")
            local nuevo_nombre="${ruta_base}${nombre_dir}"

            # Ruta destino en el primer nivel
            local destino="$DIRECTORIO_RAIZ/${nuevo_nombre}"

            # Mover si no existe en la raíz, sino agregar sufijo único
            if [ -e "$destino" ]; then
                contador=1
                while [ -e "${destino}_$contador" ]; do
                    contador=$((contador + 1))
                done
                destino="${destino}_$contador"
            fi

            # Mover el directorio al primer nivel
            mv "$item" "$destino"
            echo "Movido: $item -> $destino"

            # Procesar recursivamente los subdirectorios
            mover_subdirectorios "$destino" "${nuevo_nombre}_"
        fi
    done
}

# Iniciar la operación desde el directorio raíz
mover_subdirectorios "$DIRECTORIO_RAIZ" ""

echo "Operación completada."

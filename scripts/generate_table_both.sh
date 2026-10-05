#!/bin/bash
# Genera la tabla conjunta de noopt y opt (noopt arriba, opt abajo con el superíndice opt, separados por una doble
# línea) con generate_table.py, a partir de las salidas de run_all_noopt.sh y run_all_opt.sh
# (table-experiments-both.tex)
# Uso: ./generate_table_both.sh
# Con DRY_RUN=1 solo muestra lo que haría
cd "$(dirname "$0")" || exit 1

if [ $# -gt 0 ]; then
    echo "Uso: $0"
    exit 1
fi
PREFIX=salida
TABLE=table-experiments-both.tex

# Las 12 salidas que necesita la tabla: tests y most_called, noopt y opt, normal, junk y -d 8
missing=0
for mode in noopt opt; do
    for dataset in test mostcalled; do
        for suffix in "" "-junk" "8"; do
            file="$PREFIX-$dataset-$mode$suffix"
            if [ ! -f "$file" ]; then
                echo "ERROR: falta $file"
                missing=1
            elif ! grep -q "^Procesamiento completado" "$file"; then
                echo "ERROR: $file no ha terminado"
                missing=1
            fi
        done
        # generate_table.py elige <...>8 antes que <...>-8: un -8 antiguo no se usa, pero conviene saberlo
        if [ -f "$PREFIX-$dataset-${mode}8" ] && [ -f "$PREFIX-$dataset-$mode-8" ]; then
            echo "AVISO: existen $PREFIX-$dataset-${mode}8 y $PREFIX-$dataset-$mode-8; se usa el primero"
        fi
    done
done
[ "$missing" = 1 ] && exit 1

echo "[$(date '+%d-%m %H:%M')] python3 generate_table.py $PREFIX both -o $TABLE"
[ -n "$DRY_RUN" ] && exit 0
python3 generate_table.py "$PREFIX" both -o "$TABLE" || { echo "ERROR al generar la tabla"; exit 1; }
echo "[$(date '+%d-%m %H:%M')] tabla conjunta: $TABLE"

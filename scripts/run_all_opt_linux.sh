#!/bin/bash
# Versión para Linux de run_all_opt.sh, generada por make_linux_scripts.py: no la edites a mano
# Exportadas: las opciones de grey (p. ej. --solc-cfg-fallback) se construyen dentro de los procesos en paralelo
export GREY_ROOT=${GREY_ROOT:-$HOME/grey}
export GREY_TOOLS=${GREY_TOOLS:-$HOME/grey_tools}
# grey sin pygraphviz (solo lo usa para los .dot de depuración)
export PYTHONPATH=$GREY_TOOLS/pyshim${PYTHONPATH:+:$PYTHONPATH}
# Ejecuta todas las configuraciones (y stack too deep) de opt (normal, junk y -d 8) de los tests y de most_called, una detrás de otra,
# y genera su tabla con generate_table.py (table-experiments-opt.tex)
# Uso: ./run_all_opt_linux.sh
# Con DRY_RUN=1 solo muestra lo que haría
MODE=opt
cd "$(dirname "$0")" || exit 1

if [ $# -gt 0 ]; then
    echo "Uso: $0"
    exit 1
fi
PREFIX=salida
TABLE=table-experiments-$MODE.tex

# run <script> <fichero de salida> [argumentos]: lanza una configuración y comprueba que haya terminado
run() {
    local script=$1 out=$2
    shift 2
    echo "[$(date '+%d-%m %H:%M')] ./$script $MODE $* > $out"
    [ -n "$DRY_RUN" ] && return 0
    ./"$script" "$MODE" "$@" > "$out" 2>&1
    if ! grep -q "^Procesamiento completado" "$out"; then
        echo "ERROR: $script $MODE $* no ha terminado (mira $out)"
        exit 1
    fi
}

run run_experiments_linux.sh "$PREFIX-test-$MODE"
run run_experiments_linux.sh "$PREFIX-test-$MODE-junk" junk
run run_experiments_linux.sh "$PREFIX-test-${MODE}8" 8
run run_experiments_most_called_linux.sh "$PREFIX-mostcalled-$MODE"
run run_experiments_most_called_linux.sh "$PREFIX-mostcalled-$MODE-junk" junk
run run_experiments_most_called_linux.sh "$PREFIX-mostcalled-${MODE}8" 8
# Stack too deep (test_stack_too_deep_<modo>): no entra en la tabla, pero sí en las figuras de tiempos (generate_figures.sh)
run run_experiments_stack_too_deep_linux.sh "$PREFIX-std-$MODE"

echo "[$(date '+%d-%m %H:%M')] python3 generate_table.py $PREFIX $MODE -o $TABLE"
[ -n "$DRY_RUN" ] && exit 0
python3 generate_table.py "$PREFIX" "$MODE" -o "$TABLE" || { echo "ERROR al generar la tabla"; exit 1; }
echo "[$(date '+%d-%m %H:%M')] $MODE terminado: $TABLE"

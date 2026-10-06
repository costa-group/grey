#!/bin/bash
# Genera las figuras de tiempos del paper (times-per-phase-all.png y comparison-plot.png) de una configuración, a
# partir de las salidas de run_all*.sh (salida-test-<modo> y salida-mostcalled-<modo>, sus .log por contrato) y de la
# ejecución de stack-too-deep (test_stack_too_deep_<modo>), en figs_paper/<modo> (cada modo en su carpeta: no se pisan)
# Uso: ./generate_figures.sh opt|noopt
cd "$(dirname "$0")" || exit 1
MODE=$1
if [ "$MODE" != "opt" ] && [ "$MODE" != "noopt" ]; then
    echo "Uso: $0 opt|noopt"
    exit 1
fi
for file in salida-test-$MODE salida-mostcalled-$MODE; do
    if [ ! -f "$file" ] || ! grep -q "^Procesamiento completado" "$file"; then
        echo "ERROR: falta $file o no ha terminado"
        exit 1
    fi
done
STD=$PWD/test_stack_too_deep_$MODE
[ -d "$STD" ] || { echo "ERROR: no existe $STD"; exit 1; }
[ -n "$(ls "$STD"/*/*.log 2>/dev/null)" ] || echo "AVISO: $STD no tiene .log (ejecuta run_experiments_stack_too_deep_*.sh $MODE)"
OUT=figs_paper/$MODE
mkdir -p "$OUT/figs"
# Las líneas NUM INS de los tests y de most_called (como get_stats): print_times_all.py lee los .log de cada contrato
grep -h "NUM INS" salida-test-$MODE salida-mostcalled-$MODE > "$OUT/num_instructions_all.txt"
(cd "$OUT" && MPLBACKEND=Agg python3 ../../print_times_all.py num_instructions_all.txt "$STD" > print_times_all.out 2>&1) \
    || { echo "ERROR en print_times_all.py (mira $OUT/print_times_all.out)"; exit 1; }
cp "$OUT/figs/times-per-phase.png" "$OUT/times-per-phase-all.png"
cp "$OUT/figs/comparison-plot.png" "$OUT/comparison-plot.png"
echo "Figuras de $MODE en $OUT: times-per-phase-all.png, comparison-plot.png (y el resto en $OUT/figs)"

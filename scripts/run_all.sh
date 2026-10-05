#!/bin/bash
# Ejecuta todas las configuraciones de noopt y de opt (tests y most_called) y genera sus dos tablas
# (ver run_all_noopt.sh y run_all_opt.sh)
# Uso: ./run_all.sh
# Con DRY_RUN=1 solo muestra lo que haría
cd "$(dirname "$0")" || exit 1
if [ $# -gt 0 ]; then
    echo "Uso: $0"
    exit 1
fi
./run_all_noopt.sh || exit 1
./run_all_opt.sh || exit 1
echo "[$(date '+%d-%m %H:%M')] todo terminado"

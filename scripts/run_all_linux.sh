#!/bin/bash
# Versión para Linux de run_all.sh, generada por make_linux_scripts.py: no la edites a mano
# Exportadas: las opciones de grey (p. ej. --solc-cfg-fallback) se construyen dentro de los procesos en paralelo
export GREY_ROOT=${GREY_ROOT:-$HOME/grey}
export GREY_TOOLS=${GREY_TOOLS:-$HOME/grey_tools}
# grey sin pygraphviz (solo lo usa para los .dot de depuración)
export PYTHONPATH=$GREY_TOOLS/pyshim${PYTHONPATH:+:$PYTHONPATH}
# Ejecuta todas las configuraciones de noopt y de opt (tests y most_called) y genera sus dos tablas
# (ver run_all_noopt_linux.sh y run_all_opt_linux.sh)
# Uso: ./run_all_linux.sh
# Con DRY_RUN=1 solo muestra lo que haría
cd "$(dirname "$0")" || exit 1
if [ $# -gt 0 ]; then
    echo "Uso: $0"
    exit 1
fi
./run_all_noopt_linux.sh || exit 1
./run_all_opt_linux.sh || exit 1
echo "[$(date '+%d-%m %H:%M')] todo terminado"

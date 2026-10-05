#!/bin/bash
# Versión para Linux de run_experiments_most_called_macos.sh, generada por make_linux_scripts.py: no la edites a mano
# Exportadas: las opciones de grey (p. ej. --solc-cfg-fallback) se construyen dentro de los procesos en paralelo
export GREY_ROOT=${GREY_ROOT:-$HOME/grey}
export GREY_TOOLS=${GREY_TOOLS:-$HOME/grey_tools}
# grey sin pygraphviz (solo lo usa para los .dot de depuración)
export PYTHONPATH=$GREY_TOOLS/pyshim${PYTHONPATH:+:$PYTHONPATH}

# Number of files processed concurrently: half of the available cores (it can be overridden with JOBS=n)
if [ -z "$JOBS" ]; then
    CORES=$( (nproc || sysctl -n hw.ncpu) 2>/dev/null )
    JOBS=$(( ${CORES:-2} / 2 ))
    [ "$JOBS" -lt 1 ] && JOBS=1
fi
# The variables defined below are exported to the parallel jobs
set -a


# Uso: ./run_experiments_most_called_linux.sh opt|noopt [junk] [profundidad]
#   opt|noopt:   directorio de los contratos (test_most_called_opt o test_most_called_noopt), solc y opciones de grey
#   junk:        opcional, añade _junk al directorio y llama a grey con -j
#   profundidad: opcional, se añade al directorio (test_most_called_<modo><profundidad>) y se pasa a grey como -d <profundidad>
#   Directorio: test_most_called_<modo>[<profundidad>][_junk], p.ej. test_most_called_opt, test_most_called_noopt8
# Los argumentos opcionales pueden ir en cualquier orden
MODE=$1
shift
if [ "$MODE" != "opt" ] && [ "$MODE" != "noopt" ]; then
    echo "Uso: $0 opt|noopt [junk] [profundidad]"
    exit 1
fi
DEPTH_FLAG=""
DEPTH_SUFFIX=""
JUNK_FLAG=""
JUNK_SUFFIX=""
for arg in "$@"; do
    if [ "$arg" = "junk" ]; then
        JUNK_FLAG="-j"
        JUNK_SUFFIX="_junk"
    elif [[ "$arg" =~ ^[0-9]+$ ]]; then
        DEPTH_FLAG="-d $arg"
        DEPTH_SUFFIX="$arg"
    else
        echo "Argumento desconocido: $arg"
        echo "Uso: $0 opt|noopt [junk] [profundidad]"
        exit 1
    fi
done

# Directorio base
DIRECTORIO_BASE=$PWD/test_most_called_$MODE$DEPTH_SUFFIX$JUNK_SUFFIX

GREY_PATH=$GREY_ROOT/src/grey_main.py
if [ "$MODE" = "opt" ]; then
    SOLC_PATH=$GREY_ROOT/examples/solc-with-layout-linux
else
    SOLC_PATH=$GREY_ROOT/examples/solc-without-opt-linux
fi
SOLX_PATH=$GREY_TOOLS/solx-linux-amd64-gnu-v0.1.1
TEST_SOLX_PATH=$PWD/test_most_called_solx
#TESTRUNNER_PATH=$GREY_TOOLS/testrunner
#EVMONE_LIB=$GREY_TOOLS/libevmone.so

# Comprobar si el directorio existe
if [ ! -d "$DIRECTORIO_BASE" ]; then
    echo "El directorio $DIRECTORIO_BASE no existe."
    exit 1
fi

# Recorrer todos los subdirectorios y buscar archivos .yul
# find "$DIRECTORIO_BASE" -type f -name "*.sol" | while read -r yul_file; do

# start=$(date +%s.%N)

# find "$DIRECTORIO_BASE" -type f -name "*standard_input.json" |  grep '/externalContract[^/]*/' | while read -r yul_file; do


process_file() {
    yul_file="$1"
    # Output directory of grey: the directory of the test is unique (several tests have files with the same name)
    grey_out="/tmp/$(basename "$(dirname "$yul_file")")"

    
    # Obtener el directorio y el nombre base del archivo

    yul_dir=$(dirname "$yul_file")
    mkdir $yul_dir/sfs
    yul_base=$(basename "$yul_file" _standard_input.json)

    test_dir_name=$(basename "$yul_dir")

    solx_test_file="$test_dir_name/${yul_base}_standard_input.json"
    
    echo "Procesando archivo: $yul_file"

    pushd $yul_dir
    start_solc=$(date +%s.%N)
    $SOLC_PATH "${yul_file}" --standard-json &> "$yul_dir/$yul_base.output"
    end_solc=$(date +%s.%N)
    echo "$start_solc"
    echo "$end_solc"
    elapsed_solc=$(echo "$end_solc - $start_solc" | bc)
    echo "TIME SOLC $yul_file : $elapsed_solc"
    
    echo "$SOLC_PATH ${yul_file} --standard-json &> $yul_dir/$yul_base.output"

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
    # timeout 180s python3 $GREY_PATH -s "$yul_file" -g -if standard-json -solc $SOLC_PATH -o "$grey_out" &> "$yul_dir/$yul_base.log"
    if [ "$MODE" = "opt" ]; then
        GREY_OPTIONS="--call-convention best --prune-unused-arguments --combine-functions --reinline-after-merge --thread-empty-blocks --cse --hoist-return-labels --solc-cfg-fallback $GREY_ROOT/examples/solc-without-opt-linux"
    else
        GREY_OPTIONS="--no-inline --constants --no-merge-equivalent --solc-dedup off"
    fi
    timeout 180s python3 $GREY_PATH -s "$yul_file" $DEPTH_FLAG $JUNK_FLAG $GREY_OPTIONS -g -if standard-json -solc $SOLC_PATH -o "$grey_out" &> "$yul_dir/$yul_base.log"
    estado=$?
    end=$(date +%s.%N)
    popd
    elapsed=$(echo "$end - $start" | bc)
    echo "TIME GREY $yul_file : $elapsed"
    echo "TIME SOLC $yul_file : $elapsed_solc" >> "$yul_dir/$yul_base.log"
    
    echo "python3 $GREY_PATH -s $yul_file $DEPTH_FLAG $JUNK_FLAG $GREY_OPTIONS -g -v -if standard-json -solc $SOLC_PATH -o $grey_out &> $yul_dir/$yul_base.log"

    cp "$grey_out"/*/*_asm.json "$yul_dir/"
    # grey's output read by the mainnet gas evaluation (evaluation/scripts/pack_local_codes.py): its CSVs (creation code
    # per contract) and the assembly given to the importer (<contract>/<contract>_standard_json_output.json)
    rm -rf "$yul_dir/grey"
    rsync -a -m --include='/*.csv' --include='*/' --include='*_standard_json_output.json' --exclude='*' \
        "$grey_out/" "$yul_dir/grey/"
    cp "$grey_out"/*/sfs_*.json "$yul_dir/sfs/"
    cp "$grey_out"/repair*csv "$yul_dir/"
    
    # python3 extract_info.py "$yul_dir"


    # if [ -f "$yul_dir/test" ]; then
    
    #     python3 replace_bytecode_test.py "$yul_dir/test" "$yul_dir/$yul_base.log"

    #     python3 replace_bytecode_test.py "$yul_dir/test" "$yul_dir/$yul_base.output" init
        
    #     echo "python3 replace_bytecode_test.py $yul_dir/test $yul_dir/$yul_base.log"

    #     echo "python3 replace_bytecode_test.py $yul_dir/test $yul_dir/$yul_base.output init"

        
    #     $TESTRUNNER_PATH  $EVMONE_LIB $yul_dir/test $yul_dir/resultOriginal.json

    #     $TESTRUNNER_PATH  $EVMONE_LIB $yul_dir/test_grey $yul_dir/resultGrey.json

    #     # python3 compare_outputs.py $yul_dir/resultOriginal.json $yul_dir/resultGrey.json $yul_file
    #     python3 compare_outputs.py $yul_dir/resultOriginal.json $yul_dir/test $yul_dir/resultGrey.json $yul_dir/test_grey $yul_file
    #     echo "python3 compare_outputs.py $yul_dir/resultOriginal.json $yul_dir/test $yul_dir/resultGrey.json $yul_dir/test_grey $yul_file"
    #     RES=$?
    #     # if diff $yul_dir/resultOriginal.json $yul_dir/resultGrey.json > /dev/null; then
    #     if [ $RES -eq 0 ]; then
    #         echo "[RES]: Test passed."

    

    if [ $estado -eq 124 ]; then
        echo "[ERROR]: Timeout"
    else
    
        echo "python3 count_num_ins_fixed.py $yul_dir/$yul_base.output $yul_dir/$yul_base.log $yul_dir/$yul_base.solx_output"
        python3 count_num_ins_fixed.py "$yul_dir/$yul_base.output" "$yul_dir/$yul_base.log" "$yul_dir/$yul_base.solx_output"

        echo "python3 compare_solx.py $yul_dir/$yul_base.log $yul_dir/$yul_base.solx_output $yul_dir/intermediate.json"
        python3 compare_solx.py "$yul_dir/$yul_base.log" "$yul_dir/$yul_base.solx_output" "$yul_dir/intermediate.json"
    fi
    #     else
    #         echo "[RES]: Test failed."
    #     fi

    # else
    #     echo "Test not found: $yul_dir/"

    # fi
    
    echo "*************************************"

    
}

# Runs process_file buffering its output, which is printed at once when it finishes (the lock keeps the output
# of each file together)
run_job() {
    local out
    out=$(mktemp)
    process_file "$1" > "$out" 2>&1
    until mkdir "$LOCK_DIR" 2>/dev/null; do sleep 0.1; done
    cat "$out"
    rmdir "$LOCK_DIR"
    rm -f "$out"
}
export -f process_file run_job
LOCK_DIR=$(mktemp -u "${TMPDIR:-/tmp}/run_experiments_lock.XXXXXX")

echo "Processing with $JOBS parallel jobs"
find "$DIRECTORIO_BASE" -type f -name "*standard_input.json" -print0 | xargs -0 -n 1 -P "$JOBS" bash -c 'run_job "$1"' _


# end=$(date +%s.%N)
# elapsed=$(echo "$end - $start" | bc)
echo "Procesamiento completado."
# echo "Time passed: $elapsed seconds."

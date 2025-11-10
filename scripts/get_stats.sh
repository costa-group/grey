#!/bin/bash

RES_FILE=$1


grep -F "NUM INS:" $RES_FILE &> num_instructions.txt
grep -F "GAS:" $RES_FILE &> num_gas.txt
grep -F "NUM BYTES:" $RES_FILE &> num_bytes.txt
grep -F "OWN COSTAG:" $RES_FILE &> num_own_gas.txt
grep "NUM INS" $RES_FILE &> all_num_instructions.txt


grep Times test/*/*.log | cut -d':' -f3- &> salida.csv
grep Times test/*/*.log | cut -d':' -f1 &> salida-ficheros.txt
grep TIME $RES_FILE &> salida-times.txt


grep "SOLXRES" $RES_FILE &> solx_res.txt

python times.py
python print_times.py num_instructions.txt
python plot_solc_solx_grey.py

python sum_instructions.py num_instructions.txt
python sum_gas.py num_gas.txt
python sum_bytes.py num_bytes.txt
python sum_own_gas.py num_own_gas.txt

python count_solx.py

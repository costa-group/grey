#!/bin/bash

RES_FILE=$1

grep -F "NUM INS:" $RES_FILE &> num_instructions.txt
grep -F "GAS:" $RES_FILE &> num_gas.txt
grep -F "NUM BYTES:" $RES_FILE &> num_bytes.txt

python sum_instructions.py
python sum_gas.py
python sum_bytes.py

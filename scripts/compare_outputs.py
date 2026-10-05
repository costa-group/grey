import sys
import json
from jsondiff import diff
from typing import List, Dict, Any, Tuple

def information_from_files(json_file) -> Tuple[List[int], List[int], Dict[str, Any]]:
    with open(json_file, 'r') as f:
        json_dict = json.load(f)

    gas_json = []
    gas_json_no_deposit = []

    gas_json_creation = []
    gas_json_no_deposit_creation = []

    for key, json_answers in json_dict.items():

        for answer in json_answers:
            gas = int(answer.pop("gasUsed", 0))
            gas_deposit = int(answer.pop("gasUsedForDeposit", 0))

            message = answer.pop("message", "")
   
           
            
            if message.find("Creation succeeded") !=-1:
                gas_json_creation.append(gas)
                gas_json_no_deposit_creation.append(gas-gas_deposit)
            else:
                gas_json_no_deposit.append(gas - gas_deposit)
                gas_json.append(gas) 
               
    return gas_json, gas_json_no_deposit, gas_json_creation, gas_json_no_deposit_creation, json_dict

def compare_files(json_file1, json_file2, original_name_file):

    gas_json1_list, gas_json1_no_deposit_list, gas_json1_list_creation, gas_json1_no_deposit_list_creation, json1 = information_from_files(json_file1)

    gas_json2_list, gas_json2_no_deposit_list,gas_json2_list_creation, gas_json2_no_deposit_list_creation, json2 = information_from_files(json_file2)

    gas_json1 = sum(gas_json1_list)
    gas_json2 = sum(gas_json2_list)

    gas_json1_creation = sum(gas_json1_list_creation)
    gas_json2_creation = sum(gas_json2_list_creation)

    
    gas_json1_no_deposit = sum(gas_json1_no_deposit_list)
    gas_json2_no_deposit = sum(gas_json2_no_deposit_list)

    gas_json1_no_deposit_creation = sum(gas_json1_no_deposit_list_creation)
    gas_json2_no_deposit_creation = sum(gas_json2_no_deposit_list_creation)
    
    
    if json1.keys() != json2.keys():
        print("JSONS have different contract fields")
        return 1

    answer = diff(json1, json2)
    #print("FINAL", answer, type(answer))

    print(original_name_file + " ORIGINAL EXECUTION GAS: "+str(gas_json1))
    print(original_name_file + " OPT EXECUTION GAS: "+str(gas_json2))
    print(original_name_file + " ORIGINAL CREATION GAS: "+str(gas_json1_creation))
    print(original_name_file + " OPT CREATION GAS: "+str(gas_json2_creation))

    
    # Empty diff means they are the same
    return 0 if len(answer) == 0 else 1, gas_json1_no_deposit, gas_json2_no_deposit


def tests_outcome(test_file):
    with open(test_file, 'r') as f:
        test_dict = json.load(f)

    if len(test_dict) == 0:
        return 100 * [False]

    # print(list(test_dict.values())[0], flush=True)
    tests = list(test_dict.values())[0]["tests"]
    has_failed = []

    for test in tests:
        output = test.get("output", None)
        if output is not None:
            has_failed.append(output.get("status", None) == "failure")
        else:
            has_failed.append(False)
            
    return has_failed
    
# Intrinsic gas charged by the testrunner (EVMHost::call, depth 0) with its default EVM version (Cancun): it does not
# depend on the code generation and is the same for solc and grey
TX_GAS = 21000
TX_CREATE_GAS = 53000
TX_DATA_ZERO_GAS = 4
TX_DATA_NON_ZERO_GAS = 16


def data_gas(data: bytes) -> int:
    return sum(TX_DATA_ZERO_GAS if b == 0 else TX_DATA_NON_ZERO_GAS for b in data)


def gas_from_files(json_file, test_file):
    """
    Gas of the calls and of the creation of a test, without the calls that must fail (status "failure" in the test
    file) and without the intrinsic gas: 21000 + calldata in the calls, 53000 + calldata of the constructor arguments
    in the creation (the calldata of the creation bytecode and the code deposit depend on the code generation and are
    kept). Each result corresponds to the entry of the test in the same position, constructor included.
    Returns (execution, creation, execution with intrinsic gas, creation with intrinsic gas, execution without deposit,
    creation without deposit)
    """
    with open(json_file, 'r') as f:
        results = list(json.load(f).values())
    with open(test_file, 'r') as f:
        tests = list(json.load(f).values())
    if not results or not tests:
        return 0, 0, 0, 0, 0, 0
    execution = creation = execution_raw = creation_raw = execution_no_deposit = creation_no_deposit = 0
    for answer, test in zip(results[0], tests[0]["tests"]):
        gas = int(answer.get("gasUsed", 0))
        gas_deposit = int(answer.get("gasUsedForDeposit", 0))
        calldata = bytes.fromhex(test["input"]["calldata"])
        if test["kind"] == "constructor":
            if answer.get("message", "").find("Creation succeeded") == -1:
                continue
            creation_raw += gas
            creation += gas - TX_CREATE_GAS - data_gas(calldata)
            creation_no_deposit += gas - gas_deposit
        elif test.get("output", {}).get("status") != "failure":
            execution_raw += gas
            execution += gas - TX_GAS - data_gas(calldata)
            execution_no_deposit += gas - gas_deposit
    return execution, creation, execution_raw, creation_raw, execution_no_deposit, creation_no_deposit


def compare_files_removing_failed_tests(json_file1, test_file1, json_file2, test_file2, original_name_file):

    *_, json1 = information_from_files(json_file1)
    *_, json2 = information_from_files(json_file2)

    gas_json1, gas_json1_creation, gas_json1_raw, gas_json1_creation_raw, gas_json1_no_deposit, _ = \
        gas_from_files(json_file1, test_file1)
    gas_json2, gas_json2_creation, gas_json2_raw, gas_json2_creation_raw, gas_json2_no_deposit, _ = \
        gas_from_files(json_file2, test_file2)

    if json1.keys() != json2.keys():
        print("JSONS have different contract fields")
        return 1, 0, 0

    answer = diff(json1, json2)

    if len(answer) > 0:
        return 1, 0, 0

    #print("FINAL", answer, type(answer))

    # Without the intrinsic gas (sum_gas.py uses these lines)
    print(original_name_file+" ORIGINAL EXECUTION GAS: "+str(gas_json1))
    print(original_name_file+" OPT EXECUTION GAS: "+str(gas_json2))
    print(original_name_file+" ORIGINAL CREATION GAS: "+str(gas_json1_creation))
    print(original_name_file+" OPT CREATION GAS: "+str(gas_json2_creation))
    # gasUsed as given by the testrunner, intrinsic gas included
    print(original_name_file+" ORIGINAL RAW EXEC GAS: "+str(gas_json1_raw))
    print(original_name_file+" OPT RAW EXEC GAS: "+str(gas_json2_raw))
    print(original_name_file+" ORIGINAL RAW CREATE GAS: "+str(gas_json1_creation_raw))
    print(original_name_file+" OPT RAW CREATE GAS: "+str(gas_json2_creation_raw))
    print("BLA BLA BLA", gas_json1_no_deposit, flush=True)
    # Empty diff means they are the same
    return 0 if len(answer) == 0 else 1, gas_json1_no_deposit, gas_json2_no_deposit
    

if __name__ == "__main__":
    if len(sys.argv) == 4:
        res, _, _ = compare_files(sys.argv[1], sys.argv[2], sys.argv[3])
    elif len(sys.argv) == 6:
        res, _, _ = compare_files_removing_failed_tests(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5])
        
    print(res)
    sys.exit(res)

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
    
def compare_files_removing_failed_tests(json_file1, test_file1, json_file2, test_file2, original_name_file):

    gas_json1_list, gas_json1_no_deposit_list, gas_json1_list_creation, gas_json1_no_deposit_list_creation, json1 = information_from_files(json_file1)

    gas_json2_list, gas_json2_no_deposit_list,gas_json2_list_creation, gas_json2_no_deposit_list_creation, json2 = information_from_files(json_file2)

    test_outcome1 = tests_outcome(test_file1)
    test_outcome2 = tests_outcome(test_file2)

    # print(gas_json1_list)
    # print(gas_json2_list)

    gas_json1 = sum([gas for gas, failed  in zip(gas_json1_list, test_outcome1) if not failed] + [0])
    gas_json2 = sum([gas for gas, failed  in zip(gas_json2_list, test_outcome2) if not failed] + [0])

    gas_json1_creation = sum([gas for gas, failed  in zip(gas_json1_list_creation, test_outcome1) if not failed] + [0])
    gas_json2_creation = sum([gas for gas, failed  in zip(gas_json2_list_creation, test_outcome2) if not failed] + [0])

    gas_json1_no_deposit = sum([gas for gas, failed  in zip(gas_json1_no_deposit_list, test_outcome1) if not failed] + [0])
    gas_json2_no_deposit = sum([gas for gas, failed  in zip(gas_json2_no_deposit_list, test_outcome2) if not failed] + [0])

    gas_json1_no_deposit_creation = sum([gas for gas, failed  in zip(gas_json1_no_deposit_list_creation, test_outcome1) if not failed] + [0])
    gas_json2_no_deposit_creation = sum([gas for gas, failed  in zip(gas_json2_no_deposit_list_creation, test_outcome2) if not failed] + [0])

    
    # print(gas_json1_no_deposit_list)
    # print(gas_json1_no_deposit)

    # print(gas_json1_no_deposit_list_creation)
    # print(gas_json1_no_deposit_creation)

    
    if json1.keys() != json2.keys():
        print("JSONS have different contract fields")
        return 1

    answer = diff(json1, json2)

    if len(answer) > 0:
        return 1, 0, 0

    #print("FINAL", answer, type(answer))

    print(original_name_file+" ORIGINAL EXECUTION GAS: "+str(gas_json1))
    print(original_name_file+" OPT EXECUTION GAS: "+str(gas_json2))
    print(original_name_file+" ORIGINAL CREATION GAS: "+str(gas_json1_creation))
    print(original_name_file+" OPT CREATION GAS: "+str(gas_json2_creation))
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

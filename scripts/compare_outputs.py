import sys
import json
from jsondiff import diff
from typing import List, Dict, Any, Tuple

def information_from_files(json_file) -> Tuple[List[int], List[int], Dict[str, Any]]:
    with open(json_file, 'r') as f:
        json_dict = json.load(f)

    gas_json = []
    gas_json_no_deposit = []

    for key, json_answers in json_dict.items():

        for answer in json_answers:
            gas = int(answer.pop("gasUsed", 0))
            gas_deposit = int(answer.pop("gasUsedForDeposit", 0))

            gas_json_no_deposit.append(gas - gas_deposit)
            gas_json.append(gas) 
        
    return gas_json, gas_json_no_deposit, json_dict

def compare_files(json_file1, json_file2):

    gas_json1_list, gas_json1_no_deposit_list, json1 = information_from_files(json_file1)

    gas_json2_list, gas_json2_no_deposit_list, json2 = information_from_files(json_file2)

    gas_json1 = sum(gas_json1_list)
    gas_json2 = sum(gas_json2_list)

    gas_json1_no_deposit = sum(gas_json1_no_deposit_list)
    gas_json2_no_deposit = sum(gas_json2_no_deposit_list)
    
    if json1.keys() != json2.keys():
        print("JSONS have different contract fields")
        return 1

    answer = diff(json1, json2)
    #print("FINAL", answer, type(answer))

    print("ORIGINAL GAS: "+str(gas_json1))
    print("OPT GAS: "+str(gas_json2))
          
    
    # Empty diff means they are the same
    return 0 if len(answer) == 0 else 1, gas_json1_no_deposit, gas_json2_no_deposit


if __name__ == "__main__":
    res, _, _ = compare_files(sys.argv[1], sys.argv[2])
    print(res)
    sys.exit(res)

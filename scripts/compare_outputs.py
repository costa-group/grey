import sys
import json
from jsondiff import diff


def compare_files(json_file1, json_file2):
    with open(json_file1, 'r') as f:
        json1 = json.load(f)

    with open(json_file2, 'r') as f:
        json2 = json.load(f)

    if json1.keys() != json2.keys():
        print("JSONS have different contract fields")
        return 1

    gas_json1 = 0
    gas_json2 = 0
    # Drop keys for gas
    for key, json1_answers in json1.items():
        json2_answers = json2[key]

        for answer in [*json1_answers]:
            gas = answer.pop("gasUsed")
            gas_used = answer.pop("gasUsedForDeposit")

            gas_json1+= int(gas)
            
            
        for answer in [*json2_answers]:
            gas = answer.pop("gasUsed")
            gas_used = answer.pop("gasUsedForDeposit")

            gas_json2+=int(gas)
            
    answer = diff(json1, json2)
    #print("FINAL", answer, type(answer))


    print("ORIGINAL GAS: "+str(gas_json1))
    print("OPT GAS: "+str(gas_json2))
          
    
    # Empty diff means they are the same
    return 0 if len(answer) == 0 else 1, gas_json1, gas_json2


if __name__ == "__main__":
    res, _, _ = compare_files(sys.argv[1], sys.argv[2])
    print(res)
    sys.exit(res)

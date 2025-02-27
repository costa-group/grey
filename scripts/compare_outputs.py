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

    # Drop keys for gas
    for key, json1_answers in json1.items():
        json2_answers = json2[key]

        for answer in [*json1_answers, *json2_answers]:            
            answer.pop("gasUsed")
            answer.pop("gasUsedForDeposit")

    answer = diff(json1, json2)
    print("FINAL", answer, type(answer))

    # Empty diff means they are the same
    return 0 if len(answer) == 0 else 1


if __name__ == "__main__":
    print(compare_files(sys.argv[1], sys.argv[2]))

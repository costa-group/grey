import os
import json
import sys

path = sys.argv[1]
dirs = os.listdir(path)
for d in dirs:
    f = os.listdir(path+"/"+d)
    solc_file = list(filter(lambda x: x.find("_standard_input")!=-1,f))[0]
    print(path+"/"+d+"/"+solc_file)
    f = open(path+"/"+d+"/"+solc_file, "r", encoding="utf-8")
    json_dict = json.loads(f.read())
    f.close()
    json_dict["settings"]["metadata"] = {}
    json_dict["settings"]["metadata"]["appendCBOR"] = False
    json_dict["settings"]["optimizer"] = {}
    json_dict["settings"]["optimizer"]["enabled"] = True
    json_dict["settings"]["optimizer"]["runs"] = 200

    #print(json_dict)
    f = open(path+"/"+d+"/"+solc_file, "w", encoding="utf-8")
    json.dump(json_dict,f)
    f.close()
    

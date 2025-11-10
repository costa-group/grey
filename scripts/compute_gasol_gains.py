import os
import sys
import csv as csvf

if __name__ == '__main__':
    solx_blocks_dir = sys.argv[1]

    print(solx_blocks_dir)
    
    all_files = os.listdir(solx_blocks_dir)
    csv_files = list(filter(lambda x: x.endswith("csv") == True, all_files))
    print(csv_files)

    blocks = 0
    mejor = (0,0,0)
    mejora_gas = 0
    mejora_size = 0
    mejora_ins = 0

    total_ins = 0
    total_bytes = 0
    total_gas = 0

    rules = []
    
    for csv in csv_files:
        f = open(solx_blocks_dir+"/"+csv, "r")
        lines = f.readlines()
        f.close()
        lines_no_head = lines[1:]
        
        f1 = open(solx_blocks_dir+"/"+csv)
        reader = csvf.reader(f1, quotechar='"')
        for i, elem in enumerate(reader):
            if i>0:
                print(i)
                print(elem)
                if elem[7] != "":
                    rules.append(elem[7])
        for l in lines_no_head:

            blocks+=1
            
            elems = l.split(",")

            init_ins = int(elems[4])
            init_size = int(elems[5])
            init_gas = int(elems[6])
            
            total_ins+=init_ins
            total_bytes+=init_size
            total_gas+=init_gas
            
            opt_ins = int(elems[-5])
            opt_size = int(elems[-4])
            opt_gas = int(elems[-3])

            if (init_ins > opt_ins):
                mejor_ant = mejor
                mejor = (mejor_ant[0]+1, mejor_ant[1], mejor_ant[2])
                mejora_ins += (init_ins-opt_ins)

            if (init_size > opt_size):
                mejor_ant = mejor
                mejor = (mejor_ant[0], mejor_ant[1]+1, mejor_ant[2])
                mejora_size += (init_size-opt_size)


            if (init_gas > opt_gas):
                mejor_ant = mejor
                mejor = (mejor_ant[0], mejor_ant[1], mejor_ant[2]+1)
                mejora_gas += (init_gas-opt_gas)



print("[GASOLRES]: "+str(solx_blocks_dir.split("/")[-2])+";"+str(blocks)+";"+str(total_ins)+";"+str(total_bytes)+";"+str(total_gas)+";"+str(mejor)+";"+str(mejora_ins)+";"+str(mejora_size)+";"+str(mejora_gas)+";"+str(rules))


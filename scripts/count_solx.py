import os

f = open("solx_res.txt","r")
lines = f.readlines()


num_ins_solx = 0
num_ins_opt = 0

num_bytes_solx = 0
num_bytes_opt = 0

num_memory_ins_solx = 0
num_memory_ins_opt = 0

mejor = 0
iguales = 0

for l in lines:
    elems = l.strip().split(",")
    num_ins_solx = int(elems[2])
    num_ins_opt = int(elems[3])

    num_bytes_solx = int(elems[4])
    num_bytes_opt = int(elems[5])

    memory_solx = int(elems[8])
    memory_opt = int(elems[11])

    if(memory_opt < memory_solx):
        mejor+=1
    elif (memory_opt == memory_solx):
        iguales+=1
        
    num_memory_ins_solx += memory_solx
    num_memory_ins_opt += memory_opt


print("TOTAL: "+str(len(lines)))
print("MEJOR: "+str(mejor))
print("IGUALES: "+str(iguales))
print("NUM INS SOLX: "+str(num_ins_solx))
print("NUM INS OPT: "+str(num_ins_opt))
print("NUM BYTES SOLX: "+str(num_bytes_solx))
print("NUM BYTES OPT: "+str(num_bytes_opt))
print("NUM MEM INSTRUCTIONS SOLX: "+str(num_memory_ins_solx))
print("NUM MEM INSTRUCTIONS OPT: "+str(num_memory_ins_opt))

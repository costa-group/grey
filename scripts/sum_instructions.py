import compare_blocks


def cuartiles(original, optimizado, res):
    original25 = original+original*0.25
    original50 = original+original*0.5
    original75 = original+original*0.75
    original100 = original*2


    if optimizado < original25:
        res[0]+=1
    elif optimizado >= original25 and optimizado < original50:
        res[1] += 1
    elif optimizado >= original50 and optimizado < original75:
        res[2] += 1
    else:
        res[3] += 1




f = "num_instructions.txt"

ff = open(f, "r")
lines = ff.readlines()

origin = list(filter(lambda x: x.find("ORIGIN")!= -1, lines))
origin_number = list(map(lambda x: int(x.split(":")[-1].strip()), origin))

f_names = list(map(lambda x: x.split(":")[0].rstrip(" ORIGIN NUM INS"),origin))

total_origin = sum(origin_number)


opt = list(filter(lambda x: x.find("OPT")!= -1, lines))
opt_number = list(map(lambda x: int(x.split(":")[-1].strip()), opt))

total_opt = sum(opt_number)


menor = 0
mayor = 0
igual = 0

total_mejor = 0
optimizado_mejor = 0


total_peor = 0
optimizado_peor = 0

cuartiles_res = [0,0,0,0]

worse_files = {}

total_sol_terminal = 0
total_sol_pops = 0
all_pops_sol = 0

total_origin_terminal = 0
total_origin_pops = 0
all_pops_origin = 0

total_ins_terminal_sol = 0
total_ins_terminal_opt = 0

total_blocks_solc = 0
total_blocks_opt = 0

for i in range(len(origin_number)):
    original = origin_number[i]
    optimizado = opt_number[i]

    if original > optimizado:
        menor+=1
        total_mejor += original
        optimizado_mejor+= optimizado
        
    elif original == optimizado:
        igual+=1
    else:

        fname = f_names[i]

        fname_without_ext = fname.rstrip("log")

        print("CHECK: " + str((fname_without_ext+"output", fname_without_ext+"log")))
   
        
        tsol, pops_sol, allpops, torigin, pops_origin , allpops_orig, inst_opt, inst_sol, blocks_solc, blocks_opt = compare_blocks.execute_function(fname_without_ext+"output", fname_without_ext+"log")

        print("CHECK: "+ str((torigin, pops_origin , allpops_orig, inst_sol)))
        
        total_sol_terminal+=tsol
        total_sol_pops+=pops_sol
        all_pops_sol+= allpops
        total_origin_terminal+=torigin
        total_origin_pops+=pops_origin
        all_pops_origin+=allpops_orig
        total_ins_terminal_sol+=inst_sol
        total_ins_terminal_opt+=inst_opt
        total_blocks_solc+=blocks_solc
        total_blocks_opt+=blocks_opt
        
        worse_files[fname] = (original, optimizado)
        # print("PAREJA: ("+str(original)+","+str(optimizado)+")")
        total_peor+= original
        optimizado_peor+=optimizado
        cuartiles(original, optimizado, cuartiles_res)
        mayor+=1

s = ""
for k,v in worse_files.items():
    s+=k+":"+str(v)+"\n"
    
worse_file = open("worse_contracts_ins.txt", "w")
worse_file.write(s)
worse_file.close()

print()
print(" ===== OTHER STATISTICS =====")

print("TOTAL TERMINAL BLOCKS IN GREY: "+str(total_sol_terminal))
print("TOTAL POPS IN TERMINAL GREY: "+str(total_sol_pops))

print("TOTAL TERMINAL BLOCKS IN SOLC: "+str(total_origin_terminal))
print("TOTAL POPS IN TERMINAL SOLC: "+str(total_origin_pops))

print("TOTAL POPS IN GREY: "+str(all_pops_sol))
print("TOTAL POPS IN SOLC: "+str(all_pops_origin))

print("TOTAL INS TERMINAL BLOCKS IN GREY: "+str(total_ins_terminal_opt))
print("TOTAL INS TERMINAL BLOCKS IN SOLC: "+str(total_ins_terminal_sol))
print("TOTAL BLOCKS IN GREY: "+str(total_blocks_opt))
print("TOTAL IN SOLC: "+str(total_blocks_solc)) 
print()

print(" ===== NUM INSTRUCTIONS STATISTICS ===== ")
print()

# print("CASOS EN EL QUE SOMOS MEJOR: "+str(menor))
print("CASOS EN LOS QUE SOMOS IGUALES: "+str(igual))
print("CASOS EN LOS QUE SOMOS PEORES: "+str(mayor))
print()

assert(len(origin_number) == len(opt_number))

print("TOTAL")
print("TOTAL INS ORIGINAL: "+str(total_origin))
print("TOTAL INS OPT: "+str(total_opt))
print("%: "+str((total_opt/(total_origin*1.0))*100.0))
print()
print("MEJORAMOS")
print("TOTAL INS ORIGINAL: "+str(total_mejor))
print("TOTAL INS OPT: "+str(optimizado_mejor))

print("%: "+str((optimizado_mejor/total_mejor*1.0)*100.0))

print()
print("EMPEORAMOS")
print(total_peor)
print(optimizado_peor)

print((optimizado_peor/total_peor*1.0)*100.0)

print(cuartiles_res)

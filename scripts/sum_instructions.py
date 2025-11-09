import compare_blocks
import sys


def get_stats(file_name):
    f = open(file_name, "r")
    lines = f.readlines()

    time_grey_line = list(filter(lambda x: x.find("Total times") != -1, lines))[0]
    time_grey = time_grey_line.split(":")[-1].strip()

    time_solc_line = list(filter(lambda x: x.find("TIME SOLC") != -1, lines))[0]
    time_solc = time_solc_line.split(":")[-1].strip()

    blocks_cfg_line = list(filter(lambda x: x.find("Total Blocks CFG") != -1, lines))[0]
    blocks_cfg = blocks_cfg_line.split(":")[-1].strip()

    ins_cfg_line = list(filter(lambda x: x.find("Total Ins CFG") != -1, lines))[0]
    ins_cfg = ins_cfg_line.split(":")[-1].strip()
    
    return float(time_grey), float(time_solc), int(blocks_cfg), int(ins_cfg)
    

    
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




f = sys.argv[1]#"num_instructions.txt"

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

scalability = "scalability_block.csv"
f_scal = open(scalability, "w")

scalability_ins = "scalability_ins.csv"
f_scal_ins = open(scalability_ins, "w")

scalability_cfg = "scalability_cfg.csv"
f_scal_cfg = open(scalability_cfg, "w")


f_scal.write("Contract name, Time solc, blocks solc, Time grey, blocks grey\n")
f_scal_ins.write("Contract name, Time solc, ins solc, Time grey, ins grey\n")
f_scal_cfg.write("Contract name, blocks cfg, ins cfg, Time grey, Time solc,\n")



list_times_grey = []
list_times_solc = []
list_ins_cfg = []
list_blocks_cfg = []

for i in range(len(origin_number)):
    original = origin_number[i]
    optimizado = opt_number[i]

    fname = f_names[i]
    fname_without_ext = fname.rstrip("log")

    print("CHECK: " + str((fname_without_ext+"output", fname_without_ext+"log")))
   
        
    tsol, pops_sol, allpops, torigin, pops_origin , allpops_orig, inst_opt, inst_sol, blocks_solc, blocks_opt, total_ins_solc, total_ins_grey = compare_blocks.execute_function(fname_without_ext+"output", fname_without_ext+"log")
    
    try:
        time_grey, time_solc, blocks_cfg, ins_cfg = get_stats(fname_without_ext+"log")

        list_times_grey.append(time_grey)
        list_times_solc.append(time_solc)
        list_ins_cfg.append(ins_cfg)
        list_blocks_cfg.append(blocks_cfg)
    
        print([fname_without_ext,time_solc,blocks_solc,time_grey,blocks_opt])
        f_scal.write(",".join([fname_without_ext[:-1],str(time_solc),str(blocks_solc),str(time_grey),str(blocks_opt)])+"\n")

        f_scal_ins.write(",".join([fname_without_ext[:-1],str(time_solc),str(total_ins_solc),str(time_grey),str(total_ins_grey)])+"\n")

        f_scal_cfg.write(",".join([fname_without_ext[:-1],str(blocks_cfg), str(ins_cfg),str(time_grey),str(time_solc)])+"\n")

    except:
        print("Error in get stats")

    ########################
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
        
        tsol, pops_sol, allpops, torigin, pops_origin , allpops_orig, inst_opt, inst_sol, blocks_solc, blocks_opt, total_ins_solc, total_ins_grey = compare_blocks.execute_function(fname_without_ext+"output", fname_without_ext+"log")


        # time_grey, time_solc = get_times(fname_without_ext+"log")


        # print([fname_without_ext,time_solc,blocks_solc,time_grey,blocks_opt])
        # f_scal.write(",".join([fname_without_ext[:-1],str(time_solc),str(blocks_solc),str(time_grey),str(blocks_opt)])+"\n")

        # print("HOLA CARACOLA")
        # f_scal_ins.write(",".join([fname_without_ext[:-1],str(time_solc),str(total_ins_solc),str(time_grey),str(total_ins_grey)])+"\n")

        
        # print("CHECK: "+ str((torigin, pops_origin , allpops_orig, inst_sol, blocks_solc, blocks_opt)))
        
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


# Plots with instructions
    
paired = sorted(zip(list_ins_cfg, list_times_grey))
ins_cfg_sorted, times_grey_sorted = zip(*paired)

ins_cfg_sorted, times_grey_sorted = list(ins_cfg_sorted), list(times_grey_sorted)

paired_solc = sorted(zip(list_ins_cfg, list_times_solc))
ins_cfg_sorted, times_solc_sorted = zip(*paired_solc)

ins_cfg_sorted, times_solc_sorted = list(ins_cfg_sorted), list(times_solc_sorted)

index_list = range(len(ins_cfg_sorted))

import seaborn as sns
import pandas as pd
import matplotlib.pyplot as plt

plt.figure()
# Crear DataFrame
df = pd.DataFrame({"x": index_list, "y": times_grey_sorted})

# Dibujar scatter
sns.scatterplot(data=df, x="x", y="y")

plt.xlabel("Contracts ordered by number of instructions")
plt.ylabel("Time (s)")
plt.title("Grey")


plt.savefig("figs/scatter_plot_grey.png")
#plt.show()

plt.figure()
# Crear DataFrame
df_solc = pd.DataFrame({"x": index_list, "y": times_solc_sorted})

# Dibujar scatter
sns.scatterplot(data=df_solc, x="x", y="y")

plt.xlabel("Contracts ordered by number of instructions")
plt.ylabel("Time (s)")
plt.title("Solc")


plt.savefig("figs/scatter_plot_solc.png")
#plt.show()

plt.figure()
# Crear DataFrame
df = pd.DataFrame({"x": ins_cfg_sorted, "y": times_grey_sorted})

# Dibujar scatter
sns.scatterplot(data=df, x="x", y="y")

plt.xlabel("Num Instructions")
plt.ylabel("Time (s)")
plt.title("Grey")


plt.savefig("figs/scatter_plot_grey_ins.png")
#plt.show()

plt.figure()
# Crear DataFrame
df_solc = pd.DataFrame({"x": ins_cfg_sorted, "y": times_solc_sorted})

# Dibujar scatter
sns.scatterplot(data=df_solc, x="x", y="y")

plt.xlabel("Num Instructions")
plt.ylabel("Time (s)")
plt.title("Solc")


plt.savefig("figs/scatter_plot_solc_ins.png")
#plt.show()


#Plots with blocks
    
paired = sorted(zip(list_blocks_cfg, list_times_grey))
blocks_cfg_sorted, times_grey_sorted = zip(*paired)

blocks_cfg_sorted, times_grey_sorted = list(blocks_cfg_sorted), list(times_grey_sorted)

paired_blocks_solc = sorted(zip(list_blocks_cfg, list_times_solc))
blocks_cfg_sorted, times_solc_sorted = zip(*paired_solc)

blocks_cfg_sorted, times_solc_sorted = list(blocks_cfg_sorted), list(times_solc_sorted)

index_list = range(len(blocks_cfg_sorted))

plt.figure()
# Crear DataFrame
df = pd.DataFrame({"x": index_list, "y": times_grey_sorted})

# Dibujar scatter
sns.scatterplot(data=df, x="x", y="y")

plt.xlabel("Contracts ordered by number of blocks")
plt.ylabel("Time (s)")
plt.title("Grey")


plt.savefig("figs/scatter_plot_grey_blocks_relative.png")
#plt.show()

plt.figure()
# Crear DataFrame
df_solc = pd.DataFrame({"x": index_list, "y": times_solc_sorted})

# Dibujar scatter
sns.scatterplot(data=df_solc, x="x", y="y")

plt.xlabel("Contracts ordered by number of blocks")
plt.ylabel("Time (s)")
plt.title("Solc")


plt.savefig("figs/scatter_plot_solc_blocks_relative.png")
#plt.show()

plt.figure()
# Crear DataFrame
df = pd.DataFrame({"x": blocks_cfg_sorted, "y": times_grey_sorted})

# Dibujar scatter
sns.scatterplot(data=df, x="x", y="y")

plt.xlabel("Num Blocks")
plt.ylabel("Time (s)")
plt.title("Grey")


plt.savefig("figs/scatter_plot_grey_blocks.png")
#plt.show()

plt.figure()
# Crear DataFrame
df_solc = pd.DataFrame({"x": blocks_cfg_sorted, "y": times_solc_sorted})

# Dibujar scatter
sns.scatterplot(data=df_solc, x="x", y="y")

plt.xlabel("Num Blocks")
plt.ylabel("Time (s)")
plt.title("Solc")


plt.savefig("figs/scatter_plot_solc_blocks.png")
#plt.show()


s = ""
for k,v in worse_files.items():
    s+=k+":"+str(v)+"\n"
    
worse_file = open("worse_contracts_ins.txt", "w")
worse_file.write(s)
worse_file.close()

f_scal.close()
f_scal_ins.close()
f_scal_cfg.close()

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
print("TOTAL BLOCKS IN SOLC: "+str(total_blocks_solc)) 
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

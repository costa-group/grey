import seaborn as sns
import pandas as pd
import matplotlib.pyplot as plt
import sys

def parse_solc_bench(file_name):
    f = open(file_name, "r")
    lines = f.readlines()

    total = 0
    for l in lines:
        elems = l.split(":")[-1]
        nums = elems.split()
        total += float(nums[-1])
        
    return total/1000


def get_stats(file_name):
    f = open(file_name, "r")
    lines = f.readlines()

    all_times_grey_line = list(filter(lambda x: x.find("Times /User") != -1 and x.find("Total") == -1, lines))[0]

    all_times_aux = all_times_grey_line.split(":")[-1]
    all_times = list(map(lambda x: float(x.strip()), all_times_aux.split(",")))
    
    blocks_cfg_line = list(filter(lambda x: x.find("Total Blocks CFG") != -1, lines))[0]
    blocks_cfg = blocks_cfg_line.split(":")[-1].strip()

    ins_cfg_line = list(filter(lambda x: x.find("Total Ins CFG") != -1, lines))[0]
    ins_cfg = ins_cfg_line.split(":")[-1].strip()
    
    return all_times[4], int(blocks_cfg), int(ins_cfg)


f = sys.argv[1]

ff = open(f, "r")
lines = ff.readlines()

origin = list(filter(lambda x: x.find("ORIGIN")!= -1, lines))

f_names_aux = list(map(lambda x: x.split(":")[0].rstrip(" ORIGIN NUM INS"),origin))

f_names = list(set(f_names_aux))

scalability_cfg = "scalability_cfg.csv"
f_scal_cfg = open(scalability_cfg, "w")


f_scal_cfg.write("Contract name, blocks cfg, ins cfg, Time grey, Time solc,\n")

list_times_grey = []
list_times_solc = []
list_ins_cfg = []
list_blocks_cfg = []


time_cfg_generation = []
time_cfg_parser = []
time_cfg_preprocess = []
time_layout = []
time_asm_generation = []
time_solc_importer = []

for i in range(len(f_names)):

    fname = f_names[i]
    fname_without_ext = fname.rstrip("log")

    print("CHECK: " + str((fname_without_ext+"output", fname_without_ext+"log")))
   

    time_greedy, blocks_cfg, ins_cfg = get_stats(fname_without_ext+"log")
    time_solc = parse_solc_bench(fname_without_ext+"times_bench")
    
    list_times_grey.append(time_greedy)
    list_times_solc.append(time_solc)
    list_ins_cfg.append(ins_cfg)
    list_blocks_cfg.append(blocks_cfg)
    
    f_scal_cfg.write(",".join([fname_without_ext[:-1],str(blocks_cfg), str(ins_cfg),str(time_greedy),str(time_solc)])+"\n")

# Plots with instructions
    
# paired = sorted(zip(list_ins_cfg, list_times_grey))
# ins_cfg_sorted, times_grey_sorted = zip(*paired)

# ins_cfg_sorted, times_grey_sorted = list(ins_cfg_sorted), list(times_grey_sorted)

# paired_solc = sorted(zip(list_ins_cfg, list_times_solc))
# ins_cfg_sorted, times_solc_sorted = zip(*paired_solc)

# ins_cfg_sorted, times_solc_sorted = list(ins_cfg_sorted), list(times_solc_sorted)

# index_list = range(len(ins_cfg_sorted))


# # max_time_grey = max(times_grey_sorted)
# # times_grey_sorted = list(map(lambda x: x/max_time_grey*1.0, times_grey_sorted))

# # max_time_solc = max(times_solc_sorted)
# # times_solc_sorted = list(map(lambda x: x/max_time_solc*1.0, times_solc_sorted))


# print(len(times_solc_sorted))

# plt.figure()
# # Crear DataFrame
# df = pd.DataFrame({"x": index_list, "y": times_grey_sorted})

# # Dibujar scatter
# sns.scatterplot(data=df, x="x", y="y")

# plt.xlabel("Contracts ordered by number of instructions")
# plt.ylabel("Time (s)")
# plt.title("(a) Execution time of SATE")


# plt.savefig("figs/scatter-plot-grey-bech.png")
# #plt.show()

# plt.figure()
# # Crear DataFrame
# df_solc = pd.DataFrame({"x": index_list, "y": times_solc_sorted})

# # Dibujar scatter
# sns.scatterplot(data=df_solc, x="x", y="y")

# plt.xlabel("Contracts ordered by number of instructions")
# plt.ylabel("Time (s)")
# plt.title("(b) Execution time of solc")

# plt.savefig("figs/scatter-plot-solc.png")
# #plt.show()

# plt.figure()
# # Crear DataFrame
# df = pd.DataFrame({"x": ins_cfg_sorted, "y": times_grey_sorted})

# # Dibujar scatter
# sns.scatterplot(data=df, x="x", y="y")

# plt.xlabel("Num Instructions")
# plt.ylabel("Time (s)")
# plt.title("(a) Executio time of SATE")


# plt.savefig("figs/scatter-plot-grey-ins.png")
# #plt.show()

# plt.figure()
# # Crear DataFrame
# df_solc = pd.DataFrame({"x": ins_cfg_sorted, "y": times_solc_sorted})

# # Dibujar scatter
# sns.scatterplot(data=df_solc, x="x", y="y")

# plt.xlabel("Num Instructions")
# plt.ylabel("Time (s)")
# plt.title("(b) Execution time of solc")


# plt.savefig("figs/scatter-plot-solc-ins.png")
# #plt.show()


# #Plots with blocks
    
# paired = sorted(zip(list_blocks_cfg, list_times_grey))
# blocks_cfg_sorted, times_grey_sorted = zip(*paired)

# blocks_cfg_sorted, times_grey_sorted = list(blocks_cfg_sorted), list(times_grey_sorted)

# paired_blocks_solc = sorted(zip(list_blocks_cfg, list_times_solc))
# blocks_cfg_sorted, times_solc_sorted = zip(*paired_solc)

# blocks_cfg_sorted, times_solc_sorted = list(blocks_cfg_sorted), list(times_solc_sorted)

# index_list = range(len(blocks_cfg_sorted))

# plt.figure()
# # Crear DataFrame
# df = pd.DataFrame({"x": index_list, "y": times_grey_sorted})

# # Dibujar scatter
# sns.scatterplot(data=df, x="x", y="y")

# plt.xlabel("Contracts ordered by number of blocks")
# plt.ylabel("Time (s)")
# plt.title("(a) Execution time of SATE")


# plt.savefig("figs/scatter-plot-grey-blocks-relative.png")
# #plt.show()

# plt.figure()
# # Crear DataFrame
# df_solc = pd.DataFrame({"x": index_list, "y": times_solc_sorted})

# # Dibujar scatter
# sns.scatterplot(data=df_solc, x="x", y="y")

# plt.xlabel("Contracts ordered by number of blocks")
# plt.ylabel("Time (s)")
# plt.title("(b) Execution time of solc")


# plt.savefig("figs/scatter-plot-solc-blocks-relative.png")
# #plt.show()

# plt.figure()
# # Crear DataFrame
# df = pd.DataFrame({"x": blocks_cfg_sorted, "y": times_grey_sorted})

# # Dibujar scatter
# sns.scatterplot(data=df, x="x", y="y")

# plt.xlabel("Num Blocks")
# plt.ylabel("Time (s)")
# plt.title("(a) Execution time of SATE")

# plt.savefig("figs/scatter-plot-grey-blocks.png")
# #plt.show()

# plt.figure()
# # Crear DataFrame
# df_solc = pd.DataFrame({"x": blocks_cfg_sorted, "y": times_solc_sorted})

# # Dibujar scatter
# sns.scatterplot(data=df_solc, x="x", y="y")

# plt.xlabel("Num Blocks")
# plt.ylabel("Time (s)")
# plt.title("(b) Execution time of solc")

# plt.savefig("figs/scatter-plot-solc-blocks.png")
# #plt.show()


import matplotlib.pyplot as plt
import numpy as np

# Asumiendo que ya tienes estas listas:
# list_times_grey, list_times_solc, list_ins_cfg, f_names

# 1️⃣ Ordenamos los datos según el número de instrucciones
sorted_indices = np.argsort(list_ins_cfg)
ins_sorted = np.array(list_ins_cfg)[sorted_indices]
times_grey_sorted = np.array(list_times_grey)[sorted_indices]
times_solc_sorted = np.array(list_times_solc)[sorted_indices]
names_sorted = np.array(f_names)[sorted_indices]

# 2️⃣ Creamos las posiciones para las barras
x = np.arange(len(ins_sorted))
width = 0.4  # ancho de las barras

# 3️⃣ Dibujamos el gráfico
plt.figure(figsize=(12,6))
plt.bar(x - width/2, times_grey_sorted, width, label='SATE')
plt.bar(x + width/2, times_solc_sorted, width, label='solc')

# 4️⃣ Etiquetas y formato
plt.xlabel('CFG Instructions')
plt.ylabel('Execution time (s)')
# plt.title('Tiempos de ejecución: Greedy vs solc')
plt.xticks(x, ins_sorted, rotation=45)
plt.legend()
plt.grid(axis='y', linestyle='--', alpha=0.7)

plt.tight_layout()
plt.show()
plt.savefig("figs/bars-plot-code-gen.png")


plt.figure(figsize=(8,6))

# Dibujamos los puntos
plt.scatter(list_ins_cfg, list_times_grey, color='blue', alpha=0.7, label='SATE')
plt.scatter(list_ins_cfg, list_times_solc, color='orange', alpha=0.7, label='solc')

# Etiquetas y formato
plt.xlabel('CFG Instructions')
plt.ylabel('Execution time (s)')
#plt.title('Tiempo de ejecución vs complejidad (número de instrucciones)')
plt.legend()
plt.grid(True, linestyle='--', alpha=0.6)

plt.tight_layout()
plt.show()
plt.savefig("figs/scatter-plot-code-gen.png")

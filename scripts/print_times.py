import seaborn as sns
import pandas as pd
import matplotlib.pyplot as plt
import sys
def get_stats(file_name):
    f = open(file_name, "r")
    lines = f.readlines()

    all_times_grey_line = list(filter(lambda x: x.find("Times /User") != -1 and x.find("Total") == -1, lines))[0]

    all_times_aux = all_times_grey_line.split(":")[-1]
    all_times = list(map(lambda x: float(x.strip()), all_times_aux.split(",")))
    
    time_grey_line = list(filter(lambda x: x.find("Total times") != -1, lines))[0]
    time_grey = time_grey_line.split(":")[-1].strip()

    time_solc_line = list(filter(lambda x: x.find("TIME SOLC") != -1, lines))[0]
    time_solc = time_solc_line.split(":")[-1].strip()

    blocks_cfg_line = list(filter(lambda x: x.find("Total Blocks CFG") != -1, lines))[0]
    blocks_cfg = blocks_cfg_line.split(":")[-1].strip()

    ins_cfg_line = list(filter(lambda x: x.find("Total Ins CFG") != -1, lines))[0]
    ins_cfg = ins_cfg_line.split(":")[-1].strip()
    
    return float(time_grey), float(time_solc), int(blocks_cfg), int(ins_cfg), all_times


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
time_greedy = []
time_asm_generation = []
time_solc_importer = []

for i in range(len(f_names)):

    fname = f_names[i]
    fname_without_ext = fname.rstrip("log")

    print("CHECK: " + str((fname_without_ext+"output", fname_without_ext+"log")))
   

    time_grey, time_solc, blocks_cfg, ins_cfg, all_times = get_stats(fname_without_ext+"log")

    time_cfg_generation.append(all_times[0])
    time_cfg_parser.append(all_times[1])
    time_cfg_preprocess.append(all_times[2])
    time_layout.append(all_times[3])
    time_greedy.append(all_times[4])
    time_asm_generation.append(all_times[5])
    time_solc_importer.append(all_times[6])
    
    list_times_grey.append(time_grey)
    list_times_solc.append(time_solc)
    list_ins_cfg.append(ins_cfg)
    list_blocks_cfg.append(blocks_cfg)
    
    f_scal_cfg.write(",".join([fname_without_ext[:-1],str(blocks_cfg), str(ins_cfg),str(time_grey),str(time_solc)])+"\n")

# Plots with instructions
    
paired = sorted(zip(list_ins_cfg, list_times_grey))
ins_cfg_sorted, times_grey_sorted = zip(*paired)

ins_cfg_sorted, times_grey_sorted = list(ins_cfg_sorted), list(times_grey_sorted)

paired_solc = sorted(zip(list_ins_cfg, list_times_solc))
ins_cfg_sorted, times_solc_sorted = zip(*paired_solc)

ins_cfg_sorted, times_solc_sorted = list(ins_cfg_sorted), list(times_solc_sorted)

index_list = range(len(ins_cfg_sorted))


# max_time_grey = max(times_grey_sorted)
# times_grey_sorted = list(map(lambda x: x/max_time_grey*1.0, times_grey_sorted))

# max_time_solc = max(times_solc_sorted)
# times_solc_sorted = list(map(lambda x: x/max_time_solc*1.0, times_solc_sorted))


print(len(times_solc_sorted))

plt.figure()
# Crear DataFrame
df = pd.DataFrame({"x": index_list, "y": times_grey_sorted})

# Dibujar scatter
sns.scatterplot(data=df, x="x", y="y")

plt.xlabel("Contracts ordered by number of instructions")
plt.ylabel("Time (s)")
plt.title("(a) Execution time of SATE")


plt.savefig("figs/scatter-plot-grey.png")
#plt.show()

plt.figure()
# Crear DataFrame
df_solc = pd.DataFrame({"x": index_list, "y": times_solc_sorted})

# Dibujar scatter
sns.scatterplot(data=df_solc, x="x", y="y")

plt.xlabel("Contracts ordered by number of instructions")
plt.ylabel("Time (s)")
plt.title("(b) Execution time of solc")

plt.savefig("figs/scatter-plot-solc.png")
#plt.show()

plt.figure()
# Crear DataFrame
df = pd.DataFrame({"x": ins_cfg_sorted, "y": times_grey_sorted})

# Dibujar scatter
sns.scatterplot(data=df, x="x", y="y")

plt.xlabel("Num Instructions")
plt.ylabel("Time (s)")
plt.title("(a) Executio time of SATE")


plt.savefig("figs/scatter-plot-grey-ins.png")
#plt.show()

plt.figure()
# Crear DataFrame
df_solc = pd.DataFrame({"x": ins_cfg_sorted, "y": times_solc_sorted})

# Dibujar scatter
sns.scatterplot(data=df_solc, x="x", y="y")

plt.xlabel("Num Instructions")
plt.ylabel("Time (s)")
plt.title("(b) Execution time of solc")


plt.savefig("figs/scatter-plot-solc-ins.png")
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
plt.title("(a) Execution time of SATE")


plt.savefig("figs/scatter-plot-grey-blocks-relative.png")
#plt.show()

plt.figure()
# Crear DataFrame
df_solc = pd.DataFrame({"x": index_list, "y": times_solc_sorted})

# Dibujar scatter
sns.scatterplot(data=df_solc, x="x", y="y")

plt.xlabel("Contracts ordered by number of blocks")
plt.ylabel("Time (s)")
plt.title("(b) Execution time of solc")


plt.savefig("figs/scatter-plot-solc-blocks-relative.png")
#plt.show()

plt.figure()
# Crear DataFrame
df = pd.DataFrame({"x": blocks_cfg_sorted, "y": times_grey_sorted})

# Dibujar scatter
sns.scatterplot(data=df, x="x", y="y")

plt.xlabel("Num Blocks")
plt.ylabel("Time (s)")
plt.title("(a) Execution time of SATE")

plt.savefig("figs/scatter-plot-grey-blocks.png")
#plt.show()

plt.figure()
# Crear DataFrame
df_solc = pd.DataFrame({"x": blocks_cfg_sorted, "y": times_solc_sorted})

# Dibujar scatter
sns.scatterplot(data=df_solc, x="x", y="y")

plt.xlabel("Num Blocks")
plt.ylabel("Time (s)")
plt.title("(b) Execution time of solc")

plt.savefig("figs/scatter-plot-solc-blocks.png")
#plt.show()


#Times by phases
paired = sorted(zip(list_ins_cfg, time_cfg_generation))
ins_cfg_sorted, time_cfg_generation_sorted = zip(*paired)

ins_cfg_sorted, times_cfg_generation_sorted = list(ins_cfg_sorted), list(time_cfg_generation_sorted)

paired = sorted(zip(list_ins_cfg, time_cfg_parser))
ins_cfg_sorted, time_cfg_parser_sorted = zip(*paired)

ins_cfg_sorted, times_cfg_parser_sorted = list(ins_cfg_sorted), list(time_cfg_parser_sorted)

paired = sorted(zip(list_ins_cfg, time_cfg_preprocess))
ins_cfg_sorted, time_cfg_preprocess_sorted = zip(*paired)

ins_cfg_sorted, times_cfg_preprocess_sorted = list(ins_cfg_sorted), list(time_cfg_preprocess_sorted)

paired = sorted(zip(list_ins_cfg, time_layout))
ins_cfg_sorted, time_layout_sorted = zip(*paired)

ins_cfg_sorted, times_layout_sorted = list(ins_cfg_sorted), list(time_layout_sorted)

paired = sorted(zip(list_ins_cfg, time_greedy))
ins_cfg_sorted, time_greedy_sorted = zip(*paired)

ins_cfg_sorted, times_greedy_sorted = list(ins_cfg_sorted), list(time_greedy_sorted)

paired = sorted(zip(list_ins_cfg, time_asm_generation))
ins_cfg_sorted, time_asm_generation_sorted = zip(*paired)

ins_cfg_sorted, times_asm_generation_sorted = list(ins_cfg_sorted), list(time_asm_generation_sorted)

paired = sorted(zip(list_ins_cfg, time_solc_importer))
ins_cfg_sorted, time_solc_importer_sorted = zip(*paired)

ins_cfg_sorted, times_solc_importer_sorted = list(ins_cfg_sorted), list(time_solc_importer_sorted)

ys = [time_cfg_generation_sorted, time_cfg_parser_sorted, time_cfg_preprocess_sorted, time_layout_sorted, time_greedy_sorted, time_asm_generation_sorted, time_solc_importer_sorted]
labels = ['CFG Generation', 'CFG Parser', 'CFG Preprocess', 'Layout Generation', 'Greedy', 'ASM Generation', 'solc Importer']

plt.figure()

for y, label in zip(ys, labels):
    plt.plot(ins_cfg_sorted, y, label=label)

# Personalizar gráfico
plt.xlabel('Instructions in CFG')
plt.ylabel('Time (s)')
plt.title('(c) Execution time of different phases')
plt.legend()
plt.grid(False)
#plt.show()

plt.savefig("figs/times-per-phase.png")

#Barras acumulado

import numpy as np

plt.figure()
# Eje x como posiciones (pueden ser índices o categorías)
x_pos = np.arange(len(ins_cfg_sorted))

print(times_cfg_generation_sorted[-3:])
print(ins_cfg_sorted[-3:])

# Listas de valores
ys = [time_cfg_generation_sorted, time_cfg_parser_sorted, time_cfg_preprocess_sorted, time_layout_sorted, time_greedy_sorted, time_asm_generation_sorted, time_solc_importer_sorted]
labels = ['CFG Generation', 'CFG Parser', 'CFG Preprocess', 'Layout Generation', 'Greedy', 'ASM Generation', 'solc Importer']
colors = ['skyblue', 'orange', 'green', 'red', 'purple', 'gray','yellow']

# Inicializar base (bottom) en cero
bottom = np.zeros(len(ins_cfg_sorted))

# Dibujar cada serie apilada
for y, label, color in zip(ys, labels, colors):
    plt.bar(x_pos, y, bottom=bottom, label=label, color=color, width=1.0)
    bottom += np.array(y)  # Acumular para el siguiente nivel

# Personalización
plt.xlabel('Contracts sorted by num of instructions')
plt.ylabel('Time (s)')
plt.title('Total time per phase')
#plt.xticks(x_pos, ins_cfg_sorted)  # Usar tus valores reales de x como etiquetas
plt.ylim(0, 0.85)
plt.yticks(np.arange(0, 0.86, 0.05))
plt.xticks(np.arange(0, len(ins_cfg_sorted)+1, 50))
plt.legend()
plt.grid(True, axis='y', linestyle='--', alpha=0.5)

plt.savefig("figs/times-per-phase-bars.png")
#plt.show()




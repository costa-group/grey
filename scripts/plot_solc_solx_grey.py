import matplotlib.pyplot as plt
import numpy as np

# Nombre del archivo a leer
archivo = 'all_num_instructions.txt'  # Cambia esto por el nombre real de tu archivo

# Listas para guardar los valores
origin_num_ins = []
origin_num_ins_solx = []
opt_num_ins = []

# Leer el archivo línea por línea
with open(archivo, 'r') as f:
    for linea in f:
        linea = linea.strip()
        
        # Buscar patrones y extraer número
        if 'ORIGIN NUM INS SOLX:' in linea:
            numero = int(linea.split('ORIGIN NUM INS SOLX:')[1].strip())
            origin_num_ins_solx.append(numero)
        elif 'ORIGIN NUM INS:' in linea:
            numero = int(linea.split('ORIGIN NUM INS:')[1].strip())
            origin_num_ins.append(numero)
        elif 'OPT NUM INS:' in linea:
            numero = int(linea.split('OPT NUM INS:')[1].strip())
            opt_num_ins.append(numero)

# Imprimir resultados
print("ORIGIN NUM INS:", origin_num_ins)
print("ORIGIN NUM INS SOLX:", origin_num_ins_solx)
print("OPT NUM INS:", opt_num_ins)


print(len(origin_num_ins))
print(len(origin_num_ins_solx))
print(len(opt_num_ins))
assert(len(origin_num_ins) == len(origin_num_ins_solx))
assert(len(origin_num_ins_solx) == len(opt_num_ins))

init_limit = 300
end_limit = 400

origin_num_ins = origin_num_ins[init_limit:end_limit]
origin_num_ins_solx = origin_num_ins_solx[init_limit:end_limit]
opt_num_ins = opt_num_ins[init_limit:end_limit]


n = len(origin_num_ins)

separacion = 3
# Posiciones en el eje x
x = np.arange(1, n + 1)*separacion  # x = 1, 2, 3, ..., n

# Ancho de cada barra
width = 0.75

# Crear gráfico
#plt.figure(figsize=(12, 6))

plt.bar(x - width, origin_num_ins, width=width, label='NUM INS SOLC', color='skyblue')
plt.bar(x, origin_num_ins_solx, width=width, label='NUM INS SOLX', color='orange')
plt.bar(x + width, opt_num_ins, width=width, label='NUM INS GREY', color='green')

# Etiquetas y leyenda

plt.ylim(0, 3000)

plt.xlabel('Contracts')
plt.ylabel('Instructions')
plt.title('EVM Instruction per contract')
plt.xticks(x)  # Mostrar ticks en 1, 2, 3, ...
plt.legend()
plt.grid(True, axis='y', linestyle='--', alpha=0.5)

plt.tight_layout()
plt.show()

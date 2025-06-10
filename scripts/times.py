f = open("salida.csv","r")

lines = f.readlines()

lines_aux = map(lambda x: x.strip(), lines)

numbers = [0,0,0,0,0,0,0]
for l in lines_aux:
    elems = l.split(",")
    numbers_l = list(map(lambda x: float(x), elems))

    assert(len(numbers) == len(numbers_l))
    numbers = [a + b for a, b in zip(numbers, numbers_l)]

print("Numeros por fase")
print(numbers)

f1 = open("salida-times.txt","r")
lines = f1.readlines()

f2 = open("salida-ficheros.txt", "r")
nombres_ficheros_aux = f2.readlines()
nombres_ficheros = list(map(lambda x: "/Users/pablo/Repositorios/ethereum/grey/scripts/"+x.strip().rstrip("log")[:-1]+"_standard_input",nombres_ficheros_aux))

lines_solc = list(filter(lambda x: x.find("TIME SOLC") != -1, lines))
lines_grey = list(filter(lambda x: x.find("TIME GREY") != -1, lines))

solc_time = 0
grey_time = 0

for l in lines_solc:
    name = l.split(":")[0].split()[-1].rstrip("json")[:-1]
    time = float(l.split(":")[1])

    if name in nombres_ficheros:
        solc_time+=time

for l in lines_grey:
    name = l.split(":")[0].split()[-1].rstrip("json")[:-1]
    time = float(l.split(":")[1])

    if name in nombres_ficheros:
        grey_time+=time

print("TOTAL TIME SOLC: "+str(solc_time))
print("TOTAL TIME GREY: "+str(grey_time))

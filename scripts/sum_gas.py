import sys

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




f = sys.argv[1]#"num_gas.txt"

ff = open(f, "r")
lines = ff.readlines()

origin = list(filter(lambda x: x.find("ORIGINAL EXECUTION GAS")!= -1, lines))
origin_number = list(map(lambda x: int(x.split(":")[-1].strip()), origin))

# f_names = list(map(lambda x: x.split(":")[0].rstrip(" ORIGIN NUM BYTES"),origin))

total_origin = sum(origin_number)

origin_creation = list(filter(lambda x: x.find("ORIGINAL CREATION GAS")!= -1, lines))
origin_number_creation = list(map(lambda x: int(x.split(":")[-1].strip()), origin_creation))

# f_names = list(map(lambda x: x.split(":")[0].rstrip(" ORIGIN NUM BYTES"),origin))

total_origin_creation = sum(origin_number_creation)




opt = list(filter(lambda x: x.find("OPT EXECUTION GAS")!= -1, lines))
opt_number = list(map(lambda x: int(x.split(":")[-1].strip()), opt))

total_opt = sum(opt_number)


opt_creation = list(filter(lambda x: x.find("OPT CREATION GAS")!= -1, lines))
opt_number_creation = list(map(lambda x: int(x.split(":")[-1].strip()), opt_creation))

total_opt_creation = sum(opt_number_creation)


menor = 0
mayor = 0
igual = 0

total_mejor = 0
optimizado_mejor = 0


total_peor = 0
optimizado_peor = 0

cuartiles_res = [0 ,0,0,0]

# worse_files = {}

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

        # fname = f_names[i]
        
        # worse_files[fname] = (original, optimizado)
        # print("PAREJA: ("+str(original)+","+str(optimizado)+")")
        total_peor+= original
        optimizado_peor+=optimizado
        cuartiles(original, optimizado, cuartiles_res)
        mayor+=1

# s = ""
# for k,v in worse_files.items():
#     s+=k+":"+str(v)+"\n"
    
# worse_file = open("worse_bytes_contracts.txt", "w")
# worse_file.write(s)
# worse_file.close()

print()
print(" ===== GAS STATISTICS EXECUTION =====")


# print("CASOS EN EL QUE SOMOS MEJOR: "+str(menor))
print("CASOS EN LOS QUE SOMOS IGUALES EN GAS: "+str(igual))
print("CASOS EN LOS QUE SOMOS PEORES EN GAS: "+str(mayor))
print()

assert(len(origin_number) == len(opt_number))

print("TOTAL")
print("TOTAL GAS ORIGINAL: "+str(total_origin))
print("TOTAL GAS OPT: "+str(total_opt))
print("%: "+str((total_opt/(total_origin*1.0))*100.0))
print()
print("MEJORAMOS")
print("TOTAL GAS ORIGINAL: "+str(total_mejor))
print("TOTAL GAS OPT: "+str(optimizado_mejor))

print("%: "+str((optimizado_mejor/total_mejor*1.0)*100.0))

print()
print("EMPEORAMOS")
print(total_peor)
print(optimizado_peor)

print((optimizado_peor/total_peor*1.0)*100.0)

print(cuartiles_res)


menor = 0
mayor = 0
igual = 0

total_mejor = 0
optimizado_mejor = 0


total_peor = 0
optimizado_peor = 0

cuartiles_res = [0,0,0,0]

# worse_files = {}

for i in range(len(origin_number_creation)):
    original = origin_number_creation[i]
    optimizado = opt_number_creation[i]

    if original > optimizado:
        menor+=1
        total_mejor += original
        optimizado_mejor+= optimizado
        
    elif original == optimizado:
        igual+=1
    else:

        # fname = f_names[i]
        
        # worse_files[fname] = (original, optimizado)
        # print("PAREJA: ("+str(original)+","+str(optimizado)+")")
        total_peor+= original
        optimizado_peor+=optimizado
        cuartiles(original, optimizado, cuartiles_res)
        mayor+=1

# s = ""
# for k,v in worse_files.items():
#     s+=k+":"+str(v)+"\n"
    
# worse_file = open("worse_bytes_contracts.txt", "w")
# worse_file.write(s)
# worse_file.close()

print()
print(" ===== GAS STATISTICS CREATION =====")


# print("CASOS EN EL QUE SOMOS MEJOR: "+str(menor))
print("CASOS EN LOS QUE SOMOS IGUALES EN GAS: "+str(igual))
print("CASOS EN LOS QUE SOMOS PEORES EN GAS: "+str(mayor))
print()

assert(len(origin_number) == len(opt_number))

print("TOTAL")
print("TOTAL GAS ORIGINAL: "+str(total_origin_creation))
print("TOTAL GAS OPT: "+str(total_opt_creation))
print("%: "+str((total_opt_creation/(total_origin_creation*1.0))*100.0))
print()
print("MEJORAMOS")
print("TOTAL GAS ORIGINAL: "+str(total_mejor))
print("TOTAL GAS OPT: "+str(optimizado_mejor))

print("%: "+str((optimizado_mejor/total_mejor*1.0)*100.0))

print()
print("EMPEORAMOS")
print(total_peor)
print(optimizado_peor)

print((optimizado_peor/total_peor*1.0)*100.0)

print(cuartiles_res)


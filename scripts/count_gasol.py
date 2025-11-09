f = open("gasol_res.txt", "r")
lines = f.readlines()

total_blocks = 0
mejores_ins = 0
mejores_size = 0
mejores_gas = 0

total_ins = 0
gains_ins = 0

total_bytes = 0
gains_bytes = 0

total_gas = 0
gains_gas = 0

for l in lines:
    elems = l.split(":")[-1]
    nums = elems.split(";")

    print(nums)
    
    total_blocks+=int(nums[1])
    mejoras = nums[5].strip("(").strip(")").split(",")

    mejores_ins+=int(mejoras[0])
    mejores_size+=int(mejoras[1])
    mejores_gas+=int(mejoras[2])


    total_ins+=int(nums[2])
    total_bytes+=int(nums[3])
    total_gas+=int(nums[4])

    gains_ins+=int(nums[6])
    gains_bytes+=int(nums[7])
    gains_gas+=int(nums[8])

    
print("TOTAL BLOCKS: "+str(total_blocks))
print("MEJORES EN INS: "+str(mejores_ins))
print("MEJORES EN SIZE: "+str(mejores_size))
print("MEJORES EN GAS: "+str(mejores_gas))
print("***************")
print("TOTAL INS: "+str(total_ins))
print("GAINS INS: "+str(gains_ins))
print("IMPROVEMENT: "+str((gains_ins)*100.0/total_ins))
      
print("TOTAL BYTES: "+str(total_bytes))
print("GAINS BYTES: "+str(gains_bytes))
print("IMPROVEMENT: "+str((gains_bytes)*100.0/total_bytes))

print("TOTAL GAS: "+str(total_gas))
print("GAINS GAS: "+str(gains_gas))
print("IMPROVEMENT: "+str((gains_gas)*100.0/total_gas))

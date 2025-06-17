"""
Methods for applying simplification rules
"""

from typing import Dict, List, Tuple, Set
from global_params.types import var_id_T
from parser.cfg import CFG
from parser.cfg_block_list import CFGBlockList
from parser.cfg_block import CFGBlock
from parser.cfg_instruction import CFGInstruction


def apply_rule_simplification(cfg: CFG) -> None:
    for _object_id, cfg_object in cfg.objectCFG.items():

        apply_rule_simplification_block_list(cfg_object.blocks)

        for _f_id, cfg_function in cfg_object.functions.items():
            apply_rule_simplification_block_list(cfg_function.blocks)

        
def apply_rule_simplification_block_list(block_list: CFGBlockList) -> None:
    for _bl_id, bl in block_list.blocks.items():
        apply_rule_simplification_block(bl)


def apply_rule_simplification_block(block: CFGBlock)-> None:
    pass





def apply_transform(instr):
    global discount_op
    global saved_push
    global gas_saved_op
    global rule

    
    opcode = instr["disasm"]
    if opcode == "AND":
        inp_vars = instr["inpt_sk"]
        if 0 in inp_vars:
            saved_push+=2
            gas_saved_op+=3
            
            discount_op+=1
            rule = "AND(X,0)"
            return 0
        elif inp_vars[0] == inp_vars[1]:
            saved_push+=1
            gas_saved_op+=3

            discount_op+=1
            rule = "AND(X,X)"
            return inp_vars[0]
    
        elif inp_vars[0] in int_not0 or inp_vars[1] in int_not0:
            saved_push+=2
            gas_saved_op+=3

            discount_op+=1
            rule = "AND(X,2^256-1)"
            return inp_vars[1] if (inp_vars[0] in int_not0) else inp_vars[0]
        else:
            return -1
        
    elif opcode == "OR":
        inp_vars = instr["inpt_sk"]
        if 0 in inp_vars:
            saved_push+=2
            gas_saved_op+=3

            discount_op+=1
            rule = "OR(X,0)"
            return inp_vars[1] if inp_vars[0] == 0 else inp_vars[0]
        elif inp_vars[0] == inp_vars[1]:
            saved_push+=1
            gas_saved_op+=3

            discount_op+=1
            rule = "OR(X,X)"
            return inp_vars[0]
        else:
            return -1

    elif opcode == "XOR":
        inp_vars = instr["inpt_sk"]
        
        if inp_vars[0] == inp_vars[1]:
            saved_push+=1
            gas_saved_op+=3

            discount_op+=1
            rule = "XOR(X,X)"
            return 0
        elif 0 in inp_vars:
            saved_push+=2
            gas_saved_op+=3

            discount_op+=1
            rule = "XOR(X,0)"
            return inp_vars[1] if inp_vars[0] == 0 else inp_vars[0]
        else:
            return -1

    elif opcode == "EXP":
        inp_vars = instr["inpt_sk"]
        
        if inp_vars[1] == 0:
            saved_push+=2
            gas_saved_op+=60

            discount_op+=1
            rule = "EXP(X,0)"
            return 1
        elif inp_vars[1] == 1:
            saved_push+=1
            gas_saved_op+=60
            
            discount_op+=1
            rule = "EXP(X,1)"
            return inp_vars[0]
        elif inp_vars[0] == 1:
            gas_saved_op+=60
            
            discount_op+=1
            rule = "EXP(1,X)"
            return 1
        else:
            return -1

    elif opcode == "ADD":
        inp_vars = instr["inpt_sk"]
        if 0 in inp_vars:
            saved_push+=1
            gas_saved_op+=3

            discount_op+=1
            rule = "ADD(X,0)"
            return inp_vars[1] if inp_vars[0] == 0 else inp_vars[0]
        else:
            return -1

    elif opcode == "SUB":
        inp_vars = instr["inpt_sk"]
        if 0 == inp_vars[1]:
            saved_push+=1
            gas_saved_op+=3

            discount_op+=1
            rule = "SUB(X,0)"
            return inp_vars[0]
        elif inp_vars[0] == inp_vars[1]:
            saved_push+=1
            gas_saved_op+=3

            discount_op+=1
            rule = "SUB(X,X)"
            return 0
        else:
            return -1
        
    elif opcode == "MUL":
        inp_vars = instr["inpt_sk"]
        if 0 in inp_vars:
            saved_push+=2
            gas_saved_op+=5

            discount_op+=1
            rule = "MUL(X,0)"
            return 0
        elif 1 in inp_vars:
            saved_push+=1
            gas_saved_op+=5
            
            discount_op+=1
            rule = "MUL(X,1)"
            return inp_vars[1] if inp_vars[0] == 1 else inp_vars[0]
        else:
            return -1

    elif opcode == "DIV" or opcode == "SDIV":
        inp_vars = instr["inpt_sk"]
        if 1 == inp_vars[1]:
            saved_push+=1
            gas_saved_op+=5
            
            discount_op+=1
            rule = f"{opcode}(X,1)"
            return inp_vars[0]

        elif 0 in inp_vars:
            saved_push+=2
            gas_saved_op+=5

            discount_op+=1
            rule = f"{opcode}(X,0)"
            return 0

        elif inp_vars[0] == inp_vars[1]:
            saved_push+=2
            gas_saved_op+=5

            discount_op+=1
            rule = f"{opcode}(X,X)"
            return 1
        else:
            return -1

    elif opcode == "MOD":
        inp_vars = instr["inpt_sk"]
        if  1 == inp_vars[1]:
            saved_push+=2
            gas_saved_op+=5
            
            discount_op+=1
            rule = "MOD(X,1)"
            return 0

        elif inp_vars[0] == inp_vars[1]:
            saved_push+=2
            gas_saved_op+=5

            discount_op+=1
            rule = "MOD(X,X)"
            return 0

        elif inp_vars[1] == 0:
            saved_push+=2
            gas_saved_op+=5

            discount_op+=1
            rule = "MOD(X,0)"
            return 0

        else:
            return -1

    elif opcode == "EQ":
        inp_vars = instr["inpt_sk"]
        if inp_vars[0] == inp_vars[1]:
            discount_op+=1
            saved_push+=2
            gas_saved_op+=3

            rule = "EQ(X,X)"
            
            return 1
        else:
            return -1

    elif opcode == "GT" or opcode == "SGT":
        inp_vars = instr["inpt_sk"]
        if inp_vars[0] == 0 and opcode == "GT":
            saved_push+=2
            gas_saved_op+=3

            discount_op+=1

            rule = "GT(0,X)"
            
            return 0
        elif inp_vars[0] == inp_vars[1]:
            discount_op+=1
            saved_push+=2
            gas_saved_op+=3

            rule = opcode+"(X,X)"
            return 0
        else:
            return -1

    elif opcode == "LT" or opcode == "SLT":
        inp_vars = instr["inpt_sk"]
        if inp_vars[1] == 0 and opcode == "LT":
            saved_push+=2
            gas_saved_op+=3

            discount_op+=1

            rule = "LT(X,0)"
            return 0
        elif inp_vars[0] == inp_vars[1]:
            discount_op+=1
            saved_push+=2
            gas_saved_op+=3

            rule = opcode+"(X,X)"
            return 0
        else:
            return -1

    elif opcode == "NOT":
        inp_vars = instr["inpt_sk"]
        r, val = all_integers(inp_vars)
        if r:
            val_end = ~(int(val[0]))+2**256

            if size_flag:
                v0 = int(val[0])
                bytes_v0 = get_num_bytes_int(v0)
                bytes_sol = get_num_bytes_int(val_end)

                if bytes_sol <= bytes_v0+1:    
                    saved_push+=1
                    gas_saved_op+=3
                    rule = "NOT(X)"
                    return val_end
                else:
                    return -1

            else:
                saved_push+=1
                gas_saved_op+=3
                rule = "NOT(X)"
                return val_end
            
        else:
            return -1
        
    elif opcode == "ISZERO":
        inp_vars = instr["inpt_sk"]
        if inp_vars[0] == 0:
            gas_saved_op+=3
            saved_push+=1
            rule = "ISZ(0)"
            return 1
        elif inp_vars[0] == 1:
            gas_saved_op+=3
            saved_push+=1
            rule = "ISZ(1)"
            return 0
        else:
            return -1

    elif opcode == "SHR" or opcode == "SHL":
        inp_vars = instr["inpt_sk"]
        if inp_vars[0] == 0:
            discount_op+=1
            saved_push+=2
            gas_saved_op+=3

            rule = opcode+"(0,X)"
            
            return inp_vars[1]
        elif inp_vars[1] == 0:
            discount_op+=1
            saved_push+=2
            gas_saved_op+=3
            rule = opcode+"(X,0)"
            return inp_vars[0]
        else:
            return -1


def apply_all_simp_rules(user_def,list_vars,tstack):
    global rule_applied
    
    modified = True
    user_def_instrs = user_def
    target_stack = tstack
    while(modified):

        modified, user_def_instrs,target_stack = apply_transform_rules(user_def_instrs,list_vars,target_stack)
        if modified:
           rule_applied = True 
    return user_def_instrs,target_stack

def apply_transform_rules(blocks: CFGBlockList) -> None:
    global rules_applied
    global rule

    to_delete = []
    target_stack = tstack
    modified = False
    for instr in user_def_instrs:
        
        if instr["disasm"] in ["AND","OR","XOR","ADD","SUB","MUL","DIV","EXP","EQ","GT","LT","SGT","SLT","SDIV","NOT","ISZERO"]:
            r = apply_transform(instr)

            if r!=-1:
                rules_applied.append(rule)
                rule = ""
                msg = "[RULE]: Simplification rule type 1: "+str(instr)
                check_and_print_debug_info(debug, msg)
                
                replace_var_userdef(instr["outpt_sk"][0],r,user_def_instrs)
                target_stack = replace_var(instr["outpt_sk"][0],r,target_stack)
                delete_from_listvars(instr["outpt_sk"][0],list_vars)
                to_delete.append(instr)
                modified = True
    i = 0
    new_user_def = []
    while len(user_def_instrs)>0:
        instr = user_def_instrs.pop()
        if instr not in to_delete:
            new_user_def.append(instr)


    return modified, new_user_def, target_stack

    

def apply_cond_transformation(instr,user_def_instrs,tstack):
    global discount_op
    global saved_push
    global gas_saved_op
    global user_def_counter
    global rule
    
    opcode = instr["disasm"]
    
    if opcode == "GT" or opcode == "SGT":
        if 0 == instr["inpt_sk"][1] and opcode == "GT":
            out_var = instr["outpt_sk"][0]
            is_zero = list(filter(lambda x: out_var in x["inpt_sk"] and x["disasm"] == "ISZERO",user_def_instrs))
            if len(is_zero) == 1 and out_var not in tstack:
                # print(tstack)
                # raise Exception
                index = user_def_instrs.index(is_zero[0])
                zero_instr = user_def_instrs[index]
                zero_instr["inpt_sk"] = [instr["inpt_sk"][0]]
                saved_push+=2
                gas_saved_op+=3

                
                if out_var not in tstack:
                    discount_op+=2

                msg = "ISZ(GT(X,0))"
                rule = msg
                check_and_print_debug_info(debug, msg)
                
                return True, []
            else:
                return False, []

        elif 1 == instr["inpt_sk"][0] and opcode == "GT":
            var = instr["inpt_sk"][1]
            idx = user_def_counter.get("ISZERO",0)
            instr["id"] = "ISZERO_"+str(idx)
            instr["opcode"] = "15"
            instr["disasm"] = "ISZERO"
            instr["inpt_sk"] = [var]
            instr["commutative"] = False
            discount_op+=1
            saved_push+=2

            user_def_counter["ISZERO"]=idx+1
            
            msg = "GT(1,X)"
            rule = msg
            check_and_print_debug_info(debug, msg)
            return True, []


        else:
            out_var = instr["outpt_sk"][0]
            is_zero = list(filter(lambda x: out_var in x["inpt_sk"] and x["disasm"] == "ISZERO",user_def_instrs))
            if len(is_zero)==1:
                zero = is_zero[0]
                zero2 = list(filter(lambda x: zero["outpt_sk"][0] in x["inpt_sk"] and x["disasm"] == "ISZERO",user_def_instrs))
                if len(zero2) == 1 and zero["outpt_sk"][0] not in tstack:
                    # instr["outpt_sk"] = zero2[0]["outpt_sk"]
                    old_var = instr["outpt_sk"]
                    new_var = zero2[0]["outpt_sk"]
                    instr["outpt_sk"] = new_var
                    
                    discount_op+=2

                    gas_saved_op+=6

                    msg = "ISZ(ISZ("+opcode+"(X,Y)))" #It may be GT or SGT
                    rule = msg
                    check_and_print_debug_info(debug, msg)

                    update_tstack_userdef(old_var[0], new_var[0],tstack, user_def_instrs)
                    
                    return True, [zero,zero2[0]]
                else:
                    return False, []
            else:
                
                return False, []

    elif opcode == "ISZERO":
    
        out_var = instr["outpt_sk"][0]
        is_zero = list(filter(lambda x: out_var in x["inpt_sk"] and x["disasm"] == "ISZERO",user_def_instrs))

        is_eq = list(filter(lambda x: out_var in x["inpt_sk"] and x["disasm"] == "EQ",user_def_instrs))
        
        if len(is_zero)==1:
         
            zero = is_zero[0]
  
            zero2 = list(filter(lambda x: zero["outpt_sk"][0] in x["inpt_sk"] and x["disasm"] == "ISZERO",user_def_instrs))
            if len(zero2) == 1 and zero["outpt_sk"][0] not in tstack:
             
                # instr["outpt_sk"] = zero2[0]["outpt_sk"]
                old_var = instr["outpt_sk"]
                new_var = zero2[0]["outpt_sk"]
                instr["outpt_sk"] = new_var

                discount_op+=2
                
                gas_saved_op+=6

                msg = "ISZ(ISZ(ISZ(X)))"
                rule = msg
                check_and_print_debug_info(debug, msg)

                update_tstack_userdef(old_var[0], new_var[0],tstack, user_def_instrs)
                
                return True, [zero,zero2[0]]
            else:
                return False, []

        elif len(is_eq) == 1:
            eq = is_eq[0]

            if 1 in eq["inpt_sk"]:
                old_var = instr["outpt_sk"]
                new_var = eq["outpt_sk"]
                # instr["outpt_sk"] = eq["outpt_sk"]
                instr["outpt_sk"] = new_var
                discount_op+=1

                saved_push+=1
                gas_saved_op+=3

                msg = "EQ(1,ISZ(X))"
                rule = msg
                check_and_print_debug_info(debug, msg)

                update_tstack_userdef(old_var[0], new_var[0],tstack, user_def_instrs)
                
                return True, [eq]

            else:
                return False, []
        else:
                
            return False, []
            
    elif opcode == "LT" or opcode == "SLT":
         if 0 == instr["inpt_sk"][0] and opcode == "LT":
            out_var = instr["outpt_sk"][0]
            is_zero = list(filter(lambda x: out_var in x["inpt_sk"] and x["disasm"] == "ISZERO",user_def_instrs))
            if len(is_zero) == 1 and out_var not in tstack:
                index = user_def_instrs.index(is_zero[0])
                zero_instr = user_def_instrs[index]
                zero_instr["inpt_sk"] = [instr["inpt_sk"][1]]

                if out_var not in tstack:
                    discount_op+=2

                saved_push+=1
                gas_saved_op+=3

                msg = "ISZ(LT(0,X))"
                rule = msg
                check_and_print_debug_info(debug, msg)
                
                return True, []
            else:
                return False, []

         elif 1 == instr["inpt_sk"][1] and opcode == "LT":
            var = instr["inpt_sk"][0]

            new_exist = list(filter(lambda x: x["inpt_sk"] == [var] and x["disasm"] == "ISZERO", user_def_instrs))
                        
            if len(new_exist) >0:
                old_var = instr["outpt_sk"]
                new_var = new_exist[0]["outpt_sk"]
                update_tstack_userdef(old_var[0], new_var[0],tstack, user_def_instrs)
                delete = [instr]
            else:
                idx = user_def_counter.get("ISZERO",0)
                instr["id"] = "ISZERO_"+str(idx)
                instr["opcode"] = "15"
                instr["disasm"] = "ISZERO"
                instr["inpt_sk"] = [var]
                instr["commutative"] = False
                user_def_counter["ISZERO"]=idx+1
                delete = []
                
            discount_op+=1

            saved_push+=1

            msg = "LT(X,1)"
            rule = msg
            check_and_print_debug_info(debug, msg)
            return True, delete
        
         else:
            out_var = instr["outpt_sk"][0]
            is_zero = list(filter(lambda x: out_var in x["inpt_sk"] and x["disasm"] == "ISZERO",user_def_instrs))
            if len(is_zero)==1:
                zero = is_zero[0]
                zero2 = list(filter(lambda x: zero["outpt_sk"][0] in x["inpt_sk"] and x["disasm"] == "ISZERO",user_def_instrs))
                if len(zero2) == 1 and zero["outpt_sk"][0] not in tstack:
                    old_var = instr["outpt_sk"]
                    new_var = zero2[0]["outpt_sk"]
                    instr["outpt_sk"] = new_var

                    # instr["outpt_sk"] = zero2[0]["outpt_sk"]
                    discount_op+=2

                    gas_saved_op+=6

                    msg = "ISZ(ISZ("+opcode+"(X,Y)))" # It may be LT or SLT
                    rule = msg
                    check_and_print_debug_info(debug, msg)

                    update_tstack_userdef(old_var[0], new_var[0],tstack, user_def_instrs)
                    
                    return True, [zero,zero2[0]]
                else:
                    return False, []
            else:
                
                return False, []
            
    elif opcode == "EQ":
        if 0 in instr["inpt_sk"]:
            var0 = instr["inpt_sk"][0]
            var1 = instr["inpt_sk"][1]

            nonz = var1 if var0 == 0 else var0

            new_exist = list(filter(lambda x: x["inpt_sk"] == [nonz] and x["disasm"] == "ISZERO", user_def_instrs))

            if len(new_exist) >0:
                old_var = instr["outpt_sk"]
                new_var = new_exist[0]["outpt_sk"]
                update_tstack_userdef(old_var[0], new_var[0],tstack, user_def_instrs)
                delete = [instr]

            else:
                idx = user_def_counter.get("ISZERO",0)
                instr["id"] = "ISZERO_"+str(idx)
                instr["opcode"] = "15"
                instr["disasm"] = "ISZERO"
                instr["inpt_sk"] = [nonz]
                instr["commutative"] = False
                user_def_counter["ISZERO"]=idx+1
                delete = []

            

            discount_op+=1
            saved_push+=1

            msg = "EQ(0,X)"
            rule = msg
            check_and_print_debug_info(debug, msg)

            # user_def_counter["ISZERO"]=idx+1
            
            return True, delete

        else:

            out_var = instr["outpt_sk"][0]
            is_zero = list(filter(lambda x: out_var in x["inpt_sk"] and x["disasm"] == "ISZERO",user_def_instrs))
            if len(is_zero)==1:
                zero = is_zero[0]
                zero2 = list(filter(lambda x: zero["outpt_sk"][0] in x["inpt_sk"] and x["disasm"] == "ISZERO",user_def_instrs))
                if len(zero2) == 1 and zero["outpt_sk"][0] not in tstack:

                    old_var = instr["outpt_sk"]
                    new_var = zero2[0]["outpt_sk"]
                    instr["outpt_sk"] = new_var
                    # instr["outpt_sk"] = zero2[0]["outpt_sk"]
                    discount_op+=2

                    gas_saved_op+=6


                    msg = "ISZ(ISZ(EQ(X,Y)))"
                    rule = msg
                    check_and_print_debug_info(debug, msg)

                    update_tstack_userdef(old_var[0], new_var[0],tstack, user_def_instrs)
                    
                    return True, [zero,zero2[0]]
                else:
                    return False, []
            else:
                
                return False, []
            
    
    elif opcode == "AND":
        out_pt = instr["outpt_sk"][0]
        and_op = list(filter(lambda x: out_pt in x["inpt_sk"] and x["disasm"] == "AND", user_def_instrs))
        or_op = list(filter(lambda x: out_pt in x["inpt_sk"] and x["disasm"] == "OR", user_def_instrs))
        
        if len(and_op)==1:
            and_instr = and_op[0]
            if (and_instr["inpt_sk"][1] in instr["inpt_sk"]) or (and_instr["inpt_sk"][0] in instr["inpt_sk"]):
                
                old_var = instr["outpt_sk"]
                new_var = and_instr["outpt_sk"]
                instr["outpt_sk"] = new_var
                # instr["outpt_sk"] = and_instr["outpt_sk"]
                discount_op+=1

                saved_push+=1
                gas_saved_op+=3

                msg = "AND(X,AND(X,Y))"
                rule = msg
                check_and_print_debug_info(debug, msg)

                update_tstack_userdef(old_var[0], new_var[0],tstack, user_def_instrs)
                
                return True, [and_instr]
            else:
                return False, []

        elif len(or_op) == 1:
            or_instr = or_op[0]
            out_pt2 = or_instr["outpt_sk"][0]
            if out_pt == or_instr["inpt_sk"][1]: #(or(x,and(x,y)) = x, or(x,and(y,x)) = x, or(and(x,y),x) = x, or(and(y,x),x) = x
    
                if or_instr["inpt_sk"][0] == instr["inpt_sk"][0]:
                    x = instr["inpt_sk"][0]
                elif or_instr["inpt_sk"][0] == instr["inpt_sk"][1]:
                    x = instr["inpt_sk"][1]
                else:
                    return False, []
            elif out_pt == or_instr["inpt_sk"][0]:
                if or_instr["inpt_sk"][1] == instr["inpt_sk"][0]:
                    x = instr["inpt_sk"][0]
                elif or_instr["inpt_sk"][1] == instr["inpt_sk"][1]:
                    x = instr["inpt_sk"][1]
                else:
                    return False, []

            else:
                return False, []

            i = 0
                
            while (i<len(tstack)):
                if tstack[i] == (out_pt2):
                    tstack[i] = x
                i+=1
                
            for elems in user_def_instrs:
                if out_pt2 in elems["inpt_sk"]:
                    pos = elems["inpt_sk"].index(out_pt2)
                    elems["inpt_sk"][pos] = x
                    
            discount_op+=2
            gas_saved_op+=6


            msg = "OR(X,AND(X,Y))"
            rule = msg
            check_and_print_debug_info(debug, msg)
            
            return True, [or_instr]
            

        else:
            return False,[]
        
    elif opcode == "OR":
        out_pt = instr["outpt_sk"][0]
        or_op = list(filter(lambda x: out_pt in x["inpt_sk"] and x["disasm"] == "OR", user_def_instrs))
        and_op = list(filter(lambda x: out_pt in x["inpt_sk"] and x["disasm"] == "AND", user_def_instrs))
        if len(or_op)==1:
            or_instr = or_op[0]
            if (or_instr["inpt_sk"][1] in instr["inpt_sk"]) or (or_instr["inpt_sk"][0] in instr["inpt_sk"]):
                instr["outpt_sk"] = or_instr["outpt_sk"]
                discount_op+=1

                saved_push+=1
                gas_saved_op+=3

                msg = "OR(OR(X,Y),Y)"
                rule = msg
                check_and_print_debug_info(debug, msg)
                
                return True, [or_instr]
            else:
                return False, []

        elif len(and_op) == 1: 
            and_instr = and_op[0]
            out_pt2 = and_instr["outpt_sk"][0]
            if out_pt == and_instr["inpt_sk"][1]: #(and(x,or(x,y)) = x, and(x,or(y,x)) = x, and(or(x,y),x) = x, and(or(y,x),x) = x
    
                if and_instr["inpt_sk"][0] == instr["inpt_sk"][0]:
                    x = instr["inpt_sk"][0]
                elif and_instr["inpt_sk"][0] == instr["inpt_sk"][1]:
                    x = instr["inpt_sk"][1]
                else:
                    return False, []
            elif out_pt == and_instr["inpt_sk"][0]:
                if and_instr["inpt_sk"][1] == instr["inpt_sk"][0]:
                    x = instr["inpt_sk"][0]
                elif and_instr["inpt_sk"][1] == instr["inpt_sk"][1]:
                    x = instr["inpt_sk"][1]
                else:
                    return False, []

            else:
                return False, []

            i = 0
                
            while (i<len(tstack)):
                if tstack[i] == (out_pt2):
                    tstack[i] = x
                i+=1
                    
            for elems in user_def_instrs:
                if out_pt2 in elems["inpt_sk"]:
                    pos = elems["inpt_sk"].index(out_pt2)
                    elems["inpt_sk"][pos] = x
                    
            discount_op+=2
            gas_saved_op+=6

            msg = "AND(X,OR(X,Y))"
            rule = msg
            check_and_print_debug_info(debug, msg)
            
            return True, [and_instr]
            
        else:
            return False,[]


    elif opcode == "XOR":
        out_pt = instr["outpt_sk"][0]
        xor_op = list(filter(lambda x: out_pt in x["inpt_sk"] and x["disasm"] == "XOR", user_def_instrs))
        isz_op = list(filter(lambda x: out_pt in x["inpt_sk"] and x["disasm"] == "ISZERO", user_def_instrs))
        
        if len(xor_op)==1:
            xor_instr = xor_op[0]
            out_pt2 = xor_instr["outpt_sk"][0]
            if out_pt == xor_instr["inpt_sk"][1]: #xor(x,xor(x,y)) = y, xor(x,xor(y,x)) = y, xor(xor(x,y),x) = y, xor(xor(y,x),x) = y
    
                if xor_instr["inpt_sk"][0] == instr["inpt_sk"][0]:
                    y = instr["inpt_sk"][1]
                elif xor_instr["inpt_sk"][0] == instr["inpt_sk"][1]:
                    y = instr["inpt_sk"][0]
                else:
                    return False, []
            elif out_pt == xor_instr["inpt_sk"][0]:
                if xor_instr["inpt_sk"][1] == instr["inpt_sk"][0]:
                    y = instr["inpt_sk"][1]
                elif xor_instr["inpt_sk"][1] == instr["inpt_sk"][1]:
                    y = instr["inpt_sk"][0]
                else:
                    return False, []

            else:
                return False, []

            i = 0
                
            while (i<len(tstack)):
                if tstack[i] == (out_pt2):
                    tstack[i] = y
                i+=1

                    
            for elems in user_def_instrs:
                if out_pt2 in elems["inpt_sk"]:
                    pos = elems["inpt_sk"].index(out_pt2)
                    elems["inpt_sk"][pos] = y
                    
            discount_op+=2
            gas_saved_op+=6

            msg = "XOR(X,XOR(X,Y))"
            rule = msg
            check_and_print_debug_info(debug, msg)
            
            return True, [xor_instr]

        elif len(isz_op) == 1: #ISZ(XOR(X,Y)) = EQ(X,Y)
            isz_instr = isz_op[0]
            out_pt = instr["outpt_sk"][0]

            comm_inpt = [instr["inpt_sk"][1], instr["inpt_sk"][0]]
            new_exist = list(filter(lambda x: (x["inpt_sk"] == instr["inpt_sk"] or x["inpt_sk"] == comm_inpt) and x["disasm"] == "EQ", user_def_instrs))

            if len(new_exist) >0:
                old_var = isz_instr["outpt_sk"]
                new_var = new_exist[0]["outpt_sk"]
                update_tstack_userdef(old_var[0], new_var[0],tstack, user_def_instrs)
                delete = [isz_instr]

                # discount_op+=1
                # gas_saved_op+=3

                
            elif out_pt not in tstack and len(list(filter(lambda x: out_pt in x["inpt_sk"] and x!= isz_instr, user_def_instrs))) == 0:
                idx = user_def_counter.get("EQ",0)
                isz_instr["inpt_sk"] = instr["inpt_sk"]
                isz_instr["id"] = "EQ_"+str(idx)
                isz_instr["opcode"] = "14"
                isz_instr["disasm"] = "EQ"
                isz_instr["commutative"] = True
                user_def_counter["EQ"]=idx+1
                delete = []
                
                discount_op+=1
                gas_saved_op+=3
                
            else:
                return False, []
            # idx = user_def_counter.get("EQ",0)            
            # instr["outpt_sk"] = isz_instr["outpt_sk"]
            # instr["id"] = "EQ_"+str(idx)
            # instr["opcode"] = "14"
            # instr["disasm"] = "EQ"
            # instr["commutative"] = True            


            # user_def_counter["EQ"]=idx+1

            msg = "ISZ(XOR(X,Y))"
            rule = msg
            check_and_print_debug_info(debug, msg)
            
            return True, delete
                
        else:
            return False,[]

        
    elif opcode == "NOT":
        out_pt = instr["outpt_sk"][0]
        not_op = list(filter(lambda x: out_pt in x["inpt_sk"] and x["disasm"] == "NOT", user_def_instrs))
        and_op = list(filter(lambda x: out_pt in x["inpt_sk"] and x["disasm"] == "AND", user_def_instrs))
        or_op = list(filter(lambda x: out_pt in x["inpt_sk"] and x["disasm"] == "NOT", user_def_instrs))

        if len(not_op)==1:
            not_instr = not_op[0]
            out_pt2 = not_instr["outpt_sk"][0]
            real_var = instr["inpt_sk"]

            i = 0
            while (i<len(tstack)):
                if tstack[i] == (out_pt2):
                    tstack[i] = real_var
                i += 1

            for elems in user_def_instrs:
                if out_pt2 in elems["inpt_sk"]:
                    pos = elems["inpt_sk"].index(out_pt2)
                    elems["inpt_sk"][pos] = real_var
                    
                discount_op+=2
                gas_saved_op+=6

                msg = "NOT(NOT(X))"
                rule = msg
                check_and_print_debug_info(debug, msg)
                
                return True, [not_instr]
            else:
                return False, []

        elif len(and_op) == 1: #and(x,not(x)) = 0
            and_instr = and_op[0]
            out_pt2 = and_instr["outpt_sk"][0]

            if instr["inpt_sk"][0] in and_instr["inpt_sk"]:
                real_var = 0
                i = 0
                while (i<len(tstack)):
                    if tstack[i] == (out_pt2):
                        tstack[i] = real_var
                    i+=1
                    
                for elems in user_def_instrs:
                    if out_pt2 in elems["inpt_sk"]:
                        pos = elems["inpt_sk"].index(out_pt2)
                        elems["inpt_sk"][pos] = real_var
                    
                discount_op+=2
                gas_saved_op+=6

                msg = "AND(X,NOT(X))"
                rule = msg
                check_and_print_debug_info(debug, msg)
                
                return True, [and_instr]

            else:
                return False, []

        elif len(or_op) == 1: #or(x,not(x)) = 2^256-1
            or_instr = or_op[0]
            out_pt2 = or_instr["outpt_sk"][0]

            if instr["inpt_sk"][0] in or_instr["inpt_sk"]:
                real_var = -1+2**256
                i = 0
                while (i<len(tstack)):
                    if tstack[i] == (out_pt2):
                        tstack[i] = real_var
                    i+=1
                    
                for elems in user_def_instrs:
                    if out_pt2 in elems["inpt_sk"]:
                        pos = elems["inpt_sk"].index(out_pt2)
                        elems["inpt_sk"][pos] = real_var
                    
                discount_op+=2
                gas_saved_op+=6

                msg = "OR(X,NOT(X))"
                rule = msg
                check_and_print_debug_info(debug, msg)
                
                return True, [or_instr]

        else:
            return False,[]


    elif opcode == "ORIGIN" or opcode == "COINBASE" or opcode == "CALLER":
        out_pt = instr["outpt_sk"][0]
        and_op = list(filter(lambda x: out_pt in x["inpt_sk"] and x["disasm"] == "AND", user_def_instrs))
        if len(and_op) == 1:
            and_instr = and_op[0]
            if -1+2**160 in and_instr["inpt_sk"]:

                old_var = instr["outpt_sk"]
                new_var = and_instr["outpt_sk"]
                instr["outpt_sk"] = new_var
                discount_op+=1

                saved_push+=1
                gas_saved_op+=3

                msg = "AND(ORIGIN,2^160-1)"
                rule = msg
                check_and_print_debug_info(debug, msg)

                update_tstack_userdef(old_var[0], new_var[0],tstack, user_def_instrs)
                
                return True,[and_instr]
            else:
                return False, []
        else:
            return False, []


    elif opcode == "SUB":
        out_pt = instr["outpt_sk"][0]
        isz_op = list(filter(lambda x: out_pt in x["inpt_sk"] and x["disasm"] == "ISZERO", user_def_instrs))
        

        if len(isz_op) == 1: #ISZ(SUB(X,Y)) = EQ(X,Y)
            isz_instr = isz_op[0]

            comm_inpt = [instr["inpt_sk"][1],instr["inpt_sk"][0]]
            
            new_exist = list(filter(lambda x: (x["inpt_sk"] == instr["inpt_sk"] or x["inpt_sk"] == comm_inpt) and x["disasm"] == "EQ", user_def_instrs))

            if len(new_exist) >0:
                old_var = isz_instr["outpt_sk"]
                new_var = new_exist[0]["outpt_sk"]
                update_tstack_userdef(old_var[0], new_var[0],tstack, user_def_instrs)
                delete = [isz_instr]

            elif out_pt not in tstack and len(list(filter(lambda x: out_pt in x["inpt_sk"] and x!=isz_instr, user_def_instrs))) == 0:
                idx = user_def_counter.get("EQ",0)
                isz_instr["inpt_sk"] = instr["inpt_sk"]
                isz_instr["id"] = "EQ_"+str(idx)
                isz_instr["opcode"] = "14"
                isz_instr["disasm"] = "EQ"
                isz_instr["commutative"] = True
                user_def_counter["EQ"]=idx+1
                delete = []

                discount_op+=1
                gas_saved_op+=3

            else:
                return False, []
            # old_var = instr["outpt_sk"]
            # new_var = isz_instr["outpt_sk"]
            # instr["outpt_sk"] = new_var
            
            # # instr["outpt_sk"] = isz_instr["outpt_sk"]
            # instr["id"] = "EQ_"+str(idx)
            # instr["opcode"] = "14"
            # instr["disasm"] = "EQ"
            # instr["commutative"] = True            



            msg = "ISZ(SUB(X,Y))"
            rule = msg
            check_and_print_debug_info(debug, msg)

            # update_tstack_userdef(old_var[0], new_var[0],tstack, user_def_instrs)
            
            return True, delete
                
        else:
            return False,[]

    elif opcode == "SHL":
        out_pt = instr["outpt_sk"][0]
        mul_op = list(filter(lambda x: out_pt in x["inpt_sk"] and x["disasm"] == "MUL", user_def_instrs))
        div_op = list(filter(lambda x: out_pt in x["inpt_sk"] and x["disasm"] == "DIV", user_def_instrs))
        and_op = list(filter(lambda x: out_pt in x["inpt_sk"] and x["disasm"] == "AND", user_def_instrs))
        if len(mul_op) == 1 and instr["inpt_sk"][1] == 1:
            mul_instr = mul_op[0]

            if mul_instr["inpt_sk"][1] == out_pt:
                new_input = [instr["inpt_sk"][0],mul_instr["inpt_sk"][0]]
                new_exist = list(filter(lambda x: x["inpt_sk"] == new_input and x["disasm"] == "SHL", user_def_instrs))

                if len(new_exist) > 0:
                    old_var = mul_instr["outpt_sk"]
                    new_var = new_exist[0]["outpr_sk"]
                    update_tstack_userdef(old_var[0], new_var[0],tstack, user_def_instrs)
                    delete = [mul_instr]

                else:
                    mul_instr["inpt_sk"] = new_input
                                        
                    idx = user_def_counter.get("SHL",0)
                    mul_instr["id"] = "SHL_"+str(idx)
                    mul_instr["opcode"] = "1b"
                    mul_instr["disasm"] = "SHL"
                    mul_instr["commutative"] = False            
                    user_def_counter["SHL"]=idx+1
                    delete = []
                    
                # old_var = instr["outpt_sk"]
                # new_var = mul_instr["outpt_sk"]
                # instr["outpt_sk"] = new_var
                # instr["inpt_sk"][1] = mul_instr["inpt_sk"][0]

                discount_op+=1
                gas_saved_op+=5
                saved_push+=1

                msg = "MUL(X,SHL(Y,1)"
                rule = msg
                check_and_print_debug_info(debug, msg)

                # update_tstack_userdef(old_var[0], new_var[0],tstack, user_def_instrs)
                
                return True, delete

            elif mul_instr["inpt_sk"][0] == out_pt:
                new_input = [instr["inpt_sk"][0],mul_instr["inpt_sk"][1]]
                new_exist = list(filter(lambda x: x["inpt_sk"] == new_input and x["disasm"] == "SHL", user_def_instrs))

                if len(new_exist) > 0:
                    old_var = mul_instr["outpt_sk"]
                    new_var = new_exist[0]["outpr_sk"]
                    update_tstack_userdef(old_var[0], new_var[0],tstack, user_def_instrs)
                    delete = [mul_instr]

                else:
                    mul_instr["inpt_sk"] = new_input
                                        
                    idx = user_def_counter.get("SHL",0)
                    mul_instr["id"] = "SHL_"+str(idx)
                    mul_instr["opcode"] = "1b"
                    mul_instr["disasm"] = "SHL"
                    mul_instr["commutative"] = False            
                    user_def_counter["SHL"]=idx+1
                    delete = []

                # instr["outpt_sk"] = mul_instr["outpt_sk"]
                # old_var = instr["outpt_sk"]
                # new_var = mul_instr["outpt_sk"]
                # instr["outpt_sk"] = new_var
                # instr["inpt_sk"][1] = mul_instr["inpt_sk"][1]

                discount_op+=1
                gas_saved_op+=5
                saved_push+=1

                msg = "MUL(SHL(X,1),Y)"
                rule = msg
                check_and_print_debug_info(debug, msg)

                # update_tstack_userdef(old_var[0], new_var[0],tstack, user_def_instrs)
                
                return True, delete

            else:
                return False, []

        elif len(div_op) == 1 and instr["inpt_sk"][1] == 1:
            div_instr = div_op[0]

            if div_instr["inpt_sk"][1] == out_pt:
                new_input = [instr["inpt_sk"][0], div_instr["inpt_sk"][0]]
                new_exist = list(filter(lambda x: x["inpt_sk"] == new_input and x["disasm"] == "SHR", user_def_instrs))

                if len(new_exist) > 0:
                    old_var = div_instr["outpt_sk"]
                    new_var = new_exist[0]["outpt_sk"]
                    update_tstack_userdef(old_var[0], new_var[0],tstack, user_def_instrs)
                    delete = [div_instr]
                else:
                    div_instr["inpt_sk"] = new_input
                    
                    idx = user_def_counter.get("SHR",0)
                    div_instr["id"] = "SHR_"+str(idx)
                    div_instr["opcode"] = "1c"
                    div_instr["disasm"] = "SHR"
                    div_instr["commutative"] = False            
                    user_def_counter["SHR"]=idx+1
                    delete = []
                    
                # old_var = instr["outpt_sk"]
                # new_var = div_instr["outpt_sk"]
                # instr["outpt_sk"] = new_var
                # # instr["outpt_sk"] = div_instr["outpt_sk"]
                # instr["inpt_sk"][1] = div_instr["inpt_sk"][0]

                # idx = user_def_counter.get("SHR",0)
            
                # instr["id"] = "SHR_"+str(idx)
                # instr["opcode"] = "1c"
                # instr["disasm"] = "SHR"
                # instr["commutative"] = False            
                
                
                discount_op+=1
                gas_saved_op+=5
                saved_push+=1

                # user_def_counter["SHR"]=idx+1
                msg = "DIV(X,SHL(Y,1))"
                rule = msg
                check_and_print_debug_info(debug, msg)

                # update_tstack_userdef(old_var[0], new_var[0],tstack, user_def_instrs)
                
                return True, delete
            return False, []

        elif len(and_op) > 0: #AND(SHL(X,Y), SHL(X,Z)) => SHL(X,AND(Y,Z))

            found = False
            i = 0
            while i < len(and_op) and not found:
                
                and_ins = and_op[i]
                if out_pt == and_ins["inpt_sk"][0]:
                    out_pt1 = and_ins["inpt_sk"][1]
                else:
                    out_pt1 = and_ins["inpt_sk"][0]

                new_ins = list(filter(lambda x: out_pt1 in x["outpt_sk"] and x["disasm"] == "SHL" and x["inpt_sk"][0] == instr["inpt_sk"][0],user_def_instrs))
                if len(new_ins) == 1:
                    shl1 = new_ins[0]
                    found = True

                i+=1

            #if the shl instructions are not used by any other operation or do not appear in the target stack, then I can simplify them
            if found and out_pt not in tstack and out_pt1 not in tstack and len(list(filter(lambda x: out_pt in x["inpt_sk"] and x!= and_ins, user_def_instrs))) == 0 and len(list(filter(lambda x: out_pt1 in x["inpt_sk"] and x!= and_ins, user_def_instrs))) == 0:

                inpt1 = instr["inpt_sk"][0]
                inpt2 = instr["inpt_sk"][1]
                inpt3 = shl1["inpt_sk"][1]
                
                new_and_idx = user_def_counter.get("AND",0)

                instr["inpt_sk"] = [inpt2,inpt3]
                instr["id"] = "AND_"+str(new_and_idx)
                instr["opcode"] = "16"
                instr["disasm"] = "AND"
                instr["commutative"] = True
                user_def_counter["AND"]=new_and_idx+1

                new_shl_idx = user_def_counter.get("SHL",0)
                
                and_ins["inpt_sk"] = [inpt1,instr["outpt_sk"][0]]
                and_ins["id"] = "SHL_"+str(new_shl_idx)
                and_ins["opcode"] = "1b"
                and_ins["disasm"] = "SHL"
                and_ins["commutative"] = False
                user_def_counter["SHL"]=new_shl_idx+1

                delete = [shl1]
                
                discount_op+=1
                gas_saved_op+=3

                msg = "AND(SHL(X,Y), SHL(X,Z))"
                rule = msg
                check_and_print_debug_info(debug, msg)

                return True, delete
            else:
                return False, []
        else:
            return False, []

    elif opcode == "ADDRESS":
        out_pt = instr["outpt_sk"][0]
        bal_op = list(filter(lambda x: out_pt in x["inpt_sk"] and x["disasm"] == "BALANCE", user_def_instrs))

        and_op = list(filter(lambda x: out_pt in x["inpt_sk"] and x["disasm"] == "AND", user_def_instrs))

        if len(bal_op) == 1:
            bal_instr = bal_op[0]

            new_exist = list(filter(lambda x: x["disasm"] == "SELFBALANCE", user_def_instrs))

            if len(new_exist) > 0:
                    old_var = bal_instr["outpt_sk"]
                    new_var = new_exist[0]["outpt_sk"]
                    update_tstack_userdef(old_var[0], new_var[0],tstack, user_def_instrs)
                    delete = [bal_instr]
            else:
                bal_instr["inpt_sk"] = []
                    
                idx = user_def_counter.get("SELFBALANCE",0)
                bal_instr["id"] = "SELFBALANCE_"+str(idx)
                bal_instr["opcode"] = "47"
                bal_instr["disasm"] = "SELFBALANCE"
                bal_instr["commutative"] = False            
                user_def_counter["SELFBALANCE"]=idx+1
                delete = []

            
            # old_var = instr["outpt_sk"]
            # new_var = bal_instr["outpt_sk"]
            # instr["outpt_sk"] = new_var
            
            # instr["outpt_sk"] = bal_instr["outpt_sk"]

            # idx = user_def_counter.get("SELFBALANCE",0)
            
            # instr["id"] = "SELFBALANCE_"+str(idx)
            # instr["opcode"] = "47"
            # instr["disasm"] = "SELFBALANCE"
            # instr["commutative"] = False            
                
            discount_op+=1
            gas_saved_op+=397 #BALANCE 400 ADDRESS 2 SELFBALANCE 5

            # user_def_counter["SELFBALANCE"]=idx+1
            msg = "BALANCE(ADDRESS)"
            rule = msg
            check_and_print_debug_info(debug, msg)

            # update_tstack_userdef(old_var[0], new_var[0],tstack, user_def_instrs)
            
            return True, delete
        
        elif len(and_op) == 1:
            and_instr = and_op[0]
            if -1+2**160 in and_instr["inpt_sk"]:
                # instr["outpt_sk"] = and_instr["outpt_sk"]
                old_var = instr["outpt_sk"]
                new_var = and_instr["outpt_sk"]
                instr["outpt_sk"] = new_var

                discount_op+=1

                saved_push+=1
                gas_saved_op+=3

                msg = "AND(ADDRESS,2^160)"
                rule = msg
                check_and_print_debug_info(debug, msg)

                update_tstack_userdef(old_var[0], new_var[0],tstack, user_def_instrs)
                
                return True,[and_instr]
            else:
                return False, []
        else:
            return False, []
        
    elif opcode == "EXP":
        if instr["inpt_sk"][0] == 0:
            instr["inpt_sk"].pop(0)

            new_exist = list(filter(lambda x: x["inpt_sk"] == instr["inpt_sk"] and x["disasm"] == "ISZERO", user_def_instrs))

            if len(new_exist) > 0:
                old_var = instr["outpt_sk"]
                new_var = new_exist[0]["outpt_sk"]
                update_tstack_userdef(old_var[0], new_var[0],tstack, user_def_instrs)
                delete = [instr]
            else:
                idx = user_def_counter.get("ISZERO",0)
            
                instr["id"] = "ISZERO_"+str(idx)
                instr["opcode"] = "15"
                instr["disasm"] = "ISZERO"
                instr["commutative"] = False            
                user_def_counter["ISZERO"]=idx+1
                delete = []
                
            saved_push+=1
            gas_saved_op+=57


            msg = "EXP(0,X)"
            rule = msg
            check_and_print_debug_info(debug, msg)
            
            return True, delete

        elif instr["inpt_sk"][0] == 2:
            instr["inpt_sk"].pop(0)

            new_input = [instr["inpt_sk"][0],1]
            new_exist = list(filter(lambda x: x["inpt_sk"] == new_input and x["disasm"] == "SHL", user_def_instrs))

            if len(new_exist) > 0:
                old_var = instr["outpt_sk"]
                new_var = new_exist[0]["outpt_sk"]
                update_tstack_userdef(old_var[0], new_var[0],tstack, user_def_instrs)
                delete = [instr]
            else:
                idx = user_def_counter.get("SHL",0)
                instr["inpt_sk"] = new_input
                instr["id"] = "SHL_"+str(idx)
                instr["opcode"] = "1b"
                instr["disasm"] = "SHL"
                instr["commutative"] = False            
                user_def_counter["SHL"]=idx+1
                delete = []
            
            
            
            # instr["inpt_sk"].append(1)
            # idx = user_def_counter.get("SHL",0)
            
            # instr["id"] = "SHL_"+str(idx)
            # instr["opcode"] = "1b"
            # instr["disasm"] = "SHL"
            # instr["commutative"] = False            
                
            gas_saved_op+=57 #EXP-SHL

            # user_def_counter["SHL"]=idx+1
            msg = "EXP(2,X)"
            rule = msg
            check_and_print_debug_info(debug, msg)

            return True, delete

        else:
            return False, []

    else:
        return False, []


    
def apply_all_comparison(user_def_instrs,tstack):
    global rule_applied

    modified = True
    while(modified):
        msg = "********************IT*********************"
        check_and_print_debug_info(debug, msg)
        modified = apply_comparation_rules(user_def_instrs,tstack)
        if modified:
            rule_applied = True
        
def apply_comparation_rules(user_def_instrs,tstack):
    global rules_applied
    global rule
    
    modified = False

    for instr in user_def_instrs:
        
        r, d_instr = apply_cond_transformation(instr,user_def_instrs,tstack)

        if r:
            
            rules_applied.append(rule)
            rule = ""
            msg = "[RULE]: Simplification rule type 2: "+str(instr)
            msg = msg+"\n[RULE]: Delete rules: "+str(d_instr)
            check_and_print_debug_info(debug, msg)

            modified = True
            for b in d_instr:
                idx = user_def_instrs.index(b)
                user_def_instrs.pop(idx)
    return modified

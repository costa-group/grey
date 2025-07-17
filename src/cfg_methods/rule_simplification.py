"""
Methods for applying simplification rules
"""

from typing import Dict, List, Tuple, Set, Union
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


def update_vars(block: CFGBlock, block_list: CFGBlockList, vars_to_update: Dict[str,str]) -> None:
    liveness = block.get_liveness()

    out_args = liveness.get("out",[])

    potential_replace = set(vars_to_update.keys()).intersection(set(out_args))

    if len(potential_replace)!= 0:
        succ = block.get_successors()
        for next_block_id in succ:
            next_block = block_list.get_block(next_block_id)
            next_block_ins = next_block.get_instructions()
            for old_var, new_var in vars_to_update.items():
                update_instructions_block(next_block_ins, old_var, new_var)

            updat_vars(next_block, block_list, vars_to_update)
            
def apply_rule_simplification_block_list(block_list: CFGBlockList) -> None:


    assigment_dict = block_list.get_assigment_dict()
    
    for _bl_id, bl in block_list.blocks.items():

        vars_to_update = {}

        apply_transformation_rule_simplification_block(bl, assigment_dict, vars_to_update)
        
        update_vars(bl, block_list, vars_to_update)

        vars_to_update = {}
        
        apply_semantics_rule_simplification_block(bl, assigment_dict, vars_to_update)

        update_vars(bl, block_list, vars_to_update)

        
def apply_transformation_rule_simplification_block(block: CFGBlock, assigments_dict: Dict[str,str], vars_to_update: Dict[str,str]) -> bool:
    
    modified = True
    
    while(modified):

        modified = apply_transform_rules(block, assigments_dict, vars_to_update)
        
    return modified


def apply_semantics_rule_simplification_block(block: CFGBlock, assigments_dict: Dict[str,str], vars_to_update: Dict[str,str]) -> bool:

    modified = True    
    while(modified):

        modified = apply_semantics_rules(block, assigments_dict, vars_to_update)
        
    return modified


def apply_transform_rules(block: CFGBlock, assigments_dict: Dict[str,str], vars_to_update: Dict[str,str]) -> bool:
    
    to_delete = []
    rules_applied = []
    modified = False
    instructions = block.get_instructions()

    index = -1
    for instr in instructions:
        
        index+=1
        if instr.get_op_name() in ["and","or","xor","add","sub","mul","div","exp","eq","gt","lt","sgt","slt","sdiv","not","iszero","shl","shr"]:
            r = apply_transform(instr, assigments_dict, rules_applied)

            if r!=-1:

                assert(len(instr.get_out_args())== 1, "ERROR. OP's involved in rule simplification must have only one returned value")
                old_out_var = instr.get_out_args()[0]

                update_instructions_block(instructions[idx+1:],old_out_var,r)
                
                vars_to_update[old_out_var] = r
                
                modified = True


    return modified


def update_instructions_block(instructions, old_var, new_var):

    for ins in instructions:
        if(old_var in ins.get_in_args()):
            new_input = [new_var if x == old_var else x for x in ins.get_in_args()]

            ins.set_in_args(new_input)


def get_input_assigment(inp:str, assigments_dict: Dict[str,str]) ->  Union[str,int]:
    '''
    It checks if the value assgined to a input argument of a CFGInstruction if an integer.
    In case that it is not an integer, it checks if it is the result of an assigment.
    '''

    try:
        inp_ret = int(inp,16)
    except:        
        assigment = assigments_dict.get(inp,-1)
        if assigment !=-1:
            inp_ret = int(assigment,16)
        else:
            inp_ret = inp

    return inp

def get_input_values(inp_vars: List[str], assigments_dict: Dict[str,str])-> List[Union[str,int]]:
    inp_res = []
    for inp in inp_vars:
        ret_inp = get_input_assigment(inp, assigments_dict)
        inp_res.append(ret_inp)

    return inp_res

        
def apply_transform(instr: CFGInstruction, assigments_dict: Dict[str,str], rules_applied: List[str]) -> bool:
    int_not0 = [-1+2**256]
    
    opcode = instr.get_op_name()
    inp_initial_vars = instr.get_in_args()

    inp_vars = get_input_values(inp_initial_vars, assigments_dict)
    
    if opcode == "and":
        if 0 in inp_vars:
            rule = "AND(X,0)"
            rules_applied.append(rule)
            return "0x00"

        elif inp_vars[0] == inp_vars[1]:
            
            rule = "AND(X,X)"
            rules_applied.append(rule)
            return inp_vars[0]
    
        elif inp_vars[0] in int_not0 or inp_vars[1] in int_not0:
            
            rule = "AND(X,2^256-1)"
            rules_applied.append(rule)
            return inp_vars[1] if (inp_vars[0] in int_not0) else inp_vars[0]

        else:
            return -1
        
    elif opcode == "or":
        if 0 in inp_vars:
            
            rule = "OR(X,0)"
            rules_applied.append(rule)
            return inp_vars[1] if inp_vars[0] == 0 else inp_vars[0]

        elif inp_vars[0] == inp_vars[1]:
            rule = "OR(X,X)"
            rules_applied.append(rule)
            return inp_vars[0]

        else:
            return -1

    elif opcode == "xor":
        
        if inp_vars[0] == inp_vars[1]:
            rule = "XOR(X,X)"
            rules_applied.append(rule)
            return "0x00"

        elif 0 in inp_vars:
            rule = "XOR(X,0)"
            rules_applied.append(rule)
            return inp_vars[1] if inp_vars[0] == 0 else inp_vars[0]

        else:
            return -1

    elif opcode == "exp":
        
        if inp_vars[1] == 0:
            rule = "EXP(X,0)"
            rules_applied.append(rule)
            return "0x01"

        elif inp_vars[1] == 1:
            rule = "EXP(X,1)"
            rules_applied.append(rule)
            return inp_vars[0]

        elif inp_vars[0] == 1:
            rule = "EXP(1,X)"
            rules_applied.append(rule)
            return "0x01"

        else:
            return -1

    elif opcode == "add":
        if 0 in inp_vars:
            rule = "ADD(X,0)"
            rules_applied.append(rule)
            return inp_vars[1] if inp_vars[0] == 0 else inp_vars[0]

        else:
            return -1

    elif opcode == "sub":
        if 0 == inp_vars[1]:
            rule = "SUB(X,0)"
            rules_applied.append(rule)
            return inp_vars[0]

        elif inp_vars[0] == inp_vars[1]:
            rule = "SUB(X,X)"
            return "0x00"

        else:
            return -1
        
    elif opcode == "mul":
        if 0 in inp_vars:
            rule = "MUL(X,0)"
            rules_applied.append(rule)
            return "0x00"

        elif 1 in inp_vars:
            rule = "MUL(X,1)"
            rules_applied.append(rule)
            return inp_vars[1] if inp_vars[0] == 1 else inp_vars[0]

        else:
            return -1

    elif opcode == "div" or opcode == "sdiv":
        if 1 == inp_vars[1]:
            rule = f"{opcode}(X,1)"
            rules_applied.append(rule)
            return inp_vars[0]

        elif 0 in inp_vars:
            rule = f"{opcode}(X,0)"
            rules_applied.append(rule)
            return "0x00"

        elif inp_vars[0] == inp_vars[1]:
            rule = f"{opcode}(X,X)"
            rules_applied.append(rule)
            return "0x01"

        else:
            return -1

    elif opcode == "mod":
        if  1 == inp_vars[1]:
            rule = "MOD(X,1)"
            rules_applied.append(rule)
            return "0x00"

        elif inp_vars[0] == inp_vars[1]:
            rule = "MOD(X,X)"
            rules_applied.append(rule)
            return "0x00"

        elif inp_vars[1] == 0:
            rule = "MOD(X,0)"
            rules_applied.append(rule)
            return "0x00"

        else:
            return -1

    elif opcode == "eq":
        if inp_vars[0] == inp_vars[1]:

            rule = "EQ(X,X)"
            rules_applied.append(rule)
            return "0x01"

        else:
            return -1

    elif opcode == "gt" or opcode == "sgt":
        if inp_vars[0] == 0 and opcode == "GT":

            rule = f"{opcode}(0,X)"
            rules_applied.append(rule)
            return "0x00"

        elif inp_vars[0] == inp_vars[1]:

            rule = f"{opcode}(X,X)"
            rules_applied.append(rule)
            return "0x00"

        else:
            return -1

    elif opcode == "lt" or opcode == "slt":
        if inp_vars[1] == 0 and opcode == "LT":

            rule = "LT(X,0)"
            rules_applied.append(rule)
            return "0x00"

        elif inp_vars[0] == inp_vars[1]:

            rule = f"{opcode}(X,X)"
            rules_applied.append(rule)
            return "0x00"
        
        else:
            return -1

    elif opcode == "not":
        r, val = all_integers(inp_vars)
        if r:
            val_end = ~(int(val[0]))+2**256

            if size_flag:
                v0 = int(val[0])
                bytes_v0 = get_num_bytes_int(v0)
                bytes_sol = get_num_bytes_int(val_end)

                if bytes_sol <= bytes_v0+1:    
                    rule = "NOT(X)"
                    rules_applied.append(rule)
                    return hex(val_end)

                else:
                    return -1

            else:
                rule = "NOT(X)"
                rules_applied.append(rule)
                return hex(val_end)
            
        else:
            return -1
        
    elif opcode == "iszero":
        if inp_vars[0] == 0:
            rule = "ISZ(0)"
            rules_applied.append(rule)
            return "0x01"

        elif inp_vars[0] == 1:
            rule = "ISZ(1)"
            rules_applied.append(rule)
            return "0x00"

        else:
            return -1

    elif opcode == "shr" or opcode == "shl":
        if inp_vars[0] == 0:
            rule = opcode+"(0,X)"
            rules_applied.append(rule)
            return inp_vars[0]
        
        elif inp_vars[1] == 0:
            rule = opcode+"(X,0)"
            rules_applied.append(rule)
            return inp_vars[0]
        
        else:
            return -1
    



def apply_semantics_rules(block: CFGBlock, assigments_dict: Dict[str,str], vars_to_update: Dict[str,str]) -> bool:
        
    to_delete = []
    rules_applied = []
    modified = False
    instructions = block.get_instructions()

    liveness = block.get_liveness()
    out_args = liveness.get("out",[])

    
    index = -1
    for instr in list(instructions):
        index+=1
        r, d_instr = apply_semantics_transformation(instr, instructions, assigments_dict, vars_to_update, out_args, rules_applied)

        if r:
            modified = True
            for b in d_instr:
                idx = user_def_instrs.index(b)
                user_def_instrs.pop(idx)
    return modified
    


        
def apply_semantics_transformation(instr: CFGInstruction, instructions: List[CFGInstruction], assigments_dict: Dict[str,str], vars_to_update: Dict[str,str], out_vars: List[str], rules: List[str]):
    
    opcode = instr.get_op_name()
    init_instr_input = instr.get_in_args()
    inp_vars = get_input_values(init_instr_input, assigments_dict)
    
    if opcode == "gt" or opcode == "sgt":
        if 0 == inp_vars[1] and opcode == "gt":
            out_var = instr.get_out_args()[0]
            is_zero = list(filter(lambda x: out_var in x.get_in_args() and x.get_op_name() == "iszero",instructions))
            
            if len(is_zero) == 1 and out_var not in out_vars:
                index = instructions.index(is_zero[0])
                zero_instr = instructions[index]
                zero_instr.set_in_args([instr.get_in_args()[0]])

                msg = "ISZ(GT(X,0))"
                rules.append(msg)
                
                return True, [instr]
            else:
                return False, []

        elif 0 == inp_vars[0] and opcode == "gt":
            instr.set_op_name("iszero")
            instr.set_in_agrs([instr.get_in_args()[1]])
            
            msg = "GT(1,X)"
            rules.append(msg)
            
            return True, []

        else:
            out_var = instr.get_out_args()[0]
            is_zero = list(filter(lambda x: out_var in x.get_in_args() and x.get_op_name() == "iszero",instructions))
            if len(is_zero)==1:
                zero = is_zero[0]
                zero2 = list(filter(lambda x: zero.get_out_args()[0] in x.get_in_args() and x.get_op_name() == "iszero",instructions))
                if len(zero2) == 1 and zero.get_out_args()[0] not in out_vars:
                    old_var = instr.get_out_args()
                    new_var = zero2[0].get_out_args()
                    instr.set_out_args(new_var)
                    
                    msg = "ISZ(ISZ("+opcode+"(X,Y)))" #It may be GT or SGT
                    rules.append(msg)
                    

                    vars_to_update[old_var[0]] = new_var[0]

                    #update_tstack_userdef(old_var[0], new_var[0],tstack, instructions)
                    return True, [zero,zero2[0]]
                else:
                    return False, []
            else:
                
                return False, []

    elif opcode == "ISZERO":
    
        out_var = instr.get_out_args()[0]
        is_zero = list(filter(lambda x: out_var in x.get_in_args() and x.get_op_name() == "ISZERO",instructions))

        is_eq = list(filter(lambda x: out_var in x.get_in_args() and x.get_op_name() == "EQ",instructions))
        
        if len(is_zero)==1:
         
            zero = is_zero[0]
  
            zero2 = list(filter(lambda x: zero.get_out_args()[0] in x.get_in_args() and x.get_op_name() == "ISZERO",instructions))
            if len(zero2) == 1 and zero.get_out_args()[0] not in out_vars:
             
                # instr.get_out_args() = zero2[0].get_out_args()
                old_var = instr.get_out_args()
                new_var = zero2[0].get_out_args()
                instr.set_out_args(new_var)

                msg = "ISZ(ISZ(ISZ(X)))"
                rules.append(msg)

                vars_to_update[old_var[0]] = new_var[0]
                #update_tstack_userdef(old_var[0], new_var[0],tstack, instructions)
                
                return True, [zero,zero2[0]]
            else:
                return False, []

        elif len(is_eq) == 1:
            eq = is_eq[0]

            if 1 in eq.get_in_args():
                old_var = instr.get_out_args()
                new_var = eq.get_out_args()
                # instr.get_out_args() = eq.get_out_args()
                instr.set_out_args(new_var)

                msg = "EQ(1,ISZ(X))"
                rules.append(msg)
                
                vars_to_update[old_var[0]] = new_var[0]
                #update_tstack_userdef(old_var[0], new_var[0],tstack, instructions)
                
                return True, [eq]

            else:
                return False, []
        else:
                
            return False, []
            
    elif opcode == "lt" or opcode == "slt":
         if 0 == inp_vars[0] and opcode == "lt":
            out_var = instr.get_out_args()[0]
            is_zero = list(filter(lambda x: out_var in x.get_in_args() and x.get_op_name() == "iszero",instructions))
            if len(is_zero) == 1 and out_var not in out_vars:
                index = instructions.index(is_zero[0])
                zero_instr = instructions[index]
                zero_instr.set_in_args([instr.get_in_args()[1]])

                msg = "ISZ(LT(0,X))"
                rules.append(msg)
                
                
                return True, []
            else:
                return False, []

         elif 1 == inp_vars[1] and opcode == "lt":
            var = instr.get_in_args()[0]

            new_exist = list(filter(lambda x: var in x.get_in_args() and x.get_op_name() == "iszero", instructions))
                        
            if len(new_exist)>0:
                old_var = instr.get_out_args()
                new_var = new_exist[0].get_out_args()

                vars_to_update[old_var[0]] = new_var[0]
                #update_tstack_userdef(old_var[0], new_var[0],tstack, instructions)
                delete = [instr]
            else:

                instr.set_op_name("iszero")
                instr.set_in_args([var])

                delete = []
                
            msg = "LT(X,1)"
            rules.append(msg)
            
            return True, delete
        
         else:
            out_var = instr.get_out_args()[0]
            is_zero = list(filter(lambda x: out_var in x.get_in_args() and x.get_op_name() == "iszero",instructions))
            if len(is_zero)==1:
                zero = is_zero[0]
                zero2 = list(filter(lambda x: zero.get_out_args()[0] in x.get_in_args() and x.get_op_name() == "iszero",instructions))
                if len(zero2) == 1 and zero.get_out_args()[0] not in out_vars:
                    old_var = instr.get_out_args()
                    new_var = zero2[0].get_out_args()
                    instr.set_out_args(new_var)

                    msg = "ISZ(ISZ("+opcode+"(X,Y)))" # It may be LT or SLT
                    rules.append(msg)
                    
                    vars_to_update[old_var[0]] = new_var[0]
                    #update_tstack_userdef(old_var[0], new_var[0],tstack, instructions)
                    return True, [zero,zero2[0]]
                else:
                    return False, []
            else:
                
                return False, []
            
    elif opcode == "eq":
        if 0 in inp_vars:
            var0 = instr.get_in_args()[0]
            var1 = instr.get_in_args()[1]

            nonz = var1 if inp_vars[0] == 0 else var0

            new_exist = list(filter(lambda x: nonz in x.get_in_args() and x.get_op_name() == "iszero", instructions))

            if len(new_exist) >0:
                old_var = instr.get_out_args()
                new_var = new_exist[0].get_out_args()
                vars_to_update[old_var[0]] = new_var[0]
                #update_tstack_userdef(old_var[0], new_var[0],tstack, instructions)
                delete = [instr]

            else:
                instr.set_op_name("iszero")
                instr.set_in_args([nonz])
                delete = []

            msg = "EQ(0,X)"
            rules.append(msg)

            # user_def_counter["ISZERO"]=idx+1
            
            return True, delete

        else:

            out_var = instr.get_out_args()[0]
            is_zero = list(filter(lambda x: out_var in x.get_in_args() and x.get_op_name() == "iszero",instructions))
            if len(is_zero)==1:
                zero = is_zero[0]
                zero2 = list(filter(lambda x: zero.get_out_args()[0] in x.get_in_args() and x.get_op_name() == "iszero",instructions))
                if len(zero2) == 1 and zero.get_out_args()[0] not in out_vars:

                    old_var = instr.get_out_args()
                    new_var = zero2[0].get_out_args()
                    instr.set_out_args(new_var)

                    msg = "ISZ(ISZ(EQ(X,Y)))"
                    rules.append(msg)
                    
                    vars_to_update[old_var[0]] = new_var[0]
                    #update_tstack_userdef(old_var[0], new_var[0],tstack, instructions)
                
                    return True, [zero,zero2[0]]
                else:
                    return False, []
            else:
                
                return False, []
            
    
    elif opcode == "and":
        out_pt = instr.get_out_args()[0]
        and_op = list(filter(lambda x: out_pt in x.get_in_args() and x.get_op_name() == "and", instructions))
        or_op = list(filter(lambda x: out_pt in x.get_in_args() and x.get_op_name() == "or", instructions))
        
        if len(and_op)==1:
            and_instr = and_op[0]
            if (and_instr.get_in_args()[1] in instr.get_in_args()) or (and_instr.get_in_args()[0] in instr.get_in_args()):
                
                old_var = instr.get_out_args()
                new_var = and_instr.get_out_args()
                instr.set_out_args(new_var)

                msg = "AND(X,AND(X,Y))"
                rules.append(msg)
                
                vars_to_update[old_var[0]] = new_var[0]
                #update_tstack_userdef(old_var[0], new_var[0],tstack, instructions)
                
                return True, [and_instr]
            else:
                return False, []

        elif len(or_op) == 1:
            or_instr = or_op[0]
            out_pt2 = or_instr.get_out_args()[0]
            if out_pt == or_instr.get_in_args()[1]: #(or(x,and(x,y)) = x, or(x,and(y,x)) = x, or(and(x,y),x) = x, or(and(y,x),x) = x
    
                if or_instr.get_in_args()[0] == instr.get_in_args()[0]:
                    x = instr.get_in_args()[0]
                elif or_instr.get_in_args()[0] == instr.get_in_args()[1]:
                    x = instr.get_in_args()[1]
                else:
                    return False, []
            elif out_pt == or_instr.get_in_args()[0]:
                if or_instr.get_in_args()[1] == instr.get_in_args()[0]:
                    x = instr.get_in_args()[0]
                elif or_instr.get_in_args()[1] == instr.get_in_args()[1]:
                    x = instr.get_in_args()[1]
                else:
                    return False, []

            else:
                return False, []


            vars_to_update[out_pt2] = x
            # i = 0
                
            # while (i<len(tstack)):
            #     if tstack[i] == (out_pt2):
            #         tstack[i] = x
            #     i+=1
                
            # for elems in instructions:
            #     if out_pt2 in elems.get_in_args():
            #         pos = elems.get_in_args().index(out_pt2)
            #         elems.get_in_args()[pos] = x
                    

            msg = "OR(X,AND(X,Y))"
            rules.append(msg)
            
            
            return True, [or_instr]
            

        else:
            return False,[]
        
    elif opcode == "or":
        out_pt = instr.get_out_args()[0]
        or_op = list(filter(lambda x: out_pt in x.get_in_args() and x.get_op_name() == "or", instructions))
        and_op = list(filter(lambda x: out_pt in x.get_in_args() and x.get_op_name() == "and", instructions))
        if len(or_op) == 1:
            or_instr = or_op[0]
            if (or_instr.get_in_args()[1] in instr.get_in_args()) or (or_instr.get_in_args()[0] in instr.get_in_args()):

                vars_to_update[instr.get_out_agrs()[0]] = or_instr.get_out_args()[0]
                instr.set_out_args(or_instr.get_out_args())
           
                msg = "OR(OR(X,Y),Y)"
                rules.append(msg)
                
                
                return True, [or_instr]
            else:
                return False, []

        elif len(and_op) == 1: 
            and_instr = and_op[0]
            out_pt2 = and_instr.get_out_args()[0]
            if out_pt == and_instr.get_in_args()[1]: #(and(x,or(x,y)) = x, and(x,or(y,x)) = x, and(or(x,y),x) = x, and(or(y,x),x) = x
    
                if and_instr.get_in_args()[0] == instr.get_in_args()[0]:
                    x = instr.get_in_args()[0]
                elif and_instr.get_in_args()[0] == instr.get_in_args()[1]:
                    x = instr.get_in_args()[1]
                else:
                    return False, []
            elif out_pt == and_instr.get_in_args()[0]:
                if and_instr.get_in_args()[1] == instr.get_in_args()[0]:
                    x = instr.get_in_args()[0]
                elif and_instr.get_in_args()[1] == instr.get_in_args()[1]:
                    x = instr.get_in_args()[1]
                else:
                    return False, []

            else:
                return False, []

            vars_to_update[out_pt2] = x
            
            # i = 0
            
            # while (i<len(tstack)):
            #     if tstack[i] == (out_pt2):
            #         tstack[i] = x
            #     i+=1
                    
            # for elems in instructions:
            #     if out_pt2 in elems.get_in_args():
            #         pos = elems.get_in_args().index(out_pt2)
            #         elems["inpt_sk"][pos] = x
                    
            msg = "AND(X,OR(X,Y))"
            rules.append(msg)
            
            return True, [and_instr]
            
        else:
            return False,[]


    elif opcode == "xor":
        out_pt = instr.get_out_args()[0]
        xor_op = list(filter(lambda x: out_pt in x.get_in_args() and x.get_op_name() == "xor", instructions))
        isz_op = list(filter(lambda x: out_pt in x.get_in_args() and x.get_op_name() == "iszero", instructions))
        
        if len(xor_op)==1:
            xor_instr = xor_op[0]
            out_pt2 = xor_instr.get_out_args()[0]
            if out_pt == xor_instr.get_in_args()[1]: #xor(x,xor(x,y)) = y, xor(x,xor(y,x)) = y, xor(xor(x,y),x) = y, xor(xor(y,x),x) = y
    
                if xor_instr.get_in_args()[0] == instr.get_in_args()[0]:
                    y = instr.get_in_args()[1]
                elif xor_instr.get_in_args()[0] == instr.get_in_args()[1]:
                    y = instr.get_in_args()[0]
                else:
                    return False, []
            elif out_pt == xor_instr.get_in_args()[0]:
                if xor_instr.get_in_args()[1] == instr.get_in_args()[0]:
                    y = instr.get_in_args()[1]
                elif xor_instr.get_in_args()[1] == instr.get_in_args()[1]:
                    y = instr.get_in_args()[0]
                else:
                    return False, []

            else:
                return False, []


            vars_to_update[out_pt2] = y

            # i = 0    
            # while (i<len(tstack)):
            #     if tstack[i] == (out_pt2):
            #         tstack[i] = y
            #     i+=1

                    
            # for elems in instructions:
            #     if out_pt2 in elems.get_in_args():
            #         pos = elems.get_in_args().index(out_pt2)
            #         elems["inpt_sk"][pos] = y
                    
            msg = "XOR(X,XOR(X,Y))"
            rules.append(msg)
            
            return True, [xor_instr]

        elif len(isz_op) == 1: #ISZ(XOR(X,Y)) = EQ(X,Y)
            isz_instr = isz_op[0]
            out_pt = instr.get_out_args()[0]

            comm_inpt = [instr.get_in_args()[1], instr.get_in_args()[0]]
            new_exist = list(filter(lambda x: (x.get_in_args() == instr.get_in_args() or x.get_in_args() == comm_inpt) and x.get_op_name() == "eq", instructions))

            if len(new_exist) >0:
                old_var = isz_instr.get_out_args()
                new_var = new_exist[0].get_out_args()
                vars_to_update[old_var[0]] = new_var[0]
                # update_tstack_userdef(old_var[0], new_var[0],tstack, instructions)
                delete = [isz_instr]
                
            elif out_pt not in out_vars and len(list(filter(lambda x: out_pt in x.get_in_args() and x!= isz_instr, instructions))) == 0:

                isz_instr.set_op_name("eq")
                isz_instr.set_in_args(instr.get_in_args())
                # idx = user_def_counter.get("EQ",0)
                # isz_instr["inpt_sk"] = instr.get_in_args()
                # isz_instr["id"] = "EQ_"+str(idx)
                # isz_instr["opcode"] = "14"
                # isz_instr["disasm"] = "EQ"
                # isz_instr["commutative"] = True
                # user_def_counter["EQ"]=idx+1
                delete = []
                                
            else:
                return False, []

            msg = "ISZ(XOR(X,Y))"
            rules.append(msg)
            
            return True, delete
                
        else:
            return False,[]

        
    elif opcode == "not":
        out_pt = instr.get_out_args()[0]
        not_op = list(filter(lambda x: out_pt in x.get_in_args() and x.get_op_name() == "not", instructions))
        and_op = list(filter(lambda x: out_pt in x.get_in_args() and x.get_op_name() == "and", instructions))
        or_op = list(filter(lambda x: out_pt in x.get_in_args() and x.get_op_name() == "not", instructions))

        if len(not_op)==1:
            not_instr = not_op[0]
            out_pt2 = not_instr.get_out_args()[0]
            real_var = instr.get_in_args()

            vars_to_update[out_pt2] = real_var[0]
            
            # i = 0
            # while (i<len(tstack)):
            #     if tstack[i] == (out_pt2):
            #         tstack[i] = real_var
            #     i += 1

            # for elems in instructions:
            #     if out_pt2 in elems.get_in_args():
            #         pos = elems.get_in_args().index(out_pt2)
            #         elems["inpt_sk"][pos] = real_var
                    
                msg = "NOT(NOT(X))"
                rules.append(msg)
                
                return True, [not_instr]
            else:
                return False, []

        elif len(and_op) == 1: #and(x,not(x)) = 0
            and_instr = and_op[0]
s            out_pt2 = and_instr.get_out_args()[0]

            if instr.get_in_args()[0] in and_instr.get_in_args():
                real_var = "0x00"

                vars_to_update[out_pt2] = real_var

                # i = 0
                # while (i<len(tstack)):
                #     if tstack[i] == (out_pt2):
                #         tstack[i] = real_var
                #     i+=1
                    
                # for elems in instructions:
                #     if out_pt2 in elems.get_in_args():
                #         pos = elems.get_in_args().index(out_pt2)
                #         elems["inpt_sk"][pos] = real_var
                    
                msg = "AND(X,NOT(X))"
                rules.append(msg)
                
                return True, [and_instr]

            else:
                return False, []

        elif len(or_op) == 1: #or(x,not(x)) = 2^256-1
            or_instr = or_op[0]
            out_pt2 = or_instr.get_out_args()[0]

            if instr.get_in_args()[0] in or_instr.get_in_args():
                real_var = hex(-1+2**256)

                vars_to_update(out_pt2, real_var)

                # i = 0
                # while (i<len(tstack)):
                #     if tstack[i] == (out_pt2):
                #         tstack[i] = real_var
                #     i+=1
                    
                # for elems in instructions:
                #     if out_pt2 in elems.get_in_args():
                #         pos = elems.get_in_args().index(out_pt2)
                #         elems["inpt_sk"][pos] = real_var
                    

                msg = "OR(X,NOT(X))"
                rules.append(msg)
                
                return True, [or_instr]

        else:
            return False,[]


    elif opcode == "origin" or opcode == "coinbase" or opcode == "caller":
        out_pt = instr.get_out_args()[0]
        and_op = list(filter(lambda x: out_pt in x.get_in_args() and x.get_op_name() == "and", instructions))
        if len(and_op) == 1:
            and_instr = and_op[0]
            if -1+2**160 in get_input_values(and_instr.get_in_args(),assigments_dict):

                old_var = instr.get_out_args()
                new_var = and_instr.get_out_args()
                instr.set_out_args(new_var)

                msg = "AND(ORIGIN,2^160-1)"
                rules.append(msg)

                vars_to_update[old_var[0]] = new_var[0]
                #update_tstack_userdef(old_var[0], new_var[0],tstack, instructions)
                
                return True,[and_instr]
            else:
                return False, []
        else:
            return False, []


    elif opcode == "sub":
        out_pt = instr.get_out_args()[0]
        isz_op = list(filter(lambda x: out_pt in x.get_in_args() and x.get_op_name() == "iszero", instructions))
        

        if len(isz_op) == 1: #ISZ(SUB(X,Y)) = EQ(X,Y)
            isz_instr = isz_op[0]

            comm_inpt = [instr.get_in_args()[1],instr.get_in_args()[0]]
            
            new_exist = list(filter(lambda x: (x.get_in_args() == instr.get_in_args() or x.get_in_args() == comm_inpt) and x.get_op_name() == "eq", instructions))

            if len(new_exist) >0:
                old_var = isz_instr.get_out_args()
                new_var = new_exist[0].get_out_args()

                vars_to_update[old_var[0]] = new_var[0]
#                update_tstack_userdef(old_var[0], new_var[0],tstack, instructions)
                delete = [isz_instr]

            elif out_pt not in out_vars and len(list(filter(lambda x: out_pt in x.get_in_args() and x!=isz_instr, instructions))) == 0:
                isz_instr.set_op_name("eq")
                isz.set_in_args(instr.get_in_args())
                
                # idx = user_def_counter.get("EQ",0)
                # isz_instr["inpt_sk"] = instr.get_in_args()
                # isz_instr["id"] = "EQ_"+str(idx)
                # isz_instr["opcode"] = "14"
                # isz_instr["disasm"] = "EQ"
                # isz_instr["commutative"] = True
                # user_def_counter["EQ"]=idx+1
                delete = []

            else:
                return False, []


            msg = "ISZ(SUB(X,Y))"
            rules.append(msg)
            
            return True, delete
                
        else:
            return False,[]

    elif opcode == "shl":
        out_pt = instr.get_out_args()[0]
        mul_op = list(filter(lambda x: out_pt in x.get_in_args() and x.get_op_name() == "mul", instructions))
        div_op = list(filter(lambda x: out_pt in x.get_in_args() and x.get_op_name() == "div", instructions))
        and_op = list(filter(lambda x: out_pt in x.get_in_args() and x.get_op_name() == "and", instructions))
        if len(mul_op) == 1 and inp_vars == 1:
            mul_instr = mul_op[0]

            if mul_instr.get_in_args()[1] == out_pt:
                new_input = [instr.get_in_args()[0],mul_instr.get_in_args()[0]]
                new_exist = list(filter(lambda x: x.get_in_args() == new_input and x.get_op_name() == "shl", instructions))

                if len(new_exist) > 0:
                    old_var = mul_instr.get_out_args()
                    new_var = new_exist[0].get_out_args()
                    vars_to_update[old_var[0]] = new_var[0]
                    #update_tstack_userdef(old_var[0], new_var[0],tstack, instructions)
                    delete = [mul_instr]

                else:
                    mul_instr.set_in_args(new_input)
                    mul_instr.set_op_name("shl")
                    
                    # mul_instr["inpt_sk"] = new_input                    
                    # idx = user_def_counter.get("SHL",0)
                    # mul_instr["id"] = "SHL_"+str(idx)
                    # mul_instr["opcode"] = "1b"
                    # mul_instr["disasm"] = "SHL"
                    # mul_instr["commutative"] = False            
                    # user_def_counter["SHL"]=idx+1
                    delete = []
                    
                msg = "MUL(X,SHL(Y,1)"
                rules.append(msg)
                
                return True, delete

            elif mul_instr.get_in_args()[0] == out_pt:
                new_input = [instr.get_in_args()[0],mul_instr.get_in_args()[1]]
                new_exist = list(filter(lambda x: new_input in x.get_in_args() and x.get_op_name() == "shl", instructions))

                if len(new_exist) > 0:
                    old_var = mul_instr.get_out_args()
                    new_var = new_exist[0].get_out_args()
                    vars_to_update[old_var[0]] = [new_var[0]]
                    #update_tstack_userdef(old_var[0], new_var[0],tstack, instructions)
                    delete = [mul_instr]

                else:

                    mul_instr.set_op_name("shl")
                    mul_instr.set_in_args(new_input)

                    # mul_instr["inpt_sk"] = new_input
                    # idx = user_def_counter.get("SHL",0)
                    # mul_instr["id"] = "SHL_"+str(idx)
                    # mul_instr["opcode"] = "1b"
                    # mul_instr["disasm"] = "SHL"
                    # mul_instr["commutative"] = False            
                    # user_def_counter["SHL"]=idx+1
                    
                    delete = []

                msg = "MUL(SHL(X,1),Y)"
                rules.append(msg)
                
                return True, delete

            else:
                return False, []

        elif len(div_op) == 1 and inp_vars[1] == 1:
            div_instr = div_op[0]

            if div_instr.get_in_args()[1] == out_pt:
                new_input = [instr.get_in_args()[0], div_instr.get_in_args()[0]]
                new_exist = list(filter(lambda x: new_input in x.get_in_args() == new_input and x.get_op_name() == "shr", instructions))

                if len(new_exist) > 0:
                    old_var = div_instr.get_out_args()
                    new_var = new_exist[0].get_out_args()

                    vars_to_update[old_var[0]] = [new_var[0]]
                    #update_tstack_userdef(old_var[0], new_var[0],tstack, instructions)
                    delete = [div_instr]
                else:
                    
                    div_instr.set_op_name("shr")
                    div_instr.set_in_args(new_input)
                    # div_instr["inpt_sk"] = new_input
                    
                    # idx = user_def_counter.get("SHR",0)
                    # div_instr["id"] = "SHR_"+str(idx)
                    # div_instr["opcode"] = "1c"
                    # div_instr["disasm"] = "SHR"
                    # div_instr["commutative"] = False            
                    # user_def_counter["SHR"]=idx+1
                    delete = []

                msg = "DIV(X,SHL(Y,1))"
                rules.append(msg)
                
                return True, delete
            return False, []

        elif len(and_op) > 0: #AND(SHL(X,Y), SHL(X,Z)) => SHL(X,AND(Y,Z))

            found = False
            i = 0
            while i < len(and_op) and not found:
                
                and_ins = and_op[i]
                if out_pt == and_ins.get_in_args()[0]:
                    out_pt1 = and_ins.get_in_args()[1]
                else:
                    out_pt1 = and_ins.get_in_args()[0]

                new_ins = list(filter(lambda x: out_pt1 in x.get_out_args() and x.get_op_name() == "shl" and x.get_in_args()[0] == instr.get_in_args()[0], instructions))
                if len(new_ins) == 1:
                    shl1 = new_ins[0]
                    found = True

                i+=1

            #if the shl instructions are not used by any other operation or do not appear in the target stack, then I can simplify them
            if found and out_pt not in out_vars and out_pt1 not in out_vars and len(list(filter(lambda x: out_pt in x.get_in_args() and x!= and_ins, instructions))) == 0 and len(list(filter(lambda x: out_pt1 in x.get_in_args() and x!= and_ins, instructions))) == 0:

                inpt1 = instr.get_in_args()[0]
                inpt2 = instr.get_in_args()[1]
                inpt3 = shl1.get_in_args()[1]
                
                new_and_idx = user_def_counter.get("AND",0)

                instr.set_op_name("and")
                instr.get_in_args([inpt2, inpt3])
                
                # instr["inpt_sk"] = [inpt2,inpt3]
                # instr["id"] = "AND_"+str(new_and_idx)
                # instr["opcode"] = "16"
                # instr["disasm"] = "AND"
                # instr["commutative"] = True
                # user_def_counter["AND"]=new_and_idx+1
                #new_shl_idx = user_def_counter.get("SHL",0)

                and_ins.set_op_name("shl")
                and_ins.set_in_args([inpt1,instr.get_out_args()[0]])

                # and_ins["inpt_sk"] = [inpt1,instr.get_out_args()[0]]
                # and_ins["id"] = "SHL_"+str(new_shl_idx)
                # and_ins["opcode"] = "1b"
                # and_ins["disasm"] = "SHL"
                # and_ins["commutative"] = False
                # user_def_counter["SHL"]=new_shl_idx+1

                delete = [shl1]
                
                msg = "AND(SHL(X,Y), SHL(X,Z))"
                rules.append(msg)

                return True, delete
            else:
                return False, []
        else:
            return False, []

    elif opcode == "address":
        out_pt = instr.get_out_args()[0]
        bal_op = list(filter(lambda x: out_pt in x.get_in_args() and x.get_op_name() == "balance", instructions))

        and_op = list(filter(lambda x: out_pt in x.get_in_args() and x.get_op_name() == "and", instructions))

        if len(bal_op) == 1:
            bal_instr = bal_op[0]

            new_exist = list(filter(lambda x: x.get_op_name() == "selfbalance", instructions))

            if len(new_exist) > 0:
                    old_var = bal_instr.get_out_args()
                    new_var = new_exist[0].get_out_args()
                    vars_to_update[old_var[0]] = new_var[0]
                    #update_tstack_userdef(old_var[0], new_var[0],tstack, instructions)
                    delete = [bal_instr]
            else:
                bal_instr["inpt_sk"] = []

                bal_instr.set_op_name("selfbalance")
                bal_instr.set_in_args([])
                
                # idx = user_def_counter.get("SELFBALANCE",0)
                # bal_instr["id"] = "SELFBALANCE_"+str(idx)
                # bal_instr["opcode"] = "47"
                # bal_instr["disasm"] = "SELFBALANCE"
                # bal_instr["commutative"] = False            
                # user_def_counter["SELFBALANCE"]=idx+1
                delete = []

            msg = "BALANCE(ADDRESS)"
            rules.append(msg)
            
            return True, delete
        
        elif len(and_op) == 1:
            and_instr = and_op[0]
            if -1+2**160 in get_input_vars(and_instr.get_in_args(), assigments_dict):
                # instr.get_out_args() = and_instr.get_out_args()
                old_var = instr.get_out_args()
                new_var = and_instr.get_out_args()
                instr.set_out_args(new_var)

                msg = "AND(ADDRESS,2^160)"
                rules.append(msg)

                vars_to_update[old_var[0]] = new_var[0]
                #update_tstack_userdef(old_var[0], new_var[0],tstack, instructions)
                
                return True,[and_instr]
            else:
                return False, []
        else:
            return False, []
        
    elif opcode == "exp":
        if inp_vars[0] == 0:
            instr.get_in_args().pop(0)

            new_exist = list(filter(lambda x: x.get_in_args() == instr.get_in_args() and x.get_op_name() == "iszero", instructions))

            if len(new_exist) > 0:
                old_var = instr.get_out_args()
                new_var = new_exist[0].get_out_args()

                vars_to_update[old_var[0]] = new_var[0]
                #update_tstack_userdef(old_var[0], new_var[0],tstack, instructions)
                delete = [instr]
            else:

                instr.set_op_name("iszero")
                
                # idx = user_def_counter.get("ISZERO",0)
            
                # instr["id"] = "ISZERO_"+str(idx)
                # instr["opcode"] = "15"
                # instr["disasm"] = "ISZERO"
                # instr["commutative"] = False            
                # user_def_counter["ISZERO"]=idx+1
                delete = []
                

            msg = "EXP(0,X)"
            rules.append(msg)
            
            return True, deletez

        elif inp_vars[0] == 2:
            instr.get_in_args().pop(0)

            new_input = [instr.get_in_args()[0],"0x01"]
            new_exist = list(filter(lambda x: x.get_in_args() == new_input and x.get_op_name() == "shl", instructions))

            if len(new_exist) > 0:
                old_var = instr.get_out_args()
                new_var = new_exist[0].get_out_args()

                vars_to_update[old_var[0]] = new_var[0]
                
                #update_tstack_userdef(old_var[0], new_var[0],tstack, instructions)

                delete = [instr]
            else:
                instr.set_op_name("shl")
                instr.set_in_args(new_input)

                # idx = user_def_counter.get("SHL",0)
                # instr["inpt_sk"] = new_input
                # instr["id"] = "SHL_"+str(idx)
                # instr["opcode"] = "1b"
                # instr["disasm"] = "SHL"
                # instr["commutative"] = False            
                # user_def_counter["SHL"]=idx+1
                delete = []
            
            msg = "EXP(2,X)"

            return True, delete

        else:
            return False, []

    else:
        return False, []

from typing import List
from utils import process_opcode, get_ins_size, is_commutative
import opcodes

class CFGInstruction:
    def __init__(self, op : str, in_args: List[str], out_args: List[str]):
        self.op = op
        self.in_args = in_args
        self.out_args = out_args
        self.builtin_args = None
        
    def set_builtin_args(self, builtin: List[str]) -> None:
        self.builtin_args = builtin


    def get_as_json(self):
        instruction = {}

        instruction["in"] = self.in_args
        instruction["out"] = self. out_args
        instruction["op"] = self.op

        if self.builtin_args == None:
            instruction["builtinArgs"] = self.builtin_agrs

        return instruction


    def build_push_spec(self, val, idx, out_idx):

        value = int(val,16)
        
        obj["id"] = "PUSH_"+str(idx) if value != 0 else "PUSH0_"+str(idx)
        obj["opcode"] = process_opcode(str(opcodes.get_opcode("PUSH")[0])) if value != 0  else process_opcode(str(opcodes.get_opcode("PUSH0")[0]))
        obj["disasm"] = "PUSH" if value != 0 else "PUSH0"
        obj["inpt_sk"] = []
        obj["value"] = [value]
        obj["outpt_sk"] = ["s"+str(out_idx)]
        obj["gas"] = opcodes.get_ins_cost("PUSH") if value != 0 else opcodes.get_ins_cost("PUSH0")
        obj["commutative"] = False
        obj["push"] = True
        obj["storage"] = False #It is true only for MSTORE and SSTORE
        obj["size"] = get_ins_size("PUSH",value)

        return obj

        
    def build_spec(self, out_idx, instrs_idx, map_instructions):
        instructions = []

        instr_spec = {}

        op_name = self.op.upper()

        try:
            opcodes.get_opcode(op_name)
        except:
            raise Exception("[ERROR]: Opcode name not found")


        input_args = []
        for inp in self.in_args:
            inp_var = inp

            if inp.startswith("0x"):
                func = uninter_functions.get(("PUSH",[inp]),-1)
                if func != -1:
                    inp_var = func["outpt_sk"][0]
                else:
                    inst_idx = instrs_idx.get(op_name, 0)
                    instrs_idx[op_name] = inst_idx+1
                    
                    push_ins = self.build_push_spec(inp,inst_idx,out_idx)

                    map_instructions[("PUSH",[inp])] = push_ins
                    
                    new_out = out_idx+1
                    instructions.append(push_ins)
                    inp_var = push_ins["outpt_sk"][0]
                    
            input_args.append(inp_var)

        idx = instrs_idx.get(op_name,0)
        instrs_idx[op_name] = idx+1
            
        instr_spec["id"] = op_name+"_"+str(idx)
        instr_spec["opcode"] = process_opcode(str(opcodes.get_opcode(op_name)[0]))
        instr_spec["disasm"] = op_name
        instr_spec["inpt_sk"] = self.input_args
        instr_spec["outpt_sk"] = self.out_args
        instr_spec["gas"] = opcodes.get_ins_cost(op_name)
        instr_spec["commutative"] = is_commutative(op_name)
        instr_spec["push"] = False
        instr_spec["storage"] = True if op_name in ["MSTORE","SSTORE"] else False #It is true only for MSTORE and SSTORE
        instr_spec["size"] = get_ins_size(op_name)

        if op_name == "MSTORE":
            instr_spec["mem_var"] = ["mem"+str(inst_idx)]
        elif op_name == "SSTORE":
            instr_spec["mem_var"] = ["sto"+str(inst_idx)]
        

        map_instructions[(op_name,self.input_args)] = instr_spec
        
        instructions.append(instr_spec)

        return instructions, new_out

    def get_out_args(self):
        return self.out_args

    def get_in_args(self):
        return self.in_args

    def get_op_name(self):
        return self.op
    
    def __str__(self):
        self.get_as_json()


        

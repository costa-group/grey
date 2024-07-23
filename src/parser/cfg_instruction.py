"""
Module for representing and building the instructions that appear in the CFG
"""
import json
from typing import List, Dict
from parser.utils_parser import process_opcode, get_ins_size, is_commutative
import parser.opcodes as opcodes


def build_instr_spec(op_name: str, idx: int, input_args: List[str], out_args: List[str]):
    """
    Generates the specification of a function from the opcode name
    """
    instr_spec = dict()
    instr_spec["id"] = op_name + "_" + str(idx)
    instr_spec["opcode"] = process_opcode(str(opcodes.get_opcode(op_name)[0]))
    instr_spec["disasm"] = op_name
    instr_spec["inpt_sk"] = input_args
    instr_spec["outpt_sk"] = out_args
    instr_spec["gas"] = opcodes.get_ins_cost(op_name)
    instr_spec["commutative"] = is_commutative(op_name)
    instr_spec["push"] = False
    instr_spec["storage"] = True if op_name in ["MSTORE", "SSTORE"] else False  # It is true only for MSTORE and SSTORE
    instr_spec["size"] = get_ins_size(op_name)

    return instr_spec


def build_push_spec(val, idx, out_idx, out_args = None):
    """
    Generates the specification of a PUSH instruction from the introduced value
    """
    obj = {}

    value = int(val, 16)

    obj["id"] = "PUSH_" + str(idx) if value != 0 else "PUSH0_" + str(idx)
    obj["opcode"] = process_opcode(str(opcodes.get_opcode("PUSH")[0])) if value != 0 else process_opcode(
        str(opcodes.get_opcode("PUSH0")[0]))
    obj["disasm"] = "PUSH" if value != 0 else "PUSH0"
    obj["inpt_sk"] = []
    obj["value"] = [value]
    obj["outpt_sk"] = ["s"+str(out_idx)] if out_args == None else out_args
    obj["gas"] = opcodes.get_ins_cost("PUSH") if value != 0 else opcodes.get_ins_cost("PUSH0")
    obj["commutative"] = False
    obj["push"] = True
    obj["storage"] = False  # It is true only for MSTORE and SSTORE
    obj["size"] = get_ins_size("PUSH", value)

    return obj


def build_pushtag_spec(idx, out_idx, tag_value):
    """
    Generates the specification of a PUSH tag instruction
    """
    obj = {}

    value = int(val, 16)

    obj["id"] = "PUSH [tag]" + str(idx)
    obj["opcode"] = process_opcode(str(opcodes.get_opcode("PUSH [tag]")[0]))
    obj["disasm"] = "PUSH [tag]"
    obj["inpt_sk"] = []
    obj["value"] = [tag_value]
    obj["outpt_sk"] = ["s"+str(out_idx)]
    obj["gas"] = opcodes.get_ins_cost("PUSH [tag]")
    obj["commutative"] = False
    obj["push"] = True
    obj["storage"] = False  # It is true only for MSTORE and SSTORE
    obj["size"] = get_ins_size("PUSH [tag]")

    return obj




def build_verbatim_spec(function_name: str, input_args: List[str], output_args: List[str], builting_args: List[str]):
    """
    Generates the specification of a verbatim
    """
    obj = {}

    # The function name is of the form 'verbatim_<n>i_<m>o("<data>", ...)'
    # (see "verbatim" in https://docs.soliditylang.org/en/latest/yul.html)
    # Hence, different functions can have the same function name
    obj["id"] = function_name + "_args_" + builting_args[0]
    obj["opcode"] = builting_args[0]
    obj["disasm"] = builting_args[0]
    obj["inpt_sk"] = input_args
    obj["outpt_sk"] = output_args
    obj["gas"] = 100 # Random value for gas, as it is unknown
    obj["commutative"] = False
    obj["push"] = False
    obj["storage"] = True # Assuming it must be performed always
    obj["size"] = len(builting_args[0]) // 2 # Assuming builtin args contain the corresponding bytecode

    return obj


def build_custom_function_spec(function_name: str, input_args: List[str], output_args: List[str], builting_args: List[str]):
    """
    Generates the specification of a custom function
    """
    obj = {}

    # The function name is of the form 'verbatim_<n>i_<m>o("<data>", ...)'
    # (see "verbatim" in https://docs.soliditylang.org/en/latest/yul.html)
    # Hence, different functions can have the same function name
    obj["id"] = function_name
    obj["opcode"] = function_name
    obj["disasm"] = function_name
    obj["inpt_sk"] = input_args
    obj["outpt_sk"] = output_args
    obj["gas"] = 100 # Random value for gas, as it is unknown
    obj["commutative"] = False
    obj["push"] = False
    obj["storage"] = True # Assuming it must be performed always
    obj["size"] = 5 # Assuming builtin args contain the corresponding bytecode

    return obj


class CFGInstruction:
    def __init__(self, op: str, in_args: List[str], out_args: List[str]):
        self.op = op
        self.in_args = in_args[::-1]
        self.out_args = out_args[::-1]
        self.builtin_args = None
        self.assignments = None

    def must_be_computed(self):
        """
        Check whether an instruction must be computed (i.e. added as part of the opertions fed into the greedy
        algorithm) or not. Instructions that must not be computed include assignments (as they are propagated directly)
        and functionReturns
        """
        return self.op != "assignments"
        
    def set_builtin_args(self, builtin: List[str]) -> None:
        self.builtin_args = builtin

    def get_as_json(self):
        instruction = {"in": self.in_args, "out": self.out_args, "op": self.op}

        if self.builtin_args is not None:
            instruction["builtinArgs"] = self.builtin_args

        if self.assignments is not None:
            instruction["assignment"] = self.assignments

        return instruction


    def build_spec_assigment(self, out_idx, instrs_idx, map_instructions):
        """
        An assigment instruction is translated into a push opcode
        """

        assert(len(self.in_args) == 1, "[ERROR]: An assignment only has one argument")
        
        instructions = []
        new_out = out_idx
        
        input_args = []
        
        inp = self.in_args[0]
        
        func = map_instructions.get(("PUSH",tuple([inp])),-1)
                
        if func != -1:
            inp_var = func["outpt_sk"][0]
        else:
            
            push_name = "PUSH" if int(inp,16) != 0 else "PUSH0"
            inst_idx = instrs_idx.get(push_name, 0)
            instrs_idx[push_name] = inst_idx+1
                    
            push_ins = build_push_spec(inp,inst_idx,new_out, self.out_args)

            map_instructions[("PUSH",tuple([inp]))] = push_ins
                    
            new_out +=1
            instructions.append(push_ins)
            inp_var = push_ins["outpt_sk"][0]
            
        return instructions, new_out


    
    # def build_spec(self, out_idx, instrs_idx, map_instructions, assignments: Dict[str, str]):
    def build_spec(self, out_idx, instrs_idx, map_instructions):
        instructions = []
        new_out = out_idx
        
        input_args = []
        for inp in self.in_args:
            inp_var = inp

            if inp.startswith("0x"):
                # Retrieve the corresponding value
                inp_value = inp
                func = map_instructions.get(("PUSH",tuple([inp_value])),-1)
                
                if func != -1:
                    inp_var = func["outpt_sk"][0]
                else:
                    if inp.startswith("0x"):
                        push_name = "PUSH" if int(inp_value,16) != 0 else "PUSH0"
                        inst_idx = instrs_idx.get(push_name, 0)
                        instrs_idx[push_name] = inst_idx+1
                    
                        push_ins = build_push_spec(inp_value,inst_idx,new_out)

                        map_instructions[("PUSH",tuple([inp_value]))] = push_ins
                    
                        new_out +=1
                        instructions.append(push_ins)
                        inp_var = push_ins["outpt_sk"][0]

                    elif inp in assignments:
                        inp_var = inp
                        
            input_args.append(inp_var)

        op_name = self.op.upper()
        idx = instrs_idx.get(op_name, 0)

        if "VERBATIM" in op_name:
            # Here we need to reverse the arguments
            instr_spec = build_verbatim_spec(op_name, input_args, self.out_args, self.builtin_args)
        elif opcodes.exists_opcode(op_name):
            instr_spec = build_instr_spec(op_name, idx, input_args, self.out_args)
        else:
            # TODO: separate wrong opcodes from custom functions
            instr_spec = build_custom_function_spec(op_name, input_args, self.out_args, self.builtin_args)

        instrs_idx[op_name] = idx+1
        map_instructions[(op_name,tuple(self.in_args))] = instr_spec
        
        instructions.append(instr_spec)

        return instructions, new_out

    def get_out_args(self):
        return self.out_args

    def get_in_args(self):
        return self.in_args

    def get_op_name(self):
        return self.op

    def get_instruction_representation(self):
        outs = ""
        if self.out_args != []:
            outs = ",".join(self.out_args)
            outs+= " = "

        inps = ""
        if self.in_args !=[]:
            inps = ",".join(self.in_args)
            
        instr = outs+self.op+"("+inps+")"

        return instr

    def dot_repr(self):
        return self.get_instruction_representation()

    def __repr__(self):
        return json.dumps(self.get_as_json())

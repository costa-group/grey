"""
Module for representing and building the instructions that appear in the CFG
"""
import json
from typing import List, Dict, Optional
from parser.utils_parser import process_opcode, get_ins_size, is_commutative
import parser.opcodes as opcodes
import parser.constants as constants

def build_instr_spec(op_name: str, idx: int, input_args: List[str], out_args: List[str], value: Optional[str]= None):
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

    if value != None:
        instr_spec["value"] = value

    return instr_spec


def build_push_spec(val: str, idx: int, out_args: List[str]):
    """
    Generates the specification of a PUSH instruction from the introduced value
    """
    obj = {}

    value = int(val, 16)

    obj["id"] = "PUSH_" + str(idx) if value != 0 else "PUSH0_" + str(idx)
    obj["opcode"] = process_opcode(str(opcodes.get_opcode("PUSH")[0])) if value != 0 else process_opcode(str(opcodes.get_opcode("PUSH0")[0]))
    obj["disasm"] = "PUSH" if value != 0 else "PUSH0"
    obj["inpt_sk"] = []
    obj["value"] = [value]
    obj["outpt_sk"] = out_args
    obj["gas"] = opcodes.get_ins_cost("PUSH") if value != 0 else opcodes.get_ins_cost("PUSH0")
    obj["commutative"] = False
    obj["push"] = True
    obj["storage"] = False  # It is true only for MSTORE and SSTORE
    obj["size"] = get_ins_size("PUSH", value)

    return obj


def build_pushtag_spec(out_idx, tag_value):
    """
    Generates the specification of a PUSH tag instruction
    """
    obj = {}

    obj["id"] = "PUSHTAG_" + str(tag_value)
    obj["opcode"] = process_opcode(str(opcodes.get_opcode("PUSH [TAG]")[0]))
    obj["disasm"] = "PUSH [TAG]"
    obj["inpt_sk"] = []
    obj["value"] = [tag_value]
    obj["outpt_sk"] = ["s"+str(out_idx)]
    obj["gas"] = opcodes.get_ins_cost("PUSH [TAG]")
    obj["commutative"] = False
    obj["push"] = True
    obj["storage"] = False  # It is true only for MSTORE and SSTORE
    obj["size"] = get_ins_size("PUSH [TAG]")

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
    obj["disasm"] = "VERBATIM" #builting_args[0]
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
        # Phi Functions must be keep the order of input arguments
        self.in_args = in_args[::-1] if op != "PhiFunction" else in_args
        self.out_args = out_args[::-1]
        self.builtin_op = None
        self.builtin_args = None
        self.translate_builtin_args = None
        self.assignments = None

        if op.startswith("verbatim"):
            constants.add_verbatim_to_split_block(op)

        
    def must_be_computed(self):
        """
        Check whether an instruction must be computed (i.e. added as part of the opertions fed into the greedy
        algorithm) or not. Instructions that must not be computed include assignments (as they are propagated directly)
        and functionReturns
        """
        return self.op not in ["assignments", "PhiFunction", "functionReturn"]

    def memory_operation(self):
        """
        Memory operation: STORE operations and function calls
        """
        # TODO: handle keccaks and loads better
        return "STORE" in self.op or self.op not in opcodes.opcodes or "LOAD" in self.op or "KECCAK" in self.op
        
    def set_builtin_args(self, builtin: List[str]) -> None:
        self.builtin_args = builtin

    def get_as_json(self):
        instruction = {"in": self.in_args, "out": self.out_args, "op": self.op}

        if self.builtin_args is not None:
            instruction["builtinArgs"] = self.builtin_args

        if self.assignments is not None:
            instruction["assignment"] = self.assignments

        return instruction
    
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
                    
                        push_ins = build_push_spec(inp_value,inst_idx, [f"s{new_out}"])

                        map_instructions[("PUSH",tuple([inp_value]))] = push_ins
                    
                        new_out +=1
                        instructions.append(push_ins)
                        inp_var = push_ins["outpt_sk"][0]

                    elif inp in self.assignments:
                        inp_var = inp
                        
            input_args.append(inp_var)

        op_name = self.op.upper()
        idx = instrs_idx.get(op_name, 0)

        
        if "VERBATIM" in op_name:
            # Here we need to reverse the arguments
            instr_spec = build_verbatim_spec(op_name, input_args, self.out_args, self.get_builtin_args())
        elif opcodes.exists_opcode(op_name):
            if self.op in ["pushlib", "push #[$]", "push [$]", "pushimmutable", "assignimmutable"]:
                instr_spec = build_instr_spec(op_name, idx, input_args, self.out_args, self.get_builtin_args())
            elif self.op == "push":
                instr_spec = build_push_spec(self.get_builtin_args()[0], idx, self.out_args) 
            else:
                instr_spec = build_instr_spec(op_name, idx, input_args, self.out_args)
        else:
            # TODO: separate wrong opcodes from custom functions
            instr_spec = build_custom_function_spec(op_name, input_args, self.out_args, self.get_builtin_args())

        instrs_idx[op_name] = idx+1

        if self.op.startswith("push"):
            map_instructions[(op_name,tuple(self.get_builtin_args()))] = instr_spec
        else:
            map_instructions[(op_name,tuple(self.in_args))] = instr_spec
        instructions.append(instr_spec)

        return instructions, new_out

    def get_out_args(self):
        return self.out_args

    def get_in_args(self):
        return self.in_args

    def get_type_mem_op(self):
        if self.op in ["sload", "mload", "keccak256", "log0","log1","log2","log3","log4", "create","create2"]:
            return "read"
        elif self.op in ["mstore", "mstore8", "codecopy","extcodecopy","calldatacopy","returndatacopy","mcopy"]:
            return "write"
        else:
            return None

    def get_builtin_op(self):
        return self.builtin_op

    def get_builtin_args(self):
        if self.translate_builtin_args != None:
            return self.translate_builtin_args

        if self.builtin_args != None:
            return self.builtin_args

        return None
    

    """
    Module to translate the special builtins in Yul to the corresponding assembly JSON.
    See "https://notes.ethereum.org/znem65ljTKaoL11xOWv-Ew" for an explanation on the different translations
    """

    def translate_linkersymbol(self) :
        self.op = "pushlib"
        # TODO: revert changes in translate builting args
        self.translate_builtin_args = list(self.builtin_args)


    def translate_memoryguard(self) :
        #It is trabslated as a push directly
        self.op = "push"
        new_builtin = []
        for o in self.builtin_args:
            hex_val = hex(int(o))
            new_builtin.append(hex_val)
        self.translate_builtin_args = new_builtin
        
        
    def translate_datasize(self, subobjects_keys: Dict[str, int]):
        self.op = "push #[$]"
        
        builtin_val = self.builtin_args[0]

        pos = subobjects_keys.get(builtin_val, None)
        if pos is not None:
            self.translate_builtin_args = ["{0:064X}".format(pos)]
        else:
            print("[WARNING ERROR]: Identifier not found in subobjects keys")
            self.translate_builtin_args = ["{0:064X}".format(0)]
                       
#            raise Exception("[ERROR]: Identifier not found in subobjects keys")

    def translate_dataoffset(self, subobjects_keys: Dict[str, int]):
        self.op = "push [$]"

        builtin_val = self.builtin_args[0]

        pos = subobjects_keys.get(builtin_val, None)
        if pos is not None:
            self.translate_builtin_args = ["{0:064X}".format(pos)]
        else:
            print("[WARNING ERROR]: Identifier not found in subobjects keys")
            self.translate_builtin_args = ["{0:064X}".format(0)]

            # raise Exception("[ERROR]: Identifier not found in subobjects keys")

    def translate_datacopy(self) :
        self.op = "codecopy"

    def translate_setimmutable(self) :
        #It is treated as a special mstore in gasol.
        self.op = "assignimmutable"
        self.translate_builtin_args = self.builtin_args

    def translate_loadimmutable(self) :
       self.op = "pushimmutable"
       self.translate_builtin_args = self.builtin_args

    def translate_built_in_function(self, subobjects_keys: Dict[str, int]):
        self.builtin_op = self.op
        
        if self.op == "linkersymbol":
            self.translate_linkersymbol()
        elif self.op == "memoryguard":
            self.translate_memoryguard()
        elif self.op == "datasize":
            self.translate_datasize(subobjects_keys)
        elif self.op == "dataoffset":
            self.translate_dataoffset(subobjects_keys)
        elif self.op == "datacopy":
            self.translate_datacopy()
        elif self.op == "setimmutable":
            self.translate_setimmutable()
        elif self.op == "loadimmutable":
            self.translate_loadimmutable()
        else:
            raise Exception("[ERROR]: Built-in function is not recognized")
        
    def translate_opcode(self, subobjects_keys: Dict[str, int]):
        if self.op in ["linkersymbol","memoryguard", "datasize", "dataoffset", "datacopy", "setimmutable", "loadimmutable"]:
            self.translate_built_in_function(subobjects_keys)

    def get_op_name(self):
        return self.op

    def get_instruction_representation(self):
        outs = f'{",".join(self.out_args)} = ' if self.out_args else ''
        inps = f'({",".join(self.in_args)})' if self.in_args else ''
        args = f'[{",".join(self.builtin_args)}]' if self.builtin_args else ''
        instr = outs + self.op + inps + args

        return instr

    def dot_repr(self):
        return self.get_instruction_representation()

    @property
    def gas_spent_op(self) -> int:
        """
        Gas spent for performing the operation. Does not consider the cost needed to generate the args
        """
        if self.op == "PhiFunction" or self.op == "FunctionReturn":
            return 0
        return opcodes.get_ins_cost(self.op)

    @property
    def bytes_required(self) -> int:
        """
        Bytes required for performing the operation. Does not consider the cost needed to generate the args (hence, 1)
        """
        if self.op == "PhiFunction" or self.op == "FunctionReturn":
            return 0
        return 1

    def __repr__(self):
        return json.dumps(self.get_as_json())

    def __eq__(self, other: 'CFGInstruction'):
        return isinstance(other, CFGInstruction) and self.out_args == other.out_args and \
            self.in_args == other.in_args and self.op == other.op

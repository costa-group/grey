from parser.cfg_instruction import CFGInstruction, build_push_spec, build_pushtag_spec
from parser.utils_parser import is_in_input_stack, is_in_output_stack, is_assigment_var_used, get_empty_spec, get_expression, are_dependent_accesses
import parser.constants as constants
import json
import networkx as nx

from typing import List, Dict, Tuple

global tag_idx
tag_idx = 0

global function_tags
function_tags = {}

class CFGBlock:
    """
    Class for representing a cfg block
    """
    
    def __init__(self, identifier : str, instructions: List[CFGInstruction], type_block: str, assignment_dict: Dict[str, str]):
        self.block_id = identifier
        self._instructions = instructions
        # minimum size of the source stack
        self.source_stack = 0
        self._jump_type = type_block
        self._jump_to = None
        self._falls_to = None
        self.assignment_dict = assignment_dict
        self.is_function_call = False
        self._comes_from = []
        self.function_calls = set()
        self.sto_dep = []
        self.mem_dep = []

        
    def get_block_id(self) -> str:
        return self.block_id
        
    def get_instructions(self) -> List[CFGInstruction]:
        return self._instructions

    def get_instructions_to_compute(self) -> List[CFGInstruction]:
        return [instruction for instruction in self._instructions if instruction.must_be_computed()]

    def get_source_stack(self) -> int:
        return self.source_stack
   
    def get_jump_type(self) -> str:
        return self._jump_type

    def get_jump_to(self) -> str:
        return self._jump_to

    def get_falls_to(self) -> str:
        return self._falls_to

    def is_function_call(self) -> bool:
        return self.is_function_call

    def set_function_call(self, v) -> None:
        self.is_function_call = v
    
    def set_instructions(self, new_instructions: List[CFGInstruction]) -> None:
        self._instructions = new_instructions

        # Then we update the source stack size
        # TODO
        #self.source_stack = utils.compute_stack_size(map(lambda x: x.disasm, self.instructions_to_optimize_bytecode()))

    def add_instruction(self, new_instr: CFGInstruction) -> None:
        self._instructions.append(new_instr)
        # TODO
        #self.source_stack = utils.compute_stack_size(map(lambda x: x.disasm, self.instructions_to_optimize_bytecode()))

    def add_comes_from(self, block_id: str):
        self._comes_from.append(block_id)

    def get_comes_from(self) -> List[str]:
        return self._comes_from

    def set_jump_type(self, t : str) -> None:
        if t not in ["conditional","unconditional","terminal", "falls_to"]:
            raise Exception("Wrong jump type")
        else:
            self._jump_type = t
    
    def set_jump_to(self, blockId : str) -> None:
        self._jump_to = blockId

    def set_falls_to(self, blockId :str) -> None:
        self._falls_to = blockId

    def set_length(self) -> int:
        return len(self._instructions)

    def set_jump_info(self, type_block: str, exit_info: List[str]) -> None:
        if type_block in ["ConditionalJump"]:
            self._jump_type = "conditional"
            self._falls_to = exit_info[0]
            self._jump_to = exit_info[1]
        elif type_block in ["Jump"]:
            self._jump_type = "unconditional"
            self._jump_to = exit_info[0]
        elif type_block in ["Terminated"]:
            #We do not store the direction as itgenerates a loop
            self._jump_type = "terminal"
        elif type_block in [""]:
            #It corresponds to falls_to blocks
            self._jump_type = "falls_to"
        elif type_block in ["MainExit"]:
            self._jump_type = "terminal"
        elif type_block in ["FunctionReturn"]:
            self._jump_type = "FunctionReturn"

    def process_function_calls(self, function_ids):
        op_names = map(lambda x: x.get_op_name(), self._instructions)
        calls = filter(lambda x: x in function_ids, op_names)
        self.function_calls = set(calls)


    def process_dependences(self, instructions):

        sto_dep = self._compute_storage_dependences(instructions)
        sto_dep = self._simplify_dependences(sto_dep)
        
        # mem_dep = self._compute_storage_dependences()
        # mem_dep = self._simplify_dependences(mem_dep)
        return sto_dep #, mem_dep
        
    def _compute_storage_dependences(self,instructions):
        sto_ins = []
        print(instructions)
        for i in range(len(instructions)):
            ins = instructions[i]
            if ins.get_op_name() in ["sload","sstore"]:
                v = ins.get_in_args()[0]
                input_val = get_expression(v, instructions[:i])
                sto_ins.append((i,input_val))
            elif ins.get_op_name() in ["call","delegatecall","staticcall","callcode"]:
                sto_ins.append((i,["inf"]))
                
        deps = [(sto_ins[i][0],j[0]) for i in range(len(sto_ins)) for j in sto_ins[i+1:] if are_dependent_accesses(sto_ins[i][1],j[1])]
        print("DEPS: "+str(deps))
        print("******")
        return deps
                                
    def _compute_memory_dependences(self, instructions):
        for i in len(instructions):
            ins = instructions[i]
            if ins.get_op_name() in ["keccak256", "mload", "mstore", "codecopy","extcodecopy","returndatacopy","mstore8","mcopy","log0","log1","log2","log3","log4","create","create2","call","delegatecall","staticcall","callcode"]:
                pass

    def _simplify_dependences(self, deps: List[Tuple[int, int]]) -> List[Tuple[int, int]]:
        dg = nx.DiGraph(deps)
        tr = nx.transitive_reduction(dg)
        return list(tr.edges)
                            
    def get_as_json(self):
        block_json = {}
        block_json["id"] = self.block_id

        instructions_json = []
        for i in self._instructions:
            i_json = i.get_as_json()
            instructions_json.append(i_json)

        block_json["instructions"] = instructions_json
        
        block_json["exit"] = self.block_id+"Exit"
        block_json["type"] = "BasicBlock"

        jump_block = {}

        if self._jump_type == "conditional":
            jump_block["id"] = self.block_id+"Exit"
            jump_block["instructions"] = []
            jump_block["type"] = "ConditionalJump"
            jump_block["exit"] = [self._falls_to, self._jump_to]
            jump_block["cond"] = self._instructions[-1].get_out_args()

        elif self._jump_type == "unconditional":
            jump_block["id"] = self.block_id+"Exit"
            jump_block["instructions"] = []
            jump_block["type"] = "Jump"
            jump_block["exit"] = [self._jump_to]

        elif self._jump_type == "mainExit":
            jump_block["id"] = self.block_id+"Exit"
            jump_block["instructions"] = []
            jump_block["type"] = "MainExit"
            jump_block["exit"] = [self._jump_to]

        block_json["comes_from"] = self._comes_from
        return block_json, jump_block

    def _get_vars_spec(self, uninter_instructions):
        vars_spec = set()

        for i in uninter_instructions:
            all_vars = i["inpt_sk"]+i["outpt_sk"]
            for a in all_vars:
                vars_spec.add(a)

        return list(vars_spec)

    def _build_spec_for_block(self, instructions, map_instructions: Dict, out_idx):
        """
        Builds the specification for a block. "map_instructions" is passed as an argument
        to reuse declarations from other blocks, as we might have split the corresponding basic block
        """
        
        spec = {}

        uninter_functions = []
        instrs_idx = {}
        new_out_idx = out_idx

        input_stack = []
        output_stack = []

        
        for i in range(len(instructions)):
            #Check if it has been already created
            
            ins = instructions[i]
            
            ins_spec = map_instructions.get((ins.get_op_name().upper(),tuple(ins.get_in_args())), None)

            if ins_spec is None:
                if ins.get_op_name().startswith("assignment"):
                    result, new_out_idx = ins.build_spec_assigment(new_out_idx, instrs_idx, map_instructions) 
                else:
                    result, new_out_idx = ins.build_spec(new_out_idx, instrs_idx, map_instructions)

                uninter_functions+=result

                for i_arg in ins.get_in_args():
                    if not i_arg.startswith("0x") and i_arg not in self.assignment_dict:
                        member = is_in_input_stack(i_arg,instructions[:i])

                        if member:
                            input_stack.append(i_arg)


                for o_arg in  ins.get_out_args():
                    member = is_in_output_stack(o_arg, instructions[i+1:])
                    if member:
                        output_stack = [o_arg]+output_stack



        # for assigment in self.assignment_dict:

        #     is_used = is_assigment_var_used(assigment, uninter_functions)
            
        #     # if is_used:

        #     in_val = self.assignment_dict.get(assigment)
        #     if in_val.startswith("0x"): #It is a push value
        #         func = map_instructions.get(("PUSH",tuple([in_val])),-1)
        #         if func == -1:
        #             push_name = "PUSH" if int(in_val,16) != 0 else "PUSH0"
        #             inst_idx = instrs_idx.get(push_name, 0)
        #             instrs_idx[push_name] = inst_idx+1
        #             push_ins = build_push_spec(in_val,inst_idx,assigment)

        #             map_instructions[("PUSH",tuple([in_val]))] = push_ins
                    
        #             uninter_functions.append(push_ins)

        #     if not is_used:
        #         output_stack.insert(0,assigment)
                        
        spec["original_instrs"] = ""
        spec["yul_expressions"] = '\n'.join(list(map(lambda x: x.get_instruction_representation(),instructions)))
        spec["src_ws"] = input_stack
        spec["tgt_ws"] = output_stack
        spec["user_instrs"] = uninter_functions
        spec["variables"] = self._get_vars_spec(uninter_functions)

        spec["memory_dependences"] = []
        spec["storage_dependences"] = []
        
        #They are not used in greedy algorithm
        spec["init_progr_len"] = 0
        spec["max_progr_len"] = 0
        spec["min_length_instrs"] = 0 
        spec["min_length_bounds"] = 0
        spec["min_length"] = 0
        spec["rules"] = ""
        
        return spec, new_out_idx

        
    def _include_function_call_tags(self,ins, out_idx, block_spec):
        global function_tags
        global tag_idx

        in_tag, out_tag = function_tags.get(ins.get_op_name(), (-1,-1))

        if in_tag == -1 and out_tag == -1:
            out_tag = tag_idx
            in_tag = tag_idx+1
            tag_idx+=2
            
            function_tags[ins.get_op_name()] = (in_tag, out_tag)
            
        in_tag_instr = build_pushtag_spec(out_idx, in_tag)
        out_idx+=1

        out_tag_instr = build_pushtag_spec(out_idx, out_tag)

        block_spec["user_instrs"]+=[in_tag_instr,out_tag_instr]

        #It adds the out jump label after the arguments of the function
        num_funct_arguments = len(ins.get_in_args())
        block_spec["tgt_ws"] = block_spec["tgt_ws"][:num_funct_arguments]+out_tag_instr["outpt_sk"]+block_spec["tgt_ws"][num_funct_arguments:]

        #It adds at top of the stack de input jump label
        block_spec["tgt_ws"] = in_tag_instr["outpt_sk"]+block_spec["tgt_ws"]

            
        #It adds in variables the new identifier for the in and out jump label
        block_spec["variables"]+=in_tag_instr["outpt_sk"]+ out_tag_instr["outpt_sk"]

        block_spec["yul_expressions"]+="\n"+ins.get_instruction_representation()

            
        return block_spec, out_idx

    def _include_jump_tag(self, block_spec, out_idx, block_tags_dict, block_tag_idx):

        tag_idx = block_tags_dict.get(self._jump_to, block_tag_idx)
        
        if self._jump_to not in block_tags_dict:
            block_tags_dict[self._jump_to] = block_tag_idx
            idx = block_tag_idx+1

        else:
            idx = block_tag_idx


        tag_instr = build_pushtag_spec(out_idx, tag_idx)
        out_idx+=1

        block_spec["user_instrs"].append(tag_instr)

        #It adds on top of the stack the jump label
        block_spec["tgt_ws"] = tag_instr["outpt_sk"]+block_spec["tgt_ws"]
            
        #It adds in variables the new identifier for  jump label
        block_spec["variables"]+=tag_instr["outpt_sk"]

        return block_spec, out_idx, block_tag_idx
        
        
        
    def build_spec(self, block_tags_dict, block_tag_idx):
        
        ins_seq = []
        map_instructions = {}
        specifications = {}

        cont = 0

        out_idx = 0
        
        i = 0

        for i in range(len(self._instructions)):
            ins = self._instructions[i]
            if ins.get_op_name().upper() in constants.split_block or ins.get_op_name() in self.function_calls:
                if  ins_seq != []:
                    r, out_idx = self._build_spec_for_block(ins_seq, map_instructions, out_idx)

                    sto_deps = self._process_dependences(ins_seq)
                    r["storage_dependences"] = sto_deps
                    # r["memory_dependences"] = mem_deps

                    specifications["block"+str(self.block_id)+"_"+str(cont)] = r
                    cont +=1
                    
                    if not ins.get_op_name() in self.function_calls: 
                        print("block"+str(self.block_id)+"_"+str(cont))
                        print(json.dumps(r, indent=4))

                        
                else:
                    r = get_empty_spec()
                    cont+=1

                if ins.get_op_name() in self.function_calls:
                    r, out_idx = self._include_function_call_tags(ins,out_idx,r)
                        
                    specifications["block"+str(self.block_id)+"_"+str(cont-1)] = r
                    print("block"+str(self.block_id)+"_"+str(cont-1))
                    print(json.dumps(r, indent=4))


                        
                #We reset the seq of instructions and the out_idx for next block
                ins_seq = []
                out_idx = 0
                map_instructions = {}
                            
            else:
                ins_seq.append(ins)
                
        if ins_seq != []:
            r, out_idx = self._build_spec_for_block(ins_seq, map_instructions, out_idx)
            
            sto_deps = self._process_dependences(ins_seq)
            r["storage_dependences"] = sto_deps
            # r["memory_dependences"] = mem_deps

            specifications["block"+str(self.block_id)+"_"+str(cont)] = r

            if not self._jump_type in ["conditional","unconditional"]:
                print("block"+str(self.block_id)+"_"+str(cont))
                print(json.dumps(r, indent=4))
                
        else:
            r = get_empty_spec()
            cont+=1

        if self._jump_type in ["conditional","unconditional"]:
            r, out_idx, block_tag_idx = self._include_jump_tag(r,out_idx, block_tags_dict, block_tag_idx)
            specifications["block"+str(self.block_id)+"_"+str(cont)] = r
            print("block"+str(self.block_id)+"_"+str(cont))
            print(json.dumps(r, indent=4))

        return specifications, block_tag_idx


    def __str__(self):

        s = "BlockID: " + self.block_id+ "\n"
        s += "Type: " + self._jump_type+ "\n"
        s += "Jump to: " + str(self._jump_to) + "\n"
        s += "Falls to: " + str(self._falls_to) + "\n"
        s += "Comes_from: " + str(self._comes_from) + "\n"
        s += "Instructions: " + str(self._instructions) + "\n"
        return s
        
    def __repr__(self):
        return json.dumps(self.get_as_json())

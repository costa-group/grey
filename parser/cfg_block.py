from parser.cfg_instruction import CFGInstruction
from parser.utils_parser import is_in_input_stack, is_in_output_stack
import parser.constants as constants


from typing import List

class CFGBlock:
    """
    Class for representing a cfg block
    """
    
    def __init__(self, identifier : str, instructions: List[CFGInstruction], type_block: str):
        self.block_id = identifier
        self._instructions = instructions
        # minimum size of the source stack
        self.source_stack = 0
        self._jump_type = type_block
        self._jump_to = None
        self._falls_to = None

        
    def get_block_id(self) -> str:
        return self.block_id
        
    def get_instructions(self) -> List[CFGInstruction]:
        return self._instructions

    def get_source_stack(self) -> int:
        return self.source_stack
   
    def get_jump_type(self) -> str:
        return self._jump_type

    def get_jump_to(self) -> str:
        return self._jump_to

    def get_falls_to(self) -> str:
        return self._falls_to

    def set_instructions(self, new_instructions: List[CFGInstruction]) -> None:
        self._instructions = new_instructions

        # Then we update the source stack size
        # TODO
        #self.source_stack = utils.compute_stack_size(map(lambda x: x.disasm, self.instructions_to_optimize_bytecode()))

    def add_instruction(self, new_instr: CFGInstruction) -> None:
        self._instructions.add(new_instr)
        # TODO
        #self.source_stack = utils.compute_stack_size(map(lambda x: x.disasm, self.instructions_to_optimize_bytecode()))


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
        if type_block == "ConditionalJump":
            self._jump_type = "conditional"
            self._falls_to = exit_info[0]
            self._jump_to = exit_info[1]
        elif type_block == "Jump":
            self._jump_type = "unconditional"
            self._jump_to = exit_info[0]
        elif type_block == "":
            self._jump_type = "terminal"
        #We do not store the direction as itgenerates a loop
        elif type_block == "MainExit":
            self._jump_type = "mainExit"
            self._jump_to = exit_info[0]

    def get_as_json(self):
        block_json = {}
        block_json["id"] = self.block_id

        instructions_json = []
        for i in self._instructions:
            i_json = i.get_as_json()
            instructions_json.append(i_json)

        block_json["instructions"] = instructions_json
        
        blocks_json["exit"] = self.block_id+"Exit"
        blocks_json["type"] = "BasicBlock"

        if self._jump_type == "conditional":
            jump_block = {}
            jump_block["id"] = self.block_id+"Exit"
            jump_block["instructions"] = []
            jump_block["type"] = "ConditionalJump"
            jump_block["exit"] = [self._falls_to, self._jump_to]
            jump_block["cond"] = self._instructions[-1].get_out_args()

        elif self._jump_type == "unconditional":
            jump_block = {}
            jump_block["id"] = self.block_id+"Exit"
            jump_block["instructions"] = []
            jump_block["type"] = "Jump"
            jump_block["exit"] = [self._jump_to]

        elif self._jump_type == "mainExit":
            jump_block = {}
            jump_block["id"] = self.block_id+"Exit"
            jump_block["instructions"] = []
            jump_block["type"] = "MainExit"
            jump_block["exit"] = [self._jump_to]

        return block_json, jump_block
    


    def _get_vars_spec(self, uninter_instructions):
        vars_spec = set()

        for i in uninter_instructions:
            all_vars = i["inpt_sk"]+i["outpt_sk"]
            for a in all_vars:
                vars_spec.add(a)

        return list(vars_spec)



    def _build_spec_for_block(self, instructions):
        spec = {}

        uninter_functions = []
        map_instructions = {}
        instrs_idx = {}
        out_idx = 0

        input_stack = []
        output_stack = []
        
        i = 0
        
        for i in range(len(instructions)):
            #Check if it has been already created
            
            ins = instructions[i]
            
            ins_spec = map_instructions.get((ins.get_op_name().upper(),tuple(ins.get_in_args())), None)

            if ins_spec == None:
                #if not
                result, out_idx = ins.build_spec(out_idx,instrs_idx, map_instructions)

                uninter_functions+=result

                for i_arg in ins.get_in_args():
                    if not i_arg.startswith("0x"):
                        member = is_in_input_stack(i_arg,instructions[:i])

                        if member:
                            input_stack.append(i_arg)


                for o_arg in  ins.get_out_args():
                    member = is_in_output_stack(o_arg, instructions[i+1:])
                    if member:
                        output_stack = [o_arg]+output_stack



        spec["original_instrs"] = list(map(lambda x: x.get_instruction_representation(),instructions))
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
        spec["rules"] = False
        
        return spec

        
    
    def build_spec(self):
        ins_seq = []

        specifications = {}

        cont = 0
        
        i = 0
        for i in range(len(self._instructions)):
            ins = self._instructions[i]
            if ins.get_op_name().upper() in constants.split_block:
                if  ins_seq != []:
                    r = self._build_spec_for_block(ins_seq)
                    specifications["block"+str(self.block_id)+"_"+str(cont)] = r
                    cont +=1
                    print("block"+str(self.block_id)+"_"+str(cont))
                    print(r)
                    print("******************")
                    ins_seq = []
            else:
                ins_seq.append(ins)

        r = self._build_spec_for_block(ins_seq)
        specifications["block"+str(self.block_id)+"_"+str(cont)] = r
        print("block"+str(self.block_id)+"_"+str(cont))
        print(r)
        return specifications
        

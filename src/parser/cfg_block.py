import itertools
import logging

from global_params.types import instr_id_T, dependencies_T, var_id_T, block_id_T, function_name_T, SMS_T
from parser.cfg_instruction import CFGInstruction, build_push_spec, build_pushtag_spec
from parser.utils_parser import replace_pos_instrsid, replace_aliasing_spec, detect_unused_instructions, delete_unsued_instructions_from_deps
from analysis.instruction_dependencies import compute_memory_dependences, compute_storage_dependences, simplify_dependences
import parser.constants as constants
import json
import networkx as nx
from parser.constants import split_block
from enum import Enum, auto
from typing import List, Dict, Tuple, Any, Set, Optional

global tag_idx
tag_idx = 0

global function_tags
function_tags = {}


class JumpTypes(Enum):
    """
    Class to represent the different types of exits associated to a block
    """
    CONDITIONAL = auto()
    UNCONDITIONAL = auto()
    TERMINATED = auto()
    MAIN_EXIT = auto()
    FUNCTION_EXIT = auto()


def include_function_call_tags(ins, out_idx, block_spec):
    global function_tags
    global tag_idx

    in_tag, out_tag = function_tags.get(ins.get_op_name(), (-1, -1))

    if in_tag == -1 and out_tag == -1:
        out_tag = tag_idx
        in_tag = tag_idx + 1
        tag_idx += 2

        function_tags[ins.get_op_name()] = (in_tag, out_tag)

    in_tag_instr = build_pushtag_spec(out_idx, in_tag)
    out_idx += 1

    out_tag_instr = build_pushtag_spec(out_idx, out_tag)

    block_spec["user_instrs"] += [in_tag_instr, out_tag_instr]

    # It adds the out jump label after the arguments of the function
    num_funct_arguments = len(ins.get_in_args())
    block_spec["tgt_ws"] = block_spec["tgt_ws"][:num_funct_arguments] + out_tag_instr["outpt_sk"] + block_spec[
                                                                                                        "tgt_ws"][
                                                                                                    num_funct_arguments:]

    # It adds at top of the stack de input jump label
    block_spec["tgt_ws"] = in_tag_instr["outpt_sk"] + block_spec["tgt_ws"]

    # It adds in variables the new identifier for the in and out jump label
    block_spec["variables"] += in_tag_instr["outpt_sk"] + out_tag_instr["outpt_sk"]

    block_spec["yul_expressions"] += "\n" + ins.get_instruction_representation()

    return block_spec, out_idx


class CFGBlock:
    """
    Class for representing a cfg block
    """
    
    def __init__(self, identifier: block_id_T, instructions: List[CFGInstruction], type_block: str,
                 assignment_dict: Dict[str, str]):
        self.block_id = identifier
        self._instructions = instructions

        # Split instruction is recognized as the last instruction
        # As we don't have information on the function calls, we assign it to None and then
        # identify it once we set the function calls
        self._split_instruction = None

        self._jump_type = type_block
        self._jump_to = None
        self._falls_to = None
        self._condition = None
        self.assignment_dict = assignment_dict
        self.is_function_call = False
        self._comes_from = []
        self.function_calls = set()
        self._previous_type = None

        # Stack elements that must be placed in a specific order in the stack after performing
        self._final_stack_elements: List[str] = self._split_instruction.get_out_args() \
            if self._split_instruction is not None else []

        # Entries corresponds to the predecessors blocks from which the value of a phi function
        # at position i is generated. Hence, all phi functions must define the values in the same order
        self._entries: List[block_id_T] = []

        self._spec: SMS_T = None
        self._greedy_ids: List[instr_id_T] = None

        # Sets that represent which variables can be reached using a DUP instruction.
        # Useful for determining when to store a variable
        self._reachable_in: Set[var_id_T] = None
        self._reachable_out: Set[var_id_T] = None

        # Set of variables that are computed in the current block
        self._id2var = None

        self.liveness = {}

    @property
    def final_stack_elements(self) -> List[str]:
        """
        Stack elements that must be placed in a specific order in the stack after performing the operations
        in the block. It can be either the condition of a JUMPI or when invoking a function just after a sub block
        """
        return self._split_instruction.get_out_args() if self._split_instruction is not None else []

    @property
    def split_instruction(self) -> Optional[CFGInstruction]:
        return self._split_instruction

    @split_instruction.setter
    def split_instruction(self, value: CFGInstruction) -> None:
        self._split_instruction = value

    @property
    def entries(self) -> List[block_id_T]:
        return self._entries

    @entries.setter
    def entries(self, value: List[block_id_T]) -> None:
        self._entries = value

    def get_condition(self) -> Optional[var_id_T]:
        return self._condition

    def set_condition(self, cond: var_id_T) -> None:
        self._condition = cond

    def get_block_id(self) -> str:
        return self.block_id

    def set_block_id(self, value: var_id_T) -> None:
        self.block_id = value

    def get_instructions(self) -> List[CFGInstruction]:
        return self._instructions

    def rename_cfg(self, renaming_dict: Dict[var_id_T, var_id_T]) -> None:
        """
        Changes the successors and predecessors according to the renaming dict
        """
        self._jump_to = renaming_dict.get(self._jump_to, self._jump_to)
        self._falls_to = renaming_dict.get(self._falls_to, self._falls_to)
        self._comes_from = [renaming_dict.get(predecessor, predecessor) for predecessor in self._comes_from]
        self._entries = [renaming_dict.get(entry, entry) for entry in self._entries]

    def instructions_without_phi_functions(self) -> List[CFGInstruction]:
        return [instr for instr in self._instructions if instr.get_op_name() != "PhiFunction"]

    def phi_instructions(self) -> List[CFGInstruction]:
        return [instr for instr in self._instructions if instr.get_op_name() == "PhiFunction"]

    def remove_instruction(self, instr_idx: int) -> CFGInstruction:
        """
        Removes the instruction at position instr_index, updating the last split instruction if it affects
        the last instruction
        """

        instr_idx = (len(self._instructions) + instr_idx) % len(self._instructions)
        if instr_idx >= len(self._instructions):
            raise ValueError("Attempting to remove an instruction index out of bounds")
        if instr_idx == len(self._instructions) - 1:
            # There is no split instruction at this point
            self._split_instruction = None

        return self._instructions.pop(instr_idx)

    def insert_instruction(self, index: int, instruction: CFGInstruction) -> None:
        self._instructions.insert(index, instruction)


    def get_liveness(self):
        return self.liveness

    def set_liveness(self, liveness_set: Dict[str,List[str]]):
        self.liveness = liveness_set
        
    def get_instructions_to_compute(self) -> List[CFGInstruction]:
        return [instruction for instruction in self._instructions if instruction.must_be_computed()]

    def get_jump_type(self) -> str:
        return self._jump_type

    def get_jump_to(self) -> str:
        return self._jump_to

    def get_falls_to(self) -> str:
        return self._falls_to

    @property
    def successors(self) -> List[block_id_T]:
        return [next_block for next_block in [self._jump_to, self._falls_to] if next_block is not None]

    @property
    def previous_type(self) -> str:
        return self._previous_type

    @previous_type.setter
    def previous_type(self, previous_type: str):
        self._previous_type = previous_type

    def is_function_call(self) -> bool:
        return self.is_function_call

    def set_function_call(self, v) -> None:
        self.is_function_call = v

    def add_comes_from(self, block_id: str) -> None:
        self._comes_from.append(block_id)

    def get_comes_from(self) -> List[str]:
        return self._comes_from

    def set_comes_from(self, new_comes_from: List[str]) -> None:
        self._comes_from = new_comes_from

    def set_jump_type(self, t: str) -> None:
        if t not in ["conditional", "unconditional", "terminal", "falls_to", "sub_block", "mainExit"]:
            raise Exception("Wrong jump type")
        else:
            self._jump_type = t

    def set_jump_to(self, blockId: str) -> None:
        self._jump_to = blockId

    def set_falls_to(self, blockId: str) -> None:
        self._falls_to = blockId

    def set_length(self) -> int:
        return len(self._instructions)

    def insert_jump_instruction(self, tag_value: str) -> None:
        """
        Inserts a JUMP instruction and the corresponding tag
        """
        # Add a PUSH tag instruction
        self._instructions.append(CFGInstruction("PUSH [tag]", [], [tag_value]))

        # Add a JUMP instruction
        jump_instr = CFGInstruction("JUMP", [tag_value], [])
        self._instructions.append(jump_instr)
        self._split_instruction = jump_instr

    def insert_jumpi_instruction(self, tag_value: str) -> None:
        """
        Inserts a JUMPI instruction and the corresponding tag
        """

        assert self._condition is not None, \
            f"Trying to introduce a JUMPI with an empty condition in block {self.block_id}"

        # Add a PUSH tag instruction
        self._instructions.append(CFGInstruction("PUSH [tag]", [], [tag_value]))

        # Add a JUMPI instruction
        jumpi_instr = CFGInstruction("JUMPI", [self._condition, tag_value], [])
        self._instructions.append(jumpi_instr)

        # Finally, assign the JUMPI instruction to the split one
        self._split_instruction = jumpi_instr

    def _process_instructions_from_function_return(self, values: List[var_id_T]):
        """
        Introduces an extra operation representing the application of a return function.
        Hack which guarantees the liveness and layout analysis generate the correct stack
        """
        function_return = CFGInstruction("functionReturn", list(reversed(values)), [])
        self._instructions.append(function_return)
        self._split_instruction = function_return

    def set_jump_info(self, exit_info: Dict[str, Any]) -> None:
        type_block = exit_info["type"]
        if type_block in ["ConditionalJump"]:
            targets = exit_info["targets"]
            self._jump_type = "conditional"
            self._falls_to = targets[0]
            self._jump_to = targets[1]
            self._condition = exit_info["cond"]

        elif type_block in ["Jump"]:
            targets = exit_info["targets"]
            self._jump_type = "unconditional"
            self._jump_to = targets[0]
            # Add to the instructions a JUMP

        elif type_block in ["Terminated"]:
            # We do not store the direction as it generates a loop
            self._jump_type = "terminal"
        elif type_block in [""]:
            # It corresponds to falls_to blocks
            self._jump_type = "falls_to"
        elif type_block in ["MainExit"]:
            self._jump_type = "mainExit"
        elif type_block in ["FunctionReturn"]:
            self._jump_type = "FunctionReturn"
            self._process_instructions_from_function_return(exit_info["returnValues"])

    def process_function_calls(self, function_ids):
        op_names = map(lambda x: x.get_op_name(), self._instructions)
        calls = filter(lambda x: x in function_ids, op_names)
        self.function_calls = set(calls)

        # Finally, we identify the possible split instruction using the now generated information
        if len(self._instructions) > 0 and \
                self._instructions[-1].get_op_name() in itertools.chain(split_block, self.function_calls, ["JUMP","JUMPI"]):
            self._split_instruction = self._instructions[-1]

    @property
    def instructions_to_synthesize(self) -> List[CFGInstruction]:
        if self.split_instruction is not None:
            prefix_instrs = self._instructions[:-1]
        else:
            prefix_instrs = self._instructions

        return [instr for instr in prefix_instrs if instr.get_op_name() != "PhiFunction"]

    @instructions_to_synthesize.setter
    def instructions_to_synthesize(self, value):
        raise NotImplementedError("The instructions for the greedy algorithm cannot be assigned")

    def check_validity_arguments(self):
        """
        It checks for each instruction in the block that there is not
        any previous instruction that uses as input argument the variable
        that is generating as output (there is not aliasing).
        """

        for i in range(len(self._instructions)):
            instr = self._instructions[i]
            out_var = instr.get_out_args()
            if len(out_var) > 0:
                out_var_set = set(out_var)
                pred_inputs = map(lambda x: set(x.get_in_args()).intersection(out_var_set), self._instructions[:i + 1])
                candidates = list(filter(lambda x: x != set(), pred_inputs))
                if len(candidates) != 0:
                    logging.warning("[WARNING]: Aliasing between variables!")

    def _process_dependences(self, instructions: List[CFGInstruction],
                             map_positions: Dict[int, instr_id_T]) -> Tuple[dependencies_T, dependencies_T]:
        """
        Given the list of instructions and a dict that maps each position in a sequence to the instruction id, generates
        a list of dependencies
        """
        sto_dep = compute_storage_dependences(instructions)
        sto_dep = simplify_dependences(sto_dep)
        sto_deps = replace_pos_instrsid(sto_dep, map_positions)

        mem_dep = compute_memory_dependences(instructions)
        mem_dep = simplify_dependences(mem_dep)
        mem_deps = replace_pos_instrsid(mem_dep, map_positions)
        return sto_deps, mem_deps


    def translate_opcodes(self, objects_keys, next_idx, subobjects_idx):
        for ins in self._instructions:
            next_idx = ins.translate_opcode(objects_keys, next_idx, subobjects_idx)

        return next_idx
    
    def get_stats(self):
        return len(self._instructions)

    
    def get_as_json(self):
        block_json = {}
        block_json["id"] = self.block_id

        instructions_json = []
        for i in self._instructions:
            i_json = i.get_as_json()
            instructions_json.append(i_json)

        block_json["instructions"] = instructions_json

        block_json["exit"] = self.block_id + "Exit"
        block_json["type"] = "BasicBlock"

        jump_block = {}

        if self._jump_type == "conditional":
            jump_block["id"] = self.block_id + "Exit"
            jump_block["instructions"] = []
            jump_block["type"] = "ConditionalJump"
            jump_block["exit"] = [self._falls_to, self._jump_to]
            jump_block["cond"] = self._instructions[-1].get_out_args()

        elif self._jump_type == "unconditional":
            jump_block["id"] = self.block_id + "Exit"
            jump_block["instructions"] = []
            jump_block["type"] = "Jump"
            jump_block["exit"] = [self._jump_to]

        elif self._jump_type == "mainExit":
            jump_block["id"] = self.block_id + "Exit"
            jump_block["instructions"] = []
            jump_block["type"] = "MainExit"
            jump_block["exit"] = [self._jump_to]

        block_json["comes_from"] = self._comes_from
        return block_json, jump_block

    def _get_vars_spec(self, uninter_instructions):
        vars_spec = set()

        for i in uninter_instructions:
            all_vars = i["inpt_sk"] + i["outpt_sk"]
            for a in all_vars:
                vars_spec.add(a)

        return list(vars_spec)

    def _build_spec_for_sequence(self, instructions: List[CFGInstruction], map_instructions: Dict, out_idx,
                                 initial_stack: List[str], final_stack: List[str]):
        """
        Builds the specification for a sequence of instructions. "map_instructions" is passed as an argument
        to reuse declarations from other blocks, as we might have split the corresponding basic block
        """
        
        spec = {}

        uninter_functions = []
        instrs_idx = {}
        new_out_idx = out_idx

        map_positions_instructions = {}

        #Key is the original variable and the value is the one that we use
        aliasing_dict = {}

        unprocessed_instr = None

        for i, ins in enumerate(instructions):
            # Check if it has been already created
            if ins.get_op_name().startswith("push"):
                ins_spec = map_instructions.get((ins.get_op_name().upper(), tuple(ins.get_literal_args())), None)
            elif not ins.memory_operation():
                ins_spec = map_instructions.get((ins.get_op_name().upper(), tuple(ins.get_in_args())), None)
            else:
                ins_spec = map_instructions.get((ins.get_op_name().upper(), tuple(ins.get_in_args())), None)
                if ins.get_op_name().startswith("LiteralAssigment") and ins_spec != None:
                    raise Exception("LOOK: Two different literalAssigments with the same value")
                
                if ins_spec is not None:
                    if len(ins_spec["outpt_sk"]) == 0 or ins_spec["outpt_sk"] != ins.get_out_args():
                        # Memory operations have an extra check: repeated keccaks or loads with the same arguments
                        # generate no instruction unless their output stack value is different
                        ins_spec = None
                    else:
                        map_positions_instructions[i] = ins_spec["id"]

            if ins_spec is None:
                if ins.get_op_name().startswith("LiteralAssignment"):
                    in_val = ins.get_in_args()[0]
                    push_name = "PUSH" if int(in_val, 16) != 0 else "PUSH0"
                    inst_idx = instrs_idx.get(push_name, 0)
                    instrs_idx[push_name] = inst_idx + 1
                    push_ins = build_push_spec(in_val, inst_idx, ins.get_out_args())

                    map_instructions[("LITERALASSIGMENT", tuple(ins.get_in_args()))] = push_ins

                    uninter_functions.append(push_ins)
                    
                else:
                    result, new_out_idx = ins.build_spec(new_out_idx, instrs_idx, map_instructions)
                    uninter_functions += result

                map_positions_instructions[i] = uninter_functions[-1]["id"]

            # it is a push value that has been already created. If it comes from a memoryguard,
            # we have to rename the previous instructions to the output of the memoryguard
            elif ins_spec != None and ins.get_op_name() == "push":
                out_var_list = ins_spec["outpt_sk"]
                new_out_var_list = ins.get_out_args()

                ins_spec["outpt_sk"] = new_out_var_list

                out_var = out_var_list[0]
                new_out_var = new_out_var_list[0]

                candidate_instructions = filter(lambda x: out_var in x["inpt_sk"],uninter_functions)
                for uninter in candidate_instructions:
                    pos = uninter["inpt_sk"].index(out_var)
                    uninter["inpt_sk"][pos] = new_out_var

            #ins_spec != None. We have to rename the aliasing information
            else:
                old_variable = ins.get_out_args()[0]
                aliasing_dict[old_variable] = ins_spec["outpt_sk"][0]

        # We must remove the final output variable from the unprocessed instruction and
        # add the inputs from that instruction
        if self.split_instruction is not None:
            unprocess_out = self.split_instruction.get_out_args()

            # As the unprocessed instruction is not considered as part of the SFS,
            # we must remove the corresponding values from the final stack
            final_stack_bef_jump = self.split_instruction.get_in_args() + final_stack[len(unprocess_out):]

        else:
            final_stack_bef_jump = final_stack

        # If there is a bottom value in the final stack, then we introduce it as part of the assignments and
        # then we pop it. Same for constant values in the final stack
        assignments_out_to_remove = set()
        for stack_value in final_stack_bef_jump:
            if stack_value == "bottom" or stack_value.startswith("0x"):
                self.assignment_dict[stack_value] = "0x00" if stack_value == "bottom" else stack_value
                assignments_out_to_remove.add(stack_value)

        # Assignments might be generated from phi functions
        for out_val, in_val in self.assignment_dict.items():
            # if is_used:

            if in_val.startswith("0x"):  # It is a push value
                func = map_instructions.get(("PUSH", tuple([in_val])), -1)
                if func == -1:
                    push_name = "PUSH" if int(in_val, 16) != 0 else "PUSH0"
                    inst_idx = instrs_idx.get(push_name, 0)
                    instrs_idx[push_name] = inst_idx + 1
                    push_ins = build_push_spec(in_val, inst_idx, [out_val])

                    map_instructions[("PUSH", tuple([in_val]))] = push_ins

                    uninter_functions.append(push_ins)
                    aliasing_dict[out_val] = out_val
                else:
                    aliasing_dict[out_val] = func["outpt_sk"][0]

        # After constructing the specification, we remove the auxiliary values we have introduced in the
        # assignment dict
        for assignment_out in assignments_out_to_remove:
            self.assignment_dict.pop(assignment_out, None)

        instr_repr = '\n'.join([instr.get_instruction_representation() for instr in self._instructions])
        assignment_repr = '\n'.join(
            [f"{out_value} = {in_value}" for out_value, in_value in self.assignment_dict.items()])

        combined_repr = '\n'.join(repr_ for repr_ in [assignment_repr, instr_repr] if repr_ != "")

        spec["original_instrs"] = ""
        spec["yul_expressions"] = combined_repr
        spec["src_ws"] = initial_stack

        # Some of the final stack values can correspond to constant values already assigned, so we need to
        # unify the format with the corresponding representative stack variable
        tgt_stack = [aliasing_dict.get(stack_value, stack_value) for stack_value in final_stack_bef_jump]
        spec["tgt_ws"] = tgt_stack

        # There can be instructions in the list of user instructions that do not need to be computed. We remove
        # them before assigning
        unused_instruction_ids = detect_unused_instructions(uninter_functions, tgt_stack)
        filtered_uninter_functions = [instr for instr in uninter_functions if instr["id"] not in unused_instruction_ids]

        spec["user_instrs"] = filtered_uninter_functions
        vars_list = self._get_vars_spec(filtered_uninter_functions)
        spec["variables"] = vars_list

        spec["memory_dependences"] = []
        spec["storage_dependences"] = []

        # They are not used in greedy algorithm
        spec["init_progr_len"] = 0
        spec["max_progr_len"] = 0
        spec["min_length_instrs"] = 0
        spec["min_length_bounds"] = 0
        spec["min_length"] = 0
        spec["rules"] = ""
        spec["name"] = self.block_id

        if aliasing_dict != {}:
            replace_aliasing_spec(aliasing_dict, filtered_uninter_functions, vars_list, tgt_stack)

        return spec, new_out_idx, map_positions_instructions, unused_instruction_ids

    def _include_jump_tag(self, block_spec: Dict, out_idx: int, block_tags_dict: Dict, block_tag_idx: int) -> \
            Tuple[Dict, int, int]:
        tag_idx = block_tags_dict.get(self._jump_to, block_tag_idx)

        if self._jump_to not in block_tags_dict:
            block_tags_dict[self._jump_to] = block_tag_idx
            block_tag_idx += 1

        tag_instr = build_pushtag_spec(out_idx, tag_idx)
        out_idx += 1

        block_spec["user_instrs"].append(tag_instr)

        # It adds on top of the stack the jump label
        block_spec["tgt_ws"] = tag_instr["outpt_sk"] + block_spec["tgt_ws"]

        # It adds in variables the new identifier for jump label
        block_spec["variables"] += tag_instr["outpt_sk"]

        return block_spec, out_idx, block_tag_idx

    def build_spec(self, initial_stack: List[str], final_stack: List[str]) -> Dict[str, Any]:
        
        map_instructions = {}

        out_idx = 0

        spec, out_idx, map_positions, unused_ids = self._build_spec_for_sequence(self.instructions_to_synthesize, map_instructions, out_idx,
                                                                     initial_stack, final_stack)
        with open("sms.json", 'w') as f:
            json.dump(spec, f, indent=4)

        sto_deps, mem_deps = self._process_dependences(self.instructions_to_synthesize, map_positions)
        sto_deps, mem_deps = delete_unsued_instructions_from_deps(sto_deps,mem_deps, unused_ids)
        spec["storage_dependences"] = sto_deps
        spec["memory_dependences"] = mem_deps
        spec["dependencies"] = [*sto_deps, *mem_deps]

        # Just to print information if it is not a jump
        if not self._jump_type in ["conditional", "unconditional"]:
            logging.debug(f"Building Spec of block {self.block_id}...")
            logging.debug(json.dumps(spec, indent=4))

        return spec

    @property
    def spec(self) -> SMS_T:
        return self._spec

    @spec.setter
    def spec(self, spec: SMS_T) -> None:
        if self._spec is not None:
            raise ValueError("Specification already computed")
        self._spec = spec

        # We also assigne the set of reachable stack values at the beginning and end of the block
        self._reachable_in = set(spec["src_ws"][:16])
        self._reachable_out = set(spec["tgt_ws"][:16])

    @property
    def greedy_ids(self) -> List[instr_id_T]:
        return self._greedy_ids

    @greedy_ids.setter
    def greedy_ids(self, greedy_ids: List[instr_id_T]) -> None:
        self._greedy_ids = greedy_ids

    def is_accessible_in(self, var_id: var_id_T):
        """
        Given a stack variable, detects whether it can be accessed
        with a DUPx instruction by the beginning of the block
        """
        assert self._reachable_in is not None, "Trying to access reachable_in when not computed yet"
        return var_id in self._reachable_in

    def is_accessible_out(self, var_id: var_id_T):
        """
        Given a stack variable, detects whether it can be accessed
        with a DUPx instruction by the end of the block
        """
        assert self._reachable_out is not None, "Trying to access reachable_out when not computed yet"
        return var_id in self._reachable_out

    def _compute_declared_variables(self):
        """
        Returns a dict that links every stack variable to the id of the instruction that
        introduced it
        """
        return {instr["id"]: instr["outpt_sk"]  for instr in self._spec["user_instrs"]}

    @property
    def declared_variables(self) -> Set[var_id_T]:
        """
        Variables declared in the block
        """
        if self._id2var is None:
            self._id2var = self._compute_declared_variables()
        return set(out_var for out_var_list in self._id2var.values() for out_var in out_var_list)

    def out_vars_from_id(self, instr_id: instr_id_T) -> List[var_id_T]:
        """
        Returns the out vars associated to an instruction id.
        Assumes the id belongs to the spec
        """
        if self._id2var is None:
            self._id2var = self._compute_declared_variables()

        return self._id2var.get(instr_id, [])

    def __str__(self):
        s = "BlockID: " + self.block_id + "\n"
        s += "Type: " + self._jump_type + "\n"
        s += "Jump to: " + str(self._jump_to) + "\n"
        s += "Falls to: " + str(self._falls_to) + "\n"
        s += "Comes_from: " + str(self._comes_from) + "\n"
        s += "Instructions: " + str(self._instructions) + "\n"
        return s

    def __repr__(self):
        return json.dumps(self.get_as_json())

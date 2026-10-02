import collections
"""
Module that contains the methods for reconstructing the bytecode in different formats
"""
import json
from typing import Dict, Any, List, Optional, Union, Iterable, Tuple
from solution_generation.utils import to_hex_default
from global_params.types import SMS_T, ASM_bytecode_T, ASM_contract_T, block_id_T, function_name_T
from parser.cfg import CFG
from parser.cfg_object import CFGObject
from parser.cfg_function import CFGFunction
from parser.cfg_block_list import CFGBlockList
from parser.cfg_block import CFGBlock
from parser.cfg_instruction import CFGInstruction
from cfg_methods.jump_insertion import tag_from_tag_dict
from reparation.utils import PUSH_CONSTANT
import parser.opcodes as opcodes
import global_params.constants as constants
from pathlib import Path
import networkx as nx


# Solution ids to EVM assembly


def asm_from_op_info(op: str, value: Optional[Union[int, str]] = None,
                     jump_type: Optional[str] = None, source: Optional[int] = -1) -> ASM_bytecode_T:
    """
    JSON asm initialized with default values
    """
    
    default_asm = {"name": op, "begin": -1, "end": -1, "source": source}

    if value is not None:
        default_asm["value"] = str(value).upper()

    if jump_type is not None:
        default_asm["jumpType"] = jump_type

    return default_asm


def id_to_asm_bytecode(uf_instrs: Dict[str, Dict[str, Any]], instr_id: str) -> ASM_bytecode_T:
    """
    Given the dictionary of instructions in a SMS and an id, generates the corresponding ASM JSON
    """
    if instr_id in uf_instrs:
        associated_instr = uf_instrs[instr_id]

        # Special case: reconstructing PUSH0 (see sfs_generator/parser_asm.py)
        if associated_instr["disasm"] == "PUSH0":
            return asm_from_op_info("PUSH", "0")
        # Special PUSH cases that were transformed to decimal are analyzed separately
        elif associated_instr['disasm'] == "PUSH" or associated_instr['disasm'] == "PUSH data" \
                or associated_instr['disasm'] == "PUSHIMMUTABLE" or associated_instr['disasm'] == "ASSIGNIMMUTABLE":
            value = to_hex_default(associated_instr['value'][0])
            return asm_from_op_info(associated_instr['disasm'], value)
        elif associated_instr["disasm"] == "PUSH [TAG]":
            value = int(associated_instr["outpt_sk"][0])
            return asm_from_op_info("PUSH [tag]", value)
        else:
            return asm_from_op_info(associated_instr['disasm'],
                                    None if 'value' not in associated_instr else associated_instr['value'][0])

    # Constants pushed by the reparation ("PUSH-CONSTANT 0x20"): the asm JSON values have no 0x prefix
    elif instr_id.startswith(PUSH_CONSTANT):
        value = instr_id.split(' ')[1]
        return asm_from_op_info("PUSH", value[2:] if value.startswith("0x") else value)
    elif "PUSH" in instr_id:
        value = instr_id.split(' ')[1]
        return asm_from_op_info("PUSH", value)
    else:
        # The id is the instruction itself (SWAPx, DUPx, ...)
        # a PUSH instruction or a MSTORE
        return asm_from_op_info(instr_id)


def id_seq_to_asm_bytecode(uf_instrs: Dict[str, Dict[str, Any]], id_seq: List[str]) -> List[ASM_bytecode_T]:
    """
    Converts a sequence of ids from the greedy algorithm to assembly bytecode
    """
    return [id_to_asm_bytecode(uf_instrs, instr_id) for instr_id in id_seq if instr_id != 'NOP']


def asm_from_ids(sms: SMS_T, id_seq: List[str]) -> List[ASM_bytecode_T]:
    """
    Converts the result from the greedy algorithm and the block specification into a list of JSON asm opcodes
    """
    instr_id_to_instr = {instr['id']: instr for instr in sms['user_instrs']}
    return id_seq_to_asm_bytecode(instr_id_to_instr, id_seq)


def asm_for_split_instruction(split_ins: CFGInstruction, function_name2entry: Dict[block_id_T, block_id_T]) -> List[ASM_bytecode_T]:
    """
    Reconstructs the assembly from a block with a single split instruction. If the split instruction is a
    function invocation, then it replaces it by the corresponding JUMP instruction
    """
    entry_block = function_name2entry.get(split_ins.get_op_name(), None)
    if entry_block is not None:
        # Introduces two tags: one for jumping to the instruction and one for returning.
        # Afterwards, introduce a JUMP instruction to invoke the function
        asm_ins = asm_from_op_info("JUMP", jump_type="[in]")

        asm_subblock = [asm_ins]

    elif split_ins.get_op_name() == "functionReturn":
        # For function returns, we replace them by a JUMP instruction
        asm_subblock = [asm_from_op_info("JUMP", jump_type="[out]")]

    elif split_ins.get_op_name().startswith("verbatim"):
        asm_subblock =[asm_from_op_info("VERBATIM", 0)] #WARNING: Value assigned to verbatim is 0

    elif split_ins.get_op_name().startswith("assignimmutable"):
        literal_args = split_ins.get_literal_args()
        value = to_hex_default(literal_args[0])
        asm_subblock = [asm_from_op_info(split_ins.get_op_name().upper(), value if literal_args is not None and len(literal_args) > 0 else None)]

    else:
        # Just include the corresponding instruction and the value field for builtin translations
        literal_args = split_ins.get_literal_args()
        asm_subblock = [asm_from_op_info(split_ins.get_op_name().upper(), literal_args[0] if literal_args is not None and
                                                                                       len(literal_args) > 0 else None)]
    return asm_subblock


def generate_asm_split_blocks(init_block_id: block_id_T, blocks: Dict[block_id_T, CFGBlock], tags_dict: Dict[block_id_T, int],
                              function_name2entry: Dict[function_name_T, block_id_T]) -> Tuple[CFGBlock, List[ASM_bytecode_T]]:
    """
    Joins all the instructions inside the sub blocks until we reach a function call or all sub blocks are combined.
    """
    asm_block = []

    block = blocks[init_block_id]

    jump_type = block.get_jump_type()
    is_function_call = block.split_instruction.op in function_name2entry
    while jump_type == "sub_block" and not is_function_call:

        if jump_type == "sub_block":
            asm_subblock = asm_from_ids(block.spec, block.greedy_ids)
            assert block.split_instruction is not None, \
                f"[ERROR]: Block {block.block_id} split_instructions has to contain a value in a subblock"
            asm_last = asm_for_split_instruction(block.split_instruction, function_name2entry)

        else:
            raise Exception("[ERROR]: Jump type can only be sub_block")

        asm_block += asm_subblock + asm_last
        block_id = block.get_falls_to()
        block = blocks[block_id]

        jump_type = block.get_jump_type()
        is_function_call = block.split_instruction.op in function_name2entry

    # We translate the last block
    asm_subblock = asm_from_ids(block.spec, block.greedy_ids)

    # Split instruction contains both jumps and not handled instructions
    if block.split_instruction is not None:
        asm_last = asm_for_split_instruction(block.split_instruction, function_name2entry)
    else:
        asm_last = []

    asm_block += asm_subblock + asm_last
    return block, asm_block


def locate_fallsto_block(block_id, fallsto_block, pos_dict, visited, asm_instructions, asm_block, pending_blocks):
    fallsto_id = fallsto_block.get_block_id()
    try:
        # It means that the block has been analyzed previously
        pos = pos_dict.index(fallsto_id)
        assert fallsto_id in visited, \
            "[ERROR]: Falls_to block should be in visited list when generating asm output"

        asm_instructions = asm_instructions[:pos] + asm_block + asm_instructions[pos:]
        pos_dict = pos_dict[:pos] + [block_id] * len(asm_block) + pos_dict[pos:]

    except ValueError:
        asm_instructions += asm_block
        pos_dict += [block_id] * len(asm_block)

        pending_blocks.append(fallsto_block)

    return pos_dict, asm_instructions


def generate_function_name2entry(functions: Iterable[CFGFunction]) -> Dict[function_name_T, block_id_T]:
    """
    Links each function name to its initial block
    """
    return {function.name: function.blocks.start_block for function in functions}


def removable_edge_blocks(blocks: Dict[block_id_T, CFGBlock],
                          tags_dict: Dict[block_id_T, int]) -> Tuple[Dict[block_id_T, block_id_T], Dict[str, str]]:
    """
    Edge blocks (see cfg_methods.cfg_block_actions.edge_block) that end up doing nothing, i.e. their greedy ids
    only push the tag of their jump, are not emitted: their predecessor goes directly to their successor.
    - If the predecessor jumps to the edge block, the tag it pushes is replaced by the tag of the successor.
    - If the predecessor falls to the edge block, it falls directly to the successor, provided no other block
      falls to it (the reconstruction places a falls-to block right after its predecessor) and no block falls to
      the predecessor either: if the successor has already been placed, the predecessor is moved right before it,
      which would break the fall from its own predecessor. Otherwise, the edge block is kept.
    Chains of skipped blocks are followed, and the conditions are checked on the block finally reached.
    Returns the redirections (edge block -> block reached instead) and the tag aliases
    """
    def only_jumps(block: CFGBlock) -> bool:
        return len(block.greedy_ids) <= 1 and all(instr_id.startswith("PUSH [TAG]") for instr_id in block.greedy_ids)

    # With THREAD_EMPTY_BLOCKS, every unconditional block whose code is only its jump is a candidate (its input and
    # output stacks are the same, so its successor can be reached directly), except the entry of the block list
    # (referenced by the calls of other block lists) and self-loops
    start_blocks = {block_id for block_id, block in blocks.items() if not block.get_comes_from()}
    empty_blocks = [block_id for block_id, block in blocks.items()
                    if only_jumps(block) and (block.is_edge_block or
                                              (constants.THREAD_EMPTY_BLOCKS and block.get_jump_type() == "unconditional"
                                               and block_id not in start_blocks and block.get_jump_to() != block_id))]

    # Every candidate is skipped at first. Keeping a candidate only changes the block reached from the candidates
    # that lead to it, never the one reached from itself, so the conditions are decided from the end of the chains
    # backwards, in two linear passes, and no decision is revisited
    candidate_order = {block_id: position for position, block_id in enumerate(empty_blocks)}
    redirect: Dict[block_id_T, block_id_T] = {block_id: blocks[block_id].get_jump_to() for block_id in empty_blocks}

    # 1. Chains: a skipped block must lead to an emitted block with a tag (the pushes of its tag are replaced by it).
    # Each chain is resolved once, from the emitted block backwards, recording the emitted block reached and the
    # distance to it (depth):
    # * a cycle of empty blocks (an infinite loop without code; self-loops are not candidates) keeps the block where
    #   the cycle closes, and the others lead to it;
    # * a tagged block whose chain ends in a block without a tag is kept, and the blocks leading to it end there
    chain_target: Dict[block_id_T, block_id_T] = dict()
    depth: Dict[block_id_T, int] = dict()
    for start_id in empty_blocks:
        path, in_path = [], set()
        block_id = start_id
        while block_id in redirect and block_id not in depth:
            if block_id in in_path:
                del redirect[block_id]
                break
            in_path.add(block_id)
            path.append(block_id)
            block_id = redirect[block_id]

        for block_id in reversed(path):
            # The block that closes a cycle is no longer skipped
            if block_id not in redirect:
                continue
            successor_id = redirect[block_id]
            if successor_id in depth:
                target_id, target_depth = chain_target[successor_id], depth[successor_id] + 1
            else:
                target_id, target_depth = successor_id, 1
            if block_id in tags_dict and target_id not in tags_dict:
                del redirect[block_id]
            else:
                chain_target[block_id], depth[block_id] = target_id, target_depth

    # Emitted block reached from a block following the skipped blocks. The results are cached (path compression):
    # the falls below only keep blocks closer to the emitted block than the ones already resolved, so a cached
    # result is never invalidated by them
    resolved: Dict[block_id_T, block_id_T] = dict()

    def resolve(block_id: block_id_T) -> block_id_T:
        path = []
        while block_id in redirect and block_id not in resolved:
            path.append(block_id)
            block_id = redirect[block_id]
        target_id = resolved.get(block_id, block_id)
        for path_block_id in path:
            resolved[path_block_id] = target_id
        return target_id

    # 2. Falls: the reconstruction places a falls-to block right after its predecessor, so every emitted block can be
    # fallen into by a single emitted block, and a block whose fall is redirected (moved right before its new target
    # if that one has already been placed) cannot be fallen into, or that fall would break. The falls into blocks
    # that are not skipped (including the links between split sub-blocks) are fixed. The redirected ones are granted
    # one by one, counting only the fixed falls and the ones already granted; a denied fall keeps the skipped block
    # the predecessor falls into, which then becomes a fixed fall into that block. They are decided closest to the
    # emitted block first: when a fall is decided, every block kept in its chain has already been kept, so its
    # target is final. E.g. B0 falls -> edge -> B2 and B1 falls -> edge' -> B4 (empty) -> B2: B0's fall (depth 1)
    # is granted, and B1's (depth 2) reaches B2, already fallen into, so edge' is kept (checking only the immediate
    # successor B4 moved B1 right before B2, breaking the fall from B0). Deciding the falls in the order of the
    # candidates could also deny every fall into the same block: if P1 falls -> F1 -> F2 -> T and P2 falls -> F2,
    # granting P1 first denies P2 (keeping F2), which turns P1's target into F2, already fallen into by P2
    falls_to = {block_id: block.get_falls_to() for block_id, block in blocks.items()
                if block_id not in redirect and block.get_falls_to() is not None}
    fallen_into = collections.Counter(target_id for target_id in falls_to.values() if target_id not in redirect)
    moved = set()
    redirected_falls = sorted((block_id for block_id, target_id in falls_to.items() if target_id in redirect),
                              key=lambda block_id: (depth[falls_to[block_id]], candidate_order[falls_to[block_id]]))
    for block_id in redirected_falls:
        skipped_id = falls_to[block_id]
        target_id = resolve(skipped_id)
        if fallen_into[target_id] > 0 or fallen_into[block_id] > 0 or target_id in moved:
            del redirect[skipped_id]
            resolved.pop(skipped_id, None)
            fallen_into[skipped_id] += 1
        else:
            fallen_into[target_id] += 1
            moved.add(block_id)

    redirect = {block_id: resolve(block_id) for block_id in redirect}
    tag_aliases = {str(tags_dict[edge_id]).upper(): str(tags_dict[target_id]).upper()
                   for edge_id, target_id in redirect.items() if edge_id in tags_dict and target_id in tags_dict}
    return redirect, tag_aliases


def traverse_cfg_block_list(block_list: CFGBlockList, function_name2entry: Dict[function_name_T, block_id_T],
                            tags_dict: Dict[block_id_T, int], asm_dir: Optional[Path] = None) -> List[ASM_bytecode_T]:
    """
    Traverses the blocks in the block list to generate the serialized assembly code
    """
    blocks = block_list.get_blocks_dict()

    init_block = blocks[block_list.start_block]
    assert (init_block.get_block_id().find("Block0") != -1)

    # Edge blocks that do nothing are skipped
    redirect, tag_aliases = removable_edge_blocks(blocks, tags_dict)

    pending_blocks = [init_block]
    visited = []

    # It is used to know where we have to insert the asm instructions when we have a falls_to
    # It simulates the asm_instructions list with the identifiers of the blocks
    init_pos_dict = []

    asm_instructions = []
    graph = nx.DiGraph()
    relabel_dict = dict()

    while pending_blocks:
        next_block = pending_blocks.pop()

        block_id = next_block.get_block_id()

        # A block can be pushed several times before being visited (e.g. when it is the jump target of
        # several blocks), so we skip the ones already generated
        if block_id in visited:
            continue

        visited.append(block_id)
        
        asm_index = len(asm_instructions)

        # If the block has been split we regenerate the whole block together
        # next block contains the last block of the sequence
        if next_block.get_jump_type() in ["sub_block"]:
            next_block, asm_block = generate_asm_split_blocks(block_id, blocks, tags_dict, function_name2entry)
        else:
            asm_block = asm_from_ids(next_block.spec, next_block.greedy_ids)
            
            if next_block.split_instruction is not None:
                asm_last = asm_for_split_instruction(next_block.split_instruction, function_name2entry)
            else:
                # if it is a falls_to or terminal split_instruction is None
                # Otherwise it is jump or jumpi
                asm_last = []

            if asm_block == [] and next_block.get_jump_type() == "terminal":

                # Literal assignments generate no code (the constants are propagated)
                relevant_ins = [ins for ins in next_block.get_instructions()
                                if ins.get_op_name() not in ["PhiFunction", "pop", "LiteralAssignment"]]
                assert len(relevant_ins) == 1, f"Reconstruction from next block fails: {next_block.get_instructions()}"
                ins = relevant_ins[0]

                # Terminal blocks might contain calls to terminal functions (i.e. not so terminal...)
                asm_block = asm_for_split_instruction(ins, function_name2entry)

                if ins == next_block.split_instruction:
                    asm_block = []

            asm_block += asm_last

        if block_id in tags_dict:
            tag_asm = asm_from_op_info("tag", str(tags_dict[block_id]))
            jumpdest_asm = asm_from_op_info("JUMPDEST")
            asm_block = [tag_asm, jumpdest_asm] + asm_block

        jump_type = next_block.get_jump_type()
        falls_to, jump_to = None, None
        if jump_type == "conditional":

            jump_to = redirect.get(next_block.get_jump_to(), next_block.get_jump_to())
            falls_to = redirect.get(next_block.get_falls_to(), next_block.get_falls_to())

            if falls_to not in blocks or jump_to not in blocks:
                raise Exception("[ERROR]:...")

            if jump_to not in visited:
                pending_blocks.append(blocks[jump_to])

            # It checks if falls_to is in visited or not
            init_pos_dict, asm_instructions = locate_fallsto_block(block_id, blocks[falls_to], init_pos_dict, visited,
                                                                   asm_instructions, asm_block, pending_blocks)

        elif jump_type == "unconditional":
            asm_instructions += asm_block
            init_pos_dict += [block_id] * len(asm_block)

            jump_to = redirect.get(next_block.get_jump_to(), next_block.get_jump_to())

            if jump_to not in blocks:
                raise Exception("[ERROR]:...")

            if jump_to not in visited:
                pending_blocks.append(blocks[jump_to])

        elif jump_type == "falls_to" or jump_type == "sub_block":
            # Sub blocks now also fail into this case
            falls_to = redirect.get(next_block.get_falls_to(), next_block.get_falls_to())
            init_pos_dict, asm_instructions = locate_fallsto_block(block_id, blocks[falls_to], init_pos_dict, visited,
                                                                   asm_instructions, asm_block, pending_blocks)

        elif jump_type == "terminal" or jump_type == "FunctionReturn":

            asm_instructions += asm_block
            init_pos_dict += [block_id] * len(asm_block)

        elif jump_type == "mainExit":
            asm_instructions += asm_block + [asm_from_op_info("STOP")]
            init_pos_dict += [block_id] * (len(asm_block) + 1)

        else:
            raise Exception("[ERROR]: Unknown jump type when generating asm output")

        visited.append(block_id)

        if asm_dir is not None:
            if falls_to is not None:
                graph.add_node(falls_to)
                graph.add_edge(block_id, falls_to)

            if jump_to is not None:
                graph.add_node(jump_to)
                graph.add_edge(block_id, jump_to)

            relabel_dict[block_id] = '\n'.join([block_id] +
                                               [' '.join([instruction["name"], instruction.get("value", '')])
                                                for instruction in asm_instructions[asm_index:]])

    # The jumps to the skipped edge blocks go directly to their successors
    if tag_aliases:
        for instruction in asm_instructions:
            if instruction["name"] == "PUSH [tag]" and instruction.get("value") in tag_aliases:
                instruction["value"] = tag_aliases[instruction["value"]]

    if asm_dir is not None:
        renamed_digraph = nx.relabel_nodes(graph, relabel_dict)
        nx.nx_agraph.write_dot(renamed_digraph, asm_dir.joinpath(block_list.name + ".dot"))

    return asm_instructions


def reuse_free_memory_pointer(code: List[ASM_bytecode_T]) -> List[ASM_bytecode_T]:
    """
    The code of each object starts by storing the free memory pointer (mstore(0x40, 0x80)) and, if it uses 0x80
    again right away, pushes it again. Duplicating it instead saves one byte, and leaves the same stack ([0x80]):
    PUSH 80 PUSH 40 MSTORE PUSH 80  ->  PUSH 80 DUP1 PUSH 40 MSTORE
    """
    names = [(instruction["name"], instruction.get("value")) for instruction in code[:4]]
    if names == [("PUSH", "80"), ("PUSH", "40"), ("MSTORE", None), ("PUSH", "80")]:
        return [code[0], asm_from_op_info("DUP1"), code[1], code[2]] + code[4:]
    return code


BLOCK_END_INSTRUCTIONS = {"JUMP", "JUMPI", "STOP", "RETURN", "REVERT", "INVALID", "SELFDESTRUCT"}

# Instructions without side effects whose result only depends on their operands (number of operands)
PURE_INSTRUCTIONS = {"ADD": 2, "MUL": 2, "SUB": 2, "DIV": 2, "SDIV": 2, "MOD": 2, "SMOD": 2, "EXP": 2,
                     "SIGNEXTEND": 2, "LT": 2, "GT": 2, "SLT": 2, "SGT": 2, "EQ": 2, "ISZERO": 1, "AND": 2, "OR": 2,
                     "XOR": 2, "NOT": 1, "BYTE": 2, "SHL": 2, "SHR": 2, "SAR": 2}


def inlined_copy_size(body: List[ASM_bytecode_T]) -> int:
    """
    Estimation of the number of instructions of each copy of a function body once inlined. After inlining, solc's CSE
    analyses the copy together with the code of the call site, so:
      - A constant computed from pushes (e.g. the address mask PUSH 1 PUSH 1 PUSH A0 SHL SUB) counts as a single
        instruction when it is an operand of a pure operation whose other operands come from the caller (the function
        arguments or pure computations over them): the CSE can reuse the constant if it is already in the stack of the
        call site, or remove the operation if it is redundant (e.g. and(and(x, mask), mask)). Otherwise (operand of a
        memory/storage/calldata access or of an operation over a value computed from them), it counts all its
        instructions, as the call site cannot simplify it
      - The SWAPs at the end of the body only place the return address and disappear
    """
    trailing_swaps = 0
    for instruction in reversed(body):
        if not instruction["name"].startswith("SWAP"):
            break
        trailing_swaps += 1

    # Stack of (kind, instructions needed to compute it), with kind "constant", "argument" (from the caller),
    # "argument_pure" (pure computation over arguments and constants) or "opaque"
    stack = []
    size = 0

    def pop_operands(n: int) -> List[Tuple[str, int]]:
        while len(stack) < n:
            stack.insert(0, ("argument", 0))
        return [stack.pop() for _ in range(n)]

    def constants_size(operands: List[Tuple[str, int]], simplifiable: bool) -> int:
        return sum(1 if simplifiable else cost for kind, cost in operands if kind == "constant")

    for instruction in body[:len(body) - trailing_swaps]:
        name = instruction["name"]
        if name in ("PUSH", "PUSH0"):
            stack.append(("constant", 1))
        elif name.startswith("PUSH"):
            # PUSH [tag], PUSHIMMUTABLE, PUSH [$]...
            stack.append(("opaque", 0))
            size += 1
        elif name.startswith("DUP"):
            position = int(name[3:])
            while len(stack) < position:
                stack.insert(0, ("argument", 0))
            kind, cost = stack[-position]
            if kind == "constant":
                # The copy of a constant is pushed again
                stack.append(("constant", 1))
            else:
                stack.append((kind, cost))
                size += 1
        elif name.startswith("SWAP"):
            position = int(name[4:])
            while len(stack) < position + 1:
                stack.insert(0, ("argument", 0))
            stack[-1], stack[-1 - position] = stack[-1 - position], stack[-1]
            size += 1
        elif name in PURE_INSTRUCTIONS:
            operands = pop_operands(PURE_INSTRUCTIONS[name])
            if all(kind == "constant" for kind, _ in operands):
                stack.append(("constant", sum(cost for _, cost in operands) + 1))
            else:
                simplifiable = all(kind in ("argument", "argument_pure") for kind, _ in operands if kind != "constant")
                size += 1 + constants_size(operands, simplifiable)
                stack.append(("argument_pure" if simplifiable else "opaque", 0))
        else:
            num_inputs, num_outputs = opcodes.opcodes.get(name, [0, 0, 0])[1:3]
            size += 1 + constants_size(pop_operands(num_inputs), False)
            stack.extend([("opaque", 0)] * num_outputs)

    # Constants returned by the function
    return size + sum(1 for kind, _ in stack if kind == "constant")


def restrict_importer_inlining(asm_contract: ASM_contract_T) -> None:
    """
    solc's inliner copies the body of the single-block functions (called with JUMP [in] and returning with
    JUMP [out]) in every call site whenever it saves gas according to "runs", even if the code grows. In solc's code
    most of these copies are merged afterwards by the block deduplicator, but in grey's code the copies are mixed with
    different code in each call site and remain. Hence, the [in]/[out] annotations are only kept for the functions in
    which inlining reduces the number of instructions. For a single-block function with k call sites and B
    instructions (without its JUMP [out]):
      - not inlined: 4k (PUSH ret, PUSH f, JUMP [in] and the JUMPDEST of ret per call site) + B + 2 (JUMPDEST, body
        and JUMP [out] once)
      - inlined: k * B', where B' is the estimated size of each copy (see inlined_copy_size)
    The number of PUSH [tag] of the function approximates k, as solc does. The code does not change: solc treats
    the jumps without annotations as ordinary jumps, so it does not copy the function
    """
    code = asm_contract.get(".code", [])
    tag_positions = {instruction["value"]: i for i, instruction in enumerate(code) if instruction["name"] == "tag"}
    push_tags = collections.Counter(instruction["value"] for instruction in code if instruction["name"] == "PUSH [tag]")

    call_sites = collections.defaultdict(list)
    for i, instruction in enumerate(code):
        if (instruction["name"] == "JUMP" and instruction.get("jumpType") == "[in]" and i > 0
                and code[i - 1]["name"] == "PUSH [tag]"):
            call_sites[code[i - 1]["value"]].append(i)

    for function_tag, sites in call_sites.items():
        if function_tag not in tag_positions:
            continue

        # First block of the function: from its tag to the first instruction that ends the block
        body, block_end = [], None
        for j in range(tag_positions[function_tag] + 1, len(code)):
            name = code[j]["name"]
            if name == "tag":
                break
            if name in BLOCK_END_INSTRUCTIONS:
                block_end = j
                break
            if name != "JUMPDEST":
                body.append(code[j])

        single_block = (block_end is not None and code[block_end]["name"] == "JUMP"
                        and code[block_end].get("jumpType") == "[out]")
        k = push_tags[function_tag]

        if not (single_block and k * inlined_copy_size(body) < 4 * k + len(body) + 2):
            for i in sites:
                code[i].pop("jumpType", None)
            if single_block:
                code[block_end].pop("jumpType", None)

    for sub_object in asm_contract.get(".data", {}).values():
        if isinstance(sub_object, dict):
            restrict_importer_inlining(sub_object)


def remove_jumps_to_next(code: List[ASM_bytecode_T]) -> List[ASM_bytecode_T]:
    """
    The target of an unconditional jump is placed right after it whenever possible, but the jump is kept:
    PUSH [tag] t JUMP tag t JUMPDEST. solc's code generator falls through instead (it generates the target in place
    when it has not been generated yet, see OptimizedEVMCodeTransform), so the PUSH [tag] and the JUMP are removed.
    The tag and its JUMPDEST are removed too if no other PUSH [tag] refers to them. The jumps into and out of
    functions are kept (solc's inliner relies on them)
    """
    changed = True
    while changed:
        changed = False
        references = collections.Counter(instruction["value"] for instruction in code
                                         if instruction["name"] == "PUSH [tag]")
        new_code = []
        i = 0
        while i < len(code):
            if (i + 2 < len(code) and code[i]["name"] == "PUSH [tag]" and code[i + 1]["name"] == "JUMP"
                    and code[i + 1].get("jumpType", "[jump]") not in ("[in]", "[out]")
                    and code[i + 2]["name"] == "tag" and code[i + 2].get("value") == code[i]["value"]):
                tag = code[i]["value"]
                references[tag] -= 1
                changed = True
                if references[tag] == 0 and i + 3 < len(code) and code[i + 3]["name"] == "JUMPDEST":
                    i += 4
                else:
                    i += 2
                continue
            new_code.append(code[i])
            i += 1
        code = new_code
    return code


def traverse_cfg(cfg_object: CFGObject, tags_dict: Dict[block_id_T, int], asm_dir: Optional[Path] = None) -> List[ASM_bytecode_T]:
    """
    Traverses the blocks in the CFG to generate the serialized assembly code
    """
    function_name2entry = generate_function_name2entry(cfg_object.functions.values())
    object_code = traverse_cfg_block_list(cfg_object.blocks, function_name2entry, tags_dict, asm_dir)
    object_code = reuse_free_memory_pointer(object_code)

    function_code_list = []
    # TODO: devise better strategies to decide in which order the functions are included in the code
    for function_name, function in cfg_object.functions.items():
        function_code_list.extend(traverse_cfg_block_list(function.blocks, function_name2entry, tags_dict, asm_dir))
    code = object_code + function_code_list
    if constants.FALLTHROUGH:
        code = remove_jumps_to_next(code)
    return code


def recursive_asm_from_cfg_object(cfg_object: CFGObject, tags_dict: Dict, asm_dir: Optional[Path] = None, auxdata: Optional[bool] = False) -> ASM_contract_T:
    """
    Returns the level of the form {.code: ..., .auxdata: ..., [.data: ...]}
    """
    # Represents the structure
    tags = tags_dict[cfg_object]
    asm = traverse_cfg(cfg_object, tags, asm_dir)

    # 83 bytes of 0 + 0053 in CBOR encoding (see https://playground.sourcify.dev/)
    if auxdata:
        aux_data = "00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000053"
        current_object_json = {".code": asm, ".auxdata": aux_data}
    else:
        current_object_json = {".code": asm}
    
    sub_object = cfg_object.get_subobject()
    if sub_object is not None:
        json_asm_subobjects = recursive_asm_from_cfg(sub_object, tags_dict, asm_dir, auxdata)
        current_object_json[".data"] = {}
        for i, json_asm_subobject in enumerate(json_asm_subobjects):
            current_object_json[".data"][hex(i)[2:]] = json_asm_subobject
        
    return current_object_json


def recursive_asm_from_cfg(cfg: CFG, tags_dict: Dict, asm_dir: Optional[Path] = None, auxdata: Optional[bool] = False) -> List[ASM_contract_T]:
    """
    Returns the level of the form [{.code: ..., .auxdata: ..., [.data: ...]}]. This is later passed to the data object
    """

    multiple_object_json = []
    for obj_name, obj in cfg.get_objects().items():
        multiple_object_json.append(recursive_asm_from_cfg_object(obj, tags_dict, asm_dir, auxdata))

    return multiple_object_json


def asm_from_cfg(cfg: CFG, tags_dict: Dict, filename: str, final_path: Optional[Path] = None, auxdata: Optional[bool]  = False) -> ASM_contract_T:
    """
    Generates an assembly JSON from a CFG structure and the results of the optimization
    """
    #We have to access index 0 (there is only one contract at root level)
    asm_json = recursive_asm_from_cfg(cfg, tags_dict, final_path, auxdata)[0]
    if auxdata:
        asm_json.pop(".auxdata")
    asm_json["sourceList"] = [filename]

    return asm_json


def store_asm_output(json_object: Dict[str, Any], object_name: str, cfg_dir: Path) -> Path:
    file_to_store = cfg_dir.joinpath(object_name + "_asm.json")
    with open(file_to_store, 'w') as f:
        json.dump(json_object, f, indent=4)
    return file_to_store

def store_asm_standard_json_output(json_object: Dict[str, Any], object_name: str, cfg_dir: Path, settings_opt : Dict[str, Any] = {}) -> Path:
    file_to_store = cfg_dir.joinpath(object_name + "_standard_json_output.json")
    output_file = build_standard_json_output(json_object, object_name, settings_opt)

    with open(file_to_store, 'w') as f:
        json.dump(output_file, f, indent=4)
    return file_to_store

def store_binary_output(object_name: str, evm_code: str, cfg_dir: Path) -> None:
    file_to_store = cfg_dir.joinpath(object_name + "_bin.evm")
    with open(file_to_store, 'w') as f:
        f.write(evm_code)


def build_standard_json_output(json_object: Dict[str, Any], object_name : str, settings: Dict[str, Any]) -> Dict[str,Any]:
    output = {}
    
    output["language"] = "EVMAssembly"
    build_standard_json_settings(output,settings)

    output["sources"] = {}
    output["sources"][object_name] = {}
    output["sources"][object_name]["assemblyJson"] = json_object

    
    return output
    
def build_standard_json_settings(output_json, settings_opt):
    output_json["settings"] = {}
    
    if settings_opt == {}:
        opt_config = build_optimizer_configuration()
        output_json["settings"]["optimizer"] = opt_config

        output_json["settings"]["viaIR"] = True
        output_json["settings"]["metadata"] = {}
        output_json["settings"]["metadata"]["appendCBOR"] = False

    else:

        #Options not supported by the importer
        settings_opt.pop("compilationTarget", None)
        if "metadata" in settings_opt:
            settings_opt["metadata"].pop("bytecodeHash", None)
    
        output_json["settings"] = settings_opt

        # The Yul CFG is always generated with the optimizer enabled, so the importer must run the legacy optimizer
        # (block deduplicator, peephole, CSE...) as well, even if the input disables it: otherwise the result is
        # neither comparable with solc's optimized code nor consistent with the CFG
        optimizer = settings_opt.get("optimizer", {})
        optimizer["enabled"] = True
        optimizer.setdefault("runs", 200)
        settings_opt["optimizer"] = optimizer

    # opt = output_json["settings"].get("optimizer",{})

    # opt_details = opt.get("details",{})
    # opt_details["cse"] = False
    # opt["details"] = opt_details
    
    # output_json["settings"]["optimizer"] = opt

    # solc's inliner copies the body of functions called from several places (it optimises gas according to
    # "runs"), which increases the number of instructions of grey's code, so it is disabled in the importer.
    # The rest of the optimizer steps keep their standard configuration
    # optimizer = output_json["settings"].setdefault("optimizer", {})
    # optimizer.setdefault("details", {})["inliner"] = False
    
    output = build_output_selection()
    output_json["settings"]["outputSelection"] = output
    output_json["settings"]["metadata"] = {}
    output_json["settings"]["metadata"]["appendCBOR"] = False
    output_json["settings"]["metadata"]["useLiteralContent"] = False
    output_json["settings"]["metadata"]["bytecodeHash"] = "none"


def build_output_selection():
    output_selection = {}
    output_selection["*"] = {}
    output_selection["*"][""] = ["evm.bytecode.object"]

    return output_selection

def build_optimizer_configuration():
    config = {}
    config["enabled"] = True
    config["runs"] = 200

    return config

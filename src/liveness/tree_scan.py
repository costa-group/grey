"""
Module that implements an alternative version the Tree Scan algorithm from
"SSA-based Compiler Design" (Page 309). The key difference is that we assume
an unbounded number of registers to colour, as the EVM memory can
grow indefinitely (although dangerously in cost...). Moreover, the liveness sets
are determined according to the last point in which a variable could be accessed
"""
import networkx as nx
from collections import defaultdict
from global_params.types import var_id_T, block_id_T
from typing import List, Dict, Tuple, Set, Optional
from parser.cfg_block import CFGBlock
from parser.cfg_block_list import CFGBlockList
from graphs.cfg import compute_loop_nesting_forest_graph


# First, we need to detect which program points must be stored at some point
# We use the information stored in greedy_ids, in some kind of post-order traversal
# (Algorithm 9.2 of "SSA-based Compiler Design").

# First we compute some related information in isolated functions

def variable2block_header(cfg_block_list: CFGBlockList, forest_graph: nx.DiGraph) -> Dict[var_id_T, block_id_T]:
    """
    Determines which is the loop header of the outer loop in which the variable
    is defined. Useful for determining when we want to store the variable
    """
    var2header = dict()
    # We only consider blocks that appear as part of the forest graph
    for block_id in forest_graph.nodes:
        block = cfg_block_list.get_block(block_id)

        predecessors = list(forest_graph.predecessors(block_id))
        if len(predecessors) != 0:
            assert len(predecessors) == 1, "There can only be one predecessor in the forest graph"
            predecessor = predecessors[0]

            # We only consider the variables defined in the block
            # Thanks to SSA, they are defined only once
            for variable in block.declared_variables:
                # We link the variable with the block
                var2header[variable] = predecessor
    return var2header


def compute_var2num_uses(block_list: CFGBlockList) -> Dict[var_id_T, int]:
    """
    For each variable that must be stored previously at some point, detects all the blocks
    in which it must be loaded because it is very deep
    """
    var2num_uses = defaultdict(lambda: 0)
    for block_id, block in block_list.blocks.items():
        for i, instruction_id in enumerate(reversed(block.greedy_ids)):
            if instruction_id.startswith("GET"):
                loaded_var = instruction_id[4:-1]
                var2num_uses[loaded_var] += 1

    return var2num_uses


# Phi web descovery

def unreachable_phi_arguments(block_list: CFGBlockList, dominance_tree: nx.DiGraph, start: block_id_T) -> \
        Tuple[Dict[var_id_T, List[Tuple[var_id_T, block_id_T, int]]],Set[Tuple[var_id_T, block_id_T]]]:
    """
    The unreachable phi arguments correspond to those phi functions that are never accessible
    in the dominance tree. If it is accessible at some point, we just need to store it
    """
    unreachable = set()
    phi_descovery = defaultdict(lambda: [])
    for block in block_list.blocks.values():
        for i, phi_function in enumerate(block.phi_instructions()):
            # There is always just one value
            out_arg = phi_function.get_out_args()[0]

            for in_arg, pred_id in zip(phi_function.in_args, block.entries):
                phi_descovery[out_arg].append((in_arg, pred_id, i))
                pred = block_list.get_block(pred_id)

                # Condition: An element that cannot be reached initially or finally
                # and not defined means that we have to retrieve it from a register
                if in_arg not in pred.declared_variables and not pred.is_accessible_out(in_arg) \
                        and not pred.is_accessible_in(in_arg):
                    unreachable.add((in_arg, pred_id))

    return phi_descovery, unreachable


def insert_needed_copies(phi_web: Dict[var_id_T, List[Tuple[var_id_T, block_id_T, int]]],
                         unreachable_elements: Set[Tuple[var_id_T, block_id_T]],
                         elements_to_store: Set[Tuple[var_id_T, block_id_T]],
                         block_list: CFGBlockList, get_counter: Dict[var_id_T, int]):
    """
    Inserts SET and GET_SET instructions to ensure all unreachable elements are correctly
    stored in a register when reached.

    phi_web: dict that connects every phi-function with their corresponding parameters
             (plus block id and position of the phi function)
    unreachable_elements: set that connects those phi-defs that cannot be reached in a block
    elements_to_store: elements that have been detected not to be reachable
    """
    # The atomic sets represent the instructions that
    # must contain the same value
    atomic_sets = []
    for i, tuple_element_block in enumerate(elements_to_store):
        requires_block_insertion = [tuple_element_block]

        # We use the same color for all the connected components
        color = i
        while requires_block_insertion:
            phi_element, block_id = requires_block_insertion.pop()

            # Only phi values can be considered at this point
            phi_arguments = phi_web[phi_element]

            for phi_argument, previous_block_id, instr_position in phi_arguments:
                previous_block = block_list.get_block(previous_block_id)

                # First case: the element is unreachable.
                if (phi_argument, previous_block_id) in unreachable_elements:
                    # In this case, we need to perform a GET_SET instruction (unless not necessary)
                    # We introduce by the end of the greedy ids, with the corresponding color
                    previous_block.greedy_ids.insert(-1, f"SET({phi_argument},{color})")

                    # We need to add the current block to the blocks to traverse
                    # (to ensure the arguments are also accessible)
                    # TODO: is there a way to check the predecessors?
                    requires_block_insertion.append((phi_argument, previous_block))

                # Otherwise, we just need to set the value
                # Moreover, we assign the colour to that variable
                else:
                    # Four cases: accessible initially, declared in the function or
                    # accessible in the end
                    if previous_block.is_accessible_out(phi_argument):
                        # We insert it by the end of the block
                        previous_block.greedy_ids.insert(-1, f"DUP_SET({phi_argument},{color})")

                    elif phi_argument in previous_block.declared_variables:
                        # We insert just after the instruction
                        previous_block.greedy_ids.insert(-1, f"DUP_SET({phi_argument},{color})")

                    elif previous_block.is_accessible_in(phi_argument):
                        # We insert it by the beginning of the instruction
                        previous_block.greedy_ids.insert(0, f"DUP_SET({phi_argument},{color})")

                    else:
                        raise ValueError(f"Incoherent case: the phi argument "
                                         f"{phi_argument} should be accessible in block {block_id}")


class TreeScanFirstPass:

    def __init__(self, block_list: CFGBlockList, dominance_tree: nx.DiGraph, loop_forest: nx.DiGraph,
                 get_counter: Dict[var_id_T, int]):
        """
        Modifies the cfg_block_list inserting the needed SET instructions for registers in between, and
        returns the information for performing the tree scan.
        """
        self._block_list = block_list
        self._dominance_tree = dominance_tree
        self._loop_forest = loop_forest

        # ordered_program_points maps each block to the set of variables
        # whose last use is the current block
        self._ordered_program_points = []
        self._last_visited = set()

        # Var2header matches every variable to the header of the loop
        # in which it is being declared
        self._var2header = variable2block_header(block_list, loop_forest)

        # Var2num_uses indicates how many times a variable is loaded from memory
        self._get_counter = get_counter

    def insert_instructions(self) -> List[Tuple[block_id_T, int]]:
        """
        Inserts the DUP_SET instructions and returns the first use of each variable according to a post-order
        traversal of the CFG
        """
        # Indicates the blocks that have been traversed so far
        traversed = set()

        self._dag_dfs_block(self._block_list.get_block(self._block_list.start_block), traversed)
        return self._ordered_program_points

    def _dag_dfs_block(self, cfg_block: CFGBlock) -> Set[var_id_T]:
        """
        Post-order traversal of the dominance tree in order to generate the
        information on when to introduce the variables
        """
        # Same sets as the previous functions
        vars_to_introduce, variables_used_children = set(), set()

        for block_id in self._dominance_tree.successors(cfg_block.block_id):
            vars_to_introduce_child = self._dag_dfs_block(self._block_list.blocks[block_id])
            vars_to_introduce.update(vars_to_introduce_child)

        variables_to_introduce_current = self.traverse_block(cfg_block, vars_to_introduce)

        # variables_introduced_current already considers the state from the children
        return variables_to_introduce_current

    def traverse_block(self, cfg_block: CFGBlock, vars_to_introduce: Set[var_id_T]) -> Set[var_id_T]:
        """
        Modifies the cfg_ids in cfg_block to store the variables in vars_to_introduce,
        considering the information from the var2header dict. It returns two sets:
        * 1) The stack variables that are allowed to be stored from the corresponding point (due to LCA)
        * 2) The stack variables being used in the current block
        """
        # We detect which values must be stored at some point according to the values
        for i, instruction_id in enumerate(reversed(cfg_block.greedy_ids)):
            if instruction_id.startswith("GET"):
                loaded_var = instruction_id[4:-1]

                self._get_counter[loaded_var] -= 1

                last_visited = False
                # The first ocurrence of a variable is the last placed it was used
                if loaded_var not in self._last_visited:
                    self._last_visited.add(loaded_var)
                    last_visited = True

                # Annotate when the there is a GET or a SET
                self._ordered_program_points.append((cfg_block.block_id, -i - 1, last_visited))

                # If no more uses are needed, this means that we have reached a point
                # in which it can be introduced
                if self._get_counter[loaded_var] == 0:
                    vars_to_introduce.add(loaded_var)

            # Instructions are only set for solving permutation.
            # Hence, the corresponding values do not need to be propagated upwards
            elif instruction_id.startswith("SET"):
                stored_var = instruction_id[4:-1]

                self._ordered_program_points.append((cfg_block.block_id, -i - 1, False))

                # We only remove the stored var if it has not been removed before
                if stored_var in vars_to_introduce:
                    vars_to_introduce.remove(stored_var)

            # If the instruction defines a variable that is just accessible there, then we need to store it.
            else:
                # Global form to store multiple out vars if needed (not the case in the EVM)
                for out_var in cfg_block.out_vars_from_id(instruction_id):
                    if out_var in vars_to_introduce:
                        index = len(cfg_block.greedy_ids) - i
                        vars_to_introduce.remove(out_var)

                        cfg_block.greedy_ids.insert(index, f"DUP_SET({out_var})")
                        self._ordered_program_points.append((cfg_block.block_id, -i - 1, False))

        # Finally, we detect which values are accessible at the beginning of the block
        # so that we store them in memory. By applying this step at the beginning of the block,
        # we avoid repeating SETs for the same variable inside the block if it is loaded multiple times
        to_remove = set()
        for var_id in vars_to_introduce:

            # Two conditions must be satisfied: the variable can be accessed from the initial stack
            # and it is not inside a nested loop
            if cfg_block.is_accessible_in(var_id):
                header_loop = self._var2header.get(var_id, None)

                # We only store a variable if it is in the most possible outer loop
                if header_loop is None or (
                        header_loop == cfg_block.block_id and self._loop_forest.has_edge(header_loop,
                                                                                         cfg_block.block_id)):
                    # We insert a DUP_SET instruction
                    cfg_block.greedy_ids.insert(0, f"DUP_SET({var_id})")
                    self._ordered_program_points.append((cfg_block.block_id,  -len(cfg_block.greedy_ids), False))

                    # We mark the variable for removal
                    to_remove.add(var_id)

        return vars_to_introduce.difference(to_remove)


# Then, we colour the registers using the info from the previous stage (tree scan)


class ColourAssignment:
    """
    Class to represents the colouring of the graph.
    """

    def __init__(self, block_list: CFGBlockList, dominance_tree: nx.DiGraph,
                 ordered_program_points: List[Tuple[block_id_T, int]]):
        # Parameters that are passed to colour the graph
        self._block_list = block_list
        self._dominance_tree = dominance_tree
        self._ordered_program_points = ordered_program_points

        self._total_colors: int = 0
        self._used_colors: int = 0

        # We determine which variable is associated to a colour
        self._var2color: Dict[block_id_T, int] = dict()

        # Colors currently assigned
        self._assigned_colours: Set[var_id_T] = set()

    def _pick_colour(self, v: var_id_T, available: List[bool]):
        """
        Chooses an available colour, adding a new one if there are not enough
        """
        # We add v to the set of assigned colours
        self._assigned_colours.add(v)

        # If all colours are used, we need to increase the number of colours
        if self._total_colors == self._used_colors:
            self._total_colors += 1
            self._used_colors += 1
            available.append(False)
            self._var2color[v] = self._total_colors - 1
        else:
            i = 0
            found_colour = False
            while not found_colour and i < self._total_colors:
                if available[i]:
                    available[i] = False
                    found_colour = True
                    self._used_colors += 1
                    self._var2color[v] = i
                else:
                    i += 1

            raise ValueError("There must exist a colour that has not been assigned so far")

    def _release_colour(self, v: var_id_T, available: List[bool]):
        self._used_colors -= 1
        available[self._var2color[v]] = True
        self._assigned_colours.remove(v)

    def _assign_color(self, block_id: block_id_T, available: List[bool]) -> None:
        """
        We need to assign colours to each different block, following the cfg order.
        """
        block = self._block_list.get_block(block_id)

        # Then, we traverse the instructions
        new_greedy_ids = []
        for instruction_id in block.greedy_ids:
            # DUP_SET instructions are handled
            if instruction_id.startswith("DUP_SET"):
                variable_id = instruction_id[8:-1]

                # For DUP_SET, the variable cannot be assigned previously
                assert variable_id not in self._assigned_colours, "A DUP_SET instruction should have been " \
                                                                  "inserted with no previous assignment of the value"

                self._pick_colour(variable_id, available)

            # SET instructions can convert into POP or
            elif instruction_id.startswith("SET"):
                variable_id = instruction_id[4: -1]

                # If it has been already assigned, then we replace with a POP instruction
                if variable_id in self._assigned_colours:
                    new_greedy_ids.append("POP")
                else:
                    self._pick_colour(variable_id, available)

            else:
                new_greedy_ids.append(instruction_id)

        block.greedy_ids = new_greedy_ids

        # The variables in ordered_program_points indicate which variables have the last use at the current
        # block, and can be released.
        for variable in self._ordered_program_points.get(block_id, []):
            self._release_colour(variable, available)

        for successor in self._dominance_tree.successors(block_id):
            self._assign_color(successor, available.copy())

    def tree_scan_with_last_uses(self) -> None:
        """
        Adapted from Algorithm 22.1: Tree scan in page 309. Given the block list,
        and the list of program points, registers are assigned based on colours
        """
        # Initial call with the start block and an empty list of available blocks
        self._assign_color(self._block_list.start_block, [])


# Full algorithm

def tree_scan(block_list: CFGBlockList, dominance_tree: nx.DiGraph) -> None:
    """
    Tree scan that assigns the
    """
    loop_forest = compute_loop_nesting_forest_graph(block_list, dominance_tree)
    ordered_program_points = TreeScanFirstPass(block_list, loop_forest).insert_instructions()
    ColourAssignment(block_list, dominance_tree, ordered_program_points)
